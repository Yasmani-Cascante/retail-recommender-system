# PowerShell script para desplegar la versiÃ³n completa con mÃ©tricas

# Importar funciones comunes
. .\deploy_common.ps1

Write-Host "Iniciando despliegue de la versiÃ³n completa con mÃ©tricas y exclusiÃ³n de productos vistos..." -ForegroundColor Green

# Cargar variables secretas
$SecretsLoaded = Load-SecretVariables
if (-not $SecretsLoaded) {
    Write-Host "Error: No se pudieron cargar las variables secretas. Abortando despliegue." -ForegroundColor Red
    exit 1
}

# ConfiguraciÃ³n
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

# Incluir el router de mÃ©tricas en el archivo principal
$MainPath = "src\api\main_tfidf_shopify.py"
$MetricsMainPath = "src\api\main_metrics.py"

# Modificar main_tfidf_shopify.py para incluir el router de mÃ©tricas
$MainContent = Get-Content $MainPath -Raw
$MetricsInclude = '# Importar el router de mÃ©tricas
from src.api.metrics_router import router as metrics_router'
$IncludeRouter = 'app.include_router(metrics_router)'

# Verificar si ya se ha modificado
$AlreadyModified = $MainContent -match "from src.api.metrics_router import router as metrics_router"

if (-not $AlreadyModified) {
    # Insertar la importaciÃ³n despuÃ©s de las importaciones principales
    $MainContent = $MainContent -replace "from src.api.startup_helper import StartupManager", "from src.api.startup_helper import StartupManager`n$MetricsInclude"
    
    # Insertar la inclusiÃ³n del router despuÃ©s de la creaciÃ³n de la app
    $MainContent = $MainContent -replace "app = FastAPI\(", "app = FastAPI(`n    # Incluir el router de mÃ©tricas`n    $IncludeRouter`n"
    
    # Guardar el archivo modificado con un nombre diferente
    $ModifiedMainPath = "src\api\main_tfidf_shopify_with_metrics.py"
    $MainContent | Out-File -FilePath $ModifiedMainPath -Encoding utf8
    
    Write-Host "Archivo principal modificado guardado como $ModifiedMainPath" -ForegroundColor Green
} else {
    Write-Host "El archivo principal ya ha sido modificado para incluir el router de mÃ©tricas." -ForegroundColor Yellow
    $ModifiedMainPath = $MainPath
}

# Crear Dockerfile temporal para esta versiÃ³n
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

# Copiar cÃ³digo fuente
COPY src/ /app/src/

# Crear directorio data para almacenar el modelo TF-IDF y logs
RUN mkdir -p data
RUN mkdir -p logs

# Variables de entorno y configuraciÃ³n
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

# Comando de inicio - usando la versiÃ³n con mÃ©tricas integrada
CMD ["uvicorn", "src.api.main_tfidf_shopify_with_metrics:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "info"]
"@

# Escribir Dockerfile temporal
$DockerfilePath = "Dockerfile.full_metrics"
$DockerfileContent | Out-File -FilePath $DockerfilePath -Encoding utf8

# Verificar configuraciÃ³n de GCloud
Write-Host "Verificando configuraciÃ³n de GCloud..." -ForegroundColor Yellow
$CurrentProject = gcloud config get-value project
Write-Host "Proyecto actual: $CurrentProject" -ForegroundColor Cyan

# Verificar si necesitamos configurar el proyecto
if ($CurrentProject -ne $ProjectID) {
    Write-Host "Configurando proyecto: $ProjectID" -ForegroundColor Yellow
    gcloud config set project $ProjectID
} else {
    Write-Host "Ya estÃ¡ configurado el proyecto correcto: $ProjectID" -ForegroundColor Green
}

# Configurar regiÃ³n
Write-Host "Configurando regiÃ³n: $Region" -ForegroundColor Yellow
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

# Generar string de variables de entorno
$EnvVars = Get-EnvVarsString

gcloud run deploy $ServiceName `
    --image $ImageName `
    --platform managed `
    --region $Region `
    --memory 1Gi `
    --cpu 1 `
    --min-instances 0 `
    --max-instances 10 `
    --timeout 300 `
    --set-env-vars "$EnvVars" `
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
            Write-Host "Estado de mÃ©tricas: $($Response.components.metrics.status)" -ForegroundColor Green
            Write-Host "MÃ©tricas habilitadas: $($Response.components.metrics.enabled)" -ForegroundColor Green
        }
    } catch {
        Write-Host "Error verificando estado del servicio: $_" -ForegroundColor Red
        Write-Host "El servicio podrÃ­a necesitar mÃ¡s tiempo para inicializarse completamente." -ForegroundColor Yellow
    }

    # Mostrar instrucciones para pruebas manuales
    Write-Host "`n======================================================================================" -ForegroundColor Cyan
    Write-Host "                  INSTRUCCIONES PARA PROBAR LAS NUEVAS FUNCIONALIDADES" -ForegroundColor Cyan
    Write-Host "=======================================================================================" -ForegroundColor Cyan
    
    Write-Host "`n1. Acceder al endpoint de mÃ©tricas:" -ForegroundColor White
    Write-Host "   GET $ServiceUrl/v1/metrics" -ForegroundColor Gray
    
    Write-Host "`n2. Registrar eventos para un usuario real:" -ForegroundColor White
    Write-Host "   POST $ServiceUrl/v1/events/user/real_user_123?event_type=detail-page-view&product_id=9978503037237" -ForegroundColor Gray
    
    Write-Host "`n3. Obtener recomendaciones para ese usuario (excluyendo productos vistos):" -ForegroundColor White
    Write-Host "   GET $ServiceUrl/v1/recommendations/user/real_user_123" -ForegroundColor Gray
    
    Write-Host "`nTodas las peticiones deben incluir la cabecera X-API-Key: $API_KEY" -ForegroundColor Yellow
    Write-Host "======================================================================================" -ForegroundColor Cyan
}

Write-Host "`nProceso de despliegue completado." -ForegroundColor Green
Write-Host "Esta versiÃ³n incluye:" -ForegroundColor Yellow
Write-Host "- Sistema de mÃ©tricas para evaluar la calidad de las recomendaciones" -ForegroundColor Yellow
Write-Host "- ExclusiÃ³n automÃ¡tica de productos ya vistos en las recomendaciones" -ForegroundColor Yellow
Write-Host "- Endpoint /v1/metrics para obtener informaciÃ³n de rendimiento" -ForegroundColor Yellow

# Eliminar el Dockerfile temporal
if (Test-Path $DockerfilePath) {
    Remove-Item $DockerfilePath
    Write-Host "Dockerfile temporal eliminado." -ForegroundColor Gray
}



