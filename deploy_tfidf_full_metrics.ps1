# PowerShell script para desplegar la versión completa con métricas

Write-Host "Iniciando despliegue de la versión completa con métricas y exclusión de productos vistos..." -ForegroundColor Green

# Configuración
$ProjectID = "retail-recommendations-449216"
$Region = "us-central1"
$ServiceName = "retail-recommender-full-metrics"
$ImageName = "gcr.io/$ProjectID/$ServiceName`:latest"

# Verificar si existen los archivos necesarios
$MetricsRouterPath = "src\api\metrics_router.py"
if (-not (Test-Path $MetricsRouterPath)) {
    Write-Host "Error: El archivo $MetricsRouterPath no existe. Ejecuta el script deploy_metrics.ps1 primero." -ForegroundColor Red
    exit 1
}

# Incluir el router de métricas en el archivo principal
$MainPath = "src\api\main_tfidf_shopify.py"
$MetricsMainPath = "src\api\main_metrics.py"

# Modificar main_tfidf_shopify.py para incluir el router de métricas
$MainContent = Get-Content $MainPath -Raw
$MetricsInclude = '# Importar el router de métricas
from src.api.metrics_router import router as metrics_router'
$IncludeRouter = 'app.include_router(metrics_router)'

# Verificar si ya se ha modificado
$AlreadyModified = $MainContent -match "from src.api.metrics_router import router as metrics_router"

if (-not $AlreadyModified) {
    # Insertar la importación después de las importaciones principales
    $MainContent = $MainContent -replace "from src.api.startup_helper import StartupManager", "from src.api.startup_helper import StartupManager`n$MetricsInclude"
    
    # Insertar la inclusión del router después de la creación de la app
    $MainContent = $MainContent -replace "app = FastAPI\(", "app = FastAPI(`n    # Incluir el router de métricas`n    $IncludeRouter`n"
    
    # Guardar el archivo modificado con un nombre diferente
    $ModifiedMainPath = "src\api\main_tfidf_shopify_with_metrics.py"
    $MainContent | Out-File -FilePath $ModifiedMainPath -Encoding utf8
    
    Write-Host "Archivo principal modificado guardado como $ModifiedMainPath" -ForegroundColor Green
} else {
    Write-Host "El archivo principal ya ha sido modificado para incluir el router de métricas." -ForegroundColor Yellow
    $ModifiedMainPath = $MainPath
}

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

# Comando de inicio - usando la versión con métricas integrada
CMD ["uvicorn", "src.api.main_tfidf_shopify_with_metrics:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "info"]
"@

# Escribir Dockerfile temporal
$DockerfilePath = "Dockerfile.full_metrics"
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
    --set-env-vars "GOOGLE_PROJECT_NUMBER=178362262166,GOOGLE_LOCATION=global,GOOGLE_CATALOG=default_catalog,GOOGLE_SERVING_CONFIG=default_recommendation_config,API_KEY=2fed9999056fab6dac5654238f0cae1c,SHOPIFY_SHOP_URL=ai-shoppings.myshopify.com,SHOPIFY_ACCESS_TOKEN=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,GCS_BUCKET_NAME=retail-recommendations-449216_cloudbuild,USE_GCS_IMPORT=true,DEBUG=true,METRICS_ENABLED=true,EXCLUDE_SEEN_PRODUCTS=true" `
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
    Write-Host "Esperando 20 segundos para que el servicio se inicialice..." -ForegroundColor Yellow
    Start-Sleep -Seconds 20

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

    # Mostrar instrucciones para pruebas manuales
    Write-Host "`n======================================================================================" -ForegroundColor Cyan
    Write-Host "                  INSTRUCCIONES PARA PROBAR LAS NUEVAS FUNCIONALIDADES" -ForegroundColor Cyan
    Write-Host "=======================================================================================" -ForegroundColor Cyan
    
    Write-Host "`n1. Acceder al endpoint de métricas:" -ForegroundColor White
    Write-Host "   GET $ServiceUrl/v1/metrics" -ForegroundColor Gray
    
    Write-Host "`n2. Registrar eventos para un usuario real:" -ForegroundColor White
    Write-Host "   POST $ServiceUrl/v1/events/user/real_user_123?event_type=detail-page-view&product_id=9978503037237" -ForegroundColor Gray
    
    Write-Host "`n3. Obtener recomendaciones para ese usuario (excluyendo productos vistos):" -ForegroundColor White
    Write-Host "   GET $ServiceUrl/v1/recommendations/user/real_user_123" -ForegroundColor Gray
    
    Write-Host "`nTodas las peticiones deben incluir la cabecera X-API-Key: 2fed9999056fab6dac5654238f0cae1c" -ForegroundColor Yellow
    Write-Host "======================================================================================" -ForegroundColor Cyan
}

Write-Host "`nProceso de despliegue completado." -ForegroundColor Green
Write-Host "Esta versión incluye:" -ForegroundColor Yellow
Write-Host "- Sistema de métricas para evaluar la calidad de las recomendaciones" -ForegroundColor Yellow
Write-Host "- Exclusión automática de productos ya vistos en las recomendaciones" -ForegroundColor Yellow
Write-Host "- Endpoint /v1/metrics para obtener información de rendimiento" -ForegroundColor Yellow

# Eliminar el Dockerfile temporal
if (Test-Path $DockerfilePath) {
    Remove-Item $DockerfilePath
    Write-Host "Dockerfile temporal eliminado." -ForegroundColor Gray
}
