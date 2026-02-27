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
# LOGGING
# ════════════════════════════════════════════════════════════════════════

logger.info(
    "prometheus_metrics_module_loaded",
    module="prometheus_metrics",
    metrics_count=10,
    integration_phase="M3"
)