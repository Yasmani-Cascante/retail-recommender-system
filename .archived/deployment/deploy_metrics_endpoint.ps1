# PowerShell script para añadir el endpoint de métricas y desplegarlo

Write-Host "Añadiendo endpoint de métricas al sistema de recomendaciones..." -ForegroundColor Green

# Configuración
$ProjectID = "retail-recommendations-449216"
$Region = "us-central1"
$ServiceName = "retail-recommender-tfidf-metrics"
$ImageName = "gcr.io/$ProjectID/$ServiceName`:latest"
$Dockerfile = "Dockerfile.tfidf.shopify.improved"
$MainFile = "src/api/main_tfidf_shopify.py"
$MetricsEndpoint = "metrics_endpoint.py"

# 1. Modificar el archivo principal para añadir el endpoint de métricas
Write-Host "Añadiendo el endpoint de métricas al archivo principal..." -ForegroundColor Yellow

# Leer el contenido del endpoint de métricas
$metricsEndpointContent = Get-Content $MetricsEndpoint -Raw

# Leer el archivo principal
$mainFileContent = Get-Content $MainFile -Raw

# Verificar si el archivo ya contiene el endpoint de métricas
if ($mainFileContent -match "/v1/metrics") {
    Write-Host "El endpoint de métricas ya está definido en el archivo principal" -ForegroundColor Green
} else {
    # Buscar la posición para añadir el endpoint (al final, antes de los otros endpoints)
    $pattern = '@app.get\("/v1/products/search/"'
    
    # Añadir el endpoint antes del endpoint de búsqueda
    $newContent = $mainFileContent -replace $pattern, "$metricsEndpointContent`n`n$pattern"
    
    # Guardar el archivo modificado
    $newContent | Set-Content $MainFile
    
    Write-Host "Endpoint de métricas añadido al archivo principal" -ForegroundColor Green
}

# 2. Asegurarse de que la importación de métricas esté presente
$importPattern = "from src.api.core.metrics import recommendation_metrics"
if (-not ($mainFileContent -match $importPattern)) {
    Write-Host "Añadiendo importación de métricas..." -ForegroundColor Yellow
    
    # Buscar lugar para añadir la importación
    $importInsertPattern = "from src.api.startup_helper import StartupManager"
    $importStatement = "$importInsertPattern`n`n# Importar sistema de métricas`nfrom src.api.core.metrics import recommendation_metrics, time_function, analyze_metrics_file"
    
    # Reemplazar la línea de importación
    $newContent = $mainFileContent -replace $importInsertPattern, $importStatement
    
    # Guardar el archivo modificado
    $newContent | Set-Content $MainFile
    
    Write-Host "Importación de métricas añadida al archivo principal" -ForegroundColor Green
}

# 3. Construir y desplegar la imagen Docker
Write-Host "Construyendo la imagen Docker..." -ForegroundColor Yellow
$BuildSuccess = $false
try {
    docker build -t $ImageName -f $Dockerfile .
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

    # Verificar el endpoint de métricas
    Write-Host "Verificando el endpoint de métricas..." -ForegroundColor Yellow
    try {
        $Headers = @{
            "X-API-Key" = "2fed9999056fab6dac5654238f0cae1c"
        }
        $MetricsUrl = "$ServiceUrl/v1/metrics"
        $Response = Invoke-RestMethod -Uri $MetricsUrl -Method Get -Headers $Headers -TimeoutSec 30
        
        Write-Host "Endpoint de métricas funcionando correctamente." -ForegroundColor Green
        Write-Host "Total de solicitudes: $($Response.realtime_metrics.total_requests)" -ForegroundColor Green
        
        if ($Response.realtime_metrics.fallback_rate -ne $null) {
            $FallbackRate = [math]::Round($Response.realtime_metrics.fallback_rate * 100, 2)
            Write-Host "Tasa de fallback: $FallbackRate%" -ForegroundColor Green
        }
    } catch {
        Write-Host "Error verificando el endpoint de métricas: $_" -ForegroundColor Red
        Write-Host "El endpoint de métricas podría no estar correctamente configurado." -ForegroundColor Yellow
    }
}

Write-Host "`nCómo utilizar el endpoint de métricas:" -ForegroundColor Cyan
Write-Host "1. Accede a la URL: $ServiceUrl/v1/metrics" -ForegroundColor White
Write-Host "2. Incluye el header X-API-Key: 2fed9999056fab6dac5654238f0cae1c" -ForegroundColor White
Write-Host "`nEste endpoint proporciona información sobre:" -ForegroundColor Cyan
Write-Host "- Total de recomendaciones servidas" -ForegroundColor White
Write-Host "- Tiempo promedio de respuesta" -ForegroundColor White
Write-Host "- Distribución de tipos de recomendación" -ForegroundColor White
Write-Host "- Tasa de fallback" -ForegroundColor White
Write-Host "- Categorías más recomendadas" -ForegroundColor White

Read-Host "Presiona Enter para salir"
