
# Variables
$PROJECT_ID = "retail-recommendations-449216"
$REGION = "us-central1"
$REDIS_INSTANCE = "retail-recommender-cache"
$REDIS_TIER = "basic"
$REDIS_SIZE = 1 # 1GB

# Mostrar información
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "Creando instancia de Redis en Memorystore" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "Proyecto: $PROJECT_ID" -ForegroundColor Yellow
Write-Host "Región: $REGION" -ForegroundColor Yellow
Write-Host "Instancia: $REDIS_INSTANCE" -ForegroundColor Yellow
Write-Host "Tier: $REDIS_TIER" -ForegroundColor Yellow
Write-Host "Tamaño: ${REDIS_SIZE}GB" -ForegroundColor Yellow
Write-Host "---------------------------------------------------" -ForegroundColor Cyan

# Crear la instancia
Write-Host "Creando instancia de Redis... (puede tardar unos minutos)" -ForegroundColor Green
gcloud redis instances create $REDIS_INSTANCE `
    --project=$PROJECT_ID `
    --region=$REGION `
    --tier=$REDIS_TIER `
    --size=$REDIS_SIZE `
    --redis-version=redis_6_x

# Verificar resultado
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error creando instancia de Redis" -ForegroundColor Red
    exit 1
}

# Obtener información de la instancia
Write-Host "Obteniendo información de la instancia..." -ForegroundColor Green
$REDIS_INFO = gcloud redis instances describe $REDIS_INSTANCE --region=$REGION --format=json | ConvertFrom-Json

# Extraer host y puerto
$REDIS_HOST = $REDIS_INFO.host
$REDIS_PORT = $REDIS_INFO.port

# Mostrar información
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "Instancia de Redis creada correctamente" -ForegroundColor Green
Write-Host "Host: $REDIS_HOST" -ForegroundColor Green
Write-Host "Port: $REDIS_PORT" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Cyan

# Guardar información para uso posterior
Write-Host "# Variables de entorno para Redis" > redis.env
Write-Host "REDIS_HOST=$REDIS_HOST" >> redis.env
Write-Host "REDIS_PORT=$REDIS_PORT" >> redis.env

Write-Host "Información guardada en redis.env" -ForegroundColor Green
Write-Host "Para usar estas variables, ejecuta:" -ForegroundColor Yellow
Write-Host 'Get-Content .\redis.env | ForEach-Object { $var = $_.Split("="); [System.Environment]::SetEnvironmentVariable($var[0], $var[1], "Process") }' -ForegroundColor White
