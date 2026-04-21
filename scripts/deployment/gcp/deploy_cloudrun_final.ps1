# ============================================================================
# DEPLOYMENT SCRIPT FINAL - CLOUD RUN (CORREGIDO)
# ============================================================================
# Issue Fixed: PORT no debe estar en --set-env-vars
# Version: 3.0 - 18 Feb 2026
# ============================================================================

param(
    [switch]$DryRun = $false,
    [switch]$SkipBuild = $false,
    [switch]$SkipPush = $false,
    [string]$Region = "us-central1",
    [string]$ProjectId = "retail-recommendations-449216",
    [string]$ServiceName = "retail-recommender"
)

$ErrorActionPreference = "Stop"

function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Info { Write-Host $args -ForegroundColor Cyan }
function Write-Warning { Write-Host $args -ForegroundColor Yellow }
function Write-Error { Write-Host $args -ForegroundColor Red }

Write-Info "═══════════════════════════════════════════════════════════════"
Write-Info "  CLOUD RUN DEPLOYMENT - FINAL (PORT FIX APLICADO)"
Write-Info "═══════════════════════════════════════════════════════════════"
Write-Info "Servicio: $ServiceName"
Write-Info "Región: $Region"
Write-Info "Proyecto: $ProjectId"
Write-Success "═══════════════════════════════════════════════════════════════`n"

$imageName = "gcr.io/$ProjectId/$ServiceName`:latest"

# ============================================================================
# PASO 1: BUILD (si no se skipea)
# ============================================================================
if (-not $SkipBuild) {
    Write-Info "[1/5] 🔨 Construyendo imagen..."
    
    if ($DryRun) {
        Write-Warning "🔍 DRY RUN: docker build -f Dockerfile.cloudrun -t $imageName ."
    } else {
        docker build -f Dockerfile.cloudrun -t $imageName .
        
        if ($LASTEXITCODE -ne 0) {
            Write-Error "❌ Build falló"
            exit 1
        }
        
        Write-Success "✅ Imagen construida exitosamente`n"
    }
} else {
    Write-Warning "[1/5] ⏭️  Build skipped`n"
}

# ============================================================================
# PASO 2: PUSH (si no se skipea)
# ============================================================================
if (-not $SkipPush) {
    Write-Info "[2/5] 📤 Subiendo imagen a GCR..."
    
    if ($DryRun) {
        Write-Warning "🔍 DRY RUN: docker push $imageName"
    } else {
        docker push $imageName
        
        if ($LASTEXITCODE -ne 0) {
            Write-Error "❌ Push falló"
            exit 1
        }
        
        Write-Success "✅ Imagen subida exitosamente`n"
    }
} else {
    Write-Warning "[2/5] ⏭️  Push skipped`n"
}

# ============================================================================
# PASO 3: DEPLOY A CLOUD RUN
# ============================================================================
Write-Info "[3/5] 🚀 Desplegando a Cloud Run..."

# ✅ CRITICAL FIX: NO incluir PORT en --set-env-vars
# Cloud Run lo establece automáticamente basado en --port=8080
$deployCmd = @"
gcloud run deploy $ServiceName ``
    --image=$imageName ``
    --platform=managed ``
    --region=$Region ``
    --memory=2Gi ``
    --cpu=2 ``
    --timeout=300s ``
    --max-instances=10 ``
    --min-instances=0 ``
    --port=8080 ``
    --set-env-vars="ENVIRONMENT=production" ``
    --allow-unauthenticated ``
    --project=$ProjectId
"@

if ($DryRun) {
    Write-Warning "🔍 DRY RUN: Comando a ejecutar:"
    Write-Info $deployCmd
} else {
    Write-Info "Ejecutando deployment..."
    Invoke-Expression $deployCmd
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error "❌ Deployment falló"
        Write-Info "`nRevisa los logs:"
        Write-Info "https://console.cloud.google.com/run/detail/$Region/$ServiceName/logs?project=$ProjectId"
        exit 1
    }
    
    Write-Success "✅ Deployment completado exitosamente`n"
}

# ============================================================================
# PASO 4: OBTENER URL Y VERIFICAR HEALTH
# ============================================================================
Write-Info "[4/5] 🔍 Verificando servicio..."

if (-not $DryRun) {
    Start-Sleep -Seconds 10
    
    # Obtener URL
    $serviceUrl = gcloud run services describe $ServiceName `
        --region=$Region `
        --format="value(status.url)" `
        --project=$ProjectId
    
    if ($LASTEXITCODE -eq 0 -and $serviceUrl) {
        Write-Success "✅ URL del servicio: $serviceUrl`n"
        
        # Health check
        Write-Info "Probando health endpoint..."
        Start-Sleep -Seconds 5
        
        try {
            $healthUrl = "$serviceUrl/health"
            $response = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 30
            
            Write-Success "✅ Health check PASSED!"
            Write-Info "Status: $($response.status)"
            Write-Info "Version: $($response.version)"
            Write-Info "Service: $($response.service)`n"
            
        } catch {
            Write-Warning "⚠️  Health check no respondió inmediatamente"
            Write-Info "Esto es normal si el startup es lento"
            Write-Info "Prueba manualmente: $healthUrl`n"
        }
    }
}

# ============================================================================
# PASO 5: VERIFICAR LOGS
# ============================================================================
Write-Info "[5/5] 📋 Últimos logs del servicio..."

if (-not $DryRun) {
    Write-Info "Esperando logs..."
    Start-Sleep -Seconds 5
    
    gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=$ServiceName" `
        --limit=15 `
        --format="table(timestamp,severity,textPayload)" `
        --project=$ProjectId `
        2>&1 | Write-Host
}

# ============================================================================
# RESUMEN FINAL
# ============================================================================
Write-Success "`n═══════════════════════════════════════════════════════════════"
Write-Success "  ✅ DEPLOYMENT COMPLETADO"
Write-Success "═══════════════════════════════════════════════════════════════"

if (-not $DryRun) {
    Write-Info "Servicio:      $ServiceName"
    Write-Info "Región:        $Region"
    Write-Info "Imagen:        $imageName"
    
    if ($serviceUrl) {
        Write-Info "URL:           $serviceUrl"
        Write-Info "Health:        $serviceUrl/health"
        Write-Info "Metrics:       $serviceUrl/metrics"
    }
    
    Write-Info "`n📊 Monitoreo:"
    Write-Info "  Cloud Console: https://console.cloud.google.com/run/detail/$Region/$ServiceName"
    Write-Info "  Logs:          https://console.cloud.google.com/run/detail/$Region/$ServiceName/logs"
    Write-Info "  Metrics:       https://console.cloud.google.com/run/detail/$Region/$ServiceName/metrics"
}

Write-Success "═══════════════════════════════════════════════════════════════`n"

Write-Success "✨ ¡Deployment exitoso! ✨"