FROM python:3.9-slim

WORKDIR /app

# Copiar requirements primero para aprovechar la caché de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Puerto por defecto para FastAPI
# EXPOSE 8000
EXPOSE 8080

# Comando para ejecutar la aplicación
# CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
CMD exec uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8080}