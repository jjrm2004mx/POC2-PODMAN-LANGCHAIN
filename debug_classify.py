#!/usr/bin/env python3
"""
Script para debuggear la clasificación sin ejecutar todo el stack.
Prueba el LLM directamente con el mismo system prompt.

Uso:
  python debug_classify.py "Texto del ticket aquí" [provider]
  
Ejemplo:
  python debug_classify.py "Esperando estes bien..." ollama
"""

import os
import sys
import json
import httpx
from pathlib import Path

# Simular sistema de prompts
AGENT_DOMAINS = os.getenv("AGENT_DOMAINS", "IT,cliente,operaciones,otro").split(",")

def build_system_prompt() -> str:
    dominios_str = " | ".join(AGENT_DOMAINS)
    return f"""CLASIFICADOR DE TICKETS SHARED SERVICES
================================================================
INSTRUCCIONES CRÍTICAS:
1. SOLO RESPONDE CON JSON VÁLIDO
2. SIN EXPLICACIONES, SIN MARKDOWN, SIN BACKTICKS
3. FILA 1: El JSON completo
4. NADA MÁS DESPUÉS

DOMINIOS VÁLIDOS (elige UNO):
- IT
- cliente
- operaciones
- otro

PRIORIDADES VÁLIDAS (elige UNA):
- alta
- media
- baja

CAMPOS REQUERIDOS:
{{"dominio": "IT", "categoria": "descripción corta", "prioridad": "alta", "confianza": 0.95}}

EJEMPLO CORRECTO:
{{"dominio": "operaciones", "categoria": "costos", "prioridad": "media", "confianza": 0.85}}

REGLAS:
✓ "dominio" DEBE ser: {dominios_str}
✓ "prioridad" DEBE ser: alta, media o baja
✓ "categoria" es texto libre, NUNCA vacío (mínimo 3 caracteres)
✓ "confianza" es NÚMERO entre 0.0 y 1.0

FORMATO FINAL OBLIGATORIO:
{{"dominio":"...", "categoria":"...", "prioridad":"...", "confianza":X.XX}}
================================================================"""

def debug_classify(texto: str, provider: str = "ollama"):
    """Hacer request a langchain-api y debuggear respuesta"""
    
    api_url = os.getenv("LANGCHAIN_API_URL", "http://localhost:8000")
    
    print("=" * 80)
    print(f"[DEBUG] Clasificando con provider: {provider}")
    print(f"[DEBUG] API URL: {api_url}")
    print("=" * 80)
    print(f"\n📝 TEXTO A CLASIFICAR:\n{texto}\n")
    
    system_prompt = build_system_prompt()
    print(f"🔧 SYSTEM PROMPT:\n{system_prompt}\n")
    
    payload = {
        "prompt": texto,
        "system": system_prompt,
        "provider": provider,
    }
    
    print(f"📤 ENVIANDO A /ask:")
    print(json.dumps(payload, indent=2, ensure_ascii=False)[:500] + "...\n")
    
    try:
        response = httpx.post(
            f"{api_url}/ask",
            json=payload,
            timeout=300.0,  # 5 minutos — llama3:latest puede tardar hasta 2.5 min en CPU
        )
        response.raise_for_status()
        
        data = response.json()
        raw_response = data.get("response", "")
        cached = data.get("cached", False)
        
        print(f"✅ RESPUESTA RAW (cached={cached}):")
        print(f"---\n{raw_response}\n---\n")
        
        # Intentar parse como hace classify_node
        raw = raw_response.strip()
        
        # Limpiar markdown
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:].strip()
        
        # Buscar JSON válido
        idx_start = raw.find("{")
        idx_end = raw.rfind("}")
        
        print(f"🔍 BÚSQUEDA DE JSON:")
        print(f"  - Primer '{{' en índice: {idx_start}")
        print(f"  - Último '}}' en índice: {idx_end}")
        
        if idx_start >= 0 and idx_end > idx_start:
            raw = raw[idx_start:idx_end+1].strip()
            print(f"  - JSON extraído:\n    {raw}\n")
        else:
            print(f"  ❌ NO SE ENCONTRÓ JSON VÁLIDO\n")
            return
        
        # Parse JSON
        try:
            classification = json.loads(raw)
            print(f"✅ JSON VÁLIDO:")
            print(json.dumps(classification, indent=2, ensure_ascii=False))
            print()
            
            # Validar campos
            required = {"dominio", "categoria", "prioridad", "confianza"}
            missing = required - set(classification.keys())
            if missing:
                print(f"⚠️  CAMPOS FALTANTES: {missing}\n")
            else:
                print(f"✅ TODOS LOS CAMPOS PRESENTES\n")
                
            # Validar valores
            print("📋 VALIDACIÓN DE VALORES:")
            print(f"  - dominio: '{classification.get('dominio')}' ∈ {AGENT_DOMAINS} → {classification.get('dominio') in AGENT_DOMAINS}")
            print(f"  - categoria: '{classification.get('categoria')}' → vacío={not classification.get('categoria')}")
            print(f"  - prioridad: '{classification.get('prioridad')}' ∈ [alta,media,baja] → {classification.get('prioridad') in ['alta','media','baja']}")
            try:
                conf = float(classification.get('confianza', 0))
                print(f"  - confianza: {conf} ∈ [0.0-1.0] → {0.0 <= conf <= 1.0}")
            except:
                print(f"  - confianza: {classification.get('confianza')} ❌ NO ES NUMÉRICA")
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON INVÁLIDO (error en línea {e.lineno}):")
            print(f"   {e.msg}")
            print(f"   Raw: {raw}\n")
            
    except httpx.HTTPError as e:
        print(f"❌ ERROR HTTP: {e}\n")
    except Exception as e:
        print(f"❌ ERROR: {e}\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("USO: python debug_classify.py 'texto' [provider]")
        print("Ejemplo: python debug_classify.py 'Mi email no funciona' ollama")
        sys.exit(1)
    
    texto = sys.argv[1]
    provider = sys.argv[2] if len(sys.argv) > 2 else "ollama"
    
    debug_classify(texto, provider)
