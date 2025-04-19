# PowerShell script para desplegar la versión unificada del sistema de recomendaciones

Write-Host "Iniciando despliegue de la versión unificada del sistema de recomendaciones..." -ForegroundColor Green

# Configuración
$ProjectID = "retail-recommendations-449216"
$Region = "us-central1"
$ServiceName = "retail-recommender-unified"
$ImageName = "gcr.io/$ProjectID/$ServiceName`:latest"
$Dockerfile = "Dockerfile.fixed"  # Modificado: Usando el Dockerfile más actualizado

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

# Modificar temporalmente el Dockerfile para usar main_unified.py
Write-Host "Creando Dockerfile específico para la versión unificada..." -ForegroundColor Yellow
$OriginalDockerfile = Get-Content $Dockerfile
$ModifiedDockerfile = $OriginalDockerfile -replace "CMD \[""uvicorn"", ""src\.api\.main_tfidf_shopify_with_metrics:app"", ""--host"", ""0\.0\.0\.0"", ""--port"", ""\$\{PORT:-8080\}""\]", "CMD [""uvicorn"", ""src.api.main_unified:app"", ""--host"", ""0.0.0.0"", ""--port"", ""`${PORT:-8080}""]"
$UnifiedDockerfile = "Dockerfile.unified"
$ModifiedDockerfile | Out-File -FilePath $UnifiedDockerfile -Encoding utf8

# Construir imagen Docker
Write-Host "Construyendo la imagen Docker..." -ForegroundColor Yellow
$BuildSuccess = $false
try {
    docker build -t $ImageName -f $UnifiedDockerfile .
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

# Eliminar Dockerfile temporal
Write-Host "Limpiando archivos temporales..." -ForegroundColor Yellow
Remove-Item $UnifiedDockerfile -Force

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
    Write-Host "Esperando 30 segundos para que el servicio se inicialice..." -ForegroundColor Yellow
    Start-Sleep -Seconds 30

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

    # Realizar pruebas básicas
    if ($Response.status -eq "OK" -or $Response.status -eq "ok" -or $Response.status -eq "initializing" -or $Response.status -eq "ready") {
        $Headers = @{
            "X-API-Key" = "2fed9999056fab6dac5654238f0cae1c"
        }

        # Prueba 1: Registrar eventos de usuario
        Write-Host "`nPrueba 1: Registrando eventos de usuario..." -ForegroundColor Cyan
        $TestUserId = "test_user_unified"
        $ProductId = "test_product_456"
        
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

        # Prueba 2: Obtener recomendaciones de producto
        Write-Host "`nPrueba 2: Obteniendo recomendaciones para un producto..." -ForegroundColor Cyan
        try {
            $RecommendationUrl = "$ServiceUrl/v1/recommendations/test_product_456"
            $RecommendationResponse = Invoke-RestMethod -Uri $RecommendationUrl -Method Get -Headers $Headers
            Write-Host "  ✅ Éxito: Obtenidas $($RecommendationResponse.metadata.total_recommendations) recomendaciones" -ForegroundColor Green
        } catch {
            Write-Host "  ❌ Error: $_" -ForegroundColor Red
        }

        # Prueba 3: Obtener recomendaciones personalizadas
        Write-Host "`nPrueba 3: Obteniendo recomendaciones personalizadas para un usuario..." -ForegroundColor Cyan
        try {
            $UserRecommendationUrl = "$ServiceUrl/v1/recommendations/user/test_user_unified"
            $UserRecommendationResponse = Invoke-RestMethod -Uri $UserRecommendationUrl -Method Get -Headers $Headers
            Write-Host "  ✅ Éxito: Obtenidas $($UserRecommendationResponse.metadata.total_recommendations) recomendaciones personalizadas" -ForegroundColor Green
            Write-Host "  Tiempo de respuesta: $($UserRecommendationResponse.metadata.took_ms) ms" -ForegroundColor Green
        } catch {
            Write-Host "  ❌ Error: $_" -ForegroundColor Red
        }
        
        # Prueba 4: Obtener métricas del sistema
        Write-Host "`nPrueba 4: Obteniendo métricas del sistema..." -ForegroundColor Cyan
        try {
            $MetricsUrl = "$ServiceUrl/v1/metrics"
            $MetricsResponse = Invoke-RestMethod -Uri $MetricsUrl -Method Get -Headers $Headers
            Write-Host "  ✅ Éxito: Métricas obtenidas correctamente" -ForegroundColor Green
            Write-Host "  Total de solicitudes: $($MetricsResponse.realtime_metrics.total_requests)" -ForegroundColor Green
            
            if ($MetricsResponse.realtime_metrics.fallback_rate -ne $null) {
                $FallbackRate = [math]::Round($MetricsResponse.realtime_metrics.fallback_rate * 100, 2)
                Write-Host "  Tasa de fallback: $FallbackRate%" -ForegroundColor Green
            }
            
            Write-Host "  Tiempo promedio de respuesta: $([math]::Round($MetricsResponse.realtime_metrics.average_response_time_ms, 2)) ms" -ForegroundColor Green
        } catch {
            Write-Host "  ❌ Error: $_" -ForegroundColor Red
        }
    }

    # Mostrar instrucciones para pruebas manuales
    Write-Host "`n======================================================================================" -ForegroundColor Cyan
    Write-Host "              INSTRUCCIONES PARA PROBAR LA VERSIÓN UNIFICADA" -ForegroundColor Cyan
    Write-Host "=======================================================================================" -ForegroundColor Cyan
    
    Write-Host "`n1. Registrar eventos para un usuario de prueba:" -ForegroundColor White
    Write-Host "   POST $ServiceUrl/v1/events/user/test_user_unified?event_type=detail-page-view&product_id=product123" -ForegroundColor Gray
    Write-Host "   POST $ServiceUrl/v1/events/user/test_user_unified?event_type=add-to-cart&product_id=product456" -ForegroundColor Gray
    
    Write-Host "`n2. Obtener recomendaciones para ese usuario (excluyendo productos vistos):" -ForegroundColor White
    Write-Host "   GET $ServiceUrl/v1/recommendations/user/test_user_unified" -ForegroundColor Gray
    
    Write-Host "`n3. Verificar las métricas del sistema:" -ForegroundColor White
    Write-Host "   GET $ServiceUrl/v1/metrics" -ForegroundColor Gray
    
    Write-Host "`n4. Probar que la configuración centralizada funciona:" -ForegroundColor White
    Write-Host "   1. Usar diferentes valores para content_weight en las solicitudes de recomendaciones" -ForegroundColor Gray
    Write-Host "   2. Verificar que la exclusión de productos vistos funciona correctamente" -ForegroundColor Gray
    
    Write-Host "`nTodas las peticiones deben incluir la cabecera X-API-Key: 2fed9999056fab6dac5654238f0cae1c" -ForegroundColor Yellow
    Write-Host "======================================================================================" -ForegroundColor Cyan
}

Write-Host "`nProceso de despliegue completado." -ForegroundColor Green
Write-Host "La versión unificada incluye:" -ForegroundColor Yellow
Write-Host "- Configuración centralizada para todas las funcionalidades" -ForegroundColor Yellow
Write-Host "- Sistema de fábricas para crear componentes según configuración" -ForegroundColor Yellow
Write-Host "- Recomendador híbrido unificado con exclusión de productos vistos" -ForegroundColor Yellow
Write-Host "- Sistema de extensiones para añadir funcionalidades de forma modular" -ForegroundColor Yellow
Write-Host "- Framework para facilitar la evolución futura del sistema" -ForegroundColor Yellow
