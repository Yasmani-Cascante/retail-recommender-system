**RETAIL RECOMMENDER SYSTEM v2.1.0**

Análisis de Costos Cloud · Plan de Optimización GCP · Informe Actualizado

| **Campo** | **Valor** | **Notas** |
| --- | --- | --- |
| **Proyecto GCP** | retail-recommendations-449216 | us-central1 |
| **Período analizado** | Abril – Junio 2026 | Reporte base: 02/06/2026 |
| **Fecha del informe** | 09 de junio de 2026 | Post-optimización Sesión 1 |
| **Servicios productivos** | retail-recommender + retail-embedding-service | **2 de 2 (16 zombies eliminados)** |
| **Versión revisión activa** | retail-embedding-service-00045-bjf | Request-based · CPU boost ON |

# **1\. Resumen Ejecutivo**

Esta sesión de trabajo del 6–9 de junio de 2026 ejecutó las optimizaciones críticas identificadas en el informe base del 02/06/2026. Los resultados superan las proyecciones originales gracias al hallazgo adicional de 16 servicios Cloud Run inactivos (zombies) que fueron eliminados.

| **Período** | **Costo mensual** | **vs. anterior** | **Estado** |
| --- | --- | --- | --- |
| **Abril 2026 (línea base)** | CHF 26.60 | — | Referencia |
| **Mayo 2026 (config. incorrecta)** | **CHF 120.92** | **+354.59%** | **PROBLEMA** |
| **Jun 1–8, 2026 (parcial, config mixta)** | CHF 11.67 (8 días) | –62% vs may24-31 | **Transición** |
| **Junio 2026 (proyección GCP)** | **CHF 70.85** | **–41%** | Mes de transición* |
| **Julio 2026 (primer mes limpio)** | **~CHF 20–25** | **–79%** | **TARGET** |

*\* La proyección de CHF 70.85 para junio refleja los primeros 6 días con la configuración antigua (min-instances=1, ~CHF 4/día) más el resto del mes con la nueva configuración (~CHF 0.30/día). Julio será el primer mes 100% optimizado.*

# **2\. Acciones Ejecutadas en Esta Sesión**

## **2.1 Acción 1 — Right-size y Scale-to-Zero (COMPLETADA ✓)**

Ejecutada el 06/06/2026 en dos fases:

| **Parámetro** | **Revisión 00039-qft (antes)** | **Revisión 00044-dmd Fase 1** | **Revisión 00045-bjf Fase 2 (final)** | **Impacto** |
| --- | --- | --- | --- | --- |
| **CPU limit** | 2 vCPU | 1 vCPU | 1 vCPU | –50% CPU cost |
| **Memory limit** | 4 GiB | 4 GiB | 4 GiB | Sin cambio (justificado) |
| **min-instances** | 1 (always-on) | 0 (scale-to-zero) | 0 (scale-to-zero) | **–CHF 85/mes** |
| **Billing mode** | Instance-based | Instance-based (heredado) | Request-based | Correcto semánticamente |
| **CPU throttling** | false | false (heredado) | absent = throttled | CPU solo en requests activas |
| **CPU boost (startup)** | true | true | **true** | Mitiga cold start |
| **Cold start total** | ~13s (warm) | ~96s (cold) | ~95s (cold) | Consistente — CPU boost eficaz |

**Validación de logs — Revisión 00045-bjf (request-based, configuración final):**

-   13:19:26 Starting new instance (DEPLOYMENT\_ROLLOUT)
-   13:19:29 Started server process \[1\] — Uvicorn iniciado
-   13:20:08 Loading LFM2-ColBERT-350M from HuggingFace
-   13:20:33 ColBERT warmup complete — 22.97s/it ✓
-   13:20:57 FashionSigLIP loaded in 20.7s | embed\_dim=768 | tokenizer=ready ✓
-   13:20:59 FashionSigLIP warmup — 9 categorías pre-computed ✓
-   13:21:01 GCS download: image\_index.faiss (9.0MB) ✓
-   13:21:01 Loaded from disk: 3056 productos ✓
-   13:21:01 Embedding service ready. ColBERT=OK FashionSigLIP=OK ✓
-   13:21:01 Application startup complete — total: ~95s ✓
-   13:21:01 Deploying revision succeeded in 1m38.68s ✓

**Zero errores críticos. Zero OOM. Ahorro anualizado confirmado: ~CHF 1,020/año.**

## **2.2 Acción 2A — Eliminación de 16 Servicios Cloud Run Zombies (COMPLETADA ✓)**

Ejecutada el 09/06/2026. Se identificaron y eliminaron 16 servicios Cloud Run inactivos creados durante la fase de experimentación (marzo–junio 2025). Todos con 0 req/seg y último deploy hace más de un año.

| ✅ **Estado final verificado — CLI** — Solo 2 servicios activos en el proyecto |
| --- |

| **Servicio** | **Estado** | **Acción** |
| --- | --- | --- |
| **retail-embedding-service** | ✅ Activo (producción) | **CONSERVADO** |
| **retail-recommender** | ✅ Activo (producción) | **CONSERVADO** |
| _retail-recommender-complete, -debug, -docker, -final-fixed, -fixed, -progressive, -redis-labs, -stage2-fixed, -system, -tfidf-events, -tfidf-fixed, -tfidf-improved, -tfidf-metrics, -tfidf-shopify, -unified, -unified-redis (16 servicios)_ | ⛔ Inactivos (0 req, 1+ año) | **ELIMINADOS** |

*Impacto esperado en Artifact Registry: reducción de imágenes huérfanas → CHF 3–5/mes adicionales de ahorro sobre la proyección base.*

# **3\. Estado del Sistema — Configuración Final Validada**

| **Parámetro** | **retail-embedding-service** | **retail-recommender** | **Estado** |
| --- | --- | --- | --- |
| **vCPU** | 1 (reducido de 2) | min=0 / max=default | ✅ Optimizado |
| **RAM** | 4 GiB (mantenido) | 2 GiB | ✅ Justificado |
| **min-instances** | 0 (scale-to-zero) | 0 (scale-to-zero) | ✅ Correcto |
| **Billing mode** | Request-based | Request-based | ✅ Correcto |
| **CPU boost startup** | Enabled | N/A | ✅ Mitiga cold start |
| **Ingress / Auth** | All / Require auth (IAM) | All / Public access | ✅ Arquitectura correcta |
| **Cold start observado** | ~95s (00045-bjf) | ~180s (PostgreSQL pool + KB sync) | ✅ Gestionado por widget CDN |
| **FAISS index** | 3,056 productos \| Recall@1=100% | — | ✅ Cargado desde GCS |
| **Modelos cargados** | FashionSigLIP 20.7s ColBERT 22.97s warmup | TF-IDF + LogReg + LFM | ✅ ColBERT=OK FashionSigLIP=OK |

# **4\. Análisis de Costos — Proyecciones Actualizadas**

## **4.1 Distribución de costos — Junio 1–8, 2026 (8 días observados)**

| **Servicio GCP** | **Costo Jun 1–8** | **vs. Mayo** | **Observación** |
| --- | --- | --- | --- |
| **Cloud Run (total)** | CHF 7.26 | –71% | SKU Instance-based CPU: –CHF 14.09 (–72%) |
| **Artifact Registry** | CHF 3.79 | +4% | Imágenes históricas — impacto reducido post-eliminación zombies |
| **Container Vulnerability Scanning** | CHF 0.61 | –70% | Reducción directa de imágenes en AR |
| **Cloud Storage** | CHF 0.01 | stable | FAISS index GCS (retail-recommendations-449216-visual-index) |
| **Secret Manager** | (pendiente) | — | No visible en reporte parcial — pendiente auditoría Acción 3 |
| **SUBTOTAL observado** | **CHF 11.67** | **–62%** | **Proyección junio completo: CHF 70.85\*** |

*\* La proyección de junio es alta por el efecto de transición: promedia los días costosos (1–6 jun) con los días optimizados (7–30 jun). Ver explicación en sección 4.2.*

## **4.2 Por qué la proyección de junio es CHF 70 y no CHF 25**

GCP calcula proyecciones extrapolando el costo diario promedio de los días ya transcurridos al mes completo. Con un cambio de configuración a mitad de mes:

| **Período** | **Días** | **Costo/día aprox.** | **Motivo** |
| --- | --- | --- | --- |
| **Jun 1–6 (config antigua)** | 6 días | ~CHF 4.00/día | min-instances=1 + Instance-based todavía activo |
| **Jun 7–30 (config nueva)** | 24 días | ~CHF 0.80–1.00/día | min=0 + request-based + 16 zombies eliminados |
| **Julio 2026 (mes limpio)** | 30 días | ~CHF 0.70–0.85/día | Primera factura 100% con nueva configuración |

**El número a monitorear NO es la proyección de GCP de junio, sino el costo diario a partir del 10 de junio, que debería estabilizarse en CHF 0.70–1.00/día.**

## **4.3 Proyección de costos — Escenarios**

| **Escenario** | **Costo/mes** | **vs. Mayo pico** | **Estado** |
| --- | --- | --- | --- |
| **Mayo 2026 (sin optimizaciones)** | **CHF 120.92** | baseline | Situación inicial — RESUELTA |
| **Proyección original post-Acción 1+2+3** | CHF 25–30 | –75% | Estimado en informe 02/06/2026 |
| **Julio 2026 (target revisado con zombies)** | **CHF 20–25** | **–79%** | Mejor que proyección base — zombies eliminados |
| **Go-live + Cloud Scheduler warm-up** | CHF 60–65 | –47% | Pendiente implementar (Acción 5 — go-live) |
| **Go-live + min-instances=1 justificado** | CHF 90–95 | –21% | Solo cuando &gt;50 req/día por 5 días consecutivos |

# **5\. Estado de Todas las Acciones del Plan**

| **#** | **Acción** | **Ahorro/mes** | **Estado** | **Evidencia / Próximo paso** |
| --- | --- | --- | --- | --- |
| **1** | **Right-size (1 vCPU) + scale-to-zero (min=0) + request-based billing** | **CHF 85/mes** | **✅ DONE** | Logs 00045-bjf validados — ColBERT=OK FashionSigLIP=OK |
| **2A** | **Eliminación 16 servicios Cloud Run zombies** | CHF 3–5/mes (AR+Scanning) | **✅ DONE** | CLI verificado: solo 2 servicios activos |
| **2B** | Lifecycle policy Artifact Registry (keep last 5 images) | CHF 6–8/mes | **⏳ PENDING** | Ejecutar después de eliminación zombies para mayor impacto |
| **3** | Auditoría Secret Manager — destruir versiones obsoletas + caché | CHF 3–5/mes | **⏳ PENDING** | ~CHF 9/mes actual — pendiente auditoría semana 1 |
| **4** | LLM migration (reemplazar Claude API con modelo económico) | Variable | **🔵 PLANNED** | Claude descartado como fallback. Definir modelo candidato. |
| **5** | Cloud Scheduler warm-up (ping cada 8 min, 8:00–22:00) | –CHF 40–45/mes vs min=1 | **🔵 GO-LIVE** | Implementar vía monolito (proxy IAM). CHF 0.50/mes costo. |
| **6** | Reactivar min-instances=1 cuando KPI de tráfico lo justifique | Inversión CHF 85/mes | **🔵 KPI** | Umbral: &gt;50 req/día por 5 días consecutivos en embedding-service |

# **6\. Hallazgos Técnicos de la Sesión**

## **6.1 Comportamiento del Cold Start con 1 vCPU**

El cold start con la nueva configuración (1 vCPU, request-based, CPU boost) fue validado dos veces:

| **Componente** | **Revisión 00044-dmd** | **Revisión 00045-bjf** | **Evaluación** |
| --- | --- | --- | --- |
| ColBERT LFM2-350M warmup | 23.41 s | 22.97 s | Consistente — CPU boost efectivo |
| FashionSigLIP ViT-B/16 load | 20.6 s | 20.7 s | Determinístico — cache HuggingFace activo |
| FAISS GCS download (9.0 MB) | ~1.5 s | ~1.7 s | Estable — GCS us-central1 próximo al servicio |
| **Startup total observado** | **~96 s** | **~95 s** | **Dentro del SLA del warm-up overlay del widget** |

## **6.2 FAISS AVX512/AVX2 Fallback**

Ambas revisiones muestran el siguiente patrón en logs, que NO es un error:

-   FAISS intenta cargar swigfaiss\_avx512 → falla (CPU Cloud Run no soporta AVX-512)
-   FAISS intenta cargar swigfaiss\_avx2 → falla (ídem)
-   FAISS carga la versión base → Successfully loaded faiss ✓

*El índice opera correctamente. La penalización de rendimiento es marginal para un índice de 9 MB con 3,056 productos.*

## **6.3 Nota sobre cpu-throttling heredado (Revisión 00044)**

Al hacer el primer update (00044-dmd) desde la consola, la anotación run.googleapis.com/cpu-throttling: false fue heredada de revisiones anteriores sin ser visible en la UI. Esto fue detectado en el audit log del JSON y corregido en el segundo update (00045-bjf) donde la anotación desaparece, confirmando el modo request-based. Lección: siempre verificar el JSON del audit log, no solo la UI de Cloud Run.

# **7\. Próximos Pasos**

## **Semana actual (9–16 junio 2026)**

| **#** | **Tarea** | **Ahorro esperado** | **Comando / Referencia** |
| --- | --- | --- | --- |
| **2B** | Lifecycle policy Artifact Registry — obtener nombre del repo y aplicar keep-5 | CHF 6–8/mes | gcloud artifacts repositories list --project=retail-recommendations-449216 --location=us-central1 |
| **3** | Auditoría Secret Manager — listar versiones activas y destruir obsoletas | CHF 3–5/mes | gcloud secrets list --project=retail-recommendations-449216 |

## **Punto de validación — Factura julio 2026**

Julio será el primer mes 100% con la nueva configuración. Los valores esperados:

-   Cloud Run total: ~CHF 6–8/mes (vs CHF 87 en mayo)
-   Artifact Registry: ~CHF 2–3/mes post-lifecycle-policy
-   Container Scanning: ~CHF 0.5/mes post-limpieza
-   Secret Manager: ~CHF 5–6/mes post-auditoría
-   TOTAL julio esperado: CHF 20–25/mes (target)

## **Go-live — Cloud Scheduler warm-up (Acción 5)**

Arquitectura recomendada para el warm-up:

-   Cloud Scheduler → endpoint público /health/warm-up en el monolito
-   Monolito (con IAM token via \_fetch\_id\_token\_sync) → /health del embedding-service
-   Frecuencia: cada 8 minutos entre 08:00–22:00 hora local (horario comercial)
-   Costo del scheduler: ~CHF 0.50/mes. Ahorro vs min-instances=1: ~CHF 40–45/mes

*Importante: NO enviar el ping directamente desde Scheduler al embedding-service. El servicio requiere auth IAM y el job de Scheduler necesitaría una SA adicional. La ruta via monolito reutiliza la infraestructura existente.*

## **KPI para reactivar min-instances=1 (Acción 6)**

-   Umbral operacional: >50 req/día en embedding-service por 5 días consecutivos
-   Alternativa de negocio: >1 venta incremental/semana atribuible a visual search
-   Costo de reactivar: +CHF 85/mes — justificado cuando el cold start de ~95s impacte a usuarios reales con alta probabilidad estadística

# **8\. Resumen Ejecutivo de la Sesión**

| **Logros de la sesión 06–09 junio 2026** | **Pendiente completar** |
| --- | --- |
| ✅ Right-size: 2→1 vCPU embedding-service   ✅ Scale-to-zero: min-instances 1→0   ✅ Billing: Instance-based → Request-based   ✅ CPU boost ON — cold start controlado   ✅ 16 servicios zombie eliminados   ✅ 2 deploys validados con logs limpios   **✅ Ahorro confirmado: ~CHF 1,020/año** | ⏳ Acción 2B: Lifecycle policy Artifact Registry   ⏳ Acción 3: Auditoría Secret Manager   🔵 Acción 4: Migración LLM (modelo a definir)   🔵 Acción 5: Cloud Scheduler warm-up (go-live)   🔵 Validación factura julio 2026 (target CHF 20–25) |

Retail Recommender System v2.1.0 · Optimización GCP FinOps · Actualizado: 09/06/2026 · retail-recommendations-449216 / us-central1