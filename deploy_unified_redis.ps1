# PowerShell script para desplegar la version unificada con Redis del sistema de recomendaciones

Write-Host "Iniciando despliegue de la version unificada con Redis del sistema de recomendaciones..." -ForegroundColor Green

# Configuracion
$ProjectID = "retail-recommendations-449216"
$Region = "us-central1"
$ServiceName = "retail-recommender-unified-redis"
$ImageName = "gcr.io/$ProjectID/$ServiceName`:latest"
$Dockerfile = "Dockerfile.fixed"
$UnifiedDockerfile = "Dockerfile.unified.redis"

# Verificar configuracion de GCloud
Write-Host "Verificando configuracion de GCloud..." -ForegroundColor Yellow
$CurrentProject = gcloud config get-value project
Write-Host "Proyecto actual: $CurrentProject" -ForegroundColor Cyan

if ($CurrentProject -ne $ProjectID) {
    Write-Host "Configurando proyecto: $ProjectID" -ForegroundColor Yellow
    gcloud config set project $ProjectID
} else {
    Write-Host "Ya esta configurado el proyecto correcto: $ProjectID" -ForegroundColor Green
}

# Configurar region
Write-Host "Configurando region: $Region" -ForegroundColor Yellow
gcloud config set run/region $Region

# Crear Dockerfile especifico para la version unificada con Redis
Write-Host "Creando Dockerfile especifico para la version unificada con Redis..." -ForegroundColor Yellow
$OriginalDockerfile = Get-Content $Dockerfile
$ModifiedDockerfile = $OriginalDockerfile -replace "main_tfidf_shopify_with_metrics_fixed:app", "main_unified_redis:app"
$ModifiedDockerfile | Out-File -FilePath $UnifiedDockerfile -Encoding utf8

# Verificar que el archivo main_unified_redis.py existe
if (-not (Test-Path "src/api/main_unified_redis.py")) {
    Write-Host "Error: El archivo src/api/main_unified_redis.py no existe." -ForegroundColor Red
    Write-Host "Este archivo es necesario para la arquitectura unificada con Redis." -ForegroundColor Red
    exit 1
}

# Construir imagen Docker
Write-Host "Construyendo la imagen Docker..." -ForegroundColor Yellow
try {
    docker build -t $ImageName -f $UnifiedDockerfile .
    if (-not $?) {
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

# Variables de entorno, asegurando que USE_REDIS_CACHE está habilitado
$EnvVars = "GOOGLE_PROJECT_NUMBER=178362262166,GOOGLE_LOCATION=global,GOOGLE_CATALOG=default_catalog,GOOGLE_SERVING_CONFIG=default_recommendation_config,API_KEY=2fed9999056fab6dac5654238f0cae1c,SHOPIFY_SHOP_URL=ai-shoppings.myshopify.com,SHOPIFY_ACCESS_TOKEN=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,GCS_BUCKET_NAME=retail-recommendations-449216_cloudbuild,USE_GCS_IMPORT=true,DEBUG=true,METRICS_ENABLED=true,EXCLUDE_SEEN_PRODUCTS=true,USE_REDIS_CACHE=true,REDIS_HOST=redis-14272.c259.us-central1-2.gce.redns.redis-cloud.com,REDIS_PORT=14272,REDIS_PASSWORD=34rleeRxTmFYqBZpSA5UoDP71bHEq6zO,REDIS_USERNAME=default,REDIS_SSL=false,REDIS_DB=0,CACHE_TTL=86400,CACHE_PREFIX=product:,CACHE_ENABLE_BACKGROUND_TASKS=true"

gcloud run deploy $ServiceName `
    --image $ImageName `
    --platform managed `
    --region $Region `
    --memory 1Gi `
    --cpu 1 `
    --min-instances 0 `
    --max-instances 10 `
    --timeout 300 `
    --set-env-vars $EnvVars `
    --allow-unauthenticated

if (-not $?) {
    Write-Host "Error al desplegar en Cloud Run." -ForegroundColor Red
    exit 1
}

# Limpiar archivos temporales
Write-Host "Limpiando archivos temporales..." -ForegroundColor Yellow
Remove-Item $UnifiedDockerfile -Force

# Obtener URL del servicio
Write-Host "Obteniendo URL del servicio..." -ForegroundColor Yellow
$ServiceUrl = gcloud run services describe $ServiceName --platform managed --region $Region --format 'value(status.url)'

if ($ServiceUrl) {
    Write-Host "Servicio desplegado en: $ServiceUrl" -ForegroundColor Green
    
    # Esperar para que el servicio se inicialice
    Write-Host "Esperando 30 segundos para que el servicio se inicialice..." -ForegroundColor Yellow
    Start-Sleep -Seconds 30

    # Verificar estado del servicio
    Write-Host "Verificando estado del servicio..." -ForegroundColor Yellow
    try {
        $HealthUrl = $ServiceUrl + "/health"
        $Response = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 30
        Write-Host "Estado del servicio: $($Response.status)" -ForegroundColor Green
        
        if ($Response.components -and $Response.components.recommender) {
            Write-Host "Estado del recomendador: $($Response.components.recommender.status)" -ForegroundColor Green
        }
        
        # Verificar específicamente el estado de la caché
        if ($Response.components -and $Response.components.cache) {
            $CacheStatus = $Response.components.cache
            Write-Host ""
            Write-Host "Estado del sistema de cache:" -ForegroundColor Cyan
            Write-Host "  Status: $($CacheStatus.status)" -ForegroundColor Green
            Write-Host "  Conexion Redis: $($CacheStatus.redis_connection)" -ForegroundColor Green
            
            if ($CacheStatus.redis_connection -eq "connected") {
                Write-Host "  Conexion a Redis Labs establecida correctamente" -ForegroundColor Green
            } else {
                Write-Host "  No se pudo establecer conexion con Redis Labs" -ForegroundColor Red
                Write-Host "    Verifica las credenciales y la configuracion" -ForegroundColor Yellow
            }
        } else {
            Write-Host ""
            Write-Host "No se encontro informacion sobre el sistema de cache" -ForegroundColor Red
        }
    } catch {
        Write-Host "Error verificando estado del servicio: $_" -ForegroundColor Red
        Write-Host "El servicio podria necesitar mas tiempo para inicializarse." -ForegroundColor Yellow
    }

    # Realizar pruebas basicas si el servicio esta funcionando
    if ($Response -and ($Response.status -eq "ready" -or $Response.status -eq "OK")) {
        Write-Host "`nRealizando pruebas basicas..." -ForegroundColor Cyan
        
        $Headers = @{
            "X-API-Key" = "2fed9999056fab6dac5654238f0cae1c"
        }

        # Prueba 1: Obtener productos
        Write-Host "Prueba 1: Obteniendo lista de productos..." -ForegroundColor Cyan
        try {
            $ProductsUrl = $ServiceUrl + "/v1/products/"
            $ProductsResponse = Invoke-RestMethod -Uri $ProductsUrl -Method Get
            Write-Host "  Exito: Obtenidos productos de la lista" -ForegroundColor Green
        } catch {
            Write-Host "  Error obteniendo productos: $_" -ForegroundColor Red
        }

        # Prueba 2: Obtener recomendaciones de usuario
        Write-Host "Prueba 2: Obteniendo recomendaciones de usuario..." -ForegroundColor Cyan
        try {
            $UserRecommendationUrl = $ServiceUrl + "/v1/recommendations/user/test_user_unified_redis?n=5"
            $UserRecommendationResponse = Invoke-RestMethod -Uri $UserRecommendationUrl -Method Get -Headers $Headers
            Write-Host "  Exito: Obtenidas recomendaciones de usuario" -ForegroundColor Green
        } catch {
            Write-Host "  Error obteniendo recomendaciones de usuario: $_" -ForegroundColor Red
        }
        
        # Prueba 3: Registrar evento de usuario
        Write-Host "Prueba 3: Registrando evento de usuario..." -ForegroundColor Cyan
        try {
            $EventType = "detail-page-view"
            $ProductId = "product123"
            $EventUrl = $ServiceUrl + "/v1/events/user/test_user_unified_redis"
            $EventUrl = $EventUrl + "?event_type=" + $EventType + "&product_id=" + $ProductId
            
            $EventResponse = Invoke-RestMethod -Uri $EventUrl -Method Post -Headers $Headers
            Write-Host "  Exito: Evento registrado correctamente" -ForegroundColor Green
        } catch {
            Write-Host "  Error registrando evento: $_" -ForegroundColor Red
        }
    }

    # Mostrar instrucciones finales
    Write-Host "`n===============================================================================" -ForegroundColor Cyan
    Write-Host "                    DESPLIEGUE COMPLETADO EXITOSAMENTE" -ForegroundColor Cyan
    Write-Host "===============================================================================" -ForegroundColor Cyan
    
    Write-Host "`nURL del servicio: $ServiceUrl" -ForegroundColor White
    Write-Host "`nEndpoints principales:" -ForegroundColor White
    Write-Host "  GET  $ServiceUrl/health" -ForegroundColor Gray
    Write-Host "  GET  $ServiceUrl/v1/products/" -ForegroundColor Gray
    Write-Host "  GET  $ServiceUrl/v1/recommendations/PRODUCT_ID (requiere API Key)" -ForegroundColor Gray
    Write-Host "  GET  $ServiceUrl/v1/recommendations/user/USER_ID (requiere API Key)" -ForegroundColor Gray
    Write-Host "  POST $ServiceUrl/v1/events/user/USER_ID?event_type=TYPE&product_id=ID (requiere API Key)" -ForegroundColor Gray
    
    Write-Host "`nAPI Key para pruebas: 2fed9999056fab6dac5654238f0cae1c" -ForegroundColor Yellow
    Write-Host "===============================================================================" -ForegroundColor Cyan

} else {
    Write-Host "Error: No se pudo obtener la URL del servicio" -ForegroundColor Red
    exit 1
}

Write-Host "`nProceso de despliegue completado." -ForegroundColor Green
Write-Host "La version unificada con Redis esta lista para usar!" -ForegroundColor Green
