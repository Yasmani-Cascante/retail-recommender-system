# PowerShell script para desplegar la version con Redis Labs del sistema de recomendaciones

# Configuracion basica
$ProjectID = "retail-recommendations-449216"
$Region = "us-central1"
$ServiceName = "retail-recommender-redis-labs"
$ImageName = "gcr.io/$ProjectID/$ServiceName`:latest"
$DockerfilePath = "Dockerfile.fixed"

# Funcion para cargar variables secretas
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

# Redis Labs Configuration
REDIS_HOST=redis-14272.c259.us-central1-2.gce.redns.redis-cloud.com
REDIS_PORT=14272
REDIS_PASSWORD=34rleeRxTmFYqBZpSA5UoDP71bHEq6zO
REDIS_USERNAME=default
REDIS_SSL=true
CACHE_TTL=86400
CACHE_PREFIX=product:
CACHE_ENABLE_BACKGROUND_TASKS=true
"@ | Out-File -FilePath "$SecretsFile.example" -Encoding utf8
        
        Write-Host "Por favor, crea el archivo $SecretsFile con tus secretos reales basandote en $SecretsFile.example" -ForegroundColor Red
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
                Set-Variable -Name $Key -Value $Value -Scope Script
            }
        }
    }
    
    # Verificar que las variables requeridas esten presentes
    $RequiredVars = @(
        "GOOGLE_PROJECT_NUMBER",
        "API_KEY",
        "SHOPIFY_SHOP_URL",
        "SHOPIFY_ACCESS_TOKEN",
        "GCS_BUCKET_NAME",
        "REDIS_HOST",
        "REDIS_PORT",
        "REDIS_PASSWORD",
        "REDIS_USERNAME",
        "REDIS_SSL"
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

# Inicio del script principal
Write-Host "Iniciando despliegue de la version con Redis Labs del sistema de recomendaciones..." -ForegroundColor Green

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

# Verificar configuracion de GCloud
Write-Host "Verificando configuracion de GCloud..." -ForegroundColor Yellow
$CurrentProject = gcloud config get-value project
Write-Host "Proyecto actual: $CurrentProject" -ForegroundColor Cyan

# Verificar si necesitamos configurar el proyecto
if ($CurrentProject -ne $ProjectID) {
    Write-Host "Configurando proyecto: $ProjectID" -ForegroundColor Yellow
    gcloud config set project $ProjectID
} else {
    Write-Host "Ya esta configurado el proyecto correcto: $ProjectID" -ForegroundColor Green
}

# Configurar region
Write-Host "Configurando region: $Region" -ForegroundColor Yellow
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

# Pruebas del servicio desplegado
if ($ServiceUrl) {
    Write-Host "Esperando 30 segundos para que el servicio se inicialice..." -ForegroundColor Yellow
    Start-Sleep -Seconds 30

    Write-Host "Verificando estado del servicio..." -ForegroundColor Yellow
    try {
        $Response = Invoke-RestMethod -Uri "$ServiceUrl/health" -Method Get -TimeoutSec 30
        Write-Host "Estado del servicio: $($Response.status)" -ForegroundColor Green
        Write-Host "Tiempo de funcionamiento: $($Response.uptime_seconds) segundos" -ForegroundColor Green
        
        if ($Response.components -and $Response.components.recommender) {
            Write-Host "Estado del recomendador: $($Response.components.recommender.status)" -ForegroundColor Green
            Write-Host "Productos cargados: $($Response.components.recommender.products_count)" -ForegroundColor Green
        }
        
        if ($Response.components -and $Response.components.cache) {
            $CacheStatus = $Response.components.cache
            Write-Host ""
            Write-Host "Estado del sistema de cache:" -ForegroundColor Cyan
            Write-Host "  Status: $($CacheStatus.status)" -ForegroundColor Green
            Write-Host "  Conexion Redis: $($CacheStatus.redis_connection)" -ForegroundColor Green
            Write-Host "  Hit ratio: $($CacheStatus.hit_ratio)" -ForegroundColor Green
            
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
        Write-Host "El servicio podria necesitar mas tiempo para inicializarse completamente." -ForegroundColor Yellow
    }

    # Probar recomendaciones de usuario
    $ApiKey = $script:Secrets.API_KEY
    $Headers = @{
        "X-API-Key" = "$ApiKey"
    }
    
    Write-Host ""
    Write-Host "Probando recomendaciones para usuario..." -ForegroundColor Cyan
    try {
        $UserRecommendationUrl = "$ServiceUrl/v1/recommendations/user/test_user_redis?n=5"
        Write-Host "  Solicitando: $UserRecommendationUrl" -ForegroundColor Gray
        $UserRecommendationResponse = Invoke-RestMethod -Uri $UserRecommendationUrl -Method Get -Headers $Headers
        
        Write-Host "  Exito: Obtenidas $($UserRecommendationResponse.metadata.total_recommendations) recomendaciones personalizadas" -ForegroundColor Green
        Write-Host "  Tiempo de respuesta: $($UserRecommendationResponse.metadata.took_ms) ms" -ForegroundColor Green
        
        if ($UserRecommendationResponse.recommendations -and $UserRecommendationResponse.recommendations.Count -gt 0) {
            Write-Host ""
            Write-Host "  Primeras recomendaciones:" -ForegroundColor Cyan
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

    # CORRECCION: Probar registrar un evento de usuario con query parameters
    Write-Host ""
    Write-Host "Probando registro de eventos de usuario..." -ForegroundColor Cyan
    try {
        # CORREGIDO: Enviar parametros como query parameters, no en el body
        $EventUrl = "$ServiceUrl/v1/events/user/test_user_redis?event_type=detail-page-view&product_id=product123"
        
        Write-Host "  Registrando evento detail-page-view para test_user_redis..." -ForegroundColor Gray
        Write-Host "  URL: $EventUrl" -ForegroundColor Gray
        
        # Enviar como POST pero sin body, ya que los parametros estan en la URL
        $EventResponse = Invoke-RestMethod -Uri $EventUrl -Method Post -Headers $Headers
        
        Write-Host "  Evento registrado correctamente" -ForegroundColor Green
        
        # Mostrar respuesta si esta disponible
        if ($EventResponse) {
            Write-Host "  Respuesta: $($EventResponse | ConvertTo-Json -Compress)" -ForegroundColor Gray
        }
        
    } catch {
        Write-Host "  Error al registrar evento: $_" -ForegroundColor Red
        $ErrorDetails = $_.Exception.Response
        if ($ErrorDetails) {
            Write-Host "  Detalles del error: $($ErrorDetails.StatusCode) - $($ErrorDetails.ReasonPhrase)" -ForegroundColor Red
        }
        
        # Mostrar el cuerpo del error si esta disponible
        if ($_.Exception.Response) {
            try {
                $ErrorBody = $_.Exception.Response.GetResponseStream()
                if ($ErrorBody) {
                    $Reader = New-Object System.IO.StreamReader($ErrorBody)
                    $ErrorContent = $Reader.ReadToEnd()
                    Write-Host "  Contenido del error: $ErrorContent" -ForegroundColor Red
                }
            } catch {
                Write-Host "  No se pudo leer el contenido del error" -ForegroundColor Yellow
            }
        }
    }

    # Mostrar instrucciones para pruebas manuales
    Write-Host ""
    Write-Host "======================================================================================" -ForegroundColor Cyan
    Write-Host "              INSTRUCCIONES PARA PROBAR EL SISTEMA DE CACHE CON REDIS LABS" -ForegroundColor Cyan
    Write-Host "======================================================================================" -ForegroundColor Cyan
    
    Write-Host ""
    Write-Host "1. Verificar el estado del sistema de cache:" -ForegroundColor White
    Write-Host "   GET $ServiceUrl/health" -ForegroundColor Gray
    Write-Host "   (Verificar que 'components.cache.redis_connection' sea 'connected')" -ForegroundColor Gray
    
    Write-Host ""
    Write-Host "2. Solicitar recomendaciones multiples veces para verificar cache:" -ForegroundColor White
    Write-Host "   GET $ServiceUrl/v1/recommendations/user/test_user_redis" -ForegroundColor Gray
    Write-Host "   (Las primeras solicitudes pueden ser mas lentas, luego mas rapidas debido a la cache)" -ForegroundColor Gray
    
    Write-Host ""
    Write-Host "3. Registrar eventos para ver el impacto en la cache:" -ForegroundColor White
    Write-Host "   POST $ServiceUrl/v1/events/user/test_user_redis?event_type=detail-page-view&product_id=product123" -ForegroundColor Gray
    
    Write-Host ""
    Write-Host "Todas las peticiones deben incluir la cabecera X-API-Key: $ApiKey" -ForegroundColor Yellow
    Write-Host "======================================================================================" -ForegroundColor Cyan

} else {
    Write-Host "No se pudo obtener la URL del servicio. Verifica el despliegue manualmente." -ForegroundColor Red
}

Write-Host ""
Write-Host "Proceso de despliegue completado." -ForegroundColor Green
Write-Host "Esta version incluye integracion con Redis Labs para cache distribuida." -ForegroundColor Yellow
