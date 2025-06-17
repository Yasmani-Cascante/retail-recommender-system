
# Variables
$PROJECT_ID = "retail-recommendations-449216"
$SERVICE_NAME = "retail-recommender-grpc"
$REGION = "us-central1"
$IMAGE_NAME = "gcr.io/$PROJECT_ID/$SERVICE_NAME"

# Iniciar medición de tiempo
$startTime = Get-Date

# Mostrar información del despliegue
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "Desplegando servidor gRPC para recomendaciones" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "Proyecto: $PROJECT_ID" -ForegroundColor Yellow
Write-Host "Servicio: $SERVICE_NAME" -ForegroundColor Yellow
Write-Host "Región: $REGION" -ForegroundColor Yellow
Write-Host "Imagen: $IMAGE_NAME" -ForegroundColor Yellow
Write-Host "---------------------------------------------------" -ForegroundColor Cyan

# Construir la imagen Docker
Write-Host "Paso 1: Construyendo imagen Docker para servidor gRPC..." -ForegroundColor Green
docker build -t $IMAGE_NAME -f Dockerfile.grpc_server .

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

# Desplegar en Cloud Run
Write-Host "Paso 3: Desplegando en Cloud Run..." -ForegroundColor Green
gcloud run deploy $SERVICE_NAME `
    --image $IMAGE_NAME `
    --platform managed `
    --region $REGION `
    --memory 2Gi `
    --cpu 2 `
    --timeout 1800 `
    --port 50051 `
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

# Obtener URL del servicio
$serviceUrl = gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format="value(status.url)"
$serviceHost = ($serviceUrl -replace "https://", "").Trim()

# Mostrar resultado final
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "Despliegue del servidor gRPC completado exitosamente" -ForegroundColor Green
Write-Host "Tiempo total: $minutes minutos y $seconds segundos" -ForegroundColor Yellow
Write-Host "URL del servicio: $serviceUrl" -ForegroundColor Green
Write-Host "Host gRPC: $serviceHost" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Cyan

# Guardar información del servicio gRPC para la API
Write-Host "# Variables de entorno para servidor gRPC" > grpc_server.env
Write-Host "GRPC_SERVER=$serviceHost:50051" >> grpc_server.env

Write-Host "Información del servidor gRPC guardada en grpc_server.env" -ForegroundColor Green
Write-Host "Para usar estas variables, ejecuta:" -ForegroundColor Yellow
Write-Host 'Get-Content .\grpc_server.env | ForEach-Object { $var = $_.Split("="); [System.Environment]::SetEnvironmentVariable($var[0], $var[1], "Process") }' -ForegroundColor White
