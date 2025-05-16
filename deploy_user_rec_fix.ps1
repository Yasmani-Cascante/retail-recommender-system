# Script para desplegar la versión corregida del sistema de recomendaciones
# Este script incluye las correcciones para obtener información completa de producto
# en las recomendaciones de usuario.

# Configurar variables
$REGION = "us-central1"
$SERVICE_NAME = "retail-recommender-user-rec-fix"
$IMAGE_NAME = "gcr.io/${env:GOOGLE_PROJECT_NUMBER}/${SERVICE_NAME}:latest"

# Colores para logs
function Write-ColorOutput($ForegroundColor) {
    # Guardar colores actuales
    $fc = $host.UI.RawUI.ForegroundColor
    
    # Establecer los nuevos colores
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    
    # Escribir el contenido restante
    if ($args) {
        Write-Output $args
    }
    
    # Restaurar colores originales
    $host.UI.RawUI.ForegroundColor = $fc
}

function Write-Success($message) {
    Write-ColorOutput Green "[SUCCESS] $message"
}

function Write-Info($message) {
    Write-ColorOutput Cyan "[INFO] $message"
}

function Write-Warning($message) {
    Write-ColorOutput Yellow "[WARNING] $message"
}

function Write-Error($message) {
    Write-ColorOutput Red "[ERROR] $message"
}

# Verificar entorno y variables requeridas
Write-Info "Verificando variables de entorno requeridas..."

if (-not $env:GOOGLE_PROJECT_NUMBER) {
    Write-Error "Variable de entorno GOOGLE_PROJECT_NUMBER no encontrada"
    exit 1
}

# Verificar que gcloud esté instalado
try {
    $gcloudVersion = gcloud --version
    Write-Info "gcloud está instalado: $($gcloudVersion[0])"
} catch {
    Write-Error "gcloud no está instalado o no está en el PATH"
    exit 1
}

# Crear Dockerfile para esta versión
$dockerfileContent = @"
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Exponer puerto
EXPOSE 8080

# Crear directorio para datos y logs
RUN mkdir -p data
RUN mkdir -p logs/product_validation
RUN mkdir -p logs/recommendation_metrics

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# Comando de inicio
CMD exec uvicorn src.api.main_tfidf_shopify_with_metrics:app --host 0.0.0.0 --port ${'$PORT'}
"@

# Guardar Dockerfile
$dockerfileContent | Out-File -FilePath "Dockerfile.user_rec_fix" -Encoding utf8
Write-Success "Dockerfile.user_rec_fix creado"

# Construir la imagen
Write-Info "Construyendo imagen Docker..."
gcloud builds submit --tag $IMAGE_NAME --timeout=15m

if ($LASTEXITCODE -ne 0) {
    Write-Error "Error al construir la imagen Docker"
    exit 1
}

Write-Success "Imagen Docker construida correctamente: $IMAGE_NAME"

# Obtener la URL de servicio actual si existe
$existingService = $null
try {
    $existingService = gcloud run services describe $SERVICE_NAME --region $REGION --format="value(status.url)" 2>$null
} catch {
    # Servicio no existe, lo cual está bien
}

# Desplegar el servicio
Write-Info "Desplegando servicio Cloud Run..."
gcloud run deploy $SERVICE_NAME `
    --image $IMAGE_NAME `
    --region $REGION `
    --platform managed `
    --memory 1Gi `
    --cpu 1 `
    --min-instances 0 `
    --max-instances 10 `
    --port 8080 `
    --timeout 300 `
    --allow-unauthenticated

if ($LASTEXITCODE -ne 0) {
    Write-Error "Error al desplegar el servicio Cloud Run"
    exit 1
}

# Obtener la URL del servicio
$serviceUrl = gcloud run services describe $SERVICE_NAME --region $REGION --format="value(status.url)"
Write-Success "Servicio desplegado correctamente en: $serviceUrl"

# Verificar el despliegue comprobando el endpoint de salud
Write-Info "Verificando el despliegue..."
Start-Sleep -Seconds 10  # Esperar un poco para que el servicio esté listo

try {
    $healthResponse = Invoke-RestMethod -Uri "$serviceUrl/health" -TimeoutSec 30
    Write-Info "Respuesta del health check: $($healthResponse | ConvertTo-Json -Depth 1)"
    
    if ($healthResponse.status -eq "operational") {
        Write-Success "Health check exitoso, el servicio está operativo"
    } else {
        Write-Warning "El servicio está en estado: $($healthResponse.status)"
    }
} catch {
    Write-Error "Error al verificar el health check: $_"
}

# Probar recomendaciones de usuario
Write-Info "Probando recomendaciones de usuario..."
$testUserId = "8831066177845"
$apiKey = $env:API_KEY

if (-not $apiKey) {
    Write-Warning "Variable de entorno API_KEY no encontrada, usando valor por defecto"
    $apiKey = "2fed9999056fab6dac5654238f0cae1c"  # Valor por defecto
}

try {
    $recommendationsResponse = Invoke-RestMethod -Uri "$serviceUrl/v1/recommendations/user/$testUserId`?n=5" -Headers @{"X-API-Key" = $apiKey} -TimeoutSec 60
    
    Write-Info "Respuesta de recomendaciones:"
    Write-Output ($recommendationsResponse | ConvertTo-Json -Depth 3)
    
    # Verificar si las recomendaciones tienen información completa
    $hasCompleteInfo = $true
    foreach ($rec in $recommendationsResponse.recommendations) {
        if ($rec.title -eq "Producto" -or [string]::IsNullOrEmpty($rec.title) -or $rec.title -eq $null) {
            $hasCompleteInfo = $false
            break
        }
    }
    
    if ($hasCompleteInfo) {
        Write-Success "¡Las recomendaciones contienen información completa de productos!"
    } else {
        Write-Warning "Las recomendaciones aún no contienen información completa de productos"
        Write-Warning "Revisa los logs del servicio para más detalles"
    }
} catch {
    Write-Error "Error al probar recomendaciones de usuario: $_"
}

Write-Success "Proceso de despliegue completado"
Write-Info "URL del servicio: $serviceUrl"
Write-Info "Para ver los logs del servicio: gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME' --limit 50"
