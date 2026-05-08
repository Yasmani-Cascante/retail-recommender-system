RETAIL RECOMMENDER SYSTEM v2.1.0 | Mayo 2026

**Visual Search Integration**

Documento de Continuidad Tecnica — Estado Final Validado

Revision activa: retail-embedding-service-00029-skv | 02/05/2026

| INDEXACION   **100%**   3,054 / 3,056 productos | LATENCIA p50   **435ms**   umbral <500ms | RECALL@1   **100%**   umbral >85% | IAM AUTH   **ACTIVA**   403 sin token IAM |
| --- | --- | --- | --- |

# **1\. Estado final del sistema**

Todas las deudas tecnicas identificadas en el DCT de cierre (01/05/2026) han sido implementadas y validadas en produccion. El sistema de visual search esta completamente operativo con autenticacion IAM activa, indexacion incremental disponible, y batch size adaptativo funcionando de forma transparente.

| **Componente** | **Revision activa** | **Estado** |
| --- | --- | --- |
| **retail-embedding-service** | 00029-skv | Activo — IAM auth, no-allow-unauthenticated |
| **retail-recommender (monolito)** | 00155-qg6 | Activo — VISUAL\_SEARCH\_ENABLED=true |
| **Indice FAISS en GCS** | gs://retail-recommendations-449216-visual-index/ | 3,054 productos, 9.4MB |
| **Indice FAISS en /tmp** | Cargado desde GCS en startup (~1.4s) | Disponible en caliente |

# **2\. Deudas tecnicas resueltas (01-02/05/2026)**

## **DT1 — Autenticacion IAM service-to-service**

El embedding-service ahora requiere autenticacion IAM. Solo la SA del monolito (178362262166-compute@developer.gserviceaccount.com con roles/run.invoker) puede invocar sus endpoints. Cualquier request directa sin Authorization header recibe 403 Forbidden.

### **Archivos modificados**

-   **colbert\_client.py:** \_fetch\_id\_token\_sync() obtiene ID token via ADC (metadata server de GCP en Cloud Run, sin credenciales explicitas). \_auth\_headers() cachea el token con TTL de 59min y lo renueva de forma transparente. El flag EMBEDDING\_AUTH\_DISABLED=true deshabilita la auth para desarrollo local.
-   **setup\_iam\_auth.sh:** Script corregido que elimina el binding de allUsers antes de aplicar --no-allow-unauthenticated. La version anterior no eliminaba allUsers, dejando el servicio publico a pesar del flag.

### **Leccion aprendida — update vs deploy**

La primera ejecucion del script hizo gcloud run services update (solo cambia env vars, no el codigo). El nuevo colbert\_client.py nunca llego al monolito. Fix: el script correcto usa gcloud run deploy --source . para el monolito antes de activar el IAM del embedding-service.

### **Verificacion en produccion**

curl https://retail-embedding-service-178362262166.us-central1.run.app/health

→ 403 Forbidden (sin token IAM)

\# A traves del monolito (auth automatica):

curl -X POST .../v1/mcp/visual-search -F file=@img.jpg -F market\_id=ES

→ {"recommendations":\[...\], "total\_found":8} (auth transparente)

## **DT2 — Indexacion incremental del indice**

El indice FAISS ahora puede actualizarse con solo los productos nuevos sin reconstruirlo completamente. IndexFlatIP.add() es append-only: anade vectores al final sin modificar los existentes.

### **Nuevo endpoint**

POST /v1/mcp/visual-search/index/update

→ Detecta automaticamente que IDs no estan en el indice FAISS

→ Solo descarga/encodea los productos nuevos

→ Actualiza /tmp + GCS con el indice ampliado

### **Limitaciones documentadas**

-   **Productos ELIMINADOS:** el indice los conserva hasta la proxima re-indexacion completa (IndexFlatIP no tiene .remove()). Aparecen en el indice pero el monolito los filtra porque no estan en tfidf\_recommender.id\_index.
-   **Productos con imagen CAMBIADA:** misma ID, nueva image\_url — el indice mantiene el embedding antiguo. Para actualizar: usar POST /v1/mcp/visual-search/index (re-indexacion completa).

### **Archivos modificados**

-   **visual\_retriever.py:** build\_image\_index\_incremental() + \_run\_incremental\_indexation(). El metodo filtra internamente los PIDs ya presentes en self.\_id\_map.
-   **main.py (embedding):** IndexImagesRequest.mode: Literal\['full', 'incremental'\]. Routing al metodo correcto segun mode.
-   **colbert\_client.py:** index\_images\_incremental(new\_products). Usa el mismo endpoint /v1/embed/index-images con mode='incremental'.
-   **visual\_search\_router.py:** Nuevo endpoint POST /v1/mcp/visual-search/index/update.

## **DT3 — Batch size adaptativo en indexacion**

El batch\_size de descarga de imagenes ya no es fijo (16). Tras el primer batch, el sistema mide la velocidad promedio de descarga y ajusta para los batches siguientes.

| **Condicion** | **Accion** | **Motivo** |
| --- | --- | --- |
| **\>3s por imagen** | batch\_size = max(4, actual // 2) | Imagenes grandes (>3MB) — reducir para evitar 429 del CDN de Shopify |
| **<1s por imagen** | batch\_size = min(32, actual \* 2) | Imagenes pequenas (<200KB) — aumentar para aprovechar el ancho de banda |
| **1-3s por imagen** | Sin cambio | Velocidad normal — batch\_size inicial es optimo |

El ajuste se realiza una sola vez (tras el batch 0). La velocidad del CDN de Shopify es estable durante un job, por lo que un ajuste continuo solo anadira oscilaciones sin beneficio real.

# **3\. Fix adicional — Singleton del cliente ColBERT**

Se detecto que visual\_search\_router.py instanciaba un nuevo LFM2ColBERTClient() en CADA request. Esto causaba tres problemas:

| **Problema** | **Impacto** | **Fix** |
| --- | --- | --- |
| **Token IAM solicitado en cada request** | +50-200ms de latencia al metadata server por busqueda | Singleton: el token se cachea y se renueva cada 59min |
| **Circuit-breaker se reiniciaba en cada request** | Nunca abria aunque hubiese 10 fallos seguidos | Singleton: el contador de fallos persiste entre requests |
| **Pool TCP de httpx nunca reutilizaba conexiones** | Overhead de TLS handshake en cada busqueda visual | Singleton: pool de conexiones al embedding-service persistente |

Fix: \_colbert\_client\_singleton = None a nivel de modulo. La primera llamada a \_get\_colbert\_client() crea el singleton. Las siguientes retornan la misma instancia. Inicializacion lazy para evitar problemas con COLBERT\_SERVICE\_URL no disponible en tiempo de import.

# **4\. Endpoints operativos — referencia completa**

| **Endpoint** | **Auth** | **Descripcion** |
| --- | --- | --- |
| **POST /v1/mcp/visual-search** | X-API-Key | Busqueda visual principal. Multipart: file + market\_id + top\_k. |
| **POST /v1/mcp/visual-search/index** | X-API-Key | Re-indexacion COMPLETA (~30 min). Usar tras cambios masivos o primer deploy. |
| **POST /v1/mcp/visual-search/index/update** | X-API-Key | Indexacion INCREMENTAL. Solo productos nuevos. Rapido (<1 min tipico). |
| **GET /health (monolito)** | X-API-Key | Incluye visual\_search\_enabled: true/false para el frontend. |
| **POST /v1/embed/search-image** | IAM token (\*) | Endpoint interno — solo accesible desde el monolito. |
| **POST /v1/embed/index-images** | IAM token (\*) | Endpoint interno — lanza indexacion full o incremental segun mode. |
| **GET /health (embedding)** | IAM token (\*) | 403 sin token. Solo el monolito puede acceder. |

(\*) El token IAM lo anade colbert\_client.py automaticamente via ADC. No requiere configuracion manual.

# **5\. Configuracion de deploy — estado actual**

### **retail-embedding-service**

| **Parametro** | **Valor** | **Motivo** |
| --- | --- | --- |
| **Memory** | 4Gi | ColBERT (~1400MB) + FashionSigLIP (~400MB) + OS + libs + margen |
| **CPU** | 2 vCPU | Indexacion paralela ~30 min. Busqueda: ~435ms p50. |
| **min-instances** | 1 | Modelo siempre en RAM. Sin cold start. |
| **max-instances** | 1 | Servicio interno. Nunca escala. Previene OOM por autoscaling. |
| **\--no-cpu-throttling** | activo | CPU continuo para background tasks de indexacion. |
| **\--no-allow-unauthenticated** | activo | IAM auth. Solo el monolito puede invocar. |
| **VISUAL\_INDEX\_BUCKET** | retail-recommendations-449216-visual-index | GCS para persistir indice FAISS entre deploys. |
| **HF\_HUB\_OFFLINE** | 1 | Evita verificacion de HuggingFace en runtime. |

### **retail-recommender (monolito)**

| **Variable** | **Valor** | **Descripcion** |
| --- | --- | --- |
| **VISUAL\_SEARCH\_ENABLED** | true | Feature flag activo. El boton de camara aparece en el chat. |
| **COLBERT\_SERVICE\_URL** | https://retail-embedding-service-178362262166.us-central1.run.app | URL del embedding-service. |
| **EMBEDDING\_AUTH\_DISABLED** | (no configurada) | Ausente = false = auth IAM activa. Poner 'true' solo para dev local sin ADC. |

# **6\. Metricas de produccion — estado 02/05/2026**

| **Metrica** | **Valor** | **Target** |
| --- | --- | --- |
| **Revision embedding activa** | retail-embedding-service-00029-skv | — |
| **Revision monolito activa** | retail-recommender-00155-qg6 | — |
| **Recall@1** | 100% | \>85% |
| **Recall@5** | 100% | \>95% |
| **Precision intra-categoria** | 78.5% | \>70% |
| **Latencia p50 (server-side)** | 435ms | <500ms |
| **Latencia p95 (server-side)** | 614ms | <800ms |
| **Tasa de exito HTTP 200** | 100% | \>99% |
| **OOM events desde fix** | 0 | 0 |
| **Reinicios no planificados** | 0 en ventana observada | 0 |
| **Productos en indice FAISS** | 3,054 de 3,056 | ~3,000 |
| **Tamano indice GCS** | 9.4MB (faiss) + 51.9KB (id\_map) | ~10MB |
| **Carga desde GCS en startup** | ~1.4s | <5s |
| **Tiempo ultima re-indexacion** | 1,770s (29.5 min) | <35 min |
| **IAM auth** | Activa — 403 sin token | Activa |

# **7\. Deuda tecnica residual**

### **Baja prioridad**

-   **Sincronizacion automatica del indice:** cuando ShopifyKBSyncService detecta nuevos productos, llamar a colbert\_client.index\_images\_incremental() automaticamente. Actualmente es un proceso manual (POST /v1/mcp/visual-search/index/update).
-   **Consolidacion de codigo legacy:** ~400KB de codigo muerto (main\_\*.py variantes, backups inline) coexiste con main\_unified\_redis.py activo. Consolidar antes de la siguiente fase mayor.
-   **Actualizaciones de productos con imagen cambiada:** el indice incremental no actualiza embeddings de productos con misma ID y nueva image\_url. Requiere re-indexacion completa cuando hay cambios de imagen en productos existentes.

### **No en scope**

-   **Camara en tiempo real (video streaming):** En movil, input accept=image/\* ya abre la camara nativa del dispositivo. La camara en tiempo real (getUserMedia + frame extraction) es un proyecto separado con su propio plan, fuera del scope de esta integracion.

**Estado: TODAS LAS DEUDAS TECNICAS RESUELTAS Y VALIDADAS EN PRODUCCION**

Sistema de Visual Search completamente operativo. Autenticacion IAM activa. Indexacion incremental disponible. Batch size adaptativo funcionando. Todas las metricas dentro de los umbrales del plan original.

Revision activa: retail-embedding-service-00029-skv | Fecha: 02/05/2026 | Autor: Equipo de Ingenieria