
# Variables
$PROJECT_ID = "retail-recommendations-449216"
$SERVICE_NAME = "retail-recommender-api"
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

# Cargar variables del servidor gRPC si existe el archivo
if (Test-Path -Path .\grpc_server.env) {
    $grpcEnv = Get-Content .\grpc_server.env
    $GRPC_SERVER = ($grpcEnv | Select-String -Pattern "GRPC_SERVER=(.*)").Matches.Groups[1].Value
} else {
    Write-Host "Archivo grpc_server.env no encontrado" -ForegroundColor Yellow
    $GRPC_SERVER = $null
}

# Iniciar medición de tiempo
$startTime = Get-Date

# Mostrar información del despliegue
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "Desplegando API distribuida para recomendaciones" -ForegroundColor Cyan
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
if ($GRPC_SERVER) {
    Write-Host "Servidor gRPC: $GRPC_SERVER" -ForegroundColor Yellow
} else {
    Write-Host "Servidor gRPC: No configurado" -ForegroundColor Yellow
}
Write-Host "---------------------------------------------------" -ForegroundColor Cyan

# Construir la imagen Docker
Write-Host "Paso 1: Construyendo imagen Docker para API distribuida..." -ForegroundColor Green
docker build -t $IMAGE_NAME -f Dockerfile.distributed .

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

# Preparar variables de entorno
$env_vars = "GCP_PROJECT_NUMBER=$PROJECT_ID,GCP_LOCATION=$REGION"

# Añadir variables de Redis si están disponibles
if ($REDIS_HOST) {
    $env_vars += ",REDIS_HOST=$REDIS_HOST,REDIS_PORT=$REDIS_PORT"
}

# Añadir variables de gRPC si están disponibles
if ($GRPC_SERVER) {
    $env_vars += ",GRPC_SERVER=$GRPC_SERVER"
}

# Desplegar en Cloud Run
Write-Host "Paso 3: Desplegando en Cloud Run..." -ForegroundColor Green
gcloud run deploy $SERVICE_NAME `
    --image $IMAGE_NAME `
    --platform managed `
    --region $REGION `
    --memory 1Gi `
    --cpu 1 `
    --timeout 300 `
    --concurrency 80 `
    --set-env-vars $env_vars `
    --allow-unauthenticated

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
Write-Host "Despliegue de la API distribuida completado exitosamente" -ForegroundColor Green
Write-Host "Tiempo total: $minutes minutos y $seconds segundos" -ForegroundColor Yellow
Write-Host "===================================================" -ForegroundColor Cyan

# Obtener la URL del servicio
$serviceUrl = gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format="value(status.url)"
Write-Host "URL del servicio: $serviceUrl" -ForegroundColor Green
Write-Host "Endpoints disponibles:" -ForegroundColor Yellow
Write-Host "  - $serviceUrl/health" -ForegroundColor White
Write-Host "  - $serviceUrl/v1/products/" -ForegroundColor White
Write-Host "  - $serviceUrl/v1/recommendations/content/{product_id}" -ForegroundColor White
Write-Host "  - $serviceUrl/v1/recommendations/retail/{product_id}" -ForegroundColor White
Write-Host "  - $serviceUrl/v1/recommendations/hybrid/{product_id}" -ForegroundColor White

# Mostrar estados de componentes
Write-Host "Estados de componentes:" -ForegroundColor Yellow
if ($REDIS_HOST) {
    Write-Host "  ✅ Redis configurado correctamente: $REDIS_HOST:$REDIS_PORT" -ForegroundColor Green
} else {
    Write-Host "  ❌ Redis no configurado. Ejecuta create_redis.ps1 para crear una instancia." -ForegroundColor Red
}

if ($GRPC_SERVER) {
    Write-Host "  ✅ Servidor gRPC configurado correctamente: $GRPC_SERVER" -ForegroundColor Green
} else {
    Write-Host "  ❌ Servidor gRPC no configurado. Ejecuta deploy_grpc_server.ps1 primero." -ForegroundColor Red
}
