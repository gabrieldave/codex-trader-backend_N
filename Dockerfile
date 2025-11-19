FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias del sistema si es necesario
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copiar solo requirements primero (para cachear la capa de dependencias)
COPY requirements.txt .
COPY requirements.ingest.txt .

# Instalar dependencias de Python con timeout aumentado y retry
# IMPORTANTE: Instalar stripe primero con versión específica para evitar conflictos
RUN pip install --upgrade pip setuptools wheel && \
    pip uninstall -y stripe || true && \
    pip install --no-cache-dir --default-timeout=100 "stripe>=8.0.0,<10.0.0" && \
    pip install --no-cache-dir --default-timeout=100 -r requirements.txt

# Copiar código de la aplicación (esto se cachea si no cambia)
COPY . .

# Exponer puerto (Railway usa $PORT automáticamente)
EXPOSE 8080

# Variable de entorno para el puerto
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Comando para iniciar la aplicación
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}

