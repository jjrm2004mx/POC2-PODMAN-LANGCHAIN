# =============================================================================
# langchain-agent/Dockerfile
# Orquestador LangGraph — classify → validate → save
# =============================================================================

FROM python:3.11-slim

# Evitar prompts interactivos durante la instalación
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias del sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
  && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
# En desarrollo este paso se sobreescribe por el volumen ./langchain-agent:/app
COPY . .

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
