FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias del sistema si es necesario
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .
COPY requirements.ingest.txt .

# Instalar dependencias de Python
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación
COPY . .

# Exponer puerto (Railway usa $PORT automáticamente)
EXPOSE 8080

# Variable de entorno para el puerto
ENV PORT=8080

# Comando para iniciar la aplicación
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}

