# 📊 M2: PROMETHEUS METRICS - PLAN DE IMPLEMENTACIÓN

**Fase**: M2 - Prometheus Metrics & Observability  
**Fecha**: 14 Febrero 2026  
**Prioridad**: **ALTA** (Critical for production observability)  
**Estado**: 📋 **PLANIFICADO**  
**Prerequisitos**: ✅ H1 (Structured Logging) completado

---

## 🎯 OBJETIVO

Implementar sistema completo de métricas con Prometheus para observabilidad enterprise-grade del sistema de recomendaciones.

**Targets**:
1. ✅ Exponer métricas clave en formato Prometheus
2. ✅ Dashboards para monitoreo real-time
3. ✅ Alertas proactivas antes de fallos
4. ✅ SLI/SLO tracking para SRE

---

## 📊 JUSTIFICACIÓN

### Situación Actual

**Logging ✅**: Tenemos structured logging (H1)
- ✅ Eventos bien definidos
- ✅ Contexto completo en logs
- ✅ Búsqueda y debugging excelente

**Métricas ❌**: No tenemos agregación numérica
- ❌ No sabemos throughput promedio
- ❌ No sabemos latencias p50/p95/p99
- ❌ No sabemos error rates
- ❌ No tenemos alertas automáticas

### Problema

**Logs son eventos individuales**. Para responder preguntas como:
- "¿Cuál es el throughput promedio del último mes?"
- "¿Cuántas requests fallaron hoy?"
- "¿Está aumentando la latencia p95?"

Necesitas **agregar millones de eventos** → lento, costoso, difícil.

### Solución: Prometheus Metrics

**Métricas son agregaciones**. Prometheus responde instantáneamente:
```promql
# Throughput promedio (última hora)
rate(recommendations_total[1h])

# Error rate
rate(recommendations_errors_total[5m]) / rate(recommendations_total[5m])

# Latencia p95
histogram_quantile(0.95, rate(recommendation_duration_seconds_bucket[5m]))
```

---

## 🏗️ ARQUITECTURA PROPUESTA

### Stack Tecnológico

```
┌─────────────────────────────────────────┐
│   FastAPI Application                    │
│   (Retail Recommender System)            │
└────────────┬────────────────────────────┘
             │
             │ /metrics endpoint
             │
             ▼
┌─────────────────────────────────────────┐
│   prometheus-fastapi-instrumentator     │
│   (Auto-instrumentation)                │
└────────────┬────────────────────────────┘
             │
             │ Expone métricas
             │
             ▼
┌─────────────────────────────────────────┐
│   Prometheus Server                      │
│   (Time-series DB)                       │
│   - Scraping cada 15s                    │
│   - Retention: 15 días                   │
└────────────┬────────────────────────────┘
             │
             │ PromQL queries
             │
             ▼
┌─────────────────────────────────────────┐
│   Grafana Dashboards                     │
│   - Real-time monitoring                 │
│   - Alerting rules                       │
└─────────────────────────────────────────┘
```

### Componentes

1. **prometheus-client** (Python library)
   - Crear métricas custom
   - Exponer en formato Prometheus

2. **prometheus-fastapi-instrumentator** 
   - Auto-instrumentación FastAPI
   - Métricas HTTP automáticas

3. **Prometheus Server**
   - Scraping de métricas cada 15s
   - Storage time-series
   - Alerting rules

4. **Grafana**
   - Dashboards visuales
   - Alerting notifications

---

## 📐 DISEÑO DE MÉTRICAS

### Principios de Naming

Seguimos convenciones Prometheus:
```
<namespace>_<subsystem>_<metric_name>_<unit>

Ejemplos:
- recommender_http_requests_total (counter)
- recommender_request_duration_seconds (histogram)
- recommender_cache_hit_rate (gauge)
```

### Métricas Core (Layer 1 - Essential)

#### 1. HTTP Request Metrics (Auto-instrumented)

```python
# ✅ Automático con prometheus-fastapi-instrumentator

http_requests_total
  labels: method, path, status

http_request_duration_seconds
  labels: method, path, status
  buckets: [.005, .01, .025, .05, .075, .1, .25, .5, .75, 1, 2.5, 5, 10]
```

#### 2. Recommendation Metrics (Custom)

```python
# Counter: Total recommendations generadas
recommender_recommendations_total
  labels: strategy, market, success

# Histogram: Latencia de generación
recommender_generation_duration_seconds
  labels: strategy, market
  buckets: [.1, .25, .5, 1, 2.5, 5]

# Counter: Errores
recommender_errors_total
  labels: error_type, component

# Gauge: Productos en cache
recommender_cache_products_count
  labels: market
```

#### 3. Google Retail API Metrics (Custom)

```python
# Counter: Llamadas a Google API
recommender_google_api_calls_total
  labels: method, status

# Histogram: Latencia de Google API
recommender_google_api_duration_seconds
  labels: method
  buckets: [.1, .5, 1, 2, 5, 10]

# Counter: Rate limit hits
recommender_google_api_rate_limits_total
```

#### 4. Redis Metrics (Custom)

```python
# Counter: Cache operations
recommender_cache_operations_total
  labels: operation, hit

# Histogram: Cache latency
recommender_cache_duration_seconds
  labels: operation
  buckets: [.001, .005, .01, .025, .05, .1]

# Gauge: Cache size (MB)
recommender_cache_size_bytes

# Counter: Cache evictions
recommender_cache_evictions_total
```

### Métricas Business (Layer 2 - Valuable)

```python
# Counter: Recomendaciones por categoría
recommender_recommendations_by_category_total
  labels: category, market

# Histogram: Diversity score
recommender_diversity_score
  labels: strategy
  buckets: [0, .2, .4, .6, .8, 1]

# Counter: Fallback usage
recommender_fallback_used_total
  labels: reason, market

# Gauge: Average products per recommendation
recommender_avg_products_per_recommendation
  labels: strategy
```

### Métricas KB Sync (Layer 3 - Operational)

```python
# Counter: KB syncs
kb_sync_operations_total
  labels: status

# Histogram: Sync duration
kb_sync_duration_seconds
  buckets: [.5, 1, 2, 5, 10, 30]

# Counter: Pages synced
kb_sync_pages_total
  labels: language, status

# Gauge: Last sync timestamp
kb_sync_last_success_timestamp
```

---

## 💻 IMPLEMENTACIÓN

### Paso 1: Dependencias (5 min)

```bash
# requirements.txt
prometheus-client==0.19.0
prometheus-fastapi-instrumentator==6.1.0
```

```bash
pip install prometheus-client prometheus-fastapi-instrumentator
```

### Paso 2: Metrics Module (30 min)

**Crear**: `src/api/core/metrics.py`

```python
"""
Prometheus Metrics for Retail Recommender System
=================================================

Centralizes all Prometheus metrics definition and management.

Metrics categories:
1. HTTP/API metrics (auto-instrumented)
2. Recommendation metrics (custom)
3. Google Retail API metrics (custom)
4. Redis cache metrics (custom)
5. KB sync metrics (custom)

Author: Retail Recommender System Team
Date: 2026-02-14
Version: M2 - Prometheus Metrics
"""
from prometheus_client import Counter, Histogram, Gauge, Info
import structlog

logger = structlog.get_logger(__name__)

# ══════════════════════════════════════════════════════════════════════════
# RECOMMENDATION METRICS
# ══════════════════════════════════════════════════════════════════════════

# Counter: Total recommendations generated
recommendations_total = Counter(
    'recommender_recommendations_total',
    'Total number of recommendations generated',
    ['strategy', 'market', 'success']
)

# Histogram: Recommendation generation duration
recommendation_duration_seconds = Histogram(
    'recommender_generation_duration_seconds',
    'Time spent generating recommendations',
    ['strategy', 'market'],
    buckets=[.1, .25, .5, 1, 2.5, 5, 10]
)

# Counter: Recommendation errors
recommendation_errors_total = Counter(
    'recommender_errors_total',
    'Total number of recommendation errors',
    ['error_type', 'component']
)

# Gauge: Products in cache
cache_products_count = Gauge(
    'recommender_cache_products_count',
    'Number of products currently in cache',
    ['market']
)

# Counter: Recommendations by category
recommendations_by_category_total = Counter(
    'recommender_recommendations_by_category_total',
    'Recommendations generated by product category',
    ['category', 'market']
)

# Histogram: Diversity score
diversity_score = Histogram(
    'recommender_diversity_score',
    'Product diversity score in recommendations',
    ['strategy'],
    buckets=[0, .2, .4, .6, .8, 1]
)

# Counter: Fallback usage
fallback_used_total = Counter(
    'recommender_fallback_used_total',
    'Number of times fallback recommendations were used',
    ['reason', 'market']
)

# ══════════════════════════════════════════════════════════════════════════
# GOOGLE RETAIL API METRICS
# ══════════════════════════════════════════════════════════════════════════

# Counter: Google API calls
google_api_calls_total = Counter(
    'recommender_google_api_calls_total',
    'Total Google Retail API calls',
    ['method', 'status']
)

# Histogram: Google API latency
google_api_duration_seconds = Histogram(
    'recommender_google_api_duration_seconds',
    'Google Retail API request duration',
    ['method'],
    buckets=[.1, .5, 1, 2, 5, 10, 30]
)

# Counter: Rate limit hits
google_api_rate_limits_total = Counter(
    'recommender_google_api_rate_limits_total',
    'Number of times rate limit was hit'
)

# ══════════════════════════════════════════════════════════════════════════
# REDIS CACHE METRICS
# ══════════════════════════════════════════════════════════════════════════

# Counter: Cache operations
cache_operations_total = Counter(
    'recommender_cache_operations_total',
    'Total cache operations',
    ['operation', 'hit']  # operation: get/set/delete, hit: true/false
)

# Histogram: Cache operation latency
cache_duration_seconds = Histogram(
    'recommender_cache_duration_seconds',
    'Cache operation duration',
    ['operation'],
    buckets=[.001, .005, .01, .025, .05, .1, .5]
)

# Gauge: Cache size
cache_size_bytes = Gauge(
    'recommender_cache_size_bytes',
    'Total size of cache in bytes'
)

# Counter: Cache evictions
cache_evictions_total = Counter(
    'recommender_cache_evictions_total',
    'Number of cache evictions'
)

# ══════════════════════════════════════════════════════════════════════════
# KB SYNC METRICS
# ══════════════════════════════════════════════════════════════════════════

# Counter: Sync operations
kb_sync_operations_total = Counter(
    'kb_sync_operations_total',
    'Total KB sync operations',
    ['status']  # success/failed
)

# Histogram: Sync duration
kb_sync_duration_seconds = Histogram(
    'kb_sync_duration_seconds',
    'KB sync operation duration',
    buckets=[.5, 1, 2, 5, 10, 30, 60]
)

# Counter: Pages synced
kb_sync_pages_total = Counter(
    'kb_sync_pages_total',
    'Total KB pages synced',
    ['language', 'status']
)

# Gauge: Last successful sync timestamp
kb_sync_last_success_timestamp = Gauge(
    'kb_sync_last_success_timestamp',
    'Timestamp of last successful KB sync'
)

# Gauge: Current semaphore size (M1 metric)
kb_sync_semaphore_size = Gauge(
    'kb_sync_semaphore_size',
    'Current KB sync DB semaphore size'
)

# ══════════════════════════════════════════════════════════════════════════
# SYSTEM INFO
# ══════════════════════════════════════════════════════════════════════════

# Info: System metadata
system_info = Info(
    'recommender_system',
    'System information'
)

# Set system info (call once at startup)
def set_system_info(version: str, environment: str):
    """Set system metadata."""
    system_info.info({
        'version': version,
        'environment': environment,
        'python_version': '3.11',
        'optimization_phase': 'M2'
    })
    
    logger.info(
        "prometheus_metrics_initialized",
        version=version,
        environment=environment
    )


# ══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════

def track_recommendation(
    strategy: str,
    market: str,
    duration: float,
    success: bool,
    error_type: str = None
):
    """
    Track a recommendation generation.
    
    Args:
        strategy: Recommendation strategy (content/collaborative/hybrid)
        market: Market code (US/ES/MX)
        duration: Generation time in seconds
        success: Whether recommendation succeeded
        error_type: Error type if failed
    """
    # Count
    recommendations_total.labels(
        strategy=strategy,
        market=market,
        success='true' if success else 'false'
    ).inc()
    
    # Duration
    if success:
        recommendation_duration_seconds.labels(
            strategy=strategy,
            market=market
        ).observe(duration)
    
    # Errors
    if not success and error_type:
        recommendation_errors_total.labels(
            error_type=error_type,
            component='recommendation_engine'
        ).inc()


def track_google_api_call(
    method: str,
    duration: float,
    status: str
):
    """
    Track Google Retail API call.
    
    Args:
        method: API method (predict/import/etc)
        duration: Call duration in seconds
        status: success/error/rate_limited
    """
    google_api_calls_total.labels(
        method=method,
        status=status
    ).inc()
    
    google_api_duration_seconds.labels(
        method=method
    ).observe(duration)
    
    if status == 'rate_limited':
        google_api_rate_limits_total.inc()


def track_cache_operation(
    operation: str,
    hit: bool,
    duration: float
):
    """
    Track cache operation.
    
    Args:
        operation: get/set/delete
        hit: True if cache hit (only relevant for 'get')
        duration: Operation duration in seconds
    """
    cache_operations_total.labels(
        operation=operation,
        hit='true' if hit else 'false'
    ).inc()
    
    cache_duration_seconds.labels(
        operation=operation
    ).observe(duration)


def track_kb_sync(
    duration: float,
    pages_synced: int,
    pages_failed: int,
    success: bool
):
    """
    Track KB sync operation.
    
    Args:
        duration: Sync duration in seconds
        pages_synced: Number of pages successfully synced
        pages_failed: Number of pages that failed
        success: Overall sync success
    """
    kb_sync_operations_total.labels(
        status='success' if success else 'failed'
    ).inc()
    
    kb_sync_duration_seconds.observe(duration)
    
    if pages_synced > 0:
        kb_sync_pages_total.labels(
            language='es',  # Simplification, could track per language
            status='success'
        ).inc(pages_synced)
    
    if pages_failed > 0:
        kb_sync_pages_total.labels(
            language='es',
            status='failed'
        ).inc(pages_failed)
    
    if success:
        import time
        kb_sync_last_success_timestamp.set(time.time())
```

### Paso 3: Instrumentar FastAPI (15 min)

**Modificar**: `src/api/main.py`

```python
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import REGISTRY, generate_latest
from fastapi.responses import Response
from src.api.core.metrics import set_system_info

# ... existing imports ...

app = FastAPI(
    title="Retail Recommender API",
    version="2.1.0"
)

# ══════════════════════════════════════════════════════════════════════════
# M2: PROMETHEUS METRICS
# ══════════════════════════════════════════════════════════════════════════

# Initialize system info
set_system_info(
    version="2.1.0-M2",
    environment=os.getenv("ENVIRONMENT", "development")
)

# Auto-instrument FastAPI
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Manual metrics endpoint (alternative)
@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(REGISTRY),
        media_type="text/plain; version=0.0.4"
    )

# ... rest of app ...
```

### Paso 4: Instrumentar Recommendation Engine (30 min)

**Modificar**: `src/api/routers/recommendations.py`

```python
from src.api.core.metrics import (
    track_recommendation,
    recommendations_by_category_total,
    diversity_score,
    fallback_used_total
)
import time

@router.post("/recommend", response_model=RecommendationResponse)
async def get_recommendations(request: RecommendationRequest):
    """Generate recommendations with metrics tracking."""
    
    start_time = time.time()
    strategy = request.strategy or "hybrid"
    market = request.market or "US"
    
    try:
        # Generate recommendations
        result = await recommendation_service.generate(request)
        
        # Track success
        duration = time.time() - start_time
        track_recommendation(
            strategy=strategy,
            market=market,
            duration=duration,
            success=True
        )
        
        # Track categories
        for product in result.products:
            if product.category:
                recommendations_by_category_total.labels(
                    category=product.category,
                    market=market
                ).inc()
        
        # Track diversity
        if hasattr(result, 'diversity_score'):
            diversity_score.labels(
                strategy=strategy
            ).observe(result.diversity_score)
        
        # Track fallback usage
        if result.used_fallback:
            fallback_used_total.labels(
                reason=result.fallback_reason or "unknown",
                market=market
            ).inc()
        
        return result
        
    except Exception as e:
        # Track failure
        duration = time.time() - start_time
        track_recommendation(
            strategy=strategy,
            market=market,
            duration=duration,
            success=False,
            error_type=type(e).__name__
        )
        raise
```

### Paso 5: Instrumentar Google Retail API (20 min)

**Modificar**: `src/api/integrations/google_retail_client.py`

```python
from src.api.core.metrics import track_google_api_call
import time

class GoogleRetailClient:
    
    async def predict(self, ...):
        """Predict with metrics tracking."""
        start_time = time.time()
        
        try:
            result = await self._make_prediction(...)
            
            duration = time.time() - start_time
            track_google_api_call(
                method="predict",
                duration=duration,
                status="success"
            )
            
            return result
            
        except RateLimitError as e:
            duration = time.time() - start_time
            track_google_api_call(
                method="predict",
                duration=duration,
                status="rate_limited"
            )
            raise
            
        except Exception as e:
            duration = time.time() - start_time
            track_google_api_call(
                method="predict",
                duration=duration,
                status="error"
            )
            raise
```

### Paso 6: Instrumentar Redis Cache (20 min)

**Modificar**: `src/api/core/redis_service.py`

```python
from src.api.core.metrics import track_cache_operation, cache_products_count
import time

class RedisService:
    
    async def get(self, key: str):
        """Get with metrics tracking."""
        start_time = time.time()
        
        try:
            value = await self._redis.get(key)
            duration = time.time() - start_time
            
            track_cache_operation(
                operation="get",
                hit=value is not None,
                duration=duration
            )
            
            return value
            
        except Exception as e:
            duration = time.time() - start_time
            track_cache_operation(
                operation="get",
                hit=False,
                duration=duration
            )
            raise
    
    async def update_cache_size_metric(self, market: str):
        """Update cache size gauge (call periodically)."""
        try:
            count = await self.count_products(market)
            cache_products_count.labels(market=market).set(count)
        except Exception as e:
            logger.warning("cache_size_metric_update_failed", error=str(e))
```

### Paso 7: Instrumentar KB Sync (15 min)

**Modificar**: `src/api/services/shopify_kb_sync.py`

```python
from src.api.core.metrics import track_kb_sync, kb_sync_semaphore_size

class ShopifyKBSyncService:
    
    def __init__(self, ...):
        # ... existing code ...
        
        # ✅ M2: Track semaphore size metric
        kb_sync_semaphore_size.set(semaphore_size)
    
    async def sync_all_pages(self, ...):
        """Sync with metrics tracking."""
        start_time = time.time()
        
        try:
            report = await self._perform_sync()
            
            duration = time.time() - start_time
            track_kb_sync(
                duration=duration,
                pages_synced=report.successful,
                pages_failed=report.failed,
                success=True
            )
            
            return report
            
        except Exception as e:
            duration = time.time() - start_time
            track_kb_sync(
                duration=duration,
                pages_synced=0,
                pages_failed=0,
                success=False
            )
            raise
```

---

## 🐳 DEPLOYMENT

### Docker Compose (Development)

**Crear**: `docker-compose.monitoring.yml`

```yaml
version: '3.8'

services:
  # Existing app service
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus
    volumes:
      - ./:/app
  
  # Prometheus server
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=15d'
  
  # Grafana dashboards
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_AUTH_ANONYMOUS_ENABLED=true
    volumes:
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources
      - grafana_data:/var/lib/grafana
    depends_on:
      - prometheus

volumes:
  prometheus_data:
  grafana_data:
```

### Prometheus Config

**Crear**: `monitoring/prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'retail-recommender'
    static_configs:
      - targets: ['app:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

### Grafana Datasource

**Crear**: `monitoring/grafana/datasources/prometheus.yml`

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
```

---

## 📊 DASHBOARDS

### Dashboard 1: Overview (Executive)

**Panels**:
1. **Requests/sec** (PromQL)
   ```promql
   rate(http_requests_total[5m])
   ```

2. **Error Rate %**
   ```promql
   rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) * 100
   ```

3. **P95 Latency**
   ```promql
   histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
   ```

4. **Recommendations/sec**
   ```promql
   rate(recommender_recommendations_total[5m])
   ```

### Dashboard 2: Recommendations (Detailed)

**Panels**:
1. **Recommendations by Strategy**
   ```promql
   rate(recommender_recommendations_total[5m]) by (strategy)
   ```

2. **Recommendations by Market**
   ```promql
   rate(recommender_recommendations_total[5m]) by (market)
   ```

3. **Average Generation Time**
   ```promql
   rate(recommender_generation_duration_seconds_sum[5m]) / rate(recommender_generation_duration_seconds_count[5m])
   ```

4. **Fallback Usage**
   ```promql
   rate(recommender_fallback_used_total[5m]) by (reason)
   ```

5. **Diversity Score Distribution**
   ```promql
   histogram_quantile(0.95, rate(recommender_diversity_score_bucket[5m]))
   ```

### Dashboard 3: Google Retail API

**Panels**:
1. **API Calls/sec**
   ```promql
   rate(recommender_google_api_calls_total[5m])
   ```

2. **API Latency p50/p95/p99**
   ```promql
   histogram_quantile(0.50, rate(recommender_google_api_duration_seconds_bucket[5m]))
   histogram_quantile(0.95, rate(recommender_google_api_duration_seconds_bucket[5m]))
   histogram_quantile(0.99, rate(recommender_google_api_duration_seconds_bucket[5m]))
   ```

3. **Rate Limits Hit**
   ```promql
   increase(recommender_google_api_rate_limits_total[1h])
   ```

### Dashboard 4: Cache Performance

**Panels**:
1. **Cache Hit Rate**
   ```promql
   rate(recommender_cache_operations_total{operation="get",hit="true"}[5m]) / 
   rate(recommender_cache_operations_total{operation="get"}[5m]) * 100
   ```

2. **Cache Operations/sec**
   ```promql
   rate(recommender_cache_operations_total[5m]) by (operation)
   ```

3. **Cache Latency**
   ```promql
   histogram_quantile(0.95, rate(recommender_cache_duration_seconds_bucket[5m])) by (operation)
   ```

4. **Products in Cache**
   ```promql
   recommender_cache_products_count by (market)
   ```

### Dashboard 5: KB Sync

**Panels**:
1. **Sync Duration**
   ```promql
   kb_sync_duration_seconds
   ```

2. **Pages Synced/hour**
   ```promql
   increase(kb_sync_pages_total{status="success"}[1h])
   ```

3. **Time Since Last Success**
   ```promql
   time() - kb_sync_last_success_timestamp
   ```

4. **Semaphore Size (M1)**
   ```promql
   kb_sync_semaphore_size
   ```

---

## 🚨 ALERTING RULES

**Crear**: `monitoring/prometheus/alerts.yml`

```yaml
groups:
  - name: retail_recommender_alerts
    interval: 30s
    rules:
      # High error rate
      - alert: HighErrorRate
        expr: |
          rate(http_requests_total{status=~"5.."}[5m]) / 
          rate(http_requests_total[5m]) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value | humanizePercentage }}"
      
      # High latency
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95, 
            rate(http_request_duration_seconds_bucket[5m])
          ) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High latency detected"
          description: "P95 latency is {{ $value }}s"
      
      # Google API rate limits
      - alert: GoogleAPIRateLimited
        expr: increase(recommender_google_api_rate_limits_total[5m]) > 0
        labels:
          severity: warning
        annotations:
          summary: "Google API rate limit hit"
          description: "{{ $value }} rate limit hits in last 5min"
      
      # Cache miss rate high
      - alert: LowCacheHitRate
        expr: |
          rate(recommender_cache_operations_total{operation="get",hit="true"}[5m]) / 
          rate(recommender_cache_operations_total{operation="get"}[5m]) < 0.7
        for: 10m
        labels:
          severity: info
        annotations:
          summary: "Cache hit rate below 70%"
          description: "Current hit rate: {{ $value | humanizePercentage }}"
      
      # KB sync failed
      - alert: KBSyncFailed
        expr: kb_sync_operations_total{status="failed"} > 0
        labels:
          severity: warning
        annotations:
          summary: "KB sync failed"
          description: "KB sync operation failed"
```

---

## 📋 PLAN DE IMPLEMENTACIÓN

### Fase 1: Core Setup (2-3 horas)

**Día 1 - Mañana**:
1. ✅ Instalar dependencias (5min)
2. ✅ Crear `src/api/core/metrics.py` (30min)
3. ✅ Instrumentar FastAPI en `main.py` (15min)
4. ✅ Test `/metrics` endpoint (10min)

**Expected output**:
```bash
curl http://localhost:8000/metrics

# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",path="/health"} 42

# HELP recommender_recommendations_total Total recommendations
# TYPE recommender_recommendations_total counter
recommender_recommendations_total{strategy="hybrid",market="US",success="true"} 0
```

### Fase 2: Instrumentación (3-4 horas)

**Día 1 - Tarde**:
1. ✅ Instrumentar recommendation engine (30min)
2. ✅ Instrumentar Google Retail API client (20min)
3. ✅ Instrumentar Redis service (20min)
4. ✅ Instrumentar KB sync (15min)
5. ✅ Testing integration (30min)

### Fase 3: Monitoring Stack (2 horas)

**Día 2 - Mañana**:
1. ✅ Setup Prometheus (30min)
2. ✅ Setup Grafana (30min)
3. ✅ Create dashboards (1h)

### Fase 4: Alerting (1 hora)

**Día 2 - Tarde**:
1. ✅ Configure alerting rules (30min)
2. ✅ Test alerts (30min)

### Fase 5: Documentation & Deploy (1 hora)

**Día 2 - Final**:
1. ✅ Document metrics (30min)
2. ✅ Deploy to staging (30min)

---

## 🧪 TESTING

### Test 1: Metrics Exposure

```bash
# Start app
uvicorn src.api.main:app --reload

# Check metrics endpoint
curl http://localhost:8000/metrics | grep recommender

# Expected: Metrics in Prometheus format
```

### Test 2: Metrics Collection

```bash
# Generate load
for i in {1..100}; do
  curl -X POST http://localhost:8000/api/recommend \
    -H "Content-Type: application/json" \
    -d '{"user_id": "test", "market": "US"}'
done

# Check metrics
curl http://localhost:8000/metrics | grep recommender_recommendations_total
# Expected: Count = 100
```

### Test 3: Prometheus Scraping

```bash
# Start monitoring stack
docker-compose -f docker-compose.monitoring.yml up -d

# Open Prometheus
open http://localhost:9090

# Query:
rate(recommender_recommendations_total[5m])

# Expected: Graph showing requests/sec
```

### Test 4: Grafana Dashboards

```bash
# Open Grafana
open http://localhost:3000
# Login: admin/admin

# Navigate to Dashboards
# Expected: See "Retail Recommender" dashboards
```

---

## 📊 SLIs & SLOs

### Service Level Indicators (SLIs)

```yaml
# Availability
SLI_availability:
  metric: http_requests_total{status!~"5.."}
  target: 99.9%

# Latency
SLI_latency_p95:
  metric: http_request_duration_seconds{quantile="0.95"}
  target: < 500ms

# Error Rate
SLI_error_rate:
  metric: http_requests_total{status=~"5.."}
  target: < 0.1%

# Recommendation Success Rate
SLI_recommendation_success:
  metric: recommender_recommendations_total{success="true"}
  target: > 99%
```

### Service Level Objectives (SLOs)

```
Monthly Targets:
- Availability: 99.9% (43 minutes downtime/month)
- P95 Latency: < 500ms (95% of requests)
- Error Rate: < 0.1% (1 error per 1000 requests)
- Recommendation Success: > 99%
```

---

## 💰 ROI ESTIMADO

**Esfuerzo**: 10-12 horas total
- Core setup: 2-3h
- Instrumentación: 3-4h
- Monitoring stack: 2h
- Alerting: 1h
- Docs & deploy: 1-2h

**Beneficios**:
1. ✅ **Proactive monitoring**: Detectar problemas antes que usuarios
2. ✅ **Data-driven decisions**: Métricas para optimizaciones
3. ✅ **SLO tracking**: Cumplimiento de SLAs
4. ✅ **Incident response**: MTTR reduction (Mean Time To Repair)
5. ✅ **Capacity planning**: Growth projections basadas en datos

**ROI**: **EXCELENTE** - Investment único, beneficio continuo

---

## ⚠️ CONSIDERACIONES

### Performance Impact

**Overhead de métricas**: Despreciable (~1-2ms por request)
- Counter.inc(): <0.01ms
- Histogram.observe(): <0.1ms
- Total: <1% overhead

**Mitigación**: Ya validado en producción de sistemas similares.

### Storage Requirements

**Prometheus retention**: 15 días
- Estimado: 1GB por 15 días (con scrape 15s)
- Aceptable para desarrollo/staging

**Production**: Considerar remote storage (GCS, S3) para >30 días.

---

## 📚 DOCUMENTACIÓN

### README Update

```markdown
## Monitoring

### Metrics Endpoint

```bash
curl http://localhost:8000/metrics
```

### Grafana Dashboards

```bash
docker-compose -f docker-compose.monitoring.yml up -d
open http://localhost:3000  # admin/admin
```

### Key Metrics

- `recommender_recommendations_total`: Total recommendations
- `recommender_generation_duration_seconds`: Recommendation latency
- `recommender_cache_operations_total`: Cache operations
- `kb_sync_duration_seconds`: KB sync duration

### Alerts

Configured in `monitoring/prometheus/alerts.yml`:
- High error rate (>5%)
- High latency (>2s p95)
- Google API rate limits
- Low cache hit rate (<70%)
- KB sync failures
```

---

## 🎯 SUCCESS CRITERIA

**M2 completado cuando**:
- [ ] `/metrics` endpoint expone métricas Prometheus
- [ ] 15+ custom metrics implemented
- [ ] Prometheus scraping funcional
- [ ] 5 Grafana dashboards creados
- [ ] 5 alerting rules configuradas
- [ ] Documentation actualizada
- [ ] Deployed to staging
- [ ] 24h monitoring sin issues

---

**Autor**: Yasmani Roque  
**Fecha**: 14 Febrero 2026  
**Estado**: Planificado - Listo para implementación  
**Tiempo estimado**: 10-12 horas  
**Próximo paso**: Aprobar plan → Comenzar Fase 1

