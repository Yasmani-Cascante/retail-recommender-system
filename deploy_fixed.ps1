# PowerShell script para desplegar la versión corregida del sistema de recomendaciones

# Configuración básica
$ProjectID = "retail-recommendations-449216"
$Region = "us-central1"
$ServiceName = "retail-recommender-fixed"
$ImageName = "gcr.io/$ProjectID/$ServiceName`:latest"
# $DockerfilePath = "Dockerfile.tfidf.shopify.improved"
$DockerfilePath = "Dockerfile.fixed"


# Función para cargar variables secretas
function Load-SecretVars {
    $SecretsFile = ".env.secrets"
    
    if (-not (Test-Path $SecretsFile)) {
        Write-Host "Archivo de secretos ($SecretsFile) no encontrado." -ForegroundColor Yellow
        Write-Host "Creando archivo de secretos de ejemplo..." -ForegroundColor Yellow
        
@"
# Secretos para el sistema de recomendaciones
# Copia este archivo como .env.secrets y actualiza los valores

# Google Cloud Project
GOOGLE_PROJECT_NUMBER=your_project_number
API_KEY=your_api_key

# Shopify
SHOPIFY_SHOP_URL=your_shop_url
SHOPIFY_ACCESS_TOKEN=your_access_token

# Google Cloud Storage
GCS_BUCKET_NAME=your_bucket_name
"@ | Out-File -FilePath "$SecretsFile.example" -Encoding utf8
        
        Write-Host "Por favor, crea el archivo $SecretsFile con tus secretos reales basándote en $SecretsFile.example" -ForegroundColor Red
        return $false
    }
    
    # Cargar variables del archivo .env.secrets
    $script:Secrets = @{}
    Get-Content $SecretsFile | ForEach-Object {
        if (-not [string]::IsNullOrWhiteSpace($_) -and -not $_.StartsWith("#")) {
            $KeyValue = $_ -split '=', 2
            if ($KeyValue.Length -eq 2) {
                $Key = $KeyValue[0].Trim()
                $Value = $KeyValue[1].Trim()
                $script:Secrets[$Key] = $Value
                # Crear variable en el ámbito del script
                Set-Variable -Name $Key -Value $Value -Scope Script
            }
        }
    }
    
    # Verificar que las variables requeridas estén presentes
    $RequiredVars = @(
        "GOOGLE_PROJECT_NUMBER",
        "API_KEY",
        "SHOPIFY_SHOP_URL",
        "SHOPIFY_ACCESS_TOKEN",
        "GCS_BUCKET_NAME"
    )
    
    $MissingVars = @()
    foreach ($Var in $RequiredVars) {
        if (-not $script:Secrets.ContainsKey($Var)) {
            $MissingVars += $Var
        }
    }
    
    if ($MissingVars.Count -gt 0) {
        Write-Host "Faltan las siguientes variables requeridas en ${SecretsFile}:" -ForegroundColor Red
        foreach ($Var in $MissingVars) {
            Write-Host "   - $Var" -ForegroundColor Red
        }
        return $false
    }
    
    Write-Host "Variables secretas cargadas correctamente desde $SecretsFile" -ForegroundColor Green
    return $true
}

function Get-EnvVarsString {
    # Acceder a las variables almacenadas en el ámbito del script
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
        "DEFAULT_CURRENCY=COP"  # Configuración de moneda predeterminada
    )
    
    return $EnvVars -join ","
}

# Inicio del script principal
Write-Host "Iniciando despliegue de la versión corregida del sistema de recomendaciones..." -ForegroundColor Green

# Cargar variables secretas
$SecretsLoaded = Load-SecretVars
if (-not $SecretsLoaded) {
    Write-Host "Error: No se pudieron cargar las variables secretas. Abortando despliegue." -ForegroundColor Red
    exit 1
}

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
    $ApiKey = $script:Secrets.API_KEY
    $Headers = @{
        "X-API-Key" = "$ApiKey"
    }
    
    Write-Host "`nProbando recomendaciones para usuario..." -ForegroundColor Cyan
    try {
        $UserRecommendationUrl = "$ServiceUrl/v1/recommendations/user/test_user_fixed?n=5"
        Write-Host "  Solicitando: $UserRecommendationUrl" -ForegroundColor Gray
        $UserRecommendationResponse = Invoke-RestMethod -Uri $UserRecommendationUrl -Method Get -Headers $Headers
        
        Write-Host "  Éxito: Obtenidas $($UserRecommendationResponse.metadata.total_recommendations) recomendaciones personalizadas" -ForegroundColor Green
        Write-Host "  Tiempo de respuesta: $($UserRecommendationResponse.metadata.took_ms) ms" -ForegroundColor Green
        
        # Mostrar primeras recomendaciones si hay
        if ($UserRecommendationResponse.recommendations -and $UserRecommendationResponse.recommendations.Count -gt 0) {
            Write-Host "`n  Primeras recomendaciones:" -ForegroundColor Cyan
            foreach ($rec in $UserRecommendationResponse.recommendations | Select-Object -First 2) {
                Write-Host "    - $($rec.title) (ID: $($rec.id))" -ForegroundColor Green
            }
        }
    } catch {
        Write-Host "  Error al obtener recomendaciones para usuario: $_" -ForegroundColor Red
        $ErrorDetails = $_.Exception.Response
        if ($ErrorDetails) {
            Write-Host "  Detalles del error: $($ErrorDetails.StatusCode) - $($ErrorDetails.ReasonPhrase)" -ForegroundColor Red
        }
    }

    # Probar evento de compra (para verificar la corrección)
    Write-Host "`nProbando registro de evento de compra..." -ForegroundColor Cyan
    try {
        $EventUrl = "$ServiceUrl/v1/events/user/test_deploy_fix?event_type=purchase-complete&product_id=test_product_1&purchase_amount=99.99"
        Write-Host "  Solicitando: $EventUrl" -ForegroundColor Gray
        $EventResponse = Invoke-RestMethod -Uri $EventUrl -Method Post -Headers $Headers
        
        Write-Host "  Éxito: Evento registrado" -ForegroundColor Green
        if ($EventResponse.currency_used) {
            Write-Host "  Moneda utilizada: $($EventResponse.currency_used)" -ForegroundColor Green
        }
    } catch {
        Write-Host "  Error al registrar evento de compra: $_" -ForegroundColor Red
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
    Write-Host "   GET $ServiceUrl/v1/recommendations/{product_id}" -ForegroundColor Gray
    
    Write-Host "`n3. Registrar eventos de compra (con la corrección):" -ForegroundColor White
    Write-Host "   POST $ServiceUrl/v1/events/user/real_user_123?event_type=purchase-complete&product_id=test_product_1&purchase_amount=29.99" -ForegroundColor Gray
    
    Write-Host "`nTodas las peticiones deben incluir la cabecera X-API-Key: $ApiKey" -ForegroundColor Yellow
    Write-Host "======================================================================================" -ForegroundColor Cyan
}

Write-Host "`nProceso de despliegue completado." -ForegroundColor Green
Write-Host "Esta versión incluye:" -ForegroundColor Yellow
Write-Host "- Corrección del campo currency_code en eventos de compra" -ForegroundColor Yellow
Write-Host "- Corrección de eventos en el generador de eventos" -ForegroundColor Yellow
Write-Host "- Mejoras en el sistema de recomendaciones" -ForegroundColor Yellow
