Diagnóstico de Estado del Sistema — Retail Recommender v2.1.0
Lo que veo con claridad
Antes de cualquier recomendación de nueva feature, es importante ser honesto sobre lo que revelan los números del filesystem:

1. Deuda Técnica — Inventario Real
Archivos duplicados / versiones muertas identificadas:
src/api/
├─ main.py                         ← v0.3.0, OBSOLETO
├─ main_cached.py                  ← Versión experimental, sin usar
├─ main_distributed.py             ← Versión experimental, sin usar
├─ main_precomputed.py             ← Versión experimental, sin usar
├─ main_tfidf.py                   ← Versión experimental, sin usar
├─ main_unified_redis.py           ← ACTIVO (84 KB) ← el real
├─ main_unified_redis copy.py      ← copia manual, 66 KB
├─ main_unified_redis copy 2.py    ← copia manual, 81 KB
├─ main_unified_redis.py.bak_...   ← backup, 66 KB
└─ main_unified_redis.py.backup_.. ← backup, 66 KB
Solo en main_, hay ~400 KB de código muerto que vive al lado del activo. No causan bugs, pero sí causan confusión, riesgo de editar el archivo equivocado, y tiempo perdido en búsquedas.
src/api/core/
├─ mcp_conversation_handler.py               ← ACTIVO (51 KB)
├─ mcp_conversation_handler.py_backup_07012026
├─ mcp_conversation_handler_BACKUP_21122025.py
├─ mcp_conversation_handler_BACKUP_29012026.py  ← 3 backups inline

├─ product_cache.py                          ← ACTIVO
├─ product_cache.py.backup_07022026          ← backup inline

├─ knowledge_base_v2.py                      ← ACTIVO
├─ knowledge_base_v2.py.backup_06022026      ← backup inline
├─ knowledge_base_v2.py.backup_language_fallback

├─ redis_client.py                           ← ¿activo?
├─ redis_client.py.backup_07022026

├─ redis_config_fix.py                       ← ¿activo o fix temporal?
├─ redis_config_optimized.py                 ← ¿cuál es el canónico?

├─ enhanced_hybrid_recommender.py            ← ¿activo?
├─ enhanced_hybrid_recommender copy.py       ← copia manual

├─ mcp_router_conservative_enhancement.py    ← ¿cuál es el activo?
├─ mcp_router_conservative_enhancement_balanced.py
└─ mcp_router_performance_patch.py
El patrón es claro: en lugar de usar Git como sistema de versionado, el proyecto está usando el filesystem como Git. Esto es el mayor riesgo de mantenibilidad.

2. Problema de Performance — Hipótesis
Mencionas "algún problema de performance". Con el código que he leído, tengo hipótesis concretas:
Hipótesis A — configure_structlog comentado:
python# main_unified_redis.py, línea ~64
# configure_structlog(
#     log_level=log_level,
#     json_format=json_format
# )
```
H1 (Structured Logging) está implementado pero **desactivado**. El logger structlog funciona sin configuración explícita pero no está optimizado para el entorno de producción.

**Hipótesis B — Redis health check timeout agresivo:**
El startup hace health checks anidados con timeouts sucesivos (10s → 8s → operación real). Si Redis tiene latencia variable, esto puede causar slow startups o fallbacks innecesarios.

**Hipótesis C — Archivos muertos cargados en import:**
Python importa todos los módulos en el path. Si alguno de los `redis_config_fix.py`, `redis_config_optimized.py`, o archivos `emergency_*` tienen código a nivel de módulo que ejecuta en import time, añaden latencia de startup.

---

### 3. Estado Real del Plan — Post-M5
```
FASE 0  H1 H2 H3 H4    ████████████  COMPLETADA  ✅
FASE 1  M1 M2           ████████████  COMPLETADA  ✅
FASE 2  M3 M4 M5        ████████████  COMPLETADA  ✅
FASE 3  L1 L2 L3 L4    ░░░░░░░░░░░░  PENDIENTE
Antes de entrar a Fase 3, la deuda técnica acumulada aumenta el costo de cada nueva feature. L1, L2, L3 cada uno va a añadir más archivos a un directorio que ya es difícil de navegar.