# Informe Técnico — Fase M3: GCP Cloud Monitoring
<!-- Notion: https://www.notion.so/323cfd3fcb288136b9abe1eaceaa266b -->

**Proyecto:** Retail Recommender System v2.1.0  
**Fase:** M3 — GCP Cloud Monitoring Integration  
**Período:** Febrero–Marzo 2026  
**Estado:** ✅ COMPLETADO Y VALIDADO  
**Fecha de cierre:** 15 de Marzo de 2026

---

## 1. Contexto del Sistema

El Retail Recommender System v2.1.0 es un motor de recomendaciones híbrido para e-commerce desplegado en Google Cloud Run. Combina cuatro fuentes de inteligencia: TF-IDF (content-based filtering), Google Cloud Retail API (collaborative filtering), Claude AI (conversational intelligence) y Shopify CMS/MCP (base de conocimiento).

**Stack activo en producción:**
- **Deploy:** Cloud Run — `retail-recommender-lzf2y6pspa-uc.a.run.app`
- **Revisión activa:** `retail-recommender-00045-2nk` (metrics_count=111)
- **Cache:** Redis Enterprise (`redis-14272.c259.us-central1-2.gce.redns.redis-cloud.com`)
- **Base de datos:** PostgreSQL Neon (`ep-blue-firefly-ajafeedi.c-3.us-east-2.aws.neon.tech`)
- **Proyecto GCP:** `retail-recommendations-449216` (Number: 178362262166)
- **Catálogo:** 3,062 productos indexados por TF-IDF

---

## 2. Arquitectura de Observabilidad

```
Aplicación FastAPI
  └── /metrics endpoint (Prometheus format)
        └── GCPMetricsExporter (push cada ~67s)
              └── custom.googleapis.com/ (Cloud Monitoring)
                    ├── Dashboards (3 custom)
                    ├── Alertas (5 activas)
                    └── Metrics Explorer
```

**Separación de namespaces — decisión de arquitectura clave:**

| Namespace | Fuente | Resource Type en GCP |
|---|---|---|
| `custom.googleapis.com/` | GCPMetricsExporter (push manual) | `generic_task` |
| `run.googleapis.com/` | Cloud Run nativo (automático) | `cloud_run_revision` |

Esta separación determina cómo construir todos los charts y alertas. El error más común durante M3 fue usar PromQL nativo en charts de dashboards — solo funciona con Google Managed Prometheus, no con Custom Metrics push.

---

## 3. Archivos Modificados

| Archivo | Cambio |
|---|---|
| `src/api/main_unified_redis.py` | Fix shadow de rutas + imports Prometheus |
| `src/api/core/prometheus_metrics.py` | Añadido "default" a `_MARKETS` |
| `src/api/core/gcp_metrics_exporter.py` | Fix timeout=30 + API enums |
| `src/api/core/logging_config.py` | Fix duplicate StreamHandler |
| `tests/smoke/smoke_observability_M3.ps1` | Script de smoke test (v1.1) |

**JSONs de dashboards corregidos** en `docs/0_plans/.../GCP_Cloud_Monitoring_16022026/`:
- `Business_Metrics_Dashboard_FIXED.json`
- `System_Health_Dashboard_FIXED.json`
- `HTTP_API_Performance_Dashboard_FIXED.json`

---

## 4. Métricas Implementadas

### Custom Metrics (`custom.googleapis.com/`)

| Métrica | Tipo | Labels |
|---|---|---|
| `recommender_requests_total` | Counter | market, strategy |
| `recommender_duration_seconds` | Histogram | strategy |
| `recommender_errors_total` | Counter | error_type |
| `kb_sync_operations_total` | Counter | status |
| `kb_sync_duration_seconds` | Histogram | — |
| `kb_sync_semaphore_size` | Gauge | — |
| `google_retail_api_calls_total` | Counter | method, status |
| `google_retail_api_duration_seconds` | Histogram | method |
| `http_requests_total` | Counter | method, endpoint, status_code |

### Métricas Cloud Run (automáticas)

- `run.googleapis.com/request_count`
- `run.googleapis.com/request_latencies`
- `run.googleapis.com/container/instance_count`

### Pre-inicialización de Label Sets

Patrón crítico: llamar `.labels()` al importar el módulo para registrar combinaciones de labels desde el inicio. Sin esto, el MetricDescriptor en GCP rechaza samples con nuevas combinaciones.

```python
_MARKETS = ["us", "es", "mx", "cl", "default"]
_STRATEGIES = ["hybrid", "tfidf", "google_retail", "fallback", "mcp_enhanced"]
for _m in _MARKETS:
    for _s in _STRATEGIES:
        recommendation_requests_total.labels(market=_m, strategy=_s)
```

---

## 5. Bugs Encontrados y Correcciones

### Bug 1 — Duplicate Log Output
**Causa:** `logging.basicConfig()` añadía un segundo `StreamHandler` junto al handler de structlog.  
**Fix:** Eliminado `basicConfig()` redundante en `logging_config.py`.

### Bug 2 — Dashboards GCP sin datos (namespace incorrecto)
**Causa:** Documentación de diseño asumía Google Managed Prometheus (`prometheus.googleapis.com/`). El sistema usa Custom Metrics push (`custom.googleapis.com/`).  
**Fix:** Reescritura de los 3 JSONs de dashboard usando `timeSeriesFilter` con namespace correcto y `ALIGN_DELTA + REDUCE_PERCENTILE_95` en lugar de PromQL.  
**Regla operativa:** Siempre usar el Builder visual de GCP para construir charts — el editor de código/PromQL falla silenciosamente para métricas `custom.googleapis.com/`.

### Bug 3 — Alertas con sintaxis PromQL incorrecta
**Causa:** Alertas de latencia y KB sync usaban `histogram_quantile()` y `{label="value"}` (sintaxis Prometheus pura, no MQL de GCP).  
**Fix:** Recreadas usando el Builder visual de GCP.

### Bug 4 — `recommender_duration_seconds_count` vs Distribution
**Causa:** Dashboard Latency p95 usaba el sub-campo `_count` del histograma con `ALIGN_RATE`, produciendo `req/sec` en lugar de latencia.  
**Fix:** Cambio a `recommender_duration_seconds` (Distribution) con `ALIGN_DELTA + REDUCE_PERCENTILE_95`.

### Bug 5 — Métricas inexistentes en dashboards
**Causa:** `http_requests_inprogress` y `http_request_duration_seconds_bucket` no están definidas en `prometheus_metrics.py`.  
**Fix:** Reemplazadas por métricas Cloud Run nativas.

---

## 6. Alertas Configuradas

| Alerta | Severidad | Condición |
|---|---|---|
| `[CRITICAL] Service Down` | Critical | Uptime check falla |
| `[CRITICAL] High HTTP Error Rate` | Critical | Error rate > umbral |
| `[CRITICAL] Extreme API Latency` | Critical | p95 > 5,000ms |
| `[WARNING] Elevated API Latency` | Warning | p95 > 2,000ms |
| `[WARNING] KB Sync Failures` | Warning | Rate fallos > 0.01/s |

**MQL de alertas de latencia:**
```mql
fetch cloud_run_revision
| metric 'run.googleapis.com/request_latencies'
| filter (resource.service_name == 'retail-recommender')
| group_by 5m, [value_request_latencies_percentile: percentile(value.request_latencies, 95)]
| every 5m
| condition val() > 5000 'ms'  -- CRITICAL (usar 2000 para WARNING)
```

**MQL KB Sync Failures:**
```mql
fetch generic_task
| metric 'custom.googleapis.com/kb_sync_operations_total'
| filter (metric.status == 'failed')
| align rate(15m)
| every 15m
| condition val() > 0.01 '{not_a_unit}/s'
```

**Nota cosmética:** Warning de unidades en alerta KB Sync. Fix: `cast_units(val(), "") > 0.01`.  
**Incidentes activos:** 0

---

## 7. Smoke Tests — Resultados

**Script:** `tests/smoke/smoke_observability_M3.ps1` (v1.1)

| Check | RUN 1 | RUN 2 |
|---|---|---|
| PASS | 15 | 19 |
| WARN | 1 | 0 |
| FAIL | 2 | 0 |
| Score | 83% | **100%** |

Los 2 FAILs del RUN 1 fueron artefactos de cold start (~20s). El script v1.1 incorpora retry extendido (25s + 30s).

### Datos de producción confirmados

| Hallazgo | Valor |
|---|---|
| `recommender_requests_total` | 10 total (5+5 entre los dos runs) |
| Latencia algoritmo puro | ~213ms |
| Overhead HTTP + FastAPI + Redis | ~160ms |
| Latencia p95 total | ~450ms |
| GCPMetricsExporter | 5 exports estables, metrics_count=111, intervalo ~67s |
| Cloud Run p50 | 31.384ms |
| Cloud Run p95 | 111.598ms |
| Errores 4xx/5xx | 0% |

**Insight de performance para L4:** El presupuesto de latencia disponible para un modelo ML es ~300ms para mantener el p95 total por debajo de 500ms.

---

## 8. Estado Google Retail API

**Completamente implementada e integrada.** No hay código pendiente.

- `RetailAPIRecommender` en `src/recommenders/retail_api.py` — completo
- `EnhancedHybridRecommenderWithExclusion` la llama con `content_weight=0.5`
- 3,062 productos importados vía GCS (`retail-recommendations-449216_cloudbuild/imports/`)
- `google_retail_calls_total` y `google_retail_api_duration_seconds` instrumentados

Los charts aparecen vacíos porque la API devuelve `[]` para user IDs de prueba (sin historial de eventos). Se activarán solos con tráfico real de usuarios.

---

## 9. Guía de Consulta Rápida — On-Call

**Orden de diagnóstico ante un incidente:**
1. **System Health** — ¿Instancias activas? ¿Error Trends?
2. **HTTP & API Performance** — ¿En qué capa? ¿Latencia p99 anormal?
3. **Business Metrics** — ¿Qué componente? ¿Algoritmo, KB sync, estrategia?
4. **Cloud Logging** — `severity=ERROR resource.type=cloud_run_revision`

**Links GCP:**
- Dashboards: `https://console.cloud.google.com/monitoring/dashboards?project=retail-recommendations-449216`
- Alertas: `https://console.cloud.google.com/monitoring/alerting?project=retail-recommendations-449216`
- Logs: `https://console.cloud.google.com/logs/query?project=retail-recommendations-449216`

---

## 10. Próximos Pasos Técnicos

1. **L4 ML Content Optimization** — Inicio ~26 Marzo 2026 cuando `kb_content_versions` tenga ≥3 semanas de historial.
2. **Dead code consolidation** — ~400KB de código muerto antes de L4.
3. **KB Sync Duration p95** — Verificar instrumentación del timer en `ShopifyKBSyncService` si el chart sigue vacío con tráfico real.
4. **Alerta KB Sync fix cosmético** — `cast_units(val(), "") > 0.01`.

---

*DCT — Fase M3 GCP Cloud Monitoring | Versión 1.0 | 15 de Marzo de 2026*
