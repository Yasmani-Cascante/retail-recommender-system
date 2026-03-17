Analizo todo el material sistemáticamente antes de responder.---

## Resumen general

**El sistema está funcionando correctamente.** Las dos anomalías detectadas en los logs son independientes del flujo de recomendaciones y no afectaron ninguna de las 10 llamadas de los smoke tests.

---

## Análisis de los Smoke Tests

**RUN 1 — Score 17/19 (89%):**
Los 2 WARNs son artefactos técnicos esperados, no problemas. El cold start de 23.9 segundos es Cloud Run escalando desde cero (normal cuando el servicio lleva tiempo inactivo). La ausencia de logs de exportación GCP era timing — el exporter tarda hasta 60s y los logs se consultaron antes del próximo ciclo.

**RUN 2 — Score 19/19 (100%):**
Servicio warm (327ms), todos los contadores funcionando, 3 exports GCP confirmados con `metrics_count=111` a intervalos de ~67 segundos.

**Datos cuantitativos clave entre las dos ejecuciones:**

| Métrica | RUN 1 | RUN 2 | Comportamiento |
|---|---|---|---|
| `recommender_requests_total` | 0→5 | 5→10 | ✅ Delta exacto de 5 en cada run |
| `recommender_duration_seconds` (algoritmo) | Vacío | count=5, avg=136ms | ✅ Histograma activo |
| `kb_sync_operations_total{success}` | 0 | 1 | ✅ Un sync completo ocurrió |
| `kb_sync_duration_seconds` | Vacío | count=1, sum=6.6s | ✅ Timer de sync funciona |
| Latencia promedio /recommendations | 560ms | 493ms | ✅ Mejora con caché warm |

Un hallazgo nuevo: `kb_sync_duration_seconds_count=1, sum=6.593s` en el RUN 2 confirma que la instrumentación del timer de KB sync **sí funciona** — esto resuelve la pregunta pendiente que quedó del DCT donde indicaba "verificar instrumentación del timer".

---

## Análisis de los Dashboards

**HTTP & API Performance:** Los dos picos del gráfico de Request Rate correlacionan exactamente con las ejecuciones de los smoke tests. La latencia Cloud Run de p50=10ms y p95=73ms es mejor que la sesión anterior (p50=31ms, p95=112ms) porque el servicio ya estaba warm. El chart de Recommender Requests muestra `strategy=hybrid` a 0.178/s y `fallback=0`, `google_retail=0` — esto confirma que el algoritmo híbrido funciona sin caer en estrategias de respaldo.

**Business Metrics:** El chart de "Recommendation Latency p95" muestra el mensaje *"Cannot find metrics... could take up to 10 minutes"*. Esto es el comportamiento normal de GCP para métricas de tipo Distribution recién activadas — la métrica existe en `/metrics` con datos reales, pero el backend de Cloud Monitoring necesita tiempo para procesar las primeras distribuciones. No es un bug; desaparece sola a los 10 minutos de tener tráfico.

**System Health:** Los tres scorecards muestran exactamente los valores esperados: 1 instancia activa, semáforo KB en 1. El spike visible en "Error Trends" alrededor de las 8:00 PM corresponde a los dos errores HTTP 500 en `/api/health/kb` documentados en los logs — son calls manuales del browser posterior a los smoke tests.

---

## Anomalías detectadas

**Anomalía 1 — `claude_optimization.py` NoneType error (Prioridad baja)**
El módulo `src.api.core.claude_optimization` genera errores periódicos con `NoneType object has no attribute 'messages'`. Ocurre en background, sin impacto en los endpoints de recomendaciones. Las 10 llamadas de los smoke tests devolvieron HTTP 200 sin ningún degradation observable. Es un bug en una tarea de background que necesita un guard `if result is not None:` antes de acceder a `.messages`.

**Anomalía 2 — `/api/health/kb` HTTP 500 con `[Errno 111] Connection refused` (Prioridad media)**
Los endpoints `/api/health/kb/simple` y `/api/health/kb?deep=false` fallan con error de conexión a PostgreSQL. Ocurrieron a las 20:01, tras los smoke tests, activados manualmente desde el browser. La causa probable es que el pool de Neon expiró tras un período de inactividad entre los tests y la navegación manual, o que Cloud Run no tiene las variables de entorno de DB correctas (`DB_HOST`, `DB_SSL=true`) para Neon en producción. **Este error no afecta el flujo de recomendaciones** — solo el endpoint de diagnóstico del KB. Sin embargo, vale la pena investigarlo antes de que se vuelva visible en el dashboard de System Health como un spike sostenido de 5xx.

---

## Conclusión final

**✅ La fase M3 puede considerarse validada.**

El pipeline de observabilidad está operacional de extremo a extremo: la aplicación instrumenta correctamente, el GCPMetricsExporter exporta con estabilidad, los dashboards muestran datos reales, y las alertas no han generado falsos positivos. Los smoke tests alcanzan 100% en el segundo run. Las dos anomalías son bugs menores en componentes secundarios (background task de Claude y health check de KB) que no degradan la funcionalidad principal del sistema.

**Dos issues para registrar en el backlog antes de L4:**

1. `claude_optimization.py` — Añadir null check antes de acceder a `.messages`
2. `/api/health/kb` — Verificar variables de entorno de DB en Cloud Run (`DB_HOST` apuntando a Neon, `DB_SSL=true`)