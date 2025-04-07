# PowerShell script para desplegar la versión final con eventos corregidos

Write-Host "Iniciando despliegue de la versión TF-IDF con eventos de usuario finalmente corregidos..." -ForegroundColor Green

# Configuración
$ProjectID = "retail-recommendations-449216"
$Region = "us-central1"
$ServiceName = "retail-recommender-tfidf-events"
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

    # Probar registrar un evento de usuario
    Write-Host "Probando el registro de eventos de usuario con la nueva implementación..." -ForegroundColor Yellow
    try {
        $Headers = @{
            "X-API-Key" = "2fed9999056fab6dac5654238f0cae1c"
        }
        $TestUserId = "test_user_system_final"
        $ProductId = "test_product_123"
        
        # Probar diferentes tipos de eventos
        $EventTypes = @(
            "detail-page-view", 
            "add-to-cart", 
            "purchase-complete"
        )
        
        foreach ($EventType in $EventTypes) {
            Write-Host "  Probando evento tipo: $EventType..." -ForegroundColor Cyan
            $TestUrl = "$ServiceUrl/v1/events/user/$TestUserId`?event_type=$EventType&product_id=$ProductId"
            try {
                $TestResponse = Invoke-RestMethod -Uri $TestUrl -Method Post -Headers $Headers
                
                if ($TestResponse.status -eq "success") {
                    Write-Host "    ✅ Éxito: $($TestResponse.detail.note)" -ForegroundColor Green
                } else {
                    Write-Host "    ⚠️ Advertencia: $($TestResponse.status)" -ForegroundColor Yellow
                }
            } catch {
                Write-Host "    ❌ Error: $_" -ForegroundColor Red
            }
            
            # Pequeña pausa entre peticiones
            Start-Sleep -Milliseconds 500
        }
    } catch {
        Write-Host "❌ Error general en pruebas de eventos: $_" -ForegroundColor Red
    }

    # Instrucciones para probar con IDs reales
    Write-Host ""
    Write-Host "Para probar con IDs reales de productos, use:" -ForegroundColor Cyan
    Write-Host "POST $ServiceUrl/v1/events/user/test_user_real?event_type=detail-page-view&product_id=9978503037237" -ForegroundColor White
    Write-Host "POST $ServiceUrl/v1/events/user/test_user_real?event_type=add-to-cart&product_id=9978503037237" -ForegroundColor White
    Write-Host "POST $ServiceUrl/v1/events/user/test_user_real?event_type=purchase-complete&product_id=9978503037237" -ForegroundColor White
}

Write-Host "Proceso de despliegue de TF-IDF con eventos corregidos completado." -ForegroundColor Green
Write-Host "NOTA: Esta versión corrige definitivamente el problema con el registro de eventos de usuario" -ForegroundColor Yellow
Write-Host "      con el uso correcto de WriteUserEventRequest para Google Cloud Retail API." -ForegroundColor Yellow

Write-Host "      Los tipos de eventos válidos según Google Cloud Retail API son:" -ForegroundColor Yellow
Write-Host "      - add-to-cart: Cuando un usuario añade un producto al carrito" -ForegroundColor Yellow
Write-Host "      - category-page-view: Cuando un usuario ve páginas especiales (ofertas, promociones)" -ForegroundColor Yellow
Write-Host "      - detail-page-view: Cuando un usuario ve la página de detalle de un producto" -ForegroundColor Yellow
Write-Host "      - home-page-view: Cuando un usuario visita la página de inicio" -ForegroundColor Yellow
Write-Host "      - purchase-complete: Cuando un usuario completa una compra" -ForegroundColor Yellow
Write-Host "      - search: Cuando un usuario realiza una búsqueda" -ForegroundColor Yellow
Write-Host "" -ForegroundColor Yellow
Write-Host "      El sistema también acepta nombres alternativos simplificados:" -ForegroundColor Yellow
Write-Host "      - 'view' o 'detail-page' → detail-page-view" -ForegroundColor Yellow
Write-Host "      - 'add' o 'cart' → add-to-cart" -ForegroundColor Yellow
Write-Host "      - 'buy', 'purchase' o 'checkout' → purchase-complete" -ForegroundColor Yellow
Write-Host "      - 'home' → home-page-view" -ForegroundColor Yellow
Write-Host "      - 'category' o 'promo' → category-page-view" -ForegroundColor Yellow

Read-Host "Presiona Enter para salir"
