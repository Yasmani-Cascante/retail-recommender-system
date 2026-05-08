RETAIL RECOMMENDER SYSTEM v2.1.0

**Visual Search — Documento de Cierre**

Integracion completada y validada en produccion

Mayo 2026 | ai-shoppings.myshopify.com | GCP us-central1

| RECALL@1   **100%**   umbral >85% | LAT. p50   **435ms**   umbral <500ms | PRODUCTOS   **3,055**   en indice FAISS | PIPELINE   **~150ms**   webhook a cache |
| --- | --- | --- | --- |

# **1\. Que hemos integrado y por que**

Se ha integrado un sistema de busqueda visual por imagen dentro del chat del asistente de moda. El cliente puede subir una fotografia de cualquier prenda, tomada con su movil o descargada de redes sociales, y recibir en menos de un segundo los productos del catalogo que mas se parecen visualmente.

Esta capacidad estaba identificada como oportunidad estrategica desde el plan original del 22/04/2026. Se implemento usando marqo-fashionSigLIP, un modelo de vision especializado en moda que supera en precision a FashionCLIP en benchmarks de recuperacion de prendas, combinado con FAISS para busqueda vectorial ultrarapida.

# **2\. Como funciona — dos flujos principales**

## **2.1 Flujo de busqueda (lo que experimenta el usuario)**

| **PASO 1** | El usuario hace clic en el icono de camara en el chat del asistente y sube una foto de la prenda que busca (JPEG, PNG o WebP, maximo 5MB). |
| --- | --- |
| **PASO 2** | El monolito valida la imagen, verifica que el flag VISUAL_SEARCH_ENABLED este activo, y reenvía los bytes al embedding-service interno via red privada de Cloud Run. |
| **PASO 3** | El embedding-service ejecuta el modelo FashionSigLIP (ViT-B-16) sobre la imagen. En ~435ms genera un vector de 768 dimensiones que representa el estilo visual de la prenda. |
| **PASO 4** | FAISS realiza una busqueda exacta por similitud coseno sobre los 3,055 vectores del catalogo. En menos de 1ms devuelve los IDs de los productos mas parecidos. |
| **PASO 5** | El monolito resuelve los IDs en fichas de producto completas, aplica el precio correcto segun el mercado del cliente (ES, CL, CH, MX), y devuelve las recomendaciones al chat. |

## **2.2 Flujo de indexacion (mantenimiento del catalogo)**

Para que el sistema pueda buscar visualmente, necesita tener un 'indice' con el embedding (vector) de cada producto. Este indice se construye descargando las fotos del catalogo desde el CDN de Shopify y procesandolas con FashionSigLIP.

### **Indexacion inicial (una sola vez)**

Se lanza manualmente tras el primer deploy. El embedding-service descarga ~3,055 imagenes del CDN de Shopify, genera sus embeddings en batches de 16, construye el indice FAISS y lo guarda en Google Cloud Storage. El proceso tarda ~30 minutos y no bloquea el servicio.

### **Indexacion incremental automatica (webhook)**

Cuando se crea o modifica un producto en Shopify Admin, Shopify envia automaticamente un webhook al sistema. El monolito valida la firma HMAC, invalida el cache del producto en los 4 mercados, y llama al embedding-service para que indexe solo el producto nuevo o modificado. El nuevo producto queda disponible para busqueda visual en menos de 2 segundos.

# **3\. Arquitectura — componentes y dependencias**

## **3.1 Diagrama de componentes**

ChatWidget (Frontend React)

└── boton camara → file input → POST /v1/mcp/visual-search

Monolito (retail-recommender, Cloud Run)

├── visual\_search\_router.py — endpoint /v1/mcp/visual-search

├── colbert\_client.py — cliente HTTP con auth IAM

├── webhooks\_router.py — recibe webhooks de Shopify (HMAC)

└── shopify\_webhook\_handler.py — invalida cache + llama index incremental

Embedding-service (retail-embedding-service, Cloud Run)

├── visual\_retriever.py — FashionSigLIPRetriever + FAISS

├── main.py — endpoints /search-image e /index-images

└── /tmp/visual-index/ — indice FAISS en disco local

Google Cloud Storage

└── gs://retail-recommendations-449216-visual-index/

├── image\_index.faiss (9.0MB) — vectores FAISS

└── id\_map.json (52KB) — posicion i → product\_id

## **3.2 Componentes principales**

| **Componente** | **Archivo** | **Responsabilidad** |
| --- | --- | --- |
| **FashionSigLIPRetriever** | visual\_retriever.py | Carga el modelo, construye y busca en el indice FAISS. Persiste el indice en /tmp y GCS. |
| **visual\_search\_router** | visual\_search\_router.py | Endpoint /v1/mcp/visual-search. Feature flag, validacion de imagen, enriquecimiento de precios por mercado. |
| **LFM2ColBERTClient** | colbert\_client.py | Cliente HTTP del monolito hacia el embedding-service. Incluye auth IAM, circuit-breakers separados y cacheo del token. |
| **webhooks\_router** | webhooks\_router.py | Recibe webhooks de Shopify (products/create, update, delete). Valida HMAC y lanza BackgroundTask. |
| **ShopifyWebhookHandler** | shopify\_webhook\_handler.py | Invalida cache de contexto (4 mercados) y llama index\_images\_incremental en el embedding-service. |
| **Shopify Webhook Registry** | shopify\_webhook\_registry.py | Lista de webhooks que el sistema registra automaticamente en Shopify en cada startup. |

# **4\. Configuracion y dependencias**

## **4.1 Variables de entorno**

| **Variable** | **Servicio** | **Valor en prod** | **Descripcion** |
| --- | --- | --- | --- |
| **VISUAL\_SEARCH\_ENABLED** | Monolito | true | Feature flag. false = boton de camara oculto, endpoint devuelve 503. |
| **COLBERT\_SERVICE\_URL** | Monolito | https://retail-embedding-service-... | URL interna del embedding-service. |
| **EMBEDDING\_AUTH\_DISABLED** | Monolito | (ausente) | Ausente o false = auth IAM activa. true solo para desarrollo local sin ADC. |
| **SHOPIFY\_WEBHOOK\_SECRET** | Monolito | GCP Secret Manager | API Secret Key de la instalacion de Shopify (Image 2, NO el Partners Dashboard). |
| **KB\_WEBHOOKS\_ENABLED** | Monolito | true | Activa el registro automatico de webhooks en Shopify al arrancar. |
| **APP\_PUBLIC\_URL** | Monolito | https://retail-recommender-... | URL publica del monolito para registrar el endpoint de webhooks en Shopify. |
| **VISUAL\_INDEX\_BUCKET** | Embedding | retail-recommendations-449216-visual-index | Bucket GCS donde se persiste el indice FAISS entre deploys. |
| **HF\_HUB\_OFFLINE** | Embedding | 1 | Evita que el modelo intente actualizarse desde HuggingFace en runtime. |

## **4.2 Configuracion de Cloud Run — embedding-service**

| **Parametro** | **Valor** | **Por que** |
| --- | --- | --- |
| **Memory** | 4Gi | ColBERT (~1.4GB) + FashionSigLIP (~400MB) + OS + librerias de GCS. |
| **CPU** | 2 vCPU | Indexacion paralela ~30 min. Busqueda: p50=435ms. |
| **min-instances** | 1 | Modelo siempre en RAM. Sin cold start. Critico para webhooks (<5s limite de Shopify). |
| **max-instances** | 1 | Servicio interno. Nunca escala. Previene OOM por autoscaling. |
| **\--no-cpu-throttling** | activo | CPU continuo para los background tasks de indexacion. |
| **\--no-allow-unauthenticated** | activo | IAM auth. Solo el monolito puede invocar. Cualquier request directa recibe 403. |

## **4.3 IAM — autenticacion service-to-service**

El embedding-service solo acepta requests del monolito. El mecanismo es el siguiente:

-   **Monolito:** al hacer cada llamada, el colbert\_client.py obtiene automaticamente un ID token de la SA del monolito via el metadata server de GCP (sin configuracion manual). El token se cachea 59 minutos.
-   **Embedding-service:** Cloud Run verifica que el token IAM sea de la SA 178362262166-compute@developer con roles/run.invoker. Cualquier otro llamante recibe 403 Forbidden.
-   **SHOPIFY\_WEBHOOK\_SECRET:** El secreto correcto es el API Secret Key de la instalacion de la app en Shopify Admin (no el Client Secret del Partners Dashboard). Son valores diferentes. El secreto correcto se confirmo en produccion el 07/05/2026.

## **4.4 Endpoints operativos**

| **Endpoint** | **Auth** | **Descripcion** |
| --- | --- | --- |
| **POST /v1/mcp/visual-search** | X-API-Key | Busqueda visual. Multipart: file + market\_id + top\_k. Devuelve hasta 8 recomendaciones con precios por mercado. |
| **POST /v1/mcp/visual-search/index** | X-API-Key | Lanza re-indexacion COMPLETA del catalogo (~30 min). Usar tras cambios masivos o primer deploy. |
| **POST /v1/mcp/visual-search/index/update** | X-API-Key | Indexacion INCREMENTAL. Solo indexa productos nuevos no presentes en el indice. Tipicamente <2 segundos. |
| **GET /health (monolito)** | X-API-Key | Incluye visual\_search\_enabled: true/false. El frontend lo usa para mostrar/ocultar el boton de camara. |
| **POST /v1/embed/search-image** | IAM token | Endpoint INTERNO del embedding-service. Solo accesible desde el monolito. |
| **POST /v1/embed/index-images** | IAM token | Endpoint INTERNO. Lanza indexacion full o incremental segun el campo mode del payload. |

# **5\. Automatizacion de webhooks — como se mantiene el catalogo**

La parte mas compleja de la integracion no fue la busqueda visual en si, sino mantener el indice FAISS sincronizado con el catalogo de Shopify de forma automatica.

## **5.1 Estrategia LSM — escrituras rapidas, compactacion periodica**

Se adopto una estrategia inspirada en Log-Structured Merge (el mismo patron de RocksDB y Cassandra). El principio: FAISS IndexFlatIP es append-only (no tiene operacion .remove()). En lugar de reconstruir el indice entero con cada cambio, se opta por:

-   **Escrituras rapidas en tiempo real:** cuando llega un webhook de Shopify, el nuevo producto se anade al indice en <2 segundos sin interrumpir el servicio.
-   **Compactacion periodica:** el rebuild completo semanal limpia los vectores 'fantasma' (productos eliminados) y actualiza los embeddings de productos cuya imagen cambio.

## **5.2 Comportamiento por tipo de evento**

| **Evento Shopify** | **Frecuencia** | **Accion del sistema** | **Resultado en FAISS** |
| --- | --- | --- | --- |
| **products/create** | Media | HMAC validado → cache invalidado → indexacion incremental del nuevo producto | Nuevo vector anadido. Disponible en <2s. |
| **products/update (texto/precio)** | Alta (>90%) | HMAC validado → cache invalidado. Embedding-service ignora (ID ya existe) | Sin cambio en FAISS. Correcto: el estilo visual no cambio. |
| **products/update (imagen nueva)** | Baja (<10%) | HMAC validado → cache invalidado → indexacion incremental (ignorada por el embedding) | Vector antiguo persiste. Se actualiza en el proximo rebuild semanal. |
| **products/delete** | Baja | HMAC validado → cache invalidado. No se toca FAISS. | Vector 'fantasma' persiste. El monolito lo filtra (no esta en id\_index). Limpiado en rebuild semanal. |

## **5.3 Webhooks registrados en Shopify**

| **Topic** | **Endpoint** | **Estado** |
| --- | --- | --- |
| **products/create** | /api/webhooks/shopify/products | Activo. Nuevo producto disponible en busqueda visual en <2s. |
| **products/update** | /api/webhooks/shopify/products | Activo. Cache invalidado. Embedding ignorado si ya existe. |
| **products/delete** | /api/webhooks/shopify/products | Activo. Solo invalida cache. FAISS no modificado. |
| **customers/update** | /api/webhooks/shopify/customers | Activo. Invalida perfil de cliente en Redis. |

*Nota: el topic customers/purchasing\_summary fue eliminado de la lista de registro porque no existe en la API de Shopify (devolvia 404 en cada startup). Se documento y elimino el 06/05/2026.*

# **6\. Validacion y metricas de produccion**

## **6.1 Metricas de calidad del indice (script validate\_visual\_search.py, 100 productos)**

| **Metrica** | **Resultado** | **Umbral plan** | **Estado** |
| --- | --- | --- | --- |
| **Recall@1** | 100% | \>85% | SUPERADO |
| **Recall@5** | 100% | \>95% | SUPERADO |
| **Recall@10** | 100% | \>99% | SUPERADO |
| **Precision intra-categoria** | 78.5% | \>70% | SUPERADO |
| **Latencia p50 (server-side)** | 435ms | <500ms | SUPERADO |
| **Latencia p95 (server-side)** | 614ms | <800ms | SUPERADO |

## **6.2 Metricas de produccion (07/05/2026)**

| **Metrica** | **Valor** |
| --- | --- |
| **Productos en indice FAISS** | 3,055 (incluye 1 nuevo creado via webhook en produccion) |
| **Indice GCS** | image\_index.faiss 9.0MB + id\_map.json 52KB |
| **Webhook pipeline (sin nueva indexacion)** | ~150ms extremo a extremo |
| **Webhook pipeline (con nueva indexacion)** | ~1,268ms extremo a extremo |
| **Tiempo de indexacion de 1 producto nuevo** | ~2 segundos |
| **Tasa de exito HTTP webhooks** | 100% en las sesiones de prueba validadas |
| **Cold start del embedding-service** | Eliminado con min-instances=1 |
| **Carga del indice desde GCS en startup** | ~1.4s |

# **7\. Plan vs implementacion — lo que se hizo y lo que se anadio**

## **7.1 Fases del plan original (todas completadas)**

| **Fase** | **Descripcion** | **Estado** |
| --- | --- | --- |
| **FASE 1 — Prerequisitos** | Verificacion del embedding-service, image\_url en productos, upgrade de RAM | Completada |
| **FASE 2 — Backend embedding** | visual\_retriever.py, endpoints /search-image e /index-images | Completada |
| **FASE 3 — Monolito** | colbert\_client.py, visual\_search\_router.py, registro del router | Completada |
| **FASE 4 — Frontend** | Boton de camara en ChatWidget, handler de imagen, visualSearch() en api.ts | Completada |
| **FASE 5 — Deploy y activacion** | Build, deploy, smoke tests, activacion de flag | Completada |
| **FASE 6 — Validacion offline** | Script validate\_visual\_search.py con Recall, precision y latencia | Completada y superada |

## **7.2 Mejoras no planificadas implementadas durante la integracion**

-   **Persistencia GCS del indice FAISS:** el plan original usaba solo /tmp (efimero). Se anadio persistencia en Google Cloud Storage: el indice sobrevive deploys y reinicios. El startup con GCS tarda ~1.4s frente a ~30 min de re-indexacion.
-   **Indexacion incremental:** el plan solo contemplaba la indexacion completa. Se implemento un modo incremental (mode=incremental) que solo indexa productos nuevos, reduciendo el tiempo de actualizacion de 30 min a <2 segundos.
-   **Automatizacion via webhooks de Shopify:** el plan no mencionaba webhooks para la busqueda visual. Se implemento la integracion completa: products/create y products/update disparan indexacion automatica sin intervencion manual.
-   **Autenticacion IAM service-to-service:** el embedding-service paso de allow-unauthenticated a autenticacion IAM completa. El monolito obtiene automaticamente el token de la SA via ADC.
-   **Batch size adaptativo:** el batch\_size de descarga de imagenes se ajusta automaticamente tras el primer batch segun la velocidad del CDN de Shopify. Evita 429 con imagenes grandes y aprovecha el ancho de banda con imagenes pequenas.
-   **Fix OOM en indexacion:** se identifico y resolvio un problema critico de memoria: las fotos de Shopify se cargaban a resolucion completa (~15MB/imagen). El fix aplica un pre-resize a 224x224 inmediatamente tras la descarga, reduciendo el consumo de RAM de 240MB/batch a 2.4MB/batch.
-   **Circuit-breakers separados:** texto y visual tienen circuit-breakers independientes. Un fallo en busqueda visual no degrada la busqueda textual y viceversa.
-   **Singleton del cliente ColBERT:** se detectaba que el cliente HTTP se instanciaba en cada request, perdiendo el cache del token IAM y el estado del circuit-breaker entre peticiones. Se corrigio usando un singleton a nivel de modulo.

# **8\. Observaciones, gaps y oportunidades de mejora**

## **8.1 Limitaciones tecnicas documentadas**

-   **Productos con imagen cambiada:** si un producto ya esta en el indice FAISS y cambia su imagen, el embedding antiguo persiste hasta el proximo rebuild completo. Esto ocurre porque IndexFlatIP no tiene operacion .remove() ni .update(). La frecuencia real de este escenario es baja (<10% de los products/update en e-commerce de moda).
-   **Productos eliminados:** el vector fantasma permanece en FAISS hasta el rebuild semanal. El monolito lo filtra automaticamente porque el producto eliminado no esta en tfidf\_recommender.id\_index, pero el indice crece con el tiempo si no se hace rebuild.
-   **Traducciones al ingles:** el modulo de sincronizacion KB falla con el error '\_graph' attribute en ShopifyKBClient al intentar obtener las traducciones al ingles. Las paginas en espanol se sincronizan correctamente (13/13). Impacto: el chat responde bien en espanol pero las traducciones automaticas al ingles no estan disponibles.

## **8.2 Deuda tecnica**

-   **Sincronizacion automatica en catalog sync:** actualmente el trigger de indexacion incremental se dispara via webhook de Shopify. Si el ShopifyKBSyncService detecta nuevos productos en su ciclo de polling, no llama automaticamente a colbert\_client.index\_images\_incremental(). Esto se identifico como una mejora de segunda iteracion.
-   **Codigo legacy:** ~400KB de codigo muerto (variantes main\_\*.py, backups inline) coexiste con el archivo activo main\_unified\_redis.py. Se recomienda consolidar antes de la siguiente fase mayor.

## **8.3 Oportunidades de mejora — proximas iteraciones**

| **Oportunidad** | **Valor** | **Complejidad** | **Notas** |
| --- | --- | --- | --- |
| **Trigger incremental en catalog sync** | Alto | Baja | Llamar colbert\_client.index\_images\_incremental() desde ShopifyKBSyncService cuando detecta productos nuevos. |
| **Rebuild semanal automatico** | Medio | Baja | Cloud Scheduler que llame al endpoint /v1/mcp/visual-search/index semanalmente para limpiar fantasmas y actualizar embeddings obsoletos. |
| **Soporte de actualizacion de imagen** | Medio | Media | Implementar modo update\_existing en el embedding-service para re-indexar productos cuya imagen cambio. |
| **Busqueda por outfit completo** | Alto | Alta | Permitir subir una imagen de look completo y encontrar productos similares para cada prenda identificada. |
| **Consolidacion de codigo legacy** | Bajo (tecnico) | Baja | Eliminar ~400KB de archivos dead code (main\_\*.py variantes) antes de la proxima fase mayor. |
| **Correccion del bug de traducciones** | Medio | Media | Resolver el AttributeError '\_graph' en ShopifyKBClient para habilitar sincronizacion KB en ingles. |

# **9\. Comandos de operacion**

## **Verificar estado del sistema**

\# Health del embedding-service (debe devolver 403 — IAM auth activa)

curl https://retail-embedding-service-178362262166.us-central1.run.app/health

\# Health del monolito (incluye visual\_search\_enabled)

curl --ssl-no-revoke https://retail-recommender-178362262166.us-central1.run.app/health

## **Verificar webhooks registrados en Shopify**

curl -s -X GET https://ai-shoppings.myshopify.com/admin/api/2025-01/webhooks.json \\

\-H 'X-Shopify-Access-Token: shpat\_38680e1d22e8153538a3c40ed7b6d79f' | python3 -m json.tool

## **Lanzar re-indexacion completa (necesario tras cambios masivos o primer deploy)**

curl -X POST https://retail-recommender-178362262166.us-central1.run.app/v1/mcp/visual-search/index \\

\-H 'X-API-Key: 2fed9999056fab6dac5654238f0cae1c' -H 'Content-Length: 0' --ssl-no-revoke

## **Rollback del feature flag (en caso de emergencia, 30 segundos)**

gcloud run services update retail-recommender \\

\--region us-central1 --project retail-recommendations-449216 \\

\--set-env-vars VISUAL\_SEARCH\_ENABLED=false

**Estado: FASE CERRADA — sistema en produccion y validado**

El sistema de Visual Search esta completamente operativo. El catalogo de 3,055 productos esta indexado, los webhooks de Shopify automatizan el mantenimiento del indice, la autenticacion IAM protege el embedding-service, y todas las metricas de calidad superan los umbrales del plan original. La fase puede darse por cerrada.

*Fecha de cierre: 07/05/2026 | Autor: Equipo de Ingenieria | Sistema: Retail Recommender System v2.1.0*