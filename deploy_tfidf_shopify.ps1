# PowerShell script para desplegar la versión TF-IDF con Shopify a Cloud Run

Write-Host "Iniciando despliegue de la versión TF-IDF con Shopify..." -ForegroundColor Green

# Configuración
$ProjectID = "retail-recommendations-449216"
$Region = "us-central1"
$ServiceName = "retail-recommender-tfidf-shopify"
$ImageName = "gcr.io/$ProjectID/$ServiceName`:latest"
$Dockerfile = "Dockerfile.tfidf.shopify"

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
    Write-Host "Intentando solucionar errores comunes..." -ForegroundColor Yellow
    
    # En caso de fallo, intentamos modificar el Dockerfile para solucionar problemas
    if (Test-Path $Dockerfile) {
        $content = Get-Content $Dockerfile
        $newContent = @()
        $modified = $false
        
        foreach ($line in $content) {
            # Quitar línea que copia .env si existe
            if ($line -match "COPY .env") {
                Write-Host "Eliminando línea problemática: $line" -ForegroundColor Yellow
                $modified = $true
                continue
            }
            $newContent += $line
        }
        
        if ($modified) {
            Write-Host "Modificando Dockerfile para solucionar problemas..." -ForegroundColor Yellow
            $newContent | Set-Content $Dockerfile
            
            # Intentar construir de nuevo
            Write-Host "Intentando construir imagen de nuevo..." -ForegroundColor Yellow
            docker build -t $ImageName -f $Dockerfile .
            $BuildSuccess = $?
        }
    }
    
    if (-not $BuildSuccess) {
        Write-Host "No se pudo construir la imagen Docker. Abortando despliegue." -ForegroundColor Red
        exit 1
    }
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
    Write-Host "Esperando 15 segundos para que el servicio se inicialice..." -ForegroundColor Yellow
    Start-Sleep -Seconds 15

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

Write-Host "Proceso de despliegue de TF-IDF con Shopify completado." -ForegroundColor Green
Write-Host "NOTA: Esta versión implementa un recomendador TF-IDF en lugar de transformer" -ForegroundColor Yellow
Write-Host "      e incluye integración con Shopify y Google Cloud Retail API." -ForegroundColor Yellow
Write-Host "      Si el sistema no puede conectarse a Shopify, utilizará datos de muestra." -ForegroundColor Yellow
Write-Host "      Endpoints disponibles:" -ForegroundColor Yellow
Write-Host "      - /v1/products/ (listado de productos)" -ForegroundColor Yellow
Write-Host "      - /v1/products/category/{category} (productos por categoría)" -ForegroundColor Yellow
Write-Host "      - /v1/products/search/ (búsqueda de productos)" -ForegroundColor Yellow
Write-Host "      - /v1/recommendations/{product_id} (recomendaciones basadas en producto)" -ForegroundColor Yellow
Write-Host "      - /v1/recommendations/user/{user_id} (recomendaciones personalizadas)" -ForegroundColor Yellow
Write-Host "      - /v1/events/user/{user_id} (registro de eventos de usuario)" -ForegroundColor Yellow
Write-Host "      - /v1/customers/ (listado de clientes)" -ForegroundColor Yellow
Write-Host "      - /health (estado del servicio)" -ForegroundColor Yellow

Read-Host "Presiona Enter para salir"
