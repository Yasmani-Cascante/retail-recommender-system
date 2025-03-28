# Modifica el Dockerfile
FROM python:3.9-slim

WORKDIR /app

# Actualizar pip e instalar herramientas básicas
RUN pip install --no-cache-dir --upgrade pip wheel setuptools

# Copiar requirements primero para aprovechar la caché de Docker
COPY requirements.txt .

# Instalar torch primero (versión CPU para reducir tamaño)
RUN pip install --no-cache-dir torch --extra-index-url https://download.pytorch.org/whl/cpu

# Instalar transformers, sentence-transformers y scipy específicamente
RUN pip install --no-cache-dir transformers sentence-transformers scipy==1.13.1

# Instalar el resto de dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Puerto por defecto
EXPOSE 8080

# Script de inicio con mejor manejo de errores y logging
RUN echo '#!/bin/bash\n\
echo "Starting application..."\n\
echo "Using PORT: ${PORT:-8080}"\n\
exec uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8080} --timeout-keep-alive 120\n\
' > /app/start.sh && chmod +x /app/start.sh

# Comando para ejecutar la aplicación (formato JSON array recomendado)
CMD ["/app/start.sh"]