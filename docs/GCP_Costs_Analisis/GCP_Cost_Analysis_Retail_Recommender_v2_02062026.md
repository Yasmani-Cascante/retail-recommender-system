Retail Recommender System v2.1.0

**Analisis de Costos Cloud y**

**Plan de Optimizacion GCP**

**Proyecto:** retail-recommendations-449216

**Periodo analizado:** Abril-Mayo 2026

**Fecha del informe:** 02 de junio de 2026

**Region:** us-central1 (Cloud Run)

# **1\. Resumen Ejecutivo**

La factura de Google Cloud Platform escalo de **CHF 26.60 en abril** a **CHF 120.92 en mayo de 2026**, un incremento del **+354.59%**. Este aumento no refleja un crecimiento del trafico ni de la funcionalidad del sistema, sino una unica decision de configuracion: la activacion de **min-instances=1** en el servicio de embedding, que genera facturacion continua 24/7 independientemente del uso real.

## **Hallazgos principales**

-   **Causa raiz unica:** El embedding-service con min-instances=1 genera CHF 84.67/mes (70% de la factura total) aunque el trafico es actualmente 0 req/seg.
-   **Arquitectura correcta, configuracion incorrecta:** La separacion del embedding-service del monolito es una decision tecnica justificada. El problema es operar con instancias siempre activas durante la fase de testing.
-   **Costos secundarios optimizables:** Artifact Registry (CHF 12.38), Secret Manager (CHF 9.65) y Container Vulnerability Scanning (CHF 9.66) presentan oportunidades de ahorro mediante limpieza.

## **Potencial de ahorro inmediato**

| **Accion** | **Ahorro/mes** | **Costo anual evitado** | **Riesgo** |
| --- | --- | --- | --- |
| Reducir min-instances=0 (embedding) | CHF 51 | CHF 612 | Bajo |
| Right-size: 2 vCPU -> 1 vCPU | CHF 34 | CHF 408 | Bajo |
| Limpieza Artifact Registry | CHF 6-8 | CHF 84 | Cero |
| Auditoria Secret Manager | CHF 3-5 | CHF 48 | Cero |
| **TOTAL POTENCIAL** | **CHF 94-98** | **CHF 1.152** | **—** |

**Proyeccion:** *Aplicando las acciones inmediatas, el costo mensual pasa de CHF 120.92 a aproximadamente CHF 25-30/mes durante la fase pre-lanzamiento.*

# **2\. Analisis Detallado de Costos**

## **2.1 Distribucion de costos — Mayo 2026**

| **Servicio GCP** | **Costo (CHF)** | **% total** | **vs. Abril** | **Causa principal** |
| --- | --- | --- | --- | --- |
| Cloud Run (embedding-service) | 84.67 | 70.0% | +1.090% | min-instances=1 (always-on) |
| Cloud Run (retail-recommender) | 2.61 | 2.2% | stable | min-instances=0 (correcto) |
| Artifact Registry | 12.38 | 10.2% | +154% | Acumulacion de imagenes Docker |
| Container Vuln. Scanning | 9.66 | 8.0% | \-18% | Escaneo de todas las imagenes |
| Secret Manager | 9.65 | 8.0% | +71% | Versiones sin limpiar + accesos |
| Cloud Storage + otros | 0.06 | 0.05% | stable | — |
| **TOTAL (antes de tax)** | **111.86** | **100%** | **+354.59%** | **—** |

## **2.2 Causa raiz: el embedding-service**

El embedding-service aloja tres componentes ML que justifican el dimensionamiento de recursos:

-   FashionSigLIP (modelo ViT-based de vision para moda): ~1.2-1.5 GB en memoria
-   paraphrase-multilingual-MiniLM-L6-v2 via ONNX Runtime: ~350-500 MB en memoria
-   Indice FAISS (3.055 productos x 768 dimensiones x float32): ~9 MB

Con ambos modelos co-residentes, el pico de memoria en startup supera los 3 GB, lo que hace que la configuracion de 4 GiB RAM sea tecnicamente justificada (no es sobreaprovisionamiento de memoria). La oportunidad de right-sizing existe en la dimension de CPU.

| **Parametro** | **Config. actual** | **Config. propuesta** | **Ahorro/mes** | **Justificacion** |
| --- | --- | --- | --- | --- |
| vCPU | 2 vCPU | 1 vCPU | ~CHF 34 | 0 req/seg actual; inference secuencial |
| Memoria RAM | 4 GiB | Mantener 4 GiB | CHF 0 | Justificado: FashionSigLIP + MiniLM |
| min-instances | 1 (always-on) | 0 (scale-to-zero) | ~CHF 51 | Warm-up overlay ya implementado |

**Nota importante:** *La reduccion de 2 a 1 vCPU aumentara levemente el tiempo de cold-start (de ~13s a ~15-18s). Esto es aceptable dado que el ChatWidget ya implementa el overlay de 'calentando el sistema' para gestionar este escenario ante el usuario.*

# **3\. Plan de Optimizacion**

## **3.1 Acciones inmediatas (esta semana)**

### **Accion 1 — Right-size y scale-to-zero del embedding-service**

Impacto estimado: CHF 85/mes | Esfuerzo: 5 minutos | Riesgo: Bajo

gcloud run services update retail-embedding-service \\

\--cpu=1 \\

\--memory=4Gi \\

\--min-instances=0 \\

\--region=us-central1 \\

\--project=retail-recommendations-449216

Que monitorear despues del cambio:

-   Cloud Run logs: buscar 'OOM' o 'Memory limit exceeded' en los primeros 3 minutos de cold start
-   Latencia de search\_by\_product\_id: debe mantenerse < 100ms tras el cold start
-   Si OOM: la configuracion de 1 vCPU (no la memoria) es la causa; revertir solo --cpu a 2

### **Accion 2 — Lifecycle policy en Artifact Registry**

Impacto estimado: CHF 6-8/mes | Esfuerzo: 15 minutos | Riesgo: Cero

Retener solo las ultimas 5 imagenes por repositorio. Cada deploy agrega ~1-2 GB; con limpiezas periodicas el costo se estabiliza por debajo de CHF 5/mes.

gcloud artifacts repositories set-cleanup-policies <repo-name> \\

\--project=retail-recommendations-449216 \\

\--policy='\[{"name":"keep-5","action":{"type":"Keep"},

"mostRecentVersions":{"keepCount":5}}\]'

### **Accion 3 — Auditoria de Secret Manager**

Impacto estimado: CHF 3-5/mes | Esfuerzo: 1 hora | Riesgo: Bajo

CHF 9.65 en Secret Manager es elevado para un sistema con ~15-20 secretos. Las causas probables son versiones antiguas sin eliminar (cada version activa cuesta $0.06/mes) y accesos frecuentes sin cache. Acciones:

-   Listar todas las versiones activas: gcloud secrets versions list <secret-name> --filter='state=ENABLED'
-   Destruir versiones obsoletas que no sean la version activa actual
-   Activar cache en el codigo para evitar leer el mismo secreto en cada request

## **3.2 Accion para fase go-live**

### **Cloud Scheduler warm-up (horario activo)**

Cuando el trafico real justifique mantener el embedding-service warm durante el horario comercial, la solucion optima es un Cloud Scheduler que pinga el servicio cada 8 minutos entre las 8:00 y las 22:00 hora local.

-   Costo del Scheduler: ~CHF 0.50/mes
-   Ahorro vs min-instances=1: mantiene el servicio warm durante 14h/dia vs 24h/dia
-   Ahorro estimado: ~CHF 40-45/mes frente a la configuracion actual

Esto permite el mejor balance entre experiencia de usuario (sin cold start en horario activo) y costo (no se paga el servicio de madrugada cuando no hay usuarios).

# **4\. Evaluacion Arquitectonica**

## **4.1 Estado actual — veredicto**

La arquitectura de dos servicios (monolito + embedding-service separado) es la decision correcta y no debe ser revertida. El embedding-service fue correctamente separado porque:

-   Aloja modelos ML (FashionSigLIP + MiniLM) con requisitos de memoria incompatibles con min-instances=0 del monolito
-   Tiene un ciclo de deployment independiente del core del negocio
-   Sus endpoints tienen contratos de latencia distintos (inference ~50ms vs API ~2s)

El problema no es la arquitectura; es la configuracion de runtime en la fase incorrecta del ciclo de vida del producto. Un sistema en testing con 0 req/seg no justifica la misma configuracion que un sistema en produccion con trafico real.

## **4.2 Evaluacion de migracion a microservicios**

La migracion a microservicios incrementara los costos en el corto plazo y los reducira en el largo plazo, solo si el trafico justifica el granulado fino de scaling. El principio rector es separar solo lo que escala diferente.

| **Componente** | **Accion recomendada** | **Impacto en costo** | **Justificacion** |
| --- | --- | --- | --- |
| embedding-service (FashionSigLIP + MiniLM + FAISS) | Mantener separado | Neutral | Ya fue correctamente separado |
| Intent detection (TF-IDF + LogReg) | Mantener en monolito | +CHF 0 | Ligero, no escala independiente |
| Personalization engine (LFM) | Mantener en monolito | +CHF 0 | Acoplado al flujo conversacional |
| Knowledge Base (PostgreSQL + Redis) | Mantener en monolito | +CHF 0 | Shared memory = rapido. Separar solo si multitenancy |
| Shopify integration | Mantener en monolito | +CHF 0 | Dependencia directa del core |

**Conclusion:** *El monolito actual contiene logica de negocio acoplada cuya separacion agrega complejidad operacional sin beneficio de scaling. Cada servicio nuevo implica Artifact Registry adicional, Secret Manager, networking y overhead de autenticacion IAM. La arquitectura de dos servicios es la correcta para el estadio actual y previsible del producto.*

# **5\. Observaciones Adicionales**

## **5.1 Recommendations AI (CHF 0.01/mes)**

El servicio Google Cloud Retail API aparece con un costo marginal de CHF 0.01/mes (-50% vs abril). Si no esta siendo utilizado activamente en el roadmap inmediato, puede desactivarse sin impacto. Verificar si esta en uso antes de actuar.

## **5.2 Claude API — credito agotado**

Los logs de produccion muestran 'Claude API warm-up failed: credit balance too low' en cada cold start del monolito. El sistema funciona correctamente porque LFM (Liquid AI via OpenRouter) es la ruta primaria para la generacion de respuestas. Sin embargo, el warm-up fallido aumenta levemente la latencia del primer request tras un cold start. Accion: recargar creditos Anthropic para restaurar el warm-up y el fallback a Claude.

## **5.3 Redis — respuesta lenta ocasional**

Los logs muestran ocasionalmente 'Redis slow response (ping: 1060ms, threshold: 1000ms)'. Estos eventos ocurren durante health checks periodicos, no durante requests de usuario. Monitorear la frecuencia; si aumenta, investigar la configuracion del pool de conexiones Redis.

# **6\. Resumen de Acciones Priorizadas**

| **#** | **Accion** | **Ahorro/mes** | **Esfuerzo** | **Urgencia** | **Responsable** |
| --- | --- | --- | --- | --- | --- |
| 1 | min-instances=0 + 1 vCPU en embedding-service (1 comando) | CHF 85 | 5 min | INMEDIATA | DevOps |
| 2 | Lifecycle policy en Artifact Registry | CHF 6-8 | 15 min | Semana 1 | DevOps |
| 3 | Auditoria y limpieza Secret Manager | CHF 3-5 | 1 hora | Semana 1 | DevOps |
| 4 | Recargar creditos Claude API | N/A | 5 min | Semana 1 | Finanzas |
| 5 | Cloud Scheduler warm-up (implementar en go-live) | CHF 40-45 | 2 horas | Go-live | Engineering |
| 6 | Evaluar min-instances=1 cuando trafico > 1 venta/sem | Inversion | 1 cmd | Go-live | Decision |

Retail Recommender System v2.1.0 | Analisis generado: 02/06/2026 | retail-recommendations-449216 / us-central1