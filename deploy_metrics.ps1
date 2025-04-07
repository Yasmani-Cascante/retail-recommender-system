# PowerShell script para desplegar la versión con endpoint de métricas

Write-Host "Iniciando despliegue de la versión con endpoint de métricas..." -ForegroundColor Green

# Configuración
$ProjectID = "retail-recommendations-449216"
$Region = "us-central1"
$ServiceName = "retail-recommender-metrics"
$ImageName = "gcr.io/$ProjectID/$ServiceName`:latest"

# Crear Dockerfile temporal para esta versión
$DockerfileContent = @"
# Imagen base
FROM python:3.9-slim

WORKDIR /app

# Instalar dependencias del sistema necesarias
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copiar archivos de dependencias
COPY requirements.tfidf.txt ./

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.tfidf.txt

# Copiar código fuente
COPY src/ /app/src/

# Crear directorio data para almacenar el modelo TF-IDF y logs
RUN mkdir -p data
RUN mkdir -p logs

# Variables de entorno y configuración
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV DEBUG=true
ENV METRICS_ENABLED=true

# Exponer puerto
EXPOSE `${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:`${PORT}/health || exit 1

# Comando de inicio - usando la versión simplificada de métricas
CMD ["uvicorn", "src.api.main_metrics:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "info"]
"@

# Escribir Dockerfile temporal
$DockerfilePath = "Dockerfile.metrics"
$DockerfileContent | Out-File -FilePath $DockerfilePath -Encoding utf8

# Verificar configuración de GCloud
Write-Host "Verificando configuración de GCloud..." -ForegroundColor Yellow
$CurrentProject = gcloud config get-value project
Write-Host "Proyecto actual: $CurrentProject" -ForegroundColor Cyan

# Verificar si necesitamos configurar el proyecto
if ($CurrentProject -ne $ProjectID) {
    Write-Host "Configurando proyecto: $ProjectID" -ForegroundColor Yellow
    gcloud config set project $ProjectID
} else {
    Write-Host "Ya está configurado el proyecto correcto: $ProjectID" -ForegroundColor Green
}

# Configurar región
Write-Host "Configurando región: $Region" -ForegroundColor Yellow
gcloud config set run/region $Region

# Construir imagen Docker
Write-Host "Construyendo la imagen Docker..." -ForegroundColor Yellow
$BuildSuccess = $false
try {
    docker build -t $ImageName -f $DockerfilePath .
    $BuildSuccess = $?
    if (-not $BuildSuccess) {
        throw "Error al construir la imagen Docker"
    }
    Write-Host "Imagen Docker construida exitosamente." -ForegroundColor Green
} catch {
    Write-Host "Error al construir la imagen Docker: $_" -ForegroundColor Red
    exit 1
}

# Autenticar con Google Cloud
Write-Host "Autenticando con Google Cloud..." -ForegroundColor Yellow
gcloud auth configure-docker

# Subir imagen a Container Registry
Write-Host "Subiendo imagen a Container Registry..." -ForegroundColor Yellow
docker push $ImageName
if (-not $?) {
    Write-Host "Error al subir la imagen a Container Registry. Abortando despliegue." -ForegroundColor Red
    exit 1
}

# Desplegar en Cloud Run
Write-Host "Desplegando a Cloud Run..." -ForegroundColor Yellow
gcloud run deploy $ServiceName `
    --image $ImageName `
    --platform managed `
    --region $Region `
    --memory 1Gi `
    --cpu 1 `
    --min-instances 0 `
    --max-instances 10 `
    --timeout 300 `
    --set-env-vars "API_KEY=2fed9999056fab6dac5654238f0cae1c,METRICS_ENABLED=true" `
    --allow-unauthenticated

# Verificar si el despliegue fue exitoso
if (-not $?) {
    Write-Host "Error al desplegar en Cloud Run." -ForegroundColor Red
    exit 1
}

# Obtener URL del servicio
$ServiceUrl = $null
try {
    $ServiceUrl = gcloud run services describe $ServiceName --platform managed --region $Region --format 'value(status.url)'
    Write-Host "Servicio desplegado en: $ServiceUrl" -ForegroundColor Green
} catch {
    Write-Host "Error al obtener la URL del servicio: $_" -ForegroundColor Red
}

if ($ServiceUrl) {
    # Esperar para que el servicio se inicialice
    Write-Host "Esperando 10 segundos para que el servicio se inicialice..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10

    # Verificar estado del servicio
    Write-Host "Verificando estado del servicio..." -ForegroundColor Yellow
    try {
        $Response = Invoke-RestMethod -Uri "$ServiceUrl/health" -Method Get -TimeoutSec 30
        Write-Host "Estado del servicio: $($Response.status)" -ForegroundColor Green
        
        if ($Response.components -and $Response.components.metrics) {
            Write-Host "Estado de métricas: $($Response.components.metrics.status)" -ForegroundColor Green
            Write-Host "Métricas habilitadas: $($Response.components.metrics.enabled)" -ForegroundColor Green
        }
    } catch {
        Write-Host "Error verificando estado del servicio: $_" -ForegroundColor Red
        Write-Host "El servicio podría necesitar más tiempo para inicializarse completamente." -ForegroundColor Yellow
    }

    # Probar el endpoint de métricas
    Write-Host "`nProbando el endpoint de métricas..." -ForegroundColor Cyan
    try {
        $Headers = @{
            "X-API-Key" = "2fed9999056fab6dac5654238f0cae1c"
        }
        $MetricsUrl = "$ServiceUrl/v1/metrics"
        $MetricsResponse = Invoke-RestMethod -Uri $MetricsUrl -Method Get -Headers $Headers
        Write-Host "  ✅ Éxito: Endpoint de métricas accesible" -ForegroundColor Green
        Write-Host "  Estado: $($MetricsResponse.status)" -ForegroundColor Green
        
        if ($MetricsResponse.realtime_metrics) {
            Write-Host "  Métricas en tiempo real disponibles" -ForegroundColor Green
        }
    } catch {
        Write-Host "  ❌ Error al acceder al endpoint de métricas: $_" -ForegroundColor Red
    }

    # Mostrar instrucciones para pruebas manuales
    Write-Host "`n======================================================================================" -ForegroundColor Cyan
    Write-Host "                  INSTRUCCIONES PARA PROBAR EL ENDPOINT DE MÉTRICAS" -ForegroundColor Cyan
    Write-Host "=======================================================================================" -ForegroundColor Cyan
    
    Write-Host "`nAcceder al endpoint de métricas:" -ForegroundColor White
    Write-Host "   GET $ServiceUrl/v1/metrics" -ForegroundColor Gray
    
    Write-Host "`nRecuerda incluir la cabecera X-API-Key: 2fed9999056fab6dac5654238f0cae1c" -ForegroundColor Yellow
    Write-Host "======================================================================================" -ForegroundColor Cyan
}

Write-Host "`nProceso de despliegue completado." -ForegroundColor Green
Write-Host "Esta versión incluye:" -ForegroundColor Yellow
Write-Host "- Endpoint /v1/metrics para obtener información de rendimiento del sistema de recomendaciones" -ForegroundColor Yellow

# Eliminar el Dockerfile temporal
if (Test-Path $DockerfilePath) {
    Remove-Item $DockerfilePath
    Write-Host "Dockerfile temporal eliminado." -ForegroundColor Gray
}
