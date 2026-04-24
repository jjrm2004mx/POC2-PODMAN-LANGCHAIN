# =============================================================================
# langchain-api/main.py
# Gateway FastAPI — patrón Adapter + Strategy
# POST /ask con provider intercambiable sin reiniciar el stack
# Cache Redis: MD5(prompt + system + provider), TTL 1 hora
# =============================================================================

import os
import hashlib
import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from prometheus_fastapi_instrumentator import Instrumentator

# ── Adapters por provider ─────────────────────────────────────────────────────
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="shared-services-classifier — API",
    description="Gateway de IA con patrón Adapter+Strategy. POST /ask para consultar el LLM.",
    version="1.0.0",
)

Instrumentator().instrument(app).expose(app)

# ── Redis — cache LLM ─────────────────────────────────────────────────────────
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True,
)
CACHE_TTL = 3600  # 1 hora

# ── Strategy: obtener el LLM según provider ───────────────────────────────────
def get_llm(provider: str):
    if provider == "ollama":
        return ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "4096")),
        )
    elif provider == "openai":
        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=os.getenv("OPENAI_API_KEY"),
        )
    elif provider == "anthropic":
        return ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022"),
            api_key=os.getenv("ANTHROPIC_API_KEY"),
        )
    elif provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
            google_api_key=os.getenv("GEMINI_API_KEY"),
        )
    else:
        raise ValueError(f"Provider '{provider}' no soportado. Usar: ollama | openai | anthropic | gemini")

# ── Modelos de request / response ─────────────────────────────────────────────
class AskRequest(BaseModel):
    prompt: str
    system: Optional[str] = None
    provider: Optional[str] = None    # Override del MODEL_PROVIDER del .env

class AskResponse(BaseModel):
    provider: str
    model: str
    response: str
    cached: bool

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Estado del servicio y providers disponibles."""
    providers = {
        "ollama": bool(os.getenv("OLLAMA_BASE_URL")),
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "gemini": bool(os.getenv("GEMINI_API_KEY")),
    }
    # Verificar conexión Redis
    try:
        redis_client.ping()
        redis_ok = True
    except Exception:
        redis_ok = False

    return {
        "status": "ok",
        "service": "langchain-api",
        "default_provider": os.getenv("MODEL_PROVIDER", "ollama"),
        "providers_configured": providers,
        "redis": "ok" if redis_ok else "error",
    }

@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """
    Consulta al LLM con el provider especificado.

    Flujo:
      1. Verificar cache Redis (MD5 del prompt + system + provider)
      2. Cache HIT  → respuesta en <100ms
      3. Cache MISS → llamar al LLM → cachear resultado (TTL 1h)
    """
    provider = request.provider or os.getenv("MODEL_PROVIDER", "ollama")

    # ── Cache lookup ──────────────────────────────────────────────────────────
    cache_key = hashlib.md5(
        f"{request.prompt}{request.system or ''}{provider}".encode()
    ).hexdigest()

    cached_response = redis_client.get(cache_key)
    if cached_response:
        llm = get_llm(provider)
        model_name = getattr(llm, "model", getattr(llm, "model_name", provider))
        return AskResponse(
            provider=provider,
            model=model_name,
            response=cached_response,
            cached=True,
        )

    # ── LLM call ──────────────────────────────────────────────────────────────
    try:
        llm = get_llm(provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    messages = []
    if request.system:
        messages.append(SystemMessage(content=request.system))
    messages.append(HumanMessage(content=request.prompt))

    try:
        result = await llm.ainvoke(messages)
        response_text = result.content
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error llamando al provider '{provider}': {str(e)}"
        )

    # ── Cachear resultado ─────────────────────────────────────────────────────
    try:
        redis_client.setex(cache_key, CACHE_TTL, response_text)
    except Exception:
        pass  # No romper la respuesta si falla el cache

    model_name = getattr(llm, "model", getattr(llm, "model_name", provider))
    return AskResponse(
        provider=provider,
        model=model_name,
        response=response_text,
        cached=False,
    )
