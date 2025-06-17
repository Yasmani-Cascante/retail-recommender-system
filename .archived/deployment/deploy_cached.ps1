
# Variables
$PROJECT_ID = "retail-recommendations-449216"
$SERVICE_NAME = "retail-recommender-cached"
$REGION = "us-central1"
$IMAGE_NAME = "gcr.io/$PROJECT_ID/$SERVICE_NAME"

# Cargar variables de Redis si existe el archivo
if (Test-Path -Path .\redis.env) {
    $redisEnv = Get-Content .\redis.env
    $REDIS_HOST = ($redisEnv | Select-String -Pattern "REDIS_HOST=(.*)").Matches.Groups[1].Value
    $REDIS_PORT = ($redisEnv | Select-String -Pattern "REDIS_PORT=(.*)").Matches.Groups[1].Value
} else {
    # Intentar obtener información de Redis directamente
    try {
        $REDIS_INSTANCE = "retail-recommender-cache"
        $REDIS_INFO = gcloud redis instances describe $REDIS_INSTANCE --region=$REGION --format=json | ConvertFrom-Json
        $REDIS_HOST = $REDIS_INFO.host
        $REDIS_PORT = $REDIS_INFO.port
    } catch {
        Write-Host "No se pudo obtener información de Redis" -ForegroundColor Yellow
        $REDIS_HOST = $null
        $REDIS_PORT = $null
    }
}

# Iniciar medición de tiempo
$startTime = Get-Date

# Mostrar información del despliegue
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "Desplegando versión con caché distribuida" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "Proyecto: $PROJECT_ID" -ForegroundColor Yellow
Write-Host "Servicio: $SERVICE_NAME" -ForegroundColor Yellow
Write-Host "Región: $REGION" -ForegroundColor Yellow
Write-Host "Imagen: $IMAGE_NAME" -ForegroundColor Yellow
if ($REDIS_HOST) {
    Write-Host "Redis Host: $REDIS_HOST" -ForegroundColor Yellow
    Write-Host "Redis Port: $REDIS_PORT" -ForegroundColor Yellow
} else {
    Write-Host "Redis: No configurado" -ForegroundColor Yellow
}
Write-Host "---------------------------------------------------" -ForegroundColor Cyan

# Construir la imagen Docker
Write-Host "Paso 1: Construyendo imagen Docker..." -ForegroundColor Green
docker build -t $IMAGE_NAME -f Dockerfile.cached .

# Verificar resultado
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error construyendo la imagen Docker" -ForegroundColor Red
    exit 1
}

# Subir la imagen a Container Registry
Write-Host "Paso 2: Enviando imagen a Container Registry..." -ForegroundColor Green
docker push $IMAGE_NAME

# Verificar resultado
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error enviando la imagen a Container Registry" -ForegroundColor Red
    exit 1
}

# Preparar el comando de despliegue
$deployCommand = "gcloud run deploy $SERVICE_NAME --image $IMAGE_NAME --platform managed --region $REGION --memory 1Gi --timeout 300 --concurrency 80 --allow-unauthenticated"

# Añadir variables de entorno de Redis si están disponibles
if ($REDIS_HOST) {
    $deployCommand += " --set-env-vars=`"REDIS_HOST=$REDIS_HOST,REDIS_PORT=$REDIS_PORT`""
}

# Desplegar en Cloud Run
Write-Host "Paso 3: Desplegando en Cloud Run..." -ForegroundColor Green
Invoke-Expression $deployCommand

# Verificar resultado
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error desplegando en Cloud Run" -ForegroundColor Red
    exit 1
}

# Calcular tiempo total
$endTime = Get-Date
$duration = $endTime - $startTime
$minutes = [math]::Floor($duration.TotalMinutes)
$seconds = $duration.Seconds

# Mostrar resultado final
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "Despliegue completado exitosamente" -ForegroundColor Green
Write-Host "Tiempo total: $minutes minutos y $seconds segundos" -ForegroundColor Yellow
Write-Host "===================================================" -ForegroundColor Cyan

# Obtener la URL del servicio
$serviceUrl = gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format="value(status.url)"
Write-Host "URL del servicio: $serviceUrl" -ForegroundColor Green
Write-Host "Endpoints disponibles:" -ForegroundColor Yellow
Write-Host "  - $serviceUrl/health" -ForegroundColor White
Write-Host "  - $serviceUrl/v1/products/" -ForegroundColor White
Write-Host "  - $serviceUrl/v1/recommendations/content/{product_id}" -ForegroundColor White

# Mostrar estado de Redis
if ($REDIS_HOST) {
    Write-Host "Redis configurado correctamente" -ForegroundColor Green
} else {
    Write-Host "Redis no configurado. Para habilitar la caché, crea una instancia de Redis con create_redis.ps1" -ForegroundColor Yellow
}
