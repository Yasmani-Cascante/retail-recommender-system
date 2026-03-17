# DCT — Consolidación de Observabilidad
## Retail Recommender System v2.1.0

**Fecha:** 05 de Marzo, 2026
**Sesión:** Eliminación de Deuda de Observabilidad
**Estado al cierre:** ✅ Tareas 1 y 3 completadas | ⬜ Tarea 2 (GCP PASO 7) pendiente de validación manual

---

## Resumen Ejecutivo

Se ejecutaron las tres deudas de observabilidad identificadas en `DECISION_ESTRATEGICA_L4_vs_CONSOLIDACION_05032026.md`:

| Tarea | Estado | Detalle |
|-------|--------|---------|
| **#1** configure_structlog() activado | ✅ COMPLETADO | 1 cambio quirúrgico en main_unified_redis.py |
| **#2** GCP Cloud Monitoring PASO 7 | ⬜ PENDIENTE MANUAL | Requiere credenciales GCP de Yasmani |
| **#3** Housekeeping filesystem | ✅ COMPLETADO | src/api/ y src/api/core/ limpios |

---

## Tarea #1 — configure_structlog() ACTIVADO

### Cambio Aplicado

**Archivo:** `src/api/main_unified_redis.py` — líneas 56-62

```python
# ANTES (roto — logs sin formato JSON):
# configure_structlog(
#     log_level=log_level,
#     json_format=json_format
# )

# DESPUÉS (funcional — logs JSON activos):
# ✅ H1 ACTIVADO (05/03/2026): configure_structlog descomentado — logs JSON activos en producción
configure_structlog(
    log_level=log_level,
    json_format=json_format
)
```

### Impacto
- Los logs en Cloud Run ahora se emiten en formato JSON estructurado cuando `LOG_JSON_FORMAT=true`
- GCP Cloud Logging puede indexar campos: `level`, `timestamp`, `event`, `module`, `app_name`, `environment`, `version`
- Las correlaciones trace↔log↔metric son posibles
- Prerequisito técnico de L4 (features ML desde logs) ahora satisfecho

### Variable de Entorno Requerida en Cloud Run
```
LOG_JSON_FORMAT=true    ← Asegurar que está configurada en Cloud Run env vars
LOG_LEVEL=INFO          ← Confirmar nivel de producción
```

---

## Tarea #2 — GCP Cloud Monitoring PASO 7 (PENDIENTE)

### Lo que falta hacer (manual — requiere credenciales GCP)

**Paso 2.1 — Verificar variables en Cloud Run Console:**

En GCP Console → Cloud Run → `retail-recommender` → Edit & Deploy → Variables & Secrets:
```
GOOGLE_PROJECT_ID=retail-recommendations-449216
GCP_MONITORING_ENABLED=true
SERVICE_NAME=retail-recommender
SERVICE_VERSION=2.1.0
LOG_JSON_FORMAT=true
```

**Paso 2.2 — Verificar scraping activo (Cloud Shell o local con gcloud):**
```bash
gcloud monitoring time-series list \
  --project=retail-recommendations-449216 \
  --filter="metric.type='custom.googleapis.com/recommender_requests_total'" \
  --interval-start-time="$(date -u -d '30 minutes ago' +%Y-%m-%dT%H:%M:%SZ)"
```
Criterio de done: respuesta contiene al menos 1 serie temporal con puntos de datos.

**Paso 2.3 — Verificar alertas:**

En GCP Console → Monitoring → Alerting → verificar que al menos 1 de las 5 alertas configuradas muestre estado `OK` o `Alerting` (no `No data`).

**Paso 2.4 — Smoke test post-activación:**
```bash
curl https://retail-recommender-lzf2y6pspa-uc.a.run.app/health
# Luego en Cloud Logging buscar:
# resource.type="cloud_run_revision" AND jsonPayload.event="structured_logging_initialized"
```

---

## Tarea #3 — Housekeeping Filesystem COMPLETADO

### src/api/ — Antes vs Después

**ANTES:** 18 archivos, ~493KB | **DESPUÉS:** 9 archivos, ~169KB

Archivos archivados en `src/api/0_backups/main/`:
```
main_v0.3.0_obsoleto.py               ← era main.py
main_cached_experimental.py           ← era main_cached.py
main_distributed_experimental.py      ← era main_distributed.py
main_precomputed_experimental.py      ← era main_precomputed.py
main_tfidf_experimental.py            ← era main_tfidf.py
main_unified_redis_copy_manual_A.py   ← era "main_unified_redis copy.py"
main_unified_redis_copy_manual_B.py   ← era "main_unified_redis copy 2.py"
main_unified_redis.py.backup_11122025
main_unified_redis.py.bak_14012026
```

### src/api/core/ — Antes vs Después

**ANTES:** 63 archivos | **DESPUÉS:** 47 archivos activos

Archivos archivados en `src/api/core/0_legacy/`:
```
redis_config_fix_obsoleto.py                    ← OBSOLETO. Canónico: redis_config_optimized.py
mcp_router_variants/mcp_router_conservative_enhancement_balanced.py
mcp_router_variants/mcp_router_performance_patch.py
mcp_conversation_handler_BACKUP_21122025.py
mcp_conversation_handler_BACKUP_29012026.py
mcp_conversation_handler.py_backup_07012026
knowledge_base_v2.py.backup_06022026
knowledge_base_v2.py.backup_language_fallback
enhanced_hybrid_recommender_copy.py
intent_detection.py.backup_04032026
intent_types.py.backup_04032026
intelligent_personalization_cache.py.backup_09102025
config.py.backup
product_cache.py.backup_07022026
redis_client.py.backup_07022026
store.py.backup_13022026
```

### Ambigüedades Resueltas con Evidencia

| Ambigüedad | Canónico | Evidencia |
|------------|----------|-----------|
| `redis_config_fix.py` vs `redis_config_optimized.py` | **`redis_config_optimized.py`** | `redis_service.py` línea 21: `from src.api.core.redis_config_optimized import create_optimized_redis_client` → `service_factory.py` importa `redis_service` → main activo |
| 3 variantes `mcp_router_*.py` | **`mcp_router_conservative_enhancement.py`** | `main_unified_redis.py` línea ~162: `from src.api.core.mcp_router_conservative_enhancement import apply_performance_enhancement_to_router` |

---

## Mapa de Archivos Activos Post-Housekeeping

### Archivos Canónicos en src/api/core/

```
logging_config.py              ← H1: configure_structlog() (AHORA ACTIVO)
prometheus_metrics.py          ← M2: contadores, histogramas, gauges
observability_manager.py       ← ObservabilityManager unificado
config.py                      ← RecommenderSettings (Pydantic v2)
redis_service.py               ← Capa de abstracción Redis (usa redis_config_optimized)
redis_config_optimized.py      ← Config Redis canónica ← ⚠️ NO ARCHIVAR
redis_client.py                ← Cliente Redis bajo nivel
mcp_conversation_handler.py    ← Handler conversacional MCP activo
mcp_router_conservative_enhancement.py  ← Enhancement MCP activo ← ⚠️ NO ARCHIVAR
knowledge_base_v2.py           ← KB activo (con L1 markdownify)
intent_detection.py            ← Intent detection (ML + rule-based)
intent_types.py                ← Enum de intents
```

---

## Criterios de Done — Estado Final

```
✅ configure_structlog() ACTIVO en main_unified_redis.py
⬜ Variables GCP Monitoring verificadas en Cloud Run Console
✅ src/api/ sin archivos main_*.py muertos (archivados en 0_backups/)
✅ Ambigüedad redis_config_*.py resuelta con evidencia del código
✅ Backups inline archivados en 0_legacy/
✅ docs/L4_DATA_REQUIREMENTS.md creado con función objetivo definida
⬜ Smoke test post-deploy confirma logs JSON en Cloud Logging
```

---

## Próximos Pasos para la Siguiente Sesión

1. **Verificar GCP Cloud Monitoring PASO 7** — Ejecutar los comandos del Paso 2.1-2.4 arriba
2. **Validar logs JSON en Cloud Logging** — Post-deploy: buscar `jsonPayload.event="structured_logging_initialized"`
3. **Monitorear `kb_content_versions`** — Ejecutar Query 1-3 de `L4_DATA_REQUIREMENTS.md` semanalmente
4. **Smoke test completo** — Verificar que el sistema sigue al 100% post-housekeeping

---

## Notas para el Próximo Ingeniero/Sesión

- El `main.py` que existía en `src/api/` era una versión muy antigua (v0.3.0). El único main activo es `main_unified_redis.py`.
- El directorio `legacy/` en `src/api/` existía previamente — los archivos de esta sesión fueron a `0_backups/` para mantener consistencia con la convención de la sesión.
- `dependencies_backup_09112025.py` NO fue archivado intencionalmente — evaluar si `dependencies.py` activo es distinto antes de mover.
