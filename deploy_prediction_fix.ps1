# PowerShell script para desplegar la versión con corrección del procesamiento de predicciones

# Importar funciones comunes
. .\deploy_common.ps1

Write-Host "Iniciando despliegue de la versión corregida con mejoras en el procesamiento de predicciones..." -ForegroundColor Green

# Cargar variables secretas
$SecretsLoaded = Load-SecretVariables
if (-not $SecretsLoaded) {
    Write-Host "Error: No se pudieron cargar las variables secretas. Abortando despliegue." -ForegroundColor Red
    exit 1
}

# Configuración
$ProjectID = "retail-recommendations-449216"
$Region = "us-central1"
$ServiceName = "retail-recommender-fixed"
$ImageName = "gcr.io/$ProjectID/$ServiceName`:latest"
$DockerfilePath = "Dockerfile.fixed"

# Verificar que el Dockerfile existe
if (-not (Test-Path $DockerfilePath)) {
    Write-Host "Error: El archivo $DockerfilePath no existe." -ForegroundColor Red
    exit 1
}

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
    docker build -t $ImageName -f $DockerfilePath .
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
# Generar string de variables de entorno
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

    # Probar recomendaciones de usuario
    $Headers = @{
        "X-API-Key" = "$API_KEY"
    }
    
    Write-Host "`nProbando recomendaciones para usuario..." -ForegroundColor Cyan
    try {
        $UserRecommendationUrl = "$ServiceUrl/v1/recommendations/user/test_user_fixed?n=5"
        Write-Host "  Solicitando: $UserRecommendationUrl" -ForegroundColor Gray
        $UserRecommendationResponse = Invoke-RestMethod -Uri $UserRecommendationUrl -Method Get -Headers $Headers
        
        Write-Host "  ✅ Éxito: Obtenidas $($UserRecommendationResponse.metadata.total_recommendations) recomendaciones personalizadas" -ForegroundColor Green
        Write-Host "  Tiempo de respuesta: $($UserRecommendationResponse.metadata.took_ms) ms" -ForegroundColor Green
        
        # Mostrar primeras recomendaciones si hay
        if ($UserRecommendationResponse.recommendations -and $UserRecommendationResponse.recommendations.Count -gt 0) {
            Write-Host "`n  Primeras recomendaciones:" -ForegroundColor Cyan
            foreach ($rec in $UserRecommendationResponse.recommendations | Select-Object -First 2) {
                Write-Host "    - $($rec.title) (ID: $($rec.id))" -ForegroundColor Green
            }
        }
    } catch {
        Write-Host "  ❌ Error al obtener recomendaciones para usuario: $_" -ForegroundColor Red
        $ErrorDetails = $_.Exception.Response
        if ($ErrorDetails) {
            Write-Host "  Detalles del error: $($ErrorDetails.StatusCode) - $($ErrorDetails.ReasonPhrase)" -ForegroundColor Red
        }
    }

    # Mostrar instrucciones para pruebas manuales
    Write-Host "`n======================================================================================" -ForegroundColor Cyan
    Write-Host "                  INSTRUCCIONES PARA PROBAR LAS FUNCIONALIDADES" -ForegroundColor Cyan
    Write-Host "=======================================================================================" -ForegroundColor Cyan
    
    Write-Host "`n1. Obtener recomendaciones para un usuario:" -ForegroundColor White
    Write-Host "   GET $ServiceUrl/v1/recommendations/user/test_user_123" -ForegroundColor Gray
    
    Write-Host "`n2. Obtener recomendaciones basadas en un producto:" -ForegroundColor White
    Write-Host "   GET $ServiceUrl/v1/recommendations/product1" -ForegroundColor Gray
    
    Write-Host "`n3. Registrar eventos para mejorar recomendaciones:" -ForegroundColor White
    Write-Host "   POST $ServiceUrl/v1/events/user/real_user_123?event_type=detail-page-view&product_id=product1" -ForegroundColor Gray
    
    Write-Host "`nTodas las peticiones deben incluir la cabecera X-API-Key: 2fed9999056fab6dac5654238f0cae1c" -ForegroundColor Yellow
    Write-Host "======================================================================================" -ForegroundColor Cyan
}

Write-Host "`nProceso de despliegue completado." -ForegroundColor Green
Write-Host "Esta versión incluye:" -ForegroundColor Yellow
Write-Host "- Corrección en el procesamiento de predicciones para recomendaciones de usuarios" -ForegroundColor Yellow
Write-Host "- Análisis detallado de la estructura de respuesta de Google Cloud Retail API" -ForegroundColor Yellow
Write-Host "- Manejo más robusto de diferentes formatos de respuesta" -ForegroundColor Yellow