# PowerShell script para desplegar la versión TF-IDF mejorada con generación de eventos

Write-Host "Iniciando despliegue de la versión TF-IDF mejorada con Shopify..." -ForegroundColor Green

# Configuración
$ProjectID = "retail-recommendations-449216"
$Region = "us-central1"
$ServiceName = "retail-recommender-tfidf-improved"
$ImageName = "gcr.io/$ProjectID/$ServiceName`:latest"
$Dockerfile = "Dockerfile.tfidf.shopify.improved"

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
    --set-env-vars "GOOGLE_PROJECT_NUMBER=178362262166,GOOGLE_LOCATION=global,GOOGLE_CATALOG=default_catalog,GOOGLE_SERVING_CONFIG=default_recommendation_config,API_KEY=2fed9999056fab6dac5654238f0cae1c,SHOPIFY_SHOP_URL=ai-shoppings.myshopify.com,SHOPIFY_ACCESS_TOKEN=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,GCS_BUCKET_NAME=retail-recommendations-449216_cloudbuild,USE_GCS_IMPORT=true,DEBUG=true" `
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
        Write-Host "Tiempo de funcionamiento: $($Response.uptime_seconds) segundos" -ForegroundColor Green
        
        if ($Response.components -and $Response.components.recommender) {
            Write-Host "Estado del recomendador: $($Response.components.recommender.status)" -ForegroundColor Green
            Write-Host "Productos cargados: $($Response.components.recommender.products_count)" -ForegroundColor Green
        }
    } catch {
        Write-Host "Error verificando estado del servicio: $_" -ForegroundColor Red
        Write-Host "El servicio podría necesitar más tiempo para inicializarse completamente." -ForegroundColor Yellow
    }
}

Write-Host "Proceso de despliegue de TF-IDF mejorado completado." -ForegroundColor Green
Write-Host "NOTA: Esta versión implementa un recomendador TF-IDF con estrategias de fallback mejoradas" -ForegroundColor Yellow
Write-Host "      y generación automática de datos de prueba para entrenar el sistema." -ForegroundColor Yellow
Write-Host "      Si el sistema no puede conectarse a Google Cloud Retail API, utilizará" -ForegroundColor Yellow
Write-Host "      recomendaciones inteligentes basadas en popularidad, diversidad o personalización." -ForegroundColor Yellow
Write-Host "      Endpoints disponibles:" -ForegroundColor Yellow
Write-Host "      - /v1/products/ (listado de productos)" -ForegroundColor Yellow
Write-Host "      - /v1/products/category/{category} (productos por categoría)" -ForegroundColor Yellow
Write-Host "      - /v1/products/search/ (búsqueda de productos)" -ForegroundColor Yellow
Write-Host "      - /v1/recommendations/{product_id} (recomendaciones basadas en producto)" -ForegroundColor Yellow
Write-Host "      - /v1/recommendations/user/{user_id} (recomendaciones personalizadas)" -ForegroundColor Yellow
Write-Host "      - /v1/events/user/{user_id} (registro de eventos de usuario)" -ForegroundColor Yellow
Write-Host "      - /v1/customers/ (listado de clientes)" -ForegroundColor Yellow
Write-Host "      - /health (estado del servicio)" -ForegroundColor Yellow

Write-Host "IMPORTANTE: Para probar recomendaciones personalizadas, use IDs de usuario con prefijo 'test_' o 'synthetic_'" -ForegroundColor Cyan
Write-Host "             por ejemplo: 'test_user_1', 'synthetic_user_3', etc." -ForegroundColor Cyan

Read-Host "Presiona Enter para salir"
