# ✅ FASE M3 - PASO 7: VALIDACIÓN MANUAL EN GCP

**Proyecto**: Retail Recommender System v2.1.0  
**Fase**: M3 - GCP Cloud Monitoring Integration  
**Documento**: Paso 7 de 8  
**Fecha creación**: 10 Marzo 2026  
**Tiempo estimado**: 20-30 minutos  
**Estado**: 📋 PENDIENTE DE EJECUCIÓN

---

## 🎯 OBJETIVO DEL PASO 7

Confirmar manualmente en GCP Console que toda la infraestructura de observabilidad
configurada en los pasos 1–6 está activa, recibiendo datos y alertando correctamente.

Este paso **no requiere cambios de código** — es 100% verificación de estado.

> **Prerequisitos obligatorios antes de ejecutar este paso:**
> - ✅ PASO 1–5: APIs habilitadas, IAM configurado, dashboards y alertas creados
> - ✅ PASO 6: Variables M3 (`GCP_MONITORING_ENABLED=true`, `LOG_JSON_FORMAT=true`) presentes en Cloud Run
> - ✅ **Fix H1 aplicado**: `configure_structlog()` activo y emitiendo `structured_logging_initialized`
> - ✅ **Fix Logging (10/03/2026)**: `logging_config.py` corregido — handler duplicado eliminado, logs ya no se emiten dos veces

---

## 📋 PASO 7.1 — Verificar variables en Cloud Run Console

**Dónde:** GCP Console → Cloud Run → `retail-recommender` → Edit & Deploy New Revision → Variables & Secrets

### Variables requeridas (verificar todas presentes):

| Variable | Valor esperado | Propósito |
|---|---|---|
| `GOOGLE_PROJECT_ID` | `retail-recommendations-449216` | Proyecto GCP para métricas |
| `GCP_MONITORING_ENABLED` | `true` | Habilita envío a Cloud Monitoring |
| `SERVICE_NAME` | `retail-recommender` | Label en métricas y logs |
| `SERVICE_VERSION` | `2.1.0` | Label de versión |
| `LOG_JSON_FORMAT` | `true` | Activa JSON logging (requerido por Cloud Logging) |
| `LOG_LEVEL` | `INFO` | Nivel mínimo de logs indexados |

**Criterio ✅:** Todas las 6 variables presentes con los valores exactos de la tabla.

**⚠️ Si alguna falta:** Agregarla directamente en la UI de Cloud Run antes de continuar.
No hacer nuevo deploy solo para esto — editar la revisión activa.

---

## 📋 PASO 7.2 — Verificar scraping de métricas Prometheus activo

Este paso confirma que GCP Cloud Monitoring está **recibiendo datos reales** del endpoint
`/metrics` de nuestra app.

### Opción A: Via gcloud CLI (recomendado)

```bash
# Verificar series temporales de nuestra métrica custom principal
gcloud monitoring time-series list \
  --project=retail-recommendations-449216 \
  --filter="metric.type='custom.googleapis.com/recommender_requests_total'" \
  --interval-start-time="$(date -u -d '30 minutes ago' +%Y-%m-%dT%H:%M:%SZ)"
```

**En Windows PowerShell** (alternativa):
```powershell
# Calcular timestamp de hace 30 minutos
$startTime = (Get-Date).AddMinutes(-30).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

gcloud monitoring time-series list `
  --project=retail-recommendations-449216 `
  --filter="metric.type='custom.googleapis.com/recommender_requests_total'" `
  --interval-start-time="$startTime"
```

**Criterio ✅:** Output contiene al menos 1 entrada con campo `points` no vacío.  
**Criterio ❌:** Output vacío `[]` → el scraping no está activo (ver sección Troubleshooting).

### Opción B: Via GCP Console

1. GCP Console → Monitoring → Metrics Explorer
2. En "Select a metric": escribir `recommender_requests_total`
3. Seleccionar la métrica en el dropdown
4. Verificar que el gráfico muestra datos en las últimas 24h

---

## 📋 PASO 7.3 — Verificar estado de las 5 alertas configuradas

**Dónde:** GCP Console → Monitoring → Alerting

### Las 5 alertas esperadas:

| Alerta | Severity | Estado esperado |
|---|---|---|
| `[CRITICAL] Service Down` | Critical | OK (verde) si el servicio está up |
| `[CRITICAL] High HTTP Error Rate` | Critical | OK (verde) en operación normal |
| `[CRITICAL] Extreme API Latency` | Critical | OK (verde) en operación normal |
| `[WARNING] Elevated API Latency` | Warning | OK (verde) en operación normal |
| `[WARNING] KB Sync Failures` | Warning | OK (verde) si KB sync funciona |

**Criterio ✅:** Todas las alertas muestran estado `OK` o `Alerting`.  
**Criterio ❌:** Una o más alertas muestran `No data` → GCP no está recibiendo las métricas
que activan esa alerta (problema de scraping, ver Troubleshooting).

> **Nota importante sobre `[WARNING] KB Sync Failures`:**  
> Si la alerta muestra `No data` aisladamente pero el resto está OK, puede ser normal:
> esta alerta depende de la métrica `kb_sync_failures_total` que solo tiene valor > 0 cuando
> hay fallos reales. Si nunca hubo fallos, GCP puede reportar "no data" para esa serie.
> Esto es aceptable — no es una señal de problema.

---

## 📋 PASO 7.4 — Smoke test H1: verificar structured logging activo en Cloud Logging

Este paso valida que el fix de H1 (`configure_structlog()` reactivado el 10/03/2026)
y el fix de logging duplicado están funcionando correctamente en producción.

### Step 1: Generar un request real

```bash
# Hacer un request al health endpoint para forzar un log de startup fresco
curl -X GET https://retail-recommender-lzf2y6pspa-uc.a.run.app/health \
  -H "Accept: application/json"
```

O si prefieres un restart limpio del servicio (genera los logs de startup completos):
```bash
gcloud run services update retail-recommender \
  --region=us-central1 \
  --project=retail-recommendations-449216 \
  --no-traffic  # no redirige tráfico, solo fuerza restart
```

### Step 2: Verificar en Cloud Logging

**Dónde:** GCP Console → Cloud Logging → Log Explorer

**Query para validar H1 activo:**
```
resource.type="cloud_run_revision"
resource.labels.service_name="retail-recommender"
jsonPayload.event="structured_logging_initialized"
```

**Criterio ✅:** Aparece al menos 1 entrada con:
- `jsonPayload.event` = `"structured_logging_initialized"`
- `jsonPayload.h1_phase` = `"active"`
- `jsonPayload.json_format` = `true`

**Criterio ❌:** No aparece ninguna entrada → `configure_structlog()` no se está llamando
o `LOG_JSON_FORMAT` no está en `true` en Cloud Run (los logs no llegan como JSON a Cloud Logging).

**Query adicional para verificar que NO hay logs duplicados:**
```
resource.type="cloud_run_revision"
resource.labels.service_name="retail-recommender"
textPayload:"structured_logging_initialized"
```

**Criterio ✅:** Esta query NO retorna resultados (no hay `textPayload` — todo es `jsonPayload`).  
Si retorna resultados → el fix de `logging_config.py` del 10/03/2026 aún no fue deployado.

---

## 🔧 TROUBLESHOOTING

### Problema: Métricas custom no aparecen en Cloud Monitoring

**Causa más probable:** El endpoint `/metrics` no es accesible desde el scraper de GCP,
o el scraper no está configurado para esta instancia de Cloud Run.

**Diagnóstico:**
```bash
# 1. Verificar que el endpoint /metrics responde localmente
curl https://retail-recommender-lzf2y6pspa-uc.a.run.app/metrics | head -20

# 2. Verificar que la variable GCP_MONITORING_ENABLED está en true
gcloud run services describe retail-recommender \
  --region=us-central1 \
  --project=retail-recommendations-449216 \
  --format="yaml(spec.template.spec.containers[0].env)"
```

**Solución más común:** Las métricas custom de Prometheus en Cloud Run requieren el
[Managed Service for Prometheus (GMP)](https://cloud.google.com/stackdriver/docs/managed-prometheus)
o un colector externo. Verificar en PASO 2 que la API `monitoring.googleapis.com` está
habilitada y que el scraping está configurado.

---

### Problema: Alertas muestran "No data"

**Causa más probable:** Las métricas subyacentes no están llegando a Cloud Monitoring.
Las alertas sin datos no pueden evaluar si la condición se cumple.

**Solución:** Resolver primero el problema de métricas (ver arriba). Una vez que las
métricas tienen datos, las alertas pasarán de "No data" a "OK" automáticamente dentro
de 5-10 minutos.

---

### Problema: Cloud Logging no indexa JSON (muestra textPayload en lugar de jsonPayload)

**Causa:** `LOG_JSON_FORMAT` no está en `true` en Cloud Run, o el fix de `configure_structlog()`
del 10/03/2026 no fue incluido en el último deploy.

**Verificación:**
```bash
# Verificar la variable de entorno en el servicio activo
gcloud run services describe retail-recommender \
  --region=us-central1 \
  --format="value(spec.template.spec.containers[0].env)"
```

**Solución:**
1. Asegurarse que `LOG_JSON_FORMAT=true` está en Cloud Run
2. Hacer un nuevo deploy que incluya los cambios de `logging_config.py` del 10/03/2026

---

## 📊 CHECKLIST DE VALIDACIÓN COMPLETO

Al finalizar este paso, todos los ítems deben estar marcados:

```
□ PASO 7.1 — Variables M3 verificadas en Cloud Run Console (6/6 presentes)
□ PASO 7.2 — Scraping de métricas activo (al menos 1 serie temporal con datos)
□ PASO 7.3 — Las 5 alertas con estado OK o Alerting (no "No data")
□ PASO 7.4a — Log "structured_logging_initialized" con h1_phase="active" en Cloud Logging
□ PASO 7.4b — Sin logs duplicados (query textPayload retorna vacío)
```

---

## 🔗 Referencias

- **Paso anterior**: [M3_PASO_6_INTEGRACION_CODIGO_16022026.md](./M3_PASO_6_INTEGRACION_CODIGO_16022026.md)
- **Alertas configuradas**: [M3_PASO_5_ALERTAS(CONTINUACION)_18022026.md](./M3_PASO_5_ALERTAS(CONTINUACION)_18022026.md)
- **Métricas Prometheus**: [DCT_M2_Prometheus_Metrics_&_Observability_16022026.md](../DCT_M2_Prometheus_Metrics_&_Observability_16022026.md)
- **Consolidación observabilidad**: [DCT_CONSOLIDACION_OBSERVABILIDAD_05032026.md](../../DCT_CONSOLIDACION_OBSERVABILIDAD_05032026.md)
- **Fix H1 (10/03/2026)**: `src/api/main_unified_redis.py` — `configure_structlog()` reactivado
- **Fix logging duplicado (10/03/2026)**: `src/api/core/logging_config.py` — `basicConfig` reemplazado por configuración explícita

---

## 📝 REGISTRO DE EJECUCIÓN

*(Completar al ejecutar este paso)*

| Campo | Valor |
|---|---|
| Ejecutado por | |
| Fecha de ejecución | |
| Resultado PASO 7.1 | ⬜ OK / ⬜ FAILED |
| Resultado PASO 7.2 | ⬜ OK / ⬜ FAILED |
| Resultado PASO 7.3 | ⬜ OK / ⬜ FAILED |
| Resultado PASO 7.4a | ⬜ OK / ⬜ FAILED |
| Resultado PASO 7.4b | ⬜ OK / ⬜ FAILED |
| Notas adicionales | |
