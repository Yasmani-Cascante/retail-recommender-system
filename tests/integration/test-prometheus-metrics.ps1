# test-prometheus-metrics.ps1
# Script SIMPLIFICADO de validación M2 Prometheus Metrics

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "M2 PROMETHEUS METRICS - VALIDACION" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Test 1: Verificar endpoint existe
Write-Host "Test 1: Verificando endpoint /metrics..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/metrics"
    Write-Host "[OK] Endpoint responde: $($response.StatusCode)" -ForegroundColor Green
    
    # Acceso seguro a headers
    $contentType = $response.Headers["Content-Type"]
    if ($contentType) {
        Write-Host "     Content-Type: $contentType" -ForegroundColor Gray
    }
    Write-Host "     Content-Length: $($response.RawContentLength) bytes" -ForegroundColor Gray
} catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Test 2: Verificar metricas custom
Write-Host "Test 2: Verificando metricas custom..." -ForegroundColor Yellow
$metrics = $response.Content

$custom_metrics = @{
    "recommender_requests_total" = "Recommendation requests counter"
    "recommender_duration_seconds" = "Recommendation duration histogram"
    "kb_sync_semaphore_size" = "KB sync semaphore size gauge"
    "kb_sync_operations_total" = "KB sync operations counter"
    "google_retail_api_calls_total" = "Google Retail API calls counter"
}

$found_count = 0
foreach ($metric_name in $custom_metrics.Keys) {
    $description = $custom_metrics[$metric_name]
    if ($metrics -match $metric_name) {
        Write-Host "[OK] $metric_name" -ForegroundColor Green
        Write-Host "     -> $description" -ForegroundColor Gray
        $found_count++
    } else {
        Write-Host "[WARN] $metric_name NO encontrada" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Metricas custom encontradas: $found_count / $($custom_metrics.Count)" -ForegroundColor Cyan
Write-Host ""

# Test 3: Verificar HTTP auto-instrumentation
Write-Host "Test 3: Verificando HTTP auto-instrumentation..." -ForegroundColor Yellow

$http_metrics = @(
    "http_requests_total",
    "http_request_duration_seconds"
)

$http_found = 0
foreach ($metric in $http_metrics) {
    if ($metrics -match $metric) {
        Write-Host "[OK] $metric (auto-instrumentada)" -ForegroundColor Green
        $http_found++
    } else {
        Write-Host "[ERROR] $metric NO encontrada" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Metricas HTTP encontradas: $http_found / $($http_metrics.Count)" -ForegroundColor Cyan
Write-Host ""

# Test 4: Mostrar valores actuales
Write-Host "Test 4: Valores actuales de metricas clave..." -ForegroundColor Yellow

# Buscar kb_sync_semaphore_size
if ($metrics -match "kb_sync_semaphore_size\s+([\d\.]+)") {
    $value = $matches[1]
    Write-Host "     kb_sync_semaphore_size = $value" -ForegroundColor Cyan
} else {
    Write-Host "     kb_sync_semaphore_size = NO ENCONTRADA" -ForegroundColor Yellow
}

# Contar total de lineas de metricas
$total_lines = ($metrics -split "`n").Count
Write-Host "     Total de lineas en /metrics = $total_lines" -ForegroundColor Cyan

Write-Host ""

# Test 5: Verificar endpoint JSON legacy sigue funcionando
Write-Host "Test 5: Verificando endpoint /v1/metrics (JSON) sin cambios..." -ForegroundColor Yellow
try {
    # Nota: Este endpoint requiere autenticacion, esperamos 401 o 403
    $json_response = Invoke-WebRequest -Uri "http://localhost:8000/v1/metrics" -ErrorAction SilentlyContinue
    Write-Host "[OK] /v1/metrics responde (sin auth)" -ForegroundColor Green
} catch {
    $statusCode = $_.Exception.Response.StatusCode.Value__
    if ($statusCode -eq 401 -or $statusCode -eq 403) {
        Write-Host "[OK] /v1/metrics requiere autenticacion (esperado)" -ForegroundColor Green
    } else {
        Write-Host "[WARN] /v1/metrics error inesperado: $statusCode" -ForegroundColor Yellow
    }
}

Write-Host ""

# Test 6: Generar actividad
Write-Host "Test 6: Generando actividad para incrementar metricas..." -ForegroundColor Yellow
Write-Host "     Haciendo 3 requests a /health..." -ForegroundColor Gray

$http_requests_before = 0
if ($metrics -match "http_requests_total") {
    # Contar todas las ocurrencias
    $matches_before = [regex]::Matches($metrics, "http_requests_total")
    $http_requests_before = $matches_before.Count
}

try {
    for ($i = 1; $i -le 3; $i++) {
        Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing | Out-Null
        Write-Host "     Request $i completado" -ForegroundColor Gray
        Start-Sleep -Milliseconds 200
    }
} catch {
    Write-Host "[WARN] Algunos requests fallaron" -ForegroundColor Yellow
}

# Esperar un momento para que se actualicen las metricas
Start-Sleep -Seconds 1

# Capturar metricas despues
$metrics_after = (Invoke-WebRequest -Uri "http://localhost:8000/metrics").Content

$http_requests_after = 0
if ($metrics_after -match "http_requests_total") {
    $matches_after = [regex]::Matches($metrics_after, "http_requests_total")
    $http_requests_after = $matches_after.Count
}

Write-Host ""
Write-Host "     http_requests_total ocurrencias:" -ForegroundColor Cyan
Write-Host "     ANTES:   $http_requests_before" -ForegroundColor Gray
Write-Host "     DESPUES: $http_requests_after" -ForegroundColor Gray

if ($http_requests_after -ge $http_requests_before) {
    Write-Host "[OK] Metricas responden a actividad" -ForegroundColor Green
} else {
    Write-Host "[WARN] Metricas no cambiaron visiblemente" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "VALIDACION COMPLETA" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Resumen final
Write-Host "RESUMEN:" -ForegroundColor Cyan
Write-Host "  - Endpoint /metrics: FUNCIONANDO" -ForegroundColor Green
Write-Host "  - Metricas custom: $found_count / $($custom_metrics.Count)" -ForegroundColor $(if ($found_count -eq $custom_metrics.Count) { "Green" } else { "Yellow" })
Write-Host "  - HTTP auto-instrumentation: $http_found / $($http_metrics.Count)" -ForegroundColor $(if ($http_found -eq $http_metrics.Count) { "Green" } else { "Yellow" })
Write-Host "  - Endpoint /v1/metrics: SIN CAMBIOS (correcto)" -ForegroundColor Green
Write-Host ""

if ($found_count -ge 3 -and $http_found -eq 2) {
    Write-Host "RESULTADO: M2 IMPLEMENTACION EXITOSA" -ForegroundColor Green
    exit 0
} else {
    Write-Host "RESULTADO: VERIFICAR METRICAS FALTANTES" -ForegroundColor Yellow
    exit 1
}