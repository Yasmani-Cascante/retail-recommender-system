# syntax=docker/dockerfile:1
# python:3.11-slim — requerido por pylate>=1.2.0 (usa typing.TypeAlias y otras
# features de Python 3.10+). Python 3.9 hace fallar 'pip install pylate' en build.
FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema necesarias para torch y git (requerido por huggingface_hub)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Instalar en orden: torch CPU-only primero (más liviano que GPU build)
RUN pip install --no-cache-dir torch==2.1.0+cpu \
    --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-descargar el modelo durante el build de la imagen.
# Esto evita que el primer startup descargue ~350MB desde HuggingFace.
# El modelo se bake en la imagen Docker (~900MB total con torch CPU).
# Uso de heredoc para evitar problemas de escaping con comillas.
RUN python << 'EOF'
from pylate import models
import os

# Configurar timeout para downloads de HuggingFace
os.environ.setdefault('HF_HUB_DOWNLOAD_TIMEOUT', '300')
os.environ.setdefault('HF_HUB_ETAG_TIMEOUT', '60')

m = models.ColBERT(model_name_or_path='LiquidAI/LFM2-ColBERT-350M')
print('Model pre-downloaded successfully')
EOF

ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
