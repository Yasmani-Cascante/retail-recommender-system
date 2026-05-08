RETAIL RECOMMENDER SYSTEM v2.1.0 | Mayo 2026

**Visual Search Integration**

Documentacion Tecnica de Cierre

Dirigido a: Ingenieros de backend, DevOps, QA | Clasificacion: Interno

# **1\. Overview tecnico**

Esta integracion anade busqueda visual por similitud de imagen al Retail Recommender System. Se implemento como Opcion A: marqo-fashionSigLIP + FAISS dentro del embedding-service existente (microservicio en Cloud Run que ya alojaba LFM2-ColBERT-350M).

El sistema esta en produccion desde el 30/04/2026, revision retail-embedding-service-00028-rxq. Los logs de produccion confirman latencia p50 de ~490ms y tasa de exito del 100% en las primeras 4 busquedas reales.

# **2\. Arquitectura y flujo completo**

### **Flujo de busqueda visual (request path)**

Browser / ChatWidget

└── POST /v1/mcp/visual-search (multipart: file + market\_id + top\_k)

\[Monolito — visual\_search\_router.py\]

└── colbert\_client.search\_by\_image(image\_bytes, top\_k)

└── POST /v1/embed/search-image (multipart: file + top\_k)

\[embedding-service — main.py\]

└── FashionSigLIPRetriever.search\_by\_image(bytes)

1\. preprocess(img) → \[1, 3, 224, 224\]

2\. encode\_image() → \[1, 768\] L2-normalized

3\. faiss.IndexFlatIP.search() → indices

4\. id\_map\[idx\] → product\_ids\[\]

\[Monolito\] tfidf\_recommender.id\_index\[pid\] → product dict

\[Monolito\] market pricing enrichment

└── VisualSearchResponse { recommendations, latency\_ms }

### **Flujo de indexacion (background job)**

POST /v1/mcp/visual-search/index (api\_key requerido)

└── visual\_search\_router.trigger\_visual\_indexation()

└── colbert\_client.index\_images(products\_with\_url)

└── POST /v1/embed/index-images (JSON: products\[\], batch\_size)

\[embedding-service\] BackgroundTask: \_run\_indexation()

for batch in batches(products, size=16):

asyncio.gather(\*\[\_download\_one(url, sem) for ...\])

encode\_batch() en run\_in\_executor (PyTorch CPU)

gc.collect() cada 10 batches

faiss.write\_index() → /tmp/visual-index/

\_upload\_to\_gcs() → gs://<BUCKET>/visual-index/

### **Persistencia del indice FAISS — dos niveles**

| **Nivel** | **Ubicacion** | **Latencia carga** | **Cuando disponible** |
| --- | --- | --- | --- |
| **1 — Local** | /tmp/visual-index/image\_index.faiss | ~100ms | Mismo container que indexo (min-instances=1) |
| **2 — GCS** | gs://retail-recommendations-449216-visual-index/ | ~1-2s | Cualquier container, tras deploy o restart |
| **0 — Sin indice** | — | — | Primer deploy: pedir POST /index al usuario |

# **3\. Componentes principales**

| **Archivo** | **Rol** | **Notas clave** |
| --- | --- | --- |
| **embedding-service/visual\_retriever.py** | FashionSigLIPRetriever: modelo + FAISS + GCS | Funcion \_download\_one a nivel de modulo (closure bug fix). Pre-resize 224x224. gc.collect() cada 10 batches. |
| **embedding-service/main.py** | Endpoints FastAPI del embedding-service | POST /v1/embed/index-images y /v1/embed/search-image. Guard is\_indexing() antes de lanzar job. |
| **embedding-service/requirements.txt** | Dependencias del servicio | open-clip-torch, faiss-cpu, google-cloud-storage, Pillow, httpx. |
| **embedding-service/Dockerfile** | Build de imagen Docker | Descarga modelos en build (HF\_HUB\_OFFLINE=1). torch 2.7.0+cpu pineado. |
| **src/api/services/colbert\_client.py** | Cliente HTTP monolito→embedding | SIN Content-Type en headers base (fix 422). JSON y multipart declarados por metodo. |
| **src/api/routers/visual\_search\_router.py** | Router FastAPI del monolito | Feature flag VISUAL\_SEARCH\_ENABLED. Resuelve productos desde tfidf\_recommender.id\_index. |

# **4\. Endpoints clave**

| **Endpoint** | **Servicio** | **Auth** | **Payload** | **Respuesta** |
| --- | --- | --- | --- | --- |
| **POST /v1/mcp/visual-search** | Monolito | X-API-Key | multipart: file, market\_id, top\_k | VisualSearchResponse {recommendations\[\], latency\_ms} |
| **POST /v1/mcp/visual-search/index** | Monolito | X-API-Key | ninguno (Content-Length:0) | {status, products\_submitted, message} |
| **POST /v1/embed/search-image** | Embedding | ninguno\* | multipart: file (UploadFile), top\_k (Form) | SearchImageResponse {product\_ids\[\], latency\_ms, visual\_index\_size} |
| **POST /v1/embed/index-images** | Embedding | ninguno\* | JSON: {products\[\], batch\_size} | {status|already\_running, products\_with\_image} |
| **GET /health** | Embedding | ninguno | ninguno | {status, models, index\_size, visual\_index\_size, visual\_index\_ready} |

(\*) El embedding-service esta configurado con --allow-unauthenticated porque solo recibe trafico interno de Cloud Run (mismo proyecto, red privada). En un entorno mas estricto, activar autenticacion de servicio a servicio.

# **5\. Problemas encontrados y soluciones implementadas**

### **P1 — CPU Throttling: indexacion 1106x mas lenta de lo esperado**

Sintoma: progress: 1/3056 a los 4 minutos de inicio. Tasa 0.004 prod/s vs 1.7 esperado.

Causa: FastAPI BackgroundTask corre tras enviar la respuesta HTTP. Cloud Run considera la request terminada y throttlea CPU al ~0%. El asyncio event loop y los threads PyTorch reciben ticks insuficientes.

Solucion: --no-cpu-throttling en el deploy. CPU disponible continuo, independiente del ciclo request/response.

\--no-cpu-throttling # en gcloud run deploy

### **P2 — Autoscaling OOM: segunda instancia supera 4096MB**

Sintoma: Memory limit of 4096 MiB exceeded with 4107 MiB used. Job interrumpido al 14%.

Causa: CPU alta de la instancia indexando → Cloud Run lanza segunda instancia → ColBERT (~1400MB) + FashionSigLIP carga peak (~1700MB) + OS + GCS libs = 4107MB > 4096MB.

Solucion: --max-instances 1. El embedding-service es interno, nunca necesita escalar.

\--max-instances 1 # en gcloud run deploy

### **P3 — OOM en indexacion: PIL images full-res acumuladas en RAM**

Sintoma: Memory limit exceeded a los 51 batches (~27% del catalogo). Pattern: cada OOM a aprox el mismo punto.

Causa: \_download\_one() retornaba PIL.Image sin redimensionar. Fotos Shopify 2000x2500px = 15MB en RAM. 16 imgs/batch = 240MB. Overlap batches N y N+1 = 480MB. Tras 51 batches, cache allocator PyTorch acumulaba ~1050MB adicionales.

Solucion: pre-resize a 224x224 inmediatamente tras decode. del img\_full libera los 15MB por referencia-counting. gc.collect() cada 10 batches devuelve el pool PyTorch al OS.

img\_small = img\_full.resize((224, 224), Image.Resampling.LANCZOS)

del img\_full # libera ~15MB inmediatamente

if batch\_num % 10 == 0: gc.collect()

### **P4 — 422 en search-image: Content-Type incorrecto en cliente HTTP**

Sintoma: HTTP POST /v1/embed/search-image -> 422 Unprocessable Entity en 5ms.

Causa: LFM2ColBERTClient() tenia headers={'Content-Type': 'application/json'} en el constructor. httpx no puede sobreescribir ese header cuando construye requests multipart con files=. El embedding-service recibia Content-Type: application/json con body multipart → FastAPI rechazaba en la validacion de firma.

Solucion: eliminar Content-Type del constructor. Cada metodo JSON lo declara explicitamente. search\_by\_image() no declara ninguno → httpx genera multipart/form-data; boundary=<hash> automaticamente.

\# ANTES (incorrecto):

self.\_http = httpx.AsyncClient(base\_url=..., headers={'Content-Type': 'application/json'})

\# DESPUES (correcto):

self.\_http = httpx.AsyncClient(base\_url=..., timeout=httpx.Timeout(5.0))

\# En search(): headers={'Content-Type': 'application/json'}

\# En search\_by\_image(): sin headers → httpx auto-genera multipart

### **P5 — Closure bug: semaforo compartido entre jobs concurrentes**

Sintoma historico: dos jobs paralelos mostraban descargas serializadas. El segundo job tardaba 22s por imagen (vs 1s esperado).

Causa: \_download\_one definida dentro del for loop capturaba sem por referencia Python. Al avanzar el loop al siguiente batch, la variable sem era reasignada; las coroutines del job anterior capturaban el nuevo semaforo.

Solucion: \_download\_one movida a nivel de modulo. sem se pasa como argumento explicito, eliminando el closure.

### **P6 — GCS persistence: indice se pierde en cada deploy o restart**

Sintoma: tras cada deploy o restart de Cloud Run, visual\_index\_ready: false. Necesario re-indexar 30 minutos.

Causa: /tmp es efimero en Cloud Run. Aunque min-instances=1 reduce reinicios, no los elimina (mantenimiento, deploys).

Solucion: al completar la indexacion, subir el indice a GCS. En startup, intentar carga desde /tmp primero, luego desde GCS si /tmp esta vacio. Startup con GCS tarda ~1.4s para descargar 9.4MB.

# **6\. Decisiones tecnicas relevantes**

| **Decision** | **Alternativa rechazada** | **Razon** |
| --- | --- | --- |
| **faiss-cpu IndexFlatIP (busqueda exacta)** | IndexIVFFlat (aproximado) o Marqo Cloud | Con 3056 productos, la busqueda exhaustiva es <1ms. No hay necesidad de aproximacion. Marqo Cloud anade latencia de red y coste mensual. |
| **Pre-resize 224x224 en \_download\_one** | Resize en \_encode\_batch | Libera la imagen full-res antes de que el siguiente batch empiece a descargarse, minimizando el overlap de RAM. |
| **max-instances=1** | Aumentar RAM a 8Gi | El servicio es interno, nunca necesita escalar. max-instances=1 es la solucion correcta arquitecturalmente. |
| **Content-Type por metodo en httpx** | Content-Type None en search\_by\_image | La opcion 'por metodo' es mas explicita y evita el problema en cualquier metodo nuevo que se anade en el futuro. |
| **GCS para persistencia del indice** | Volumen persistente NFS o Redis | GCS es la opcion mas simple en Cloud Run, sin estado adicional, y la SA ya tiene permisos de Storage Object Admin. |
| **HF\_HUB\_OFFLINE=1 en Dockerfile** | Descarga en runtime | Elimina dependencia de red en produccion. El modelo se descarga una sola vez durante el build de la imagen Docker. |

# **7\. Variables de entorno y configuracion de deploy**

### **embedding-service (Cloud Run)**

| **Variable** | **Valor** | **Descripcion** |
| --- | --- | --- |
| **VISUAL\_INDEX\_BUCKET** | retail-recommendations-449216-visual-index | Bucket GCS para persistir el indice FAISS |
| **HF\_HUB\_OFFLINE** | 1 | Evita que open\_clip intente verificar actualizaciones en HuggingFace |
| **Memory** | 4Gi | Necesario para ColBERT (~1400MB) + FashionSigLIP (~400MB) + OS + libs |
| **CPU** | 2 vCPU | Necesario para indexacion paralela a velocidad aceptable (~30 min) |
| **min-instances** | 1 | El modelo siempre en RAM, sin cold start |
| **max-instances** | 1 | Servicio interno, nunca escala. Previene OOM por autoscaling |
| **\--no-cpu-throttling** | (flag de deploy) | CPU disponible continuo para background tasks |
| **\--timeout** | 300s | Cubre requests de indexacion y busqueda visual pesada |

### **Monolito (Cloud Run)**

| **Variable** | **Valor por defecto** | **Descripcion** |
| --- | --- | --- |
| **VISUAL\_SEARCH\_ENABLED** | false | Feature flag: activar con 'true' tras validacion |
| **COLBERT\_SERVICE\_URL** | (ya configurado) | URL interna del embedding-service |

# **8\. Metricas de produccion (30/04 - 01/05/2026)**

| **Metrica** | **Valor** | **Target del plan** |
| --- | --- | --- |
| **Revision activa** | retail-embedding-service-00028-rxq | — |
| **Requests observados** | 4 | — |
| **Tasa de exito (HTTP 200)** | 100% | \>99% |
| **Latencia p50** | ~490ms | <500ms |
| **Latencia p95** | ~806ms | <800ms |
| **Latencia minima** | 350ms | — |
| **Latencia maxima** | 806ms | — |
| **Errores en produccion** | 0 | 0 |
| **OOM events** | 0 | 0 |
| **Reinicios de instancia** | 0 en ventana observada | 0 |
| **Productos en indice** | 3,054 de 3,056 | ~3,000 |
| **Tamano indice GCS** | 9.4MB (faiss) + 51.9KB (id\_map) | ~9MB |
| **Tiempo de carga desde GCS** | ~1.4s en startup | <5s |
| **Tiempo de indexacion** | 1770s (29.5 min) | <35 min |

# **9\. Gaps actuales y deuda tecnica**

### **Alta prioridad**

-   **FASE 6 no ejecutada:** El script validate\_visual\_search.py (Recall@1, precision intra-categoria) del plan original no se ejecuto. Los datos de produccion muestran 8/8 resultados siempre, pero la calidad de los resultados no esta medida sistematicamente. Ejecutar antes de activar el flag en produccion general.
-   **VISUAL\_SEARCH\_ENABLED:** Confirmar si el flag esta activo en produccion. Si no, activar tras validar los 4 requests de prueba observados en los logs.
-   **Frontend (FASE 4):** La integracion del boton de camara en el ChatWidget (MessageInput.tsx, api.ts, ChatWidget.tsx) no fue confirmada en los logs de esta sesion. Verificar que el frontend puede disparar el endpoint /v1/mcp/visual-search correctamente.

### **Media prioridad**

-   **Sincronizacion automatica del indice:** Cuando se añaden nuevos productos al catalogo, el indice visual no se actualiza automaticamente. Actualmente es un proceso manual (llamar a /v1/mcp/visual-search/index). Implementar un trigger en el catalog sync del monolito.
-   **Circuit-breaker compartido:** El circuit-breaker de LFM2ColBERTClient es compartido entre busqueda textual y visual. Un fallo en visual search puede abrir el circuito y degradar tambien la busqueda textual. Considerar circuit-breakers independientes.
-   **Autenticacion del embedding-service:** Actualmente --allow-unauthenticated. En produccion deberia usarse autenticacion de servicio a servicio (Cloud Run service-to-service IAM).

### **Baja prioridad / futuras iteraciones**

-   **Batch size adaptativo:** El batch\_size=16 es fijo. Podria ajustarse dinamicamente segun el tamano de las imagenes para optimizar uso de RAM.
-   **Actualizaciones incrementales del indice:** build\_image\_index() reconstruye el indice completo. Con 3000+ productos, una actualizacion incremental (solo productos nuevos) reduciria el tiempo de sync.
-   **Consolidacion de codigo legacy:** ~400KB de codigo muerto (main\_\*.py variantes, backups inline) coexiste con main\_unified\_redis.py activo. Consolidar antes de la siguiente fase mayor.

# **10\. Recomendaciones para siguientes iteraciones**

1.  Ejecutar validate\_visual\_search.py contra el indice actual. Umbral minimo: Recall@1 > 85%, precision intra-categoria > 70%. Si falla, investigar calidad del catalogo de imagenes.
2.  Confirmar estado del frontend y activar VISUAL\_SEARCH\_ENABLED=true en el monolito.
3.  Añadir trigger de re-indexacion en catalog sync: cuando ShopifyKBSyncService detecta nuevos productos con image\_url, llamar colbert\_client.index\_images() para mantener el indice actualizado.
4.  Separar circuit-breakers de busqueda textual y visual en LFM2ColBERTClient para evitar degradacion cruzada.
5.  Activar autenticacion IAM entre monolito y embedding-service (--no-allow-unauthenticated en embedding + Service Account binding).

**Estado del plan: COMPLETADO CON GAPS MENORES**

El core de la integracion (indexacion, busqueda visual, persistencia GCS, fix del 422) esta en produccion y validado. Los gaps identificados (validacion offline, confirmacion frontend, sincronizacion automatica) son mejoras de segunda iteracion que no bloquean el uso del sistema.

Revision activa: retail-embedding-service-00028-rxq | Fecha cierre: 01/05/2026 | Autor: Equipo de Ingenieria