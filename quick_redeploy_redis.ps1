# Script de redepliegue rapido para Redis Labs
# Este script redespliega solo la imagen sin reconstruir desde cero

param(
    [switch]$SkipBuild = $false,
    [switch]$SkipTests = $false
)

$ProjectID = "retail-recommendations-449216"
$Region = "us-central1"
$ServiceName = "retail-recommender-redis-labs"
$ImageName = "gcr.io/$ProjectID/$ServiceName`:latest"

Write-Host "🚀 Redepliegue rapido de Redis Labs..." -ForegroundColor Green

# Cargar variables secretas
function Load-SecretVars {
    $SecretsFile = ".env.secrets"
    
    if (-not (Test-Path $SecretsFile)) {
        Write-Host "❌ Archivo .env.secrets no encontrado" -ForegroundColor Red
        return $false
    }
    
    $script:Secrets = @{}
    Get-Content $SecretsFile | ForEach-Object {
        if (-not [string]::IsNullOrWhiteSpace($_) -and -not $_.StartsWith("#")) {
            $KeyValue = $_ -split '=', 2
            if ($KeyValue.Length -eq 2) {
                $Key = $KeyValue[0].Trim()
                $Value = $KeyValue[1].Trim()
                $script:Secrets[$Key] = $Value
            }
        }
    }
    
    Write-Host "✅ Variables secretas cargadas" -ForegroundColor Green
    return $true
}

function Get-EnvVarsString {
    $EnvVars = @(
        "GOOGLE_PROJECT_NUMBER=$($script:Secrets.GOOGLE_PROJECT_NUMBER)",
        "GOOGLE_LOCATION=global",
        "GOOGLE_CATALOG=default_catalog",
        "GOOGLE_SERVING_CONFIG=default_recommendation_config",
        "API_KEY=$($script:Secrets.API_KEY)",
        "SHOPIFY_SHOP_URL=$($script:Secrets.SHOPIFY_SHOP_URL)",
        "SHOPIFY_ACCESS_TOKEN=$($script:Secrets.SHOPIFY_ACCESS_TOKEN)",
        "GCS_BUCKET_NAME=$($script:Secrets.GCS_BUCKET_NAME)",
        "USE_GCS_IMPORT=true",
        "DEBUG=true",
        "METRICS_ENABLED=true",
        "EXCLUDE_SEEN_PRODUCTS=true",
        "DEFAULT_CURRENCY=COP",
        "USE_REDIS_CACHE=true",
        "REDIS_HOST=$($script:Secrets.REDIS_HOST)",
        "REDIS_PORT=$($script:Secrets.REDIS_PORT)",
        "REDIS_PASSWORD=$($script:Secrets.REDIS_PASSWORD)",
        "REDIS_USERNAME=$($script:Secrets.REDIS_USERNAME)",
        "REDIS_SSL=$($script:Secrets.REDIS_SSL)",
        "REDIS_DB=0",
        "CACHE_TTL=$($script:Secrets.CACHE_TTL)",
        "CACHE_PREFIX=$($script:Secrets.CACHE_PREFIX)",
        "CACHE_ENABLE_BACKGROUND_TASKS=$($script:Secrets.CACHE_ENABLE_BACKGROUND_TASKS)"
    )
    
    return $EnvVars -join ","
}

# Cargar secretos
$SecretsLoaded = Load-SecretVars
if (-not $SecretsLoaded) {
    exit 1
}

# Construir imagen solo si no se especifica SkipBuild
if (-not $SkipBuild) {
    Write-Host "🔨 Construyendo imagen..." -ForegroundColor Yellow
    docker build -t $ImageName -f Dockerfile.fixed .
    if (-not $?) {
        Write-Host "❌ Error construyendo imagen" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "📤 Subiendo imagen..." -ForegroundColor Yellow
    docker push $ImageName
    if (-not $?) {
        Write-Host "❌ Error subiendo imagen" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "⏭️ Saltando construcción de imagen" -ForegroundColor Yellow
}

# Redesplegar servicio
Write-Host "🚀 Redesplegando servicio..." -ForegroundColor Yellow
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

if (-not $?) {
    Write-Host "❌ Error en redepliegue" -ForegroundColor Red
    exit 1
}

# Obtener URL
$ServiceUrl = gcloud run services describe $ServiceName --platform managed --region $Region --format 'value(status.url)'
Write-Host "✅ Servicio redesplegado: $ServiceUrl" -ForegroundColor Green

# Pruebas rápidas si no se especifica SkipTests
if (-not $SkipTests) {
    Write-Host "🧪 Ejecutando pruebas rapidas..." -ForegroundColor Yellow
    Start-Sleep -Seconds 15
    
    try {
        $Response = Invoke-RestMethod -Uri "$ServiceUrl/health" -Method Get -TimeoutSec 15
        Write-Host "✅ Health check exitoso: $($Response.status)" -ForegroundColor Green
        
        if ($Response.components.cache.redis_connection -eq "connected") {
            Write-Host "✅ Redis conectado correctamente" -ForegroundColor Green
        } else {
            Write-Host "⚠️ Redis no conectado: $($Response.components.cache.redis_connection)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "⚠️ Health check falló, pero el servicio puede estar iniciando..." -ForegroundColor Yellow
    }
} else {
    Write-Host "⏭️ Saltando pruebas" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "🎉 Redepliegue completado!" -ForegroundColor Green
Write-Host "URL del servicio: $ServiceUrl" -ForegroundColor Cyan
Write-Host ""
Write-Host "Para probar Redis Labs, ejecuta:" -ForegroundColor White
Write-Host "  python verify_redis_labs_connection.py" -ForegroundColor Gray
