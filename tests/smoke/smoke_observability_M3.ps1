# =============================================================================
# SMOKE TEST -- Validacion Pipeline de Observabilidad M3
# Version  : 1.1 -- Fix cold start handling en B1 + http_requests_total lazy en B3
# Encoding : ASCII puro (compatible con Windows PowerShell 5.1+)
# Fecha    : 12-03-2026
#
# PROPOSITO:
#   Verificar que el pipeline completo de observabilidad funciona end-to-end:
#
#   HTTP Request (este script)
#      |
#      v
#   Cloud Run FastAPI  --> Prometheus Registry (en memoria)
#      |                        |
#      v                        v (cada 60s)
#   Response (validada)    GCP Cloud Monitoring API
#                               |
#                               v
#                          Alert Policies (evaluadas cada 60s)
#
# BLOQUES:
#   B1  -- Health check basico (servicio activo)
#   B2  -- Endpoint /metrics accesible y con datos
#   B3  -- Validar metricas clave pre-existentes en /metrics
#   B4  -- Generar trafico real (recomendaciones)
#   B5  -- Validar que contadores Prometheus se incrementaron
#   B6  -- Verificar logs de exportacion a GCP (ultimos 2 min)
#   B7  -- Instrucciones de verificacion manual en GCP Console
#
# PREREQUISITOS:
#   - gcloud CLI instalado y autenticado (gcloud auth login)
#   - Acceso al proyecto retail-recommendations-449216
#   - curl disponible (incluido en Windows 10+)
#
# USO:
#   .\smoke_observability_M3.ps1
#   .\smoke_observability_M3.ps1 -Verbose    # mas detalle en /metrics output
# =============================================================================

param(
    [switch]$Verbose  # Si se activa, imprime el output completo de /metrics
)

# ---------------------------------------------------------------------------
# CONFIGURACION
# ---------------------------------------------------------------------------
$BASE_URL   = "https://retail-recommender-lzf2y6pspa-uc.a.run.app"
$GCP_PROJ   = "retail-recommendations-449216"
$SVC_NAME   = "retail-recommender"
$REGION     = "us-central1"

# Leer API_KEY del .env (mismo patron que smoke_test_neon_V2.3.ps1)
$ENV_FILE = "C:\Users\yasma\Desktop\retail-recommender-system\.env"
$API_KEY  = ""
if (Test-Path $ENV_FILE) {
    $raw = Get-Content $ENV_FILE -Raw
    if ($raw -match '(?m)^API_KEY\s*=\s*"?([^"\r\n]+)"?') {
        $API_KEY = $matches[1].Trim()
    }
}
if ($API_KEY -eq "") {
    Write-Host "  [FATAL] No se pudo leer API_KEY del .env -- abortando" -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

# Contadores globales de resultados
$script:PASS = 0
$script:WARN = 0
$script:FAIL = 0
$script:SKIP = 0

function Write-Header($text) {
    Write-Host ""
    Write-Host "=" * 70 -ForegroundColor Cyan
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host "=" * 70 -ForegroundColor Cyan
}

function Write-Step($text) {
    Write-Host ""
    Write-Host "  >> $text" -ForegroundColor Yellow
}

function Write-Pass($text) {
    Write-Host "     [PASS] $text" -ForegroundColor Green
    $script:PASS++
}

function Write-Warn($text) {
    Write-Host "     [WARN] $text" -ForegroundColor Yellow
    $script:WARN++
}

function Write-Fail($text) {
    Write-Host "     [FAIL] $text" -ForegroundColor Red
    $script:FAIL++
}

function Write-Skip($text) {
    Write-Host "     [SKIP] $text" -ForegroundColor Gray
    $script:SKIP++
}

function Write-Info($text) {
    Write-Host "     [INFO] $text" -ForegroundColor White
}

# Invoke-API: realiza una llamada HTTP y devuelve hashtable con code, body, ms
function Invoke-API {
    param(
        [string]$Url,
        [string]$Method = "GET",
        [int]$TimeoutSec = 20
    )
    $result = @{ code = 0; body = ""; ms = 0 }
    try {
        $sw    = [System.Diagnostics.Stopwatch]::StartNew()
        $resp  = Invoke-WebRequest -Uri $Url -Method $Method `
                     -Headers @{ "X-API-Key" = $API_KEY } `
                     -TimeoutSec $TimeoutSec -UseBasicParsing -ErrorAction Stop
        $sw.Stop()
        $result.code = [int]$resp.StatusCode
        $result.body = $resp.Content
        $result.ms   = $sw.ElapsedMilliseconds
    }
    catch [System.Net.WebException] {
        $sw.Stop()
        $result.ms = $sw.ElapsedMilliseconds
        if ($_.Exception.Response) {
            $result.code = [int]$_.Exception.Response.StatusCode
        }
        $result.body = $_.Exception.Message
    }
    catch {
        $result.body = $_.Exception.Message
    }
    return $result
}

# Invoke-API-Slow: igual pero con timeout extendido (para endpoints lentos)
function Invoke-API-Slow {
    param([string]$Url, [string]$Method = "GET")
    return Invoke-API -Url $Url -Method $Method -TimeoutSec 45
}

# Extrae el valor numerico de una metrica Prometheus del texto de /metrics
# Ejemplo: Get-MetricValue "recommender_requests_total{market=" $metricsBody
function Get-MetricValue {
    param([string]$MetricPrefix, [string]$Body)
    # Busca la primera linea que empieza con el prefijo (no comentario)
    $lines = $Body -split "`n"
    foreach ($line in $lines) {
        if ($line.StartsWith($MetricPrefix) -and -not $line.StartsWith("#")) {
            # El valor es el ultimo token de la linea
            $parts = $line.Trim() -split "\s+"
            if ($parts.Length -ge 2) {
                return [double]$parts[-1]
            }
        }
    }
    return $null  # No encontrado
}

# ---------------------------------------------------------------------------
# INICIO
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "############################################################" -ForegroundColor Magenta
Write-Host "#  SMOKE TEST -- Pipeline Observabilidad M3                #" -ForegroundColor Magenta
Write-Host "#  Retail Recommender System v2.1.0                        #" -ForegroundColor Magenta
Write-Host "#  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')                              #" -ForegroundColor Magenta
Write-Host "############################################################" -ForegroundColor Magenta
Write-Info "Target: $BASE_URL"
Write-Info "GCP Project: $GCP_PROJ"

# ===========================================================================
# BLOQUE 1 -- Health Check basico
# ===========================================================================
Write-Header "BLOQUE 1 -- Health Check (servicio activo)"

# Cloud Run escala a cero -- el primer request puede tardar 15-25s (cold start).
# Reintentamos hasta 2 veces con timeout extendido antes de declarar FAIL.
Write-Step "GET /health (con retry para cold start)"
$healthPassed = $false
for ($attempt = 1; $attempt -le 2; $attempt++) {
    if ($attempt -eq 1) {
        Write-Info "  Intento $attempt/2 (timeout 25s -- cold start puede tomar ~20s)..."
        $r = Invoke-API -Url "$BASE_URL/health" -TimeoutSec 25
    } else {
        Write-Info "  Intento $attempt/2 (timeout 30s -- reintento post cold start)..."
        $r = Invoke-API -Url "$BASE_URL/health" -TimeoutSec 30
    }
    if ($r.code -eq 200) {
        if ($attempt -gt 1) {
            Write-Pass "Servicio activo tras cold start (HTTP 200) en $($r.ms)ms (intento $attempt)"
        } else {
            Write-Pass "Servicio activo (HTTP 200) en $($r.ms)ms"
        }
        # Inspeccionar el body para detectar degradacion
        try {
            $health = $r.body | ConvertFrom-Json
            if ($health.status -eq "healthy" -or $health.status -eq "ok") {
                Write-Pass "Status = '$($health.status)'"
            } elseif ($health.status -eq "degraded") {
                Write-Warn "Status = 'degraded' -- alguna dependencia tiene problemas"
                Write-Info "Body: $($r.body.Substring(0, [Math]::Min(300, $r.body.Length)))"
            } else {
                Write-Warn "Status inesperado: '$($health.status)'"
            }
        } catch {
            Write-Warn "No se pudo parsear JSON del health check"
        }
        $healthPassed = $true
        break
    } elseif ($r.code -eq 0) {
        if ($attempt -lt 2) {
            Write-Info "  Timeout en intento $attempt -- Cloud Run cold start en progreso, reintentando..."
            Start-Sleep -Seconds 5
        } else {
            Write-Fail "Timeout tras $attempt intentos ($($r.ms)ms) -- servicio no responde"
            Write-Info "ACCION: Verificar en GCP Console > Cloud Run si el servicio esta desplegado"
        }
    } else {
        Write-Fail "HTTP $($r.code) ($($r.ms)ms)"
        break
    }
}

# ===========================================================================
# BLOQUE 2 -- Endpoint /metrics accesible
# ===========================================================================
Write-Header "BLOQUE 2 -- Endpoint /metrics (Prometheus registry)"

Write-Step "GET /metrics"
$rMetrics = Invoke-API "$BASE_URL/metrics"
if ($rMetrics.code -eq 200) {
    $lineCount = ($rMetrics.body -split "`n").Count
    Write-Pass "Endpoint /metrics accesible (HTTP 200) -- $lineCount lineas"

    # Verificar que tiene el formato Prometheus esperado
    if ($rMetrics.body -match "^# HELP") {
        Write-Pass "Formato Prometheus valido (# HELP presente)"
    } else {
        Write-Warn "El cuerpo no parece texto Prometheus estandar"
    }

    if ($Verbose) {
        Write-Host ""
        Write-Host "  --- OUTPUT COMPLETO DE /metrics ---" -ForegroundColor DarkGray
        Write-Host $rMetrics.body -ForegroundColor DarkGray
        Write-Host "  --- FIN ---" -ForegroundColor DarkGray
    }
} elseif ($rMetrics.code -eq 403) {
    Write-Fail "HTTP 403 -- el endpoint /metrics requiere autenticacion o esta deshabilitado"
    Write-Skip "Bloques B3 y B5 omitidos (sin acceso a /metrics)"
    $rMetrics = $null
} else {
    Write-Fail "HTTP $($rMetrics.code) -- /metrics no disponible"
    $rMetrics = $null
}

# ===========================================================================
# BLOQUE 3 -- Metricas clave pre-existentes en /metrics (estado inicial)
# ===========================================================================
Write-Header "BLOQUE 3 -- Metricas Prometheus (estado ANTES del trafico)"

if ($null -eq $rMetrics) {
    Write-Skip "No hay acceso a /metrics -- omitiendo B3"
} else {
    $body = $rMetrics.body

    # Tabla de metricas criticas que DEBEN existir post-deploy 00045-2nk
    # NOTA: http_requests_total es LAZY -- solo aparece en /metrics despues del
    # primer request HTTP. En la primera ejecucion (cold start) puede no existir aun.
    # Por eso se marca como [WARN] en lugar de [FAIL] si no se encuentra.
    $criticalMetrics = @(
        @{ prefix = "recommender_requests_total{";     desc = "Contador recomendaciones (M2 fix)";           required = $true  },
        @{ prefix = "kb_sync_operations_total{";       desc = "Contador KB sync operations";                  required = $true  },
        @{ prefix = "recommender_duration_seconds_";   desc = "Histograma duracion recomendaciones";          required = $true  },
        @{ prefix = "http_requests_total{";            desc = "Contador HTTP (lazy -- WARN si cold start)";   required = $false },
        @{ prefix = "process_resident_memory_bytes";   desc = "Memoria del proceso (Python runtime)";         required = $true  }
    )

    Write-Step "Verificando presencia de metricas criticas..."
    foreach ($m in $criticalMetrics) {
        if ($body -match [regex]::Escape($m.prefix)) {
            Write-Pass "$($m.prefix)* -- $($m.desc)"
        } elseif ($m.required) {
            Write-Fail "$($m.prefix)* -- NO encontrada (esperada post-deploy 00045-2nk)"
        } else {
            # Metrica lazy (http_requests_total): solo existe despues del primer request.
            # En cold start aun no hay series -- es esperado, no un bug.
            Write-Warn "$($m.prefix)* -- aun no inicializada (normal en cold start, desaparece tras primer request)"
        }
    }

    # Capturar valor INICIAL de recommender_requests_total para comparar despues en B5
    # Necesitamos la suma de TODOS los labels, no solo uno
    $script:InitialRecCount = 0
    $lines = $body -split "`n"
    foreach ($line in $lines) {
        if ($line -match '^recommender_requests_total\{' -and $line -notmatch '^#') {
            $parts = $line.Trim() -split "\s+"
            if ($parts.Length -ge 2) {
                try { $script:InitialRecCount += [double]$parts[-1] } catch {}
            }
        }
    }
    Write-Info "recommender_requests_total (suma inicial) = $($script:InitialRecCount)"

    # Capturar valor inicial de kb_sync_operations_total{status="success"}
    $script:InitialKbCount = 0
    foreach ($line in $lines) {
        if ($line -match 'kb_sync_operations_total\{.*status="success"' -and $line -notmatch '^#') {
            $parts = $line.Trim() -split "\s+"
            if ($parts.Length -ge 2) {
                try { $script:InitialKbCount = [double]$parts[-1] } catch {}
            }
        }
    }
    Write-Info "kb_sync_operations_total{status=success} (inicial) = $($script:InitialKbCount)"
}

# ===========================================================================
# BLOQUE 4 -- Generar trafico real contra el servicio de produccion
# ===========================================================================
Write-Header "BLOQUE 4 -- Generacion de trafico real (produccion)"

Write-Info "Enviando requests para generar datos en Prometheus..."
Write-Info "Esto es necesario para que GCP tenga datos reales en los dashboards."

# 4.1: Obtener un product_id real del catalogo
Write-Step "4.1 -- GET /v1/products/?limit=3 (obtener product_ids reales)"
$rProducts = Invoke-API "$BASE_URL/v1/products/?limit=3"
$script:RealProdId = $null

if ($rProducts.code -eq 200) {
    Write-Pass "HTTP 200 -- catalogo accesible ($($rProducts.ms)ms)"
    try {
        $prodData = $rProducts.body | ConvertFrom-Json
        # Intentar extraer el primer product_id del resultado
        if ($prodData.products -and $prodData.products.Count -gt 0) {
            $script:RealProdId = $prodData.products[0].id
        } elseif ($prodData -is [array] -and $prodData.Count -gt 0) {
            $script:RealProdId = $prodData[0].id
        }
        if ($script:RealProdId) {
            Write-Pass "Product ID real capturado: $($script:RealProdId)"
        } else {
            Write-Warn "No se pudo extraer product_id del body -- usando ID generico"
            $script:RealProdId = "product_001"
        }
    } catch {
        Write-Warn "Error parseando productos: $_ -- usando ID generico"
        $script:RealProdId = "product_001"
    }
} else {
    Write-Warn "HTTP $($rProducts.code) para /v1/products/ -- usando product_id generico"
    $script:RealProdId = "product_001"
}

# 4.2: Hacer 5 llamadas a /v1/recommendations/{product_id}
# Objetivo: incrementar recommender_requests_total en al menos 5
Write-Step "4.2 -- 5x GET /v1/recommendations/$($script:RealProdId) (generar contadores)"
$recSuccess = 0
$recErrors  = 0
$latencies  = @()

for ($i = 1; $i -le 5; $i++) {
    $r = Invoke-API-Slow "$BASE_URL/v1/recommendations/$($script:RealProdId)"
    $latencies += $r.ms
    if ($r.code -eq 200) {
        $recSuccess++
        Write-Info "  Request $i/$5 -- HTTP 200 ($($r.ms)ms)"
    } elseif ($r.code -eq 404) {
        # 404 es aceptable si el producto no existe en el catalogo de Shopify
        # El contador Prometheus se incrementa igualmente (el handler fue ejecutado)
        $recSuccess++
        Write-Info "  Request $i/$5 -- HTTP 404 (producto no en catalogo Shopify, contador incrementado)"
    } elseif ($r.code -eq 0) {
        $recErrors++
        Write-Warn "  Request $i/$5 -- Timeout/sin respuesta ($($r.ms)ms)"
    } else {
        $recErrors++
        Write-Warn "  Request $i/$5 -- HTTP $($r.code) ($($r.ms)ms)"
    }
    # Pausa breve entre requests para no saturar el servicio
    Start-Sleep -Milliseconds 500
}

# Calcular latencia promedio
$avgLatency = if ($latencies.Count -gt 0) { ($latencies | Measure-Object -Average).Average } else { 0 }
Write-Info "Latencia promedio de las 5 llamadas: $([Math]::Round($avgLatency))ms"

if ($recErrors -eq 0) {
    Write-Pass "$recSuccess/5 requests exitosos (200 o 404)"
} elseif ($recSuccess -gt 0) {
    Write-Warn "$recSuccess/5 requests exitosos, $recErrors con error"
} else {
    Write-Fail "0/5 requests exitosos -- el endpoint de recomendaciones no responde"
}

# 4.3: Llamada al endpoint MCP para generar su contador tambien
Write-Step "4.3 -- GET /v1/mcp/recommendations/$($script:RealProdId) (MCP endpoint)"
$rMcp = Invoke-API-Slow "$BASE_URL/v1/mcp/recommendations/$($script:RealProdId)"
if ($rMcp.code -in 200, 404) {
    Write-Pass "MCP endpoint accesible -- HTTP $($rMcp.code) ($($rMcp.ms)ms)"
} elseif ($rMcp.code -eq 0) {
    Write-Warn "Timeout en MCP endpoint ($($rMcp.ms)ms) -- puede ser cold start"
} else {
    Write-Warn "MCP endpoint -- HTTP $($rMcp.code) ($($rMcp.ms)ms)"
}

# ===========================================================================
# BLOQUE 5 -- Verificar que los contadores Prometheus se incrementaron
# ===========================================================================
Write-Header "BLOQUE 5 -- Verificacion post-trafico (contadores Prometheus)"

Write-Info "Esperando 3 segundos para que los contadores se actualicen..."
Start-Sleep -Seconds 3

Write-Step "GET /metrics (segunda lectura -- post-trafico)"
$rMetrics2 = Invoke-API "$BASE_URL/metrics"

if ($null -eq $rMetrics -or $rMetrics2.code -ne 200) {
    Write-Skip "No hay acceso a /metrics -- omitiendo B5"
} else {
    $body2 = $rMetrics2.body

    # Calcular nueva suma de recommender_requests_total
    $newRecCount = 0
    $lines2 = $body2 -split "`n"
    foreach ($line in $lines2) {
        if ($line -match '^recommender_requests_total\{' -and $line -notmatch '^#') {
            $parts = $line.Trim() -split "\s+"
            if ($parts.Length -ge 2) {
                try { $newRecCount += [double]$parts[-1] } catch {}
            }
        }
    }

    $delta = $newRecCount - $script:InitialRecCount
    Write-Info "recommender_requests_total (nueva suma) = $newRecCount"
    Write-Info "Delta = $newRecCount - $($script:InitialRecCount) = $delta"

    if ($delta -ge 5) {
        Write-Pass "Contador incremento en $delta (esperado >= 5 por las 5 llamadas de B4)"
    } elseif ($delta -gt 0) {
        Write-Warn "Contador incremento en $delta (esperado >= 5) -- puede haber cold start o cache hit"
    } else {
        Write-Fail "Contador NO incremento ($delta) -- el handler legacy en main_unified_redis.py no esta ejecutando .inc()"
        Write-Info "ACCION: Verificar el fix de M2 en main_unified_redis.py (~L900)"
        Write-Info "        recommendation_requests_total.labels(market='default', strategy='hybrid').inc()"
    }

    # Verificar histograma de duracion
    $hasDuration = $body2 -match 'recommender_duration_seconds_count\{.*\}\s+[1-9]'
    if ($hasDuration) {
        Write-Pass "recommender_duration_seconds_count tiene datos (histograma activo)"
    } else {
        Write-Warn "recommender_duration_seconds_count sigue en 0 (esperar siguiente export)"
    }

    # Verificar http_requests_total para el endpoint de recomendaciones
    $httpRec = $false
    foreach ($line in $lines2) {
        if ($line -match 'http_requests_total\{.*recommendations.*\}' -and $line -notmatch '^#') {
            $parts = $line.Trim() -split "\s+"
            if ($parts.Length -ge 2 -and [double]$parts[-1] -gt 0) {
                $httpRec = $true
                Write-Pass "http_requests_total para /recommendations = $($parts[-1])"
                break
            }
        }
    }
    if (-not $httpRec) {
        Write-Warn "No se encontro http_requests_total > 0 para /recommendations en /metrics"
    }
}

# ===========================================================================
# BLOQUE 6 -- Verificar logs de exportacion a GCP (via gcloud)
# ===========================================================================
Write-Header "BLOQUE 6 -- Logs de exportacion GCP (gcloud)"

Write-Step "Verificando si gcloud CLI esta disponible..."
$gcloudAvail = $false
try {
    $gv = & gcloud --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $gcloudAvail = $true
        Write-Pass "gcloud disponible: $($gv[0])"
    }
} catch {
    Write-Warn "gcloud no encontrado en PATH"
}

if ($gcloudAvail) {
    Write-Step "Consultando logs 'gcp_metrics_exported' de los ultimos 5 minutos..."
    Write-Info "(Esto puede tardar 10-15 segundos...)"

    $logFilter = @"
resource.type="cloud_run_revision"
resource.labels.service_name="$SVC_NAME"
jsonPayload.event="gcp_metrics_exported"
"@

    try {
        # Leer logs de los ultimos 5 minutos
        $since = (Get-Date).AddMinutes(-5).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        $logOutput = & gcloud logging read `
            "resource.type=`"cloud_run_revision`" AND resource.labels.service_name=`"$SVC_NAME`" AND jsonPayload.event=`"gcp_metrics_exported`"" `
            --project=$GCP_PROJ `
            --freshness=5m `
            --limit=5 `
            --format="value(jsonPayload.metrics_count,jsonPayload.timestamp,severity)" `
            2>&1

        if ($LASTEXITCODE -eq 0 -and $logOutput -and $logOutput.Trim() -ne "") {
            $exportCount = ($logOutput -split "`n" | Where-Object { $_.Trim() -ne "" }).Count
            Write-Pass "Encontrados $exportCount exports recientes en los logs"
            Write-Info "Ultimos exports (metrics_count, timestamp, severity):"
            $logOutput -split "`n" | Where-Object { $_.Trim() -ne "" } | Select-Object -First 5 | ForEach-Object {
                Write-Info "  $_"
            }
        } else {
            Write-Warn "Sin logs 'gcp_metrics_exported' en los ultimos 5 minutos"
            Write-Info "Esto puede ser normal si el Cloud Run no recibio trafico reciente"
            Write-Info "El exporter corre cada 60s -- puede necesitar 1-2 minutos despues del trafico"
        }
    } catch {
        Write-Warn "Error consultando logs: $_"
    }

    # Verificar tambien logs de errores del exporter
    Write-Step "Verificando ausencia de errores del exporter en los ultimos 5 min..."
    try {
        $errOutput = & gcloud logging read `
            "resource.type=`"cloud_run_revision`" AND resource.labels.service_name=`"$SVC_NAME`" AND jsonPayload.event=`"gcp_metrics_batch_error`"" `
            --project=$GCP_PROJ `
            --freshness=5m `
            --limit=3 `
            --format="value(jsonPayload.error,jsonPayload.timestamp)" `
            2>&1

        if ($LASTEXITCODE -eq 0 -and $errOutput -and $errOutput.Trim() -ne "") {
            Write-Warn "Se encontraron errores del exporter en los ultimos 5 min:"
            $errOutput -split "`n" | Where-Object { $_.Trim() -ne "" } | ForEach-Object {
                Write-Info "  $_"
            }
        } else {
            Write-Pass "Sin errores 'gcp_metrics_batch_error' en los ultimos 5 minutos"
        }
    } catch {
        Write-Warn "No se pudo verificar errores del exporter: $_"
    }
} else {
    Write-Skip "gcloud no disponible -- omitiendo verificacion de logs"
    Write-Info "ACCION MANUAL: Verificar en GCP Console > Logs Explorer:"
    Write-Info "  Filter: jsonPayload.event='gcp_metrics_exported'"
    Write-Info "  Deberias ver entradas con metrics_count=111 cada ~60 segundos"
}

# ===========================================================================
# BLOQUE 7 -- Instrucciones de verificacion manual en GCP Console
# ===========================================================================
Write-Header "BLOQUE 7 -- Lista de verificacion manual en GCP Console"

Write-Host ""
Write-Host "  Completa estos pasos en GCP Console para validar el pipeline completo:" -ForegroundColor White
Write-Host ""
Write-Host "  PASO 1 -- Metrics Explorer (verifica que los datos llegan a GCP)" -ForegroundColor Cyan
Write-Host "    URL: https://console.cloud.google.com/monitoring/metrics-explorer?project=$GCP_PROJ"
Write-Host "    Buscar: custom.googleapis.com/recommender_requests_total"
Write-Host "    Esperado: Ver un spike en la linea del tiempo DESPUES de ejecutar este script"
Write-Host "    Nota: puede tardar hasta 3 minutos en aparecer (export interval = 60s)"
Write-Host ""
Write-Host "  PASO 2 -- Alerting Incidents (verifica que no hay falsas alarmas)" -ForegroundColor Cyan
Write-Host "    URL: https://console.cloud.google.com/monitoring/alerting/incidents?project=$GCP_PROJ"
Write-Host "    Esperado: 0 incidentes activos (todas las alertas en estado OK)"
Write-Host "    Si hay incidentes: revisar el threshold o la condicion de la alerta"
Write-Host ""
Write-Host "  PASO 3 -- Dashboard (verifica que los graficos tienen datos)" -ForegroundColor Cyan
Write-Host "    URL: https://console.cloud.google.com/monitoring/dashboards?project=$GCP_PROJ"
Write-Host "    Accion: abrir el dashboard del sistema y verificar que los charts muestran datos"
Write-Host "    Si estan vacios: cambiar el time range a 'Last 1 hour' o 'Last 6 hours'"
Write-Host ""
Write-Host "  PASO 4 -- Verificar run.googleapis.com/request_latencies (para alertas B1/B2)" -ForegroundColor Cyan
Write-Host "    Buscar en Metrics Explorer: run.googleapis.com/request_latencies"
Write-Host "    Filter: resource.service_name = retail-recommender"
Write-Host "    Esperado: datos con latencia tipica de 100-2000ms (los 5 requests de B4)"
Write-Host ""
Write-Host "  PASO 5 -- Verificar kb_sync_operations_total (para alerta B3)" -ForegroundColor Cyan
Write-Host "    Buscar: custom.googleapis.com/kb_sync_operations_total"
Write-Host "    Esperado: valor estable (sin incremento de 'failed')"
Write-Host ""

# ===========================================================================
# RESUMEN FINAL
# ===========================================================================
Write-Host ""
Write-Host "=" * 70 -ForegroundColor Magenta
Write-Host "  RESUMEN FINAL" -ForegroundColor Magenta
Write-Host "=" * 70 -ForegroundColor Magenta
Write-Host ""
Write-Host "  PASS : $($script:PASS)" -ForegroundColor Green
Write-Host "  WARN : $($script:WARN)" -ForegroundColor Yellow
Write-Host "  FAIL : $($script:FAIL)" -ForegroundColor Red
Write-Host "  SKIP : $($script:SKIP)" -ForegroundColor Gray
Write-Host ""

$total = $script:PASS + $script:WARN + $script:FAIL
if ($total -gt 0) {
    $pct = [Math]::Round(($script:PASS / $total) * 100)
    Write-Host "  Score: $($script:PASS)/$total checks passed ($pct%%)" -ForegroundColor White
}

if ($script:FAIL -eq 0 -and $script:WARN -le 2) {
    Write-Host ""
    Write-Host "  PIPELINE DE OBSERVABILIDAD: OPERACIONAL" -ForegroundColor Green
    Write-Host "  Completa los pasos del BLOQUE 7 para validacion visual en GCP." -ForegroundColor Green
} elseif ($script:FAIL -eq 0) {
    Write-Host ""
    Write-Host "  PIPELINE DE OBSERVABILIDAD: FUNCIONAL (con advertencias)" -ForegroundColor Yellow
    Write-Host "  Revisar los WARNs arriba antes de cerrar M3." -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "  PIPELINE DE OBSERVABILIDAD: PROBLEMAS DETECTADOS" -ForegroundColor Red
    Write-Host "  Resolver los FAILs antes de cerrar M3." -ForegroundColor Red
}

Write-Host ""
Write-Host "  Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray
Write-Host ""
