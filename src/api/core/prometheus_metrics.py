"""
Prometheus Metrics for Infrastructure Observability
====================================================

COMPLEMENTA (no reemplaza) src/api/core/metrics.py (RecommendationMetrics).

Sistema actual (/v1/metrics):
- RecommendationMetrics → Business metrics (diversity, fallback, conversions)
- JSON format, auth required
- Para Analytics teams

Sistema nuevo (/metrics):
- Prometheus metrics → Infrastructure metrics (HTTP, latency, errors)
- Prometheus format, no auth
- Para SRE/DevOps

Author: M2 Prometheus Integration
Date: 2026-02-15
Version: 1.0
"""
from prometheus_client import Counter, Histogram, Gauge
import structlog

logger = structlog.get_logger(__name__)

# ══════════════════════════════════════════════════════════════════════════
# RECOMMENDATION METRICS
# ══════════════════════════════════════════════════════════════════════════

recommendation_requests_total = Counter(
    'recommender_requests_total',
    'Total recommendation requests',
    ['market', 'strategy']
)

recommendation_duration_seconds = Histogram(
    'recommender_duration_seconds',
    'Recommendation generation time in seconds',
    ['strategy'],
    buckets=[.1, .25, .5, 1, 2.5, 5, 10]
)

recommendation_errors_total = Counter(
    'recommender_errors_total',
    'Total recommendation errors',
    ['error_type']
)

# ══════════════════════════════════════════════════════════════════════════
# KB SYNC METRICS (M1 + M2 Integration)
# ══════════════════════════════════════════════════════════════════════════

kb_sync_operations_total = Counter(
    'kb_sync_operations_total',
    'Total KB sync operations',
    ['status']  # success/failed
)

kb_sync_duration_seconds = Histogram(
    'kb_sync_duration_seconds',
    'KB sync operation duration in seconds',
    buckets=[.5, 1, 2, 5, 10, 30, 60]
)

kb_sync_semaphore_size = Gauge(
    'kb_sync_semaphore_size',
    'Current KB sync DB semaphore size (M1 metric)'
)

# ══════════════════════════════════════════════════════════════════════════
# GOOGLE RETAIL API METRICS (Si se identifica ubicación)
# ══════════════════════════════════════════════════════════════════════════

google_retail_calls_total = Counter(
    'google_retail_api_calls_total',
    'Total Google Retail API calls',
    ['method', 'status']  # method: predict/import, status: success/error
)

google_retail_duration_seconds = Histogram(
    'google_retail_api_duration_seconds',
    'Google Retail API call duration in seconds',
    ['method'],
    buckets=[.1, .5, 1, 2, 5, 10, 30]
)

# ══════════════════════════════════════════════════════════════════════════
# KB DISTRIBUTED LOCK METRICS (M3 Integration)
# ══════════════════════════════════════════════════════════════════════════

kb_distributed_lock_acquisitions_total = Counter(
    'kb_distributed_lock_acquisitions_total',
    'Total distributed lock acquisition attempts',
    ['result']  # result: acquired / timeout / degraded (redis unavailable)
)

kb_distributed_lock_wait_seconds = Histogram(
    'kb_distributed_lock_wait_seconds',
    'Time spent waiting to acquire a distributed lock (seconds)',
    buckets=[.01, .05, .1, .25, .5, 1.0, 2.5, 5.0]
)

kb_distributed_lock_timeouts_total = Counter(
    'kb_distributed_lock_timeouts_total',
    'Total distributed lock acquisition timeouts (blocking_timeout exceeded)',
)

# ── Webhooks ──────────────────────────────────────────────────────────────
kb_webhook_received_total = Counter(
    "kb_webhook_received_total",
    "Total webhooks recibidos de Shopify",
    ["topic"],
)

kb_webhook_processed_total = Counter(
    "kb_webhook_processed_total",
    "Total webhooks procesados (con resultado)",
    ["topic", "result"],  # result: success | error | duplicate | skipped
)

kb_webhook_processing_seconds = Histogram(
    "kb_webhook_processing_seconds",
    "Tiempo de procesamiento de webhook de page sync",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

kb_webhook_hmac_failures_total = Counter(
    "kb_webhook_hmac_failures_total",
    "Webhooks rechazados por HMAC inválido (potencial ataque)",
)

# ════════════════════════════════════════════════════════════════════════
# PRE-INICIALIZACIÓN DE LABEL SETS (M3 GCP Export Fix)
# ════════════════════════════════════════════════════════════════════════
#
# PROBLEMA: En prometheus_client (Python), un Counter con labels NO genera
# ningún sample en REGISTRY.collect() hasta que se llama por primera vez.
# Consecuencia: el GCPMetricsExporter nunca exporta recommender_requests_total
# si el servicio no ha recibido ningún request de recomendación real.
#
# SOLUCIÓN: Llamar a .labels(...) al importar el módulo fuerza a
# prometheus_client a registrar esos label sets con valor=0 desde el inicio.
# El acceso a .labels() sin .inc() crea la serie interna pero no modifica
# el valor visible del counter (sigue en 0, que es correcto al arrancar).
#
# MARKETS SOPORTADOS: us, es, mx, cl (multi-market deployment)
# STRATEGIES: hybrid, tfidf, google_retail, fallback, mcp_enhanced

# "default" cubre el endpoint legacy /v1/recommendations/{product_id} en main_unified_redis.py
# que no recibe market como parámetro. Sin pre-inicialización, GCP rechazaría el primer
# sample de ese counter porque el MetricDescriptor ya existía solo con markets [us/es/mx/cl].
_MARKETS = ["us", "es", "mx", "cl", "default"]
_STRATEGIES = ["hybrid", "tfidf", "google_retail", "fallback", "mcp_enhanced"]
_ERROR_TYPES = ["timeout", "validation", "service_unavailable", "unknown"]
_RETAIL_METHODS = ["predict", "import"]
_RETAIL_STATUSES = ["success", "error"]
_LOCK_RESULTS = ["acquired", "timeout", "degraded"]
_SYNC_STATUSES = ["success", "failed"]

# recommender_requests_total{market, strategy} — el counter principal del negocio
for _m in _MARKETS:
    for _s in _STRATEGIES:
        recommendation_requests_total.labels(market=_m, strategy=_s)

# recommender_duration_seconds{strategy} — histograma de latencia por estrategia
for _s in _STRATEGIES:
    recommendation_duration_seconds.labels(strategy=_s)

# recommender_errors_total{error_type} — errores por tipo
for _e in _ERROR_TYPES:
    recommendation_errors_total.labels(error_type=_e)

# google_retail_api_calls_total{method, status} — llamadas a Google Retail API
for _method in _RETAIL_METHODS:
    for _status in _RETAIL_STATUSES:
        google_retail_calls_total.labels(method=_method, status=_status)

# google_retail_api_duration_seconds{method} — latencia de Google Retail API
for _method in _RETAIL_METHODS:
    google_retail_duration_seconds.labels(method=_method)

# kb_distributed_lock_acquisitions_total{result} — conteo de locks
for _r in _LOCK_RESULTS:
    kb_distributed_lock_acquisitions_total.labels(result=_r)

# kb_sync_operations_total{status} — operaciones de sync
for _s in _SYNC_STATUSES:
    kb_sync_operations_total.labels(status=_s)


# ════════════════════════════════════════════════════════════════════════
# LOGGING
# ════════════════════════════════════════════════════════════════════════

logger.info(
    "prometheus_metrics_module_loaded",
    module="prometheus_metrics",
    metrics_count=10,
    integration_phase="M3"
)