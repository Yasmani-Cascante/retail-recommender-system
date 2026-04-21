**RETAIL RECOMMENDER SYSTEM v2.1**

Cloud Run Architecture — Min-Instances Decision Analysis

Documento técnico de arquitectura y costos

Proyecto: retail-recommendations-449216 · Región: us-central1 · Abril 2026

# **1\. ✅ Confirmación técnica**

Sí, la recomendación original del documento LiquidAI\_Integration\_Plan\_16042026.md establece min-instances = 1 para ambos servicios desplegados en Cloud Run:

| **Servicio** | **Min-instances** | **Justificación original** | **Recursos asignados** |
| --- | --- | --- | --- |
| retail-recommender (monolito) | **1** | Evitar cold start en recomendaciones MCP | 2 GiB RAM / 2 vCPU |
| retail-embedding-service (ColBERT) | **1** | Índice PLAID vive en /tmp — cold start destruye el índice | 2 GiB RAM / 1 vCPU |

| **Nota crítica sobre el embedding-service:**   El índice PLAID se almacena en /tmp/colbert-index/ — memoria efímera del contenedor. Si min-instances = 0 y el contenedor se destruye, el índice desaparece. El monolito necesitaría re-indexar POST /v1/embed/index en cada cold start, lo que implica ~5-10 segundos de latencia en el primer request después de un período de inactividad. Para el monolito, el argumento es diferente y discutible. |
| --- |

# **2\. 💰 Análisis de costos realista**

## **2.1 Cálculo base (min-instances = 1 para ambos servicios)**

| **Concepto** | **Servicio A (Monolito)** | **Servicio B (Embedding)** | **Total/mes (1 cliente)** | **Método de cálculo** |
| --- | --- | --- | --- | --- |
| CPU idle (1 vCPU × 24h × 30d) | $14.76 | $7.38 | **$22.14** | 0.000024 $/vCPU-sec |
| RAM idle (2GiB × 24h × 30d) | $7.68 | $7.68 | **$15.36** | 0.0000025 $/GiB-sec |
| Tráfico estimado (var) | $3–8 | $1–3 | **$4–11** | Requests × duración |
| Egress networking (<1GB/mes) | $0 | $0 | **~$0.12** | 0.12 $/GB salida |
| Almacenamiento imagen (Container R.) | $0.10 | $0.10 | **$0.20** | 0.10 $/GB-mes |
| **TOTAL ESTIMADO/MES (1 cliente)** | **~$26–31** | **~$16–18** | **~$42–61** | Precios GCP us-central1 |

| **Nota sobre el Free Tier:** GCP Cloud Run tiene un free tier de 2 millones de requests/mes, 360,000 GB-segundos de CPU y 180,000 GB-segundos de RAM. Para un cliente de e-commerce con tráfico moderado (<50K requests/mes), **el costo real puede ser significativamente menor que $42/mes**. El costo mostrado es el tope conservador. |
| --- |

## **2.2 Respuesta directa a tu pregunta**

| **¿Costo fijo de ~$80/mes por cliente independiente del tráfico?**   **Respuesta corta: No exactamente $80, y tampoco es completamente fijo.**   1\. El costo real está entre $42 y $61/mes para ambos servicios (no $80), calculado con precios reales de us-central1 a Abril 2026.   2\. El componente "fijo" (idle compute por min-instances=1) es ~$38/mes. El resto es variable según tráfico.   3\. A mayor tráfico, el costo variable sube, pero el idle costo desaparece (ya está pagando por trabajo real).   4\. Con el free tier activo en un cliente nuevo, el primer mes puede costar $0–$15. |
| --- |

# **3\. ⚠️ Evaluación crítica de la configuración actual**

## **3.1 ¿Cuándo SÍ tiene sentido min-instances = 1?**

| **Escenario** | **Justificación** |
| --- | --- |
| **Tienda con tráfico continuo (>500 visitas/día)** | El cold start de 8-15s del monolito sería visible para usuarios reales. Con min=1, P95 de latencia queda en <500ms. |
| **Embedding-service SIEMPRE** | El índice PLAID en /tmp es volátil. Si el contenedor muere y se levanta uno nuevo, hay 5-10s de re-indexación + degradación del servicio. min=1 garantiza que el índice siempre existe. |
| **SLA comprometido con cliente (99.9%+)** | Un cold start en horario pico es un SLA breach. $16/mes por el embedding-service es trivial frente a penalizaciones contractuales. |
| **Widget embebido en Shopify activo 24/7** | Los clientes de Shopify esperan respuestas instantáneas. Un cold start en el primer click destruye la primera impresión. |

## **3.2 ¿Cuándo NO tiene sentido min-instances = 1?**

| **Escenario** | **Problema real** |
| --- | --- |
| **Fase de desarrollo / staging** | Pagas $38/mes por una instancia que nadie usa. En dev, un cold start de 15s es aceptable. |
| **Tienda recién lanzada (<50 visitas/día)** | El tráfico no justifica el costo. Un cold start ocasional es invisible si los usuarios llegan con horas de diferencia. |
| **Múltiples clientes en infraestructura propia (multi-tenant)** | Si escalaras a 10 clientes, min=1 por cliente = $380-610/mes en idle. Insostenible. Necesitas un modelo multi-tenant con instancias compartidas. |
| **Cuando el índice ColBERT NO está activado (LFM\_COLBERT\_ENABLED=false)** | Si el embedding-service no está en uso real, min=1 es dinero quemado. El servicio debería estar en min=0 hasta activar el flag. |

# **4\. 🔁 Alternativas recomendadas**

## **Alternativa A — Diferenciación por servicio (RECOMENDADA para producción activa)**

| **Servicio** | **Configuración** | **Latencia P95** | **Costo/mes** | **Complejidad** |
| --- | --- | --- | --- | --- |
| **Monolito** | min=1, max=3, 2GiB/2vCPU | <500ms (sin cold start) | **~$26–31** | Baja |
| **Embedding-service** | min=1 SOLO si LFM\_COLBERT\_ENABLED=true | 20–40ms (warm) | **~$16–18** | Baja |

## **Alternativa B — min=0 con CPU-always-allocated (para bajo tráfico / staging)**

Cloud Run permite --cpu-boost y --no-cpu-throttling. Con CPU siempre asignada y min=0, los cold starts bajan de 15s a 3-5s.

| **Parámetro** | **Monolito** | **Embedding** | **Total/mes** | **Trade-off** |
| --- | --- | --- | --- | --- |
| min-instances | **0** | 0 (desactivado) | **~$8–15** | Cold start 3–5s en inactividad |
| **Nota crítica** | El embedding-service NO puede usar min=0 si ColBERT está activo — el índice PLAID se pierde en cada cold start y no hay mecanismo automático de re-indexación. |

## **Alternativa C — Arquitectura híbrida (escenario futuro multi-cliente)**

Si el sistema escala a múltiples tiendas Shopify, el modelo cambia fundamentalmente:

| **Componente** | **Descripción** |
| --- | --- |
| **Monolito compartido** | Un solo Cloud Run con min=2 (HA) sirve a todos los clientes. Costo: ~$35/mes fijo dividido entre N clientes. |
| **Embedding-service como plataforma** | Un solo servicio indexa catálogos de múltiples tiendas con namespacing por tenant\_id. Costo unitario baja con escala. |
| **Redis compartido** | Redis Cloud ya está compartido. Con multi-tenancy el costo por cliente baja a ~$5-8/mes en Redis. |
| **Costo por cliente a escala 10+** | ~$8–12/mes por cliente vs $42-61/mes en arquitectura dedicada. |

# **5\. 🧠 Recomendación final de arquitectura**

## **Lo que haría en producción — razonamiento paso a paso**

| Premisa: El sistema está en producción activa con una tienda Shopify (ai-shoppings.myshopify.com). La Fase C (ColBERT) todavía no está activada (LFM_COLBERT_ENABLED=false). El objetivo es minimizar costos sin degradar la experiencia del usuario real. |
| --- |

### **DECISIÓN 1: Monolito — mantener min-instances = 1 ✅**

Justificado. El monolito es el path crítico de TODAS las recomendaciones. Un cold start de 15s (arrancar FastAPI + cargar TF-IDF 3062 productos + conectar Redis + calentar Claude TCP) en horario pico destruye la experiencia. El costo de $26-31/mes es completamente razonable para una tienda activa. Si el tráfico bajara a cero por semanas (tienda inactiva), este costo se reconsideraría.

### **DECISIÓN 2: Embedding-service — min-instances = 0 hasta activar ColBERT ⚠️**

Actualmente LFM\_COLBERT\_ENABLED=false. El embedding-service NO está en el path de requests reales. Desplegar con min=1 ahora significa pagar $16-18/mes por un servicio que nadie está usando. La acción correcta es:

-   Desplegar embedding-service con min=0 inicialmente.
-   Cuando LFM\_COLBERT\_ENABLED=true y el servicio esté en producción real: cambiar a min=1.
-   Esto ahorra ~$16-18/mes hasta que ColBERT esté activo (semanas o meses de diferencia).

### **DECISIÓN 3: Añadir re-indexación automática al cold start del embedding-service**

Si el embedding-service usa min=0 y sufre un cold start, el índice PLAID necesita reconstruirse. La solución arquitectónica correcta es:

-   Al arrancar (lifespan), verificar si existe /tmp/colbert-index/catalog.
-   Si no existe, hacer GET al monolito para obtener el catálogo y re-indexar automáticamente.
-   Esto convierte el cold start de "error silencioso" a "recuperación automática en 5-10s".
-   Con esta guardia, min=0 es viable incluso cuando ColBERT esté activo, reduciendo el costo fijo.

| **Servicio** | **Ahora (Fase C inactiva)** | **Cuando ColBERT activo** | **Ahorro mensual** | **Acción** |
| --- | --- | --- | --- | --- |
| **Monolito** | min=1 ✅ | min=1 ✅ | $0 | Sin cambio |
| **Embedding-service** | **min=0 ⚠️** | min=1 ✅ | **~$16–18/mes** | Cambiar a min=0 en deploy.sh hasta activar flag |
| **TOTAL** | **~$26–31/mes** | **~$42–49/mes** | **~$16–18/mes** | Optimización aplicable hoy |

| **Acción inmediata recomendada en deploy.sh:**   Cambiar --min-instances 1 a --min-instances 0 en el embedding-service hasta que LFM\_COLBERT\_ENABLED=true esté en producción activa y validado. Esta sola modificación ahorra $16-18/mes sin impacto funcional alguno (el servicio no está siendo usado en este momento). |
| --- |

## **Tabla resumen final de trade-offs por configuración**

| **Configuración** | **Costo/mes** | **Cold start latencia** | **Riesgo índice ColBERT** | **Escenario ideal** |
| --- | --- | --- | --- | --- |
| min=1 ambos | ~$42–61 | Sin cold start | Ninguno (índice vive siempre) | Producción con ColBERT activo |
| **min=1 monolito, min=0 embedding** | ~$26–31 | Embedding: 8–15s si inactivo | Re-indexación en cold start | Producción con ColBERT inactivo (HOY) |
| min=0 ambos (CPU-boost) | ~$8–15 | 3–5s ambos | Alto (índice perdido) | Staging / desarrollo |
| min=0 ambos (sin CPU-boost) | ~$2–8 | 10–20s ambos | Alto + recuperación lenta | Solo testing / CI/CD |

Documento generado: Abril 2026 — Retail Recommender System v2.1.0

Proyecto GCP: retail-recommendations-449216 | Región: us-central1 | Servicio: retail-recommender-lzf2y6pspa-uc.a.run.app