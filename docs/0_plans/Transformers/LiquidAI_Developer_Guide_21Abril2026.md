**RETAIL RECOMMENDER SYSTEM**

Liquid AI Integration — Developer Guide

*v2.1.0 — Abril 2026*

| **Entry point: main\_unified\_redis.py**   GCP Project: retail-recommendations-449216   Service URL: retail-recommender-lzf2y6pspa-uc.a.run.app | **Fases completadas: A ✓ B ✓ C ✓**   Prerequisito: hybrid\_detector.py bug FIXED   Dead code eliminado (main\_\*.py variants) |
| --- | --- |

# **1\. Arquitectura del sistema**

## **▸ Visión general: tres puntos de integración**

Los modelos LFM2 de Liquid AI se integran en tres puntos quirúrgicos del pipeline existente. Nada de la arquitectura conversacional, Redis state management, o el intent detector cambia. Los tres puntos son:

| **Punto** | **Componente afectado** | **Modelo** | **Flag** |
| --- | --- | --- | --- |
| **Fase A** | mcp_personalization_engine.py → _generate_claude_personalized_response() | LFM2-24B-A2B | LFM_MCP_ENABLED |
| **Fase B** | kb_contextualizer.py → generate_contextual_answer() | LFM2.5-1.2B | LFM_KB_ENABLED |
| **Fase C** | hybrid_recommender.py → get_recommendations() + embedding-service | LFM2-ColBERT-350M | LFM_COLBERT_ENABLED |

## **▸ Diagrama lógico del pipeline completo**

| POST /v1/mcp/conversation   │   ├─ Language detection (mcp\_router.py)   ├─ Session management (ConversationStateManager + Redis)   │   ├─ Intent Detection \[sklearn TF-IDF + LR — SIN CAMBIOS\]   │ ├─ TRANSACTIONAL ──────────────────────────────────────────────   │ │ ├─ HybridRecommender.get\_recommendations()   │ │ │ ├─ \[Fase C ON\] LFM2ColBERTClient.search(query) ← Liquid AI   │ │ │ ├─ \[Fase C OFF\] TF-IDF vectorizer (fallback)   │ │ │ └─ Google Retail API (collaborative filtering)   │ │ └─ MCPPersonalizationEngine.\_generate\_response()   │ │ ├─ \[Fase A ON\] UnifiedLLMClient → OpenRouter → LFM2-24B ← Liquid AI   │ │ └─ \[Fase A OFF\] AsyncAnthropic → Claude Haiku (fallback)   │ │   │ └─ INFORMATIONAL ──────────────────────────────────────────────   │ ├─ KB lookup (Neon PG + Redis cache — SIN CAMBIOS)   │ └─ KBContextualizer.generate\_contextual\_answer() \[si query específica\]   │ ├─ \[Fase B ON\] UnifiedLLMClient → OpenRouter → LFM2.5-1.2B ← Liquid AI   │ └─ \[Fase B OFF\] AsyncAnthropic → Claude Haiku (fallback)   │   └─ ConversationResponse → Redis state save → HTTP response |
| --- |

## **▸ Componentes clave**

-   **UnifiedLLMClient (src/api/core/llm\_client.py):** Adaptador que expone una interfaz única complete(system, user) → LLMResponse independientemente de si el backend es Anthropic o OpenRouter. Creado en Fase A, usado en A y B.
-   **LFM\_MCP\_CONFIG / LFM\_KB\_CONFIG (src/api/core/claude\_config.py):** Configuraciones de modelo para cada fase. provider='openrouter', max\_tokens, temperature.
-   **LFM2ColBERTClient (src/api/services/colbert\_client.py):** Cliente HTTP asíncrono con circuit-breaker (3 fallos → abre por 60s) para el embedding-service.
-   **embedding-service (services/embedding-service/):** Microservicio FastAPI independiente en Cloud Run. Expone /v1/embed/index (indexar catálogo) y /v1/embed/search (buscar). Usa pylate + LFM2-ColBERT-350M.

# **2\. Implementación por Fase**

## **▸ Fase A — LFM2-24B: Personalización MCP**

Reemplaza Claude Sonnet ($3/$15 por 1M tokens) por LFM2-24B-A2B vía OpenRouter ($0.03/$0.12). El prompt no cambia, solo el cliente que lo ejecuta.

### **Archivos modificados**

-   src/api/core/llm\_client.py — NUEVO (adaptador universal)
-   src/api/core/claude\_config.py — añade LFM\_MCP\_CONFIG y LFM\_KB\_CONFIG
-   src/api/mcp/engines/mcp\_personalization\_engine.py — añade ruta LFM en \_\_init\_\_ y \_generate\_claude\_personalized\_response()

### **Patrón de integración en \_\_init\_\_**

| self.\_lfm\_mcp\_enabled = os.environ.get('LFM\_MCP\_ENABLED', 'false').lower() == 'true'   if self.\_lfm\_mcp\_enabled:   self.\_lfm\_client = UnifiedLLMClient(   provider=LFM\_MCP\_CONFIG\['provider'\], # 'openrouter'   model=LFM\_MCP\_CONFIG\['model'\], # 'liquid/lfm-2-24b-a2b'   max\_tokens=LFM\_MCP\_CONFIG\['max\_tokens'\], # 300   temperature=LFM\_MCP\_CONFIG\['temperature'\], # 0.7   )   else:   self.\_lfm\_client = None |
| --- |

### **Patrón de ejecución con fallback automático**

| if self.\_lfm\_mcp\_enabled and self.\_lfm\_client:   try:   resp = await asyncio.wait\_for(   self.\_lfm\_client.complete(system\_prompt, user\_prompt),   timeout=8.0   )   return resp.content # LFM respondió OK   except Exception as e:   logger.warning('LFM MCP call failed, falling back to Claude: %s', e)   \# continúa hacia la ruta Claude abajo   \# Ruta Claude (default / fallback)   claude\_response = await self.claude.messages.create(...)   return claude\_response.content\[0\].text |
| --- |

## **▸ Fase B — LFM2.5-1.2B: KB Contextualización**

Reemplaza Claude Haiku en kb\_contextualizer.py. Tarea RAG pura: documento KB + query específica → respuesta 2-3 frases. El modelo LFM2.5-1.2B está documentado explícitamente para RAG.

### **Lógica de activación (mismo patrón que Fase A)**

| \# Solo se llama cuando has\_specific\_entities() == True (~20-30% queries informacionales)   self.\_lfm\_kb\_enabled = os.environ.get('LFM\_KB\_ENABLED', 'false').lower() == 'true'   \# En generate\_contextual\_answer():   if self.\_lfm\_kb\_enabled and self.\_lfm\_client:   try:   resp = await asyncio.wait\_for(   self.\_lfm\_client.complete(system, user), timeout=5.0   )   return resp.content   except Exception as e:   logger.warning('LFM KB call failed, falling back to Haiku: %s', e)   \# fallback → Claude Haiku |
| --- |

## **▸ Fase C — LFM2-ColBERT-350M: Retrieval Semántico**

La más compleja. Introduce un segundo Cloud Run service (embedding-service) que corre LFM2-ColBERT-350M. El monolito lo llama vía HTTP interno. TF-IDF sigue siendo el fallback.

| **¿Por qué ColBERT mejora TF-IDF?**   TF-IDF: bag-of-words, no entiende semántica. 'vestido azul' y 'prenda azulada' tienen overlap ≈ 0. ColBERT: late interaction retrieval — encode query y documentos por separado, calcula MaxSim a nivel de token. Resultado: captura semántica sin el costo de cross-attention completo. Soporta ES, EN, FR, DE, IT, PT nativament. |
| --- |

### **Arquitectura del embedding-service**

| services/embedding-service/   ├── main.py # FastAPI: /health, /v1/embed/index, /v1/embed/search   ├── colbert\_retriever.py # LFM2ColBERTRetriever + PLAID index (pylate)   ├── Dockerfile # python:3.11-slim + torch CPU-only + modelo pre-baked   └── requirements.txt # fastapi, uvicorn, pylate>=1.2.0, transformers>=4.55.0 |
| --- |

### **Circuit-breaker en LFM2ColBERTClient**

| \# Después de 3 fallos consecutivos, el circuito se abre durante 60 segundos.   \# El monolito vuelve a TF-IDF automáticamente sin ninguna intervención manual.   if self.\_circuit\_open:   return None # caller usa TF-IDF   \# ... llamada HTTP ...   except Exception:   self.\_consecutive\_failures += 1   if self.\_consecutive\_failures >= 3:   self.\_circuit\_open = True   asyncio.get\_event\_loop().call\_later(60, reset\_circuit) # reset en 60s |
| --- |

## **▸ Decisiones técnicas clave**

-   **os.environ.get() directa (no lru\_cache):** Lección aprendida del 21/03. pydantic-settings con case\_sensitive=True no resuelve correctamente las variables de entorno en Cloud Run. Todos los flags se leen directamente de os.environ en cada \_\_init\_\_.
-   **OpenAI SDK para OpenRouter:** OpenRouter es API-compatible con OpenAI. Se reutiliza AsyncOpenAI con base\_url='https://openrouter.ai/api/v1'. No se añade nueva dependencia de cliente HTTP.
-   **Modelo pre-baked en Docker image:** El modelo ColBERT (~350MB) se descarga durante el docker build (RUN python -c 'ColBERT(...)'), no en el startup. Esto garantiza startup < 10s y elimina dependencia de HuggingFace en runtime.
-   **torch CPU-only:** Se instala torch+cpu (no CUDA) para mantener la imagen del embedding-service en ~900MB. GPU no es necesario para inferencia de un modelo de 350M parámetros a la escala actual.
-   **ingress internal en embedding-service:** El embedding-service no es accesible públicamente. El monolito lo llama directamente via red interna GCP (~5ms latencia). Esto reduce la superficie de ataque y el costo de egress.

# **3\. Variables de entorno**

| **Variable** | **Default** | **Valores** | **Descripción** |
| --- | --- | --- | --- |
| OPENROUTER_API_KEY | (req) | sk-or-v1-... | API key OpenRouter. Via GCP Secret Manager. Obligatoria para Fases A y B. |
| LFM_MCP_ENABLED | false | true\|false | Activa LFM2-24B para personalización MCP (Fase A). |
| LFM_KB_ENABLED | false | true\|false | Activa LFM2.5-1.2B para KB contextualización (Fase B). |
| LFM_COLBERT_ENABLED | false | true\|false | Activa ColBERT retrieval en HybridRecommender (Fase C). |
| COLBERT_SERVICE_URL | (req si C) | https://... | URL interna del embedding-service Cloud Run. Solo Fase C. |
| ANTHROPIC_API_KEY | (req) | sk-ant-... | Fallback para Fases A y B. Sin cambios respecto a setup previo. |
| ENABLE_INTENT_DETECTION | true | true\|false | Intent detection sklearn. Sin cambios. |
| ML_INTENT_ENABLED | true | true\|false | ML fallback en hybrid_detector. Sin cambios. |

## **▸ Comando de activación de flags**

| \# Activar Fase A   gcloud run services update retail-recommender \\   \--region us-central1 --project retail-recommendations-449216 \\   \--set-env-vars LFM\_MCP\_ENABLED=true   \# Rollback instantáneo (30s)   gcloud run services update retail-recommender \\   \--set-env-vars LFM\_MCP\_ENABLED=false   \# Mismo patrón para LFM\_KB\_ENABLED y LFM\_COLBERT\_ENABLED |
| --- |

# **4\. Flujo de ejecución — Query real**

Ejemplo: cliente en mercado CH escribe "I'm looking for elegant dresses" (Fases A, B, C activas).

| **1** | **Language detection (mcp\_router.py)**   detect\_language\_from\_text('I\\'m looking for elegant dresses') → 'en'.   Se pasa detected\_language='en' al handler. |
| --- | --- |

| **2** | **Session management**   get\_or\_create\_session(session\_id, user\_id, market\_id='CH').   Carga 2 turns previos con 8 IDs de productos ya vistos cada uno. |
| --- | --- |

| **3** | **Intent Detection (sklearn)**   hybrid\_detector.detect(query) → TRANSACTIONAL (confidence 0.78, method: ml\_fallback).   No hay return temprano: continúa al path de productos. |
| --- | --- |

| **4** | **Retrieval (Fase C activa)**   \[Fase C\] LFM2ColBERTClient.search('I\\'m looking for elegant dresses', top\_k=16).   ColBERT encode query → MaxSim contra índice PLAID → product\_ids.   \[Fallback\] Si falla → TF-IDF vectorizer. |
| --- | --- |

| **5** | **Diversificación (16 productos excluidos)**   shown\_products = {16 IDs de turns 1+2}.   ImprovedFallbackStrategies.smart\_fallback(n=8, exclude=shown\_products, user\_query=query).   Retorna 8 productos sin repetición. |
| --- | --- |

| **6** | **Enriquecimiento de precios**   \_enrich\_recommendations\_lazy(): Shopify GraphQL contextualPricing para mercado CH.   Convierte precios a CHF para los 8 productos. |
| --- | --- |

| **7** | **Personalización (Fase A activa)**   \[lang\] LFM path: using router-detected language='en'.   \_build\_advanced\_personalization\_prompt() con user\_language='en'.   UnifiedLLMClient → OpenRouter → LFM2-24B-A2B.   Respuesta: texto en inglés con contexto CH. |
| --- | --- |

| **8** | **State persistence**   add\_conversation\_turn\_with\_recommendations(recommendation\_ids=\[8 IDs\]).   Save a Redis (TTL 86400s). Confirmed: REDIS SAVE SUCCESS. |
| --- | --- |

# **5\. Testing y Validación**

## **▸ Tests de integración**

| \# Ejecutar antes del primer deploy con nuevas dependencias   pytest tests/integration/test\_liquid\_integration.py -v   \# Casos cubiertos:   \# - UnifiedLLMClient inicializa con ambos providers   \# - Fallback a Claude cuando OpenRouter falla (no HTTP 500)   \# - LFM\_MCP\_ENABLED=false nunca llama a OpenRouter   \# - Circuit-breaker se activa tras 3 fallos de ColBERT |
| --- |

## **▸ Protocolo de A/B manual (obligatorio antes de activar flag al 100%)**

| **#** | **Query** | **Qué validar** | **Criterio de pase** |
| --- | --- | --- | --- |
| **1** | busco vestidos elegantes para boda | Idioma ES, menciona precio EUR/MXN, max 2 productos no-vestido | **Idioma correcto** |
| **2** | I'm looking for casual blue shirts | Respuesta en EN, recomienda camisas, sin mezcla de idiomas | **Bilingual OK** |
| **3** | ropa para clima frío en Chile (market=CL) | Precios en CLP, no en EUR | **Market pricing** |
| **4** | algo similar a lo que me mostraste antes | No repite IDs del turn anterior | **Multi-turn** |
| **5** | ¿cuál es la política de devoluciones? | Detecta INFORMATIONAL, no activa path LFM-MCP | **Intent routing** |

| **Criterio de pase**   Si algún criterio falla en más del 20% de los casos (1 de 5 queries): NO activar el flag. Dejar en false y abrir issue. |
| --- |

## **▸ Validación del embedding-service (Fase C)**

| \# Después del deploy, ejecutar antes de activar LFM\_COLBERT\_ENABLED=true   import httpx, asyncio   async def validate\_colbert(url):   async with httpx.AsyncClient() as c:   \# 1. Health check   r = await c.get(f'{url}/health')   assert r.json()\['index\_size'\] > 0, 'Index vacío — llamar a /v1/embed/index'   \# 2. Latencia de búsqueda   r = await c.post(f'{url}/v1/embed/search',   json={'query': 'vestido elegante azul', 'top\_k': 5})   assert r.json()\['latency\_ms'\] < 200, 'Demasiado lento'   assert len(r.json()\['product\_ids'\]) > 0, 'Sin resultados'   print('OK:', r.json()) |
| --- |

# **6\. Mantenimiento y Debugging**

## **▸ Puntos de fallo más comunes**

| **Síntoma** | **Causa probable** | **Acción** |
| --- | --- | --- |
| Respuestas siempre en español con Fases A/B activas | detected_language no se propaga al engine. Ver fix BUG-LANG-LFM. | Verificar log: [lang] LFM path: using router-detected language='en' |
| LFM MCP call failed, falling back to Claude | OPENROUTER_API_KEY inválida o rate limit | Verificar en GCP Secret Manager. Revisar OpenRouter dashboard. |
| ColBERT circuit OPEN after 3 failures | embedding-service no responde | GET /health del embedding-service. Verificar min-instances=1. |
| index_size=0 en /health del embedding-service | Índice no construido tras restart del contenedor | Llamar manualmente a POST /v1/embed/index con el catálogo completo. |
| Generated 3 personalized recommendations (esperaba 8) | Bug NREC-3: sample_size hardcodeado + bug NREC-1: exclude_products no propagado | Fix ya aplicado en improved_fallback_exclude_seen.py (21/04/2026). |
| LFM MCP personalisation disabled — using Claude en logs de producción | LFM_MCP_ENABLED=false (default) o variable no inyectada | Verificar con: gcloud run services describe retail-recommender --format json \| jq '.spec.template.spec.containers[0].env' |

## **▸ Logs clave para diagnosticar (GCP Cloud Logging)**

| \# Confirmar que el flag está activo   LFM MCP personalisation enabled: model=liquid/lfm-2-24b-a2b   \# Confirmar que el idioma se detecta correctamente   \[lang\] LFM path: using router-detected language='en'   \# Confirmar respuesta de OpenRouter   LFM MCP response: model=liquid/lfm-2-24b-a2b-20260224 in=574 out=85   \# Confirmar ColBERT activo   LFM2-ColBERT retrieval enabled   \# Diagnosticar circuit-breaker   ColBERT circuit OPEN after 3 failures: \[error\]   \# Confirmar n=8 productos en diversificación   Generated 8 personalized recommendations   Top-up P2: added N products from other categories (needed M, pool=P) |
| --- |

## **▸ Reglas de logging (crítico para no romper el sistema)**

-   **src/api/core/ y src/recommenders/:** Usa logging.getLogger(\_\_name\_\_) con f-strings. NO usar kwargs de structlog (causan TypeError silencioso).
-   **src/api/routers/, src/api/services/, src/api/mcp/:** Usa structlog.get\_logger(\_\_name\_\_) con kwargs. NO usar f-strings con variables en kwargs.
-   **exc\_info=True obligatorio:** Todos los except no triviales deben incluir exc\_info=True para exponer el traceback completo en GCP Logs.

# **7\. Extensibilidad**

## **▸ Añadir un nuevo modelo LLM (Fases A o B)**

El patrón UnifiedLLMClient soporta cualquier proveedor compatible con la API de OpenAI. Para añadir uno nuevo:

-   Añadir una config dict en src/api/core/claude\_config.py (modelo, provider, max\_tokens, temperature).
-   Añadir la variable de entorno del flag en GCP Secret Manager.
-   En el engine correspondiente, añadir el bloque if flag: \_lfm\_client = UnifiedLLMClient(...) con el nuevo config.
-   No tocar el prompt. No tocar la lógica de fallback.

### **Si el proveedor no es compatible con OpenAI SDK**

| \# Añadir un nuevo método en UnifiedLLMClient:   async def \_complete\_nuevo\_proveedor(self, system: str, user: str) -> LLMResponse:   resp = await self.\_client.alguna\_llamada(system, user)   return LLMResponse(   content=resp.texto,   model=resp.modelo,   input\_tokens=resp.tokens\_entrada,   output\_tokens=resp.tokens\_salida,   )   \# Y en complete(), añadir el case:   elif self.provider == 'nuevo\_proveedor':   return await self.\_complete\_nuevo\_proveedor(system, user) |
| --- |

## **▸ Añadir nuevas fuentes de Knowledge Base**

La KB usa sub\_intents mapeados a documentos en Neon PG. Para añadir una nueva fuente:

-   Insertar el documento en la tabla knowledge\_base con el sub\_intent correspondiente (ej: 'size\_guide', 'warranty').
-   Añadir el nuevo sub\_intent al Enum InformationalSubIntent en src/api/core/intent\_types.py.
-   Añadir keywords al rule-based detector (src/api/core/intent\_detection.py) para que clasifique correctamente.
-   Opcional: regenerar el modelo sklearn si el volumen de queries del nuevo sub\_intent es significativo.

## **▸ Añadir un nuevo mercado (Shopify)**

-   **Shopify Admin:** Crear el mercado y configurar moneda.
-   **market\_utils.py / market\_config\_service.py:** Añadir el nuevo market\_id con su currency y tasa de conversión.
-   **mcp\_personalization\_engine.py → \_get\_market\_strategy\_weights():** Añadir el market\_id con sus pesos culturales.
-   **Liquid template:** Verificar que localization.market.handle devuelve el handle correcto para el nuevo mercado.

## **▸ Mejorar el ranking de recomendaciones**

El ranking actual combina ColBERT/TF-IDF (content-based) con Google Retail API (collaborative). Para mejorarlo:

-   **Señal de conversión:** Integrar el webhook de orders de Shopify para identificar qué recommendation\_ids derivaron en compra. Enriquecer el score con un factor de conversión en hybrid\_recommender.py.\_combine\_recommendations().
-   **Re-ranking por LFM2-24B:** En el prompt de personalización (Fase A), incluir el ranking de los 8 productos y pedir al modelo que los reordene según el contexto conversacional. El modelo ya tiene acceso a todos los campos del producto.
-   **A/B testing nativo:** El framework de \_track\_strategy\_effectiveness() en mcp\_personalization\_engine.py ya registra estrategias usadas en Redis. Conectar esos datos al análisis de conversiones para cerrar el loop.

*Retail Recommender System v2.1.0 — Liquid AI Integration Guide — Abril 2026*