| **Retail Recommender System v2.1.0**   **Plan de Integración — Liquid AI**   LFM2-ColBERT-350M · LFM2-24B-A2B · LFM2.5-1.2B   _Documento técnico para desarrolladores_ |
| --- |

| Versión | 1.0.0 — Abril 2026 |
| --- | --- |
| Estado | Plan aprobado — Listo para implementación |
| --- | --- |
| Sistema base | main\_unified\_redis.py — single entry point (dead code eliminado) |
| --- | --- |
| Bug resuelto | hybrid\_detector.py TRANSACTIONAL→INFORMATIONAL override — FIXED |
| --- | --- |
| Prerequisito OK | Dead code eliminado: main\_\*.py variants removidas |
| --- | --- |

# **Índice**

**0\.** Resumen ejecutivo y decisiones de diseño

**1\.** Arquitectura de la integración

**2\.** Prerequisitos e infraestructura

**3\.** FASE A — LFM2-24B via OpenRouter (Personalización MCP)

**4\.** FASE B — LFM2.5-1.2B via OpenRouter (KB Contextualización)

**5\.** FASE C — LFM2-ColBERT-350M self-hosted (Retrieval semántico)

**6\.** Testing y validación de calidad por fase

**7\.** Estrategia de rollback

**8\.** Proyección de costos

**9\.** Referencia de variables de entorno

**10\.** Cronograma y responsabilidades

# **0\. Resumen Ejecutivo y Decisiones de Diseño**

## **0.1 Objetivo**

Integrar los modelos LFM2 de Liquid AI para reemplazar progresivamente los componentes de IA del sistema, reduciendo costos de API en ~90% manteniendo o mejorando la calidad conversacional. La integración se hace en tres fases independientes, cada una con feature flag propio y rollback de un solo comando.

## **0.2 Qué se reemplaza y qué no**

| **Componente** | **Actual** | **Con Liquid AI** | **Fase** |
| --- | --- | --- | --- |
| MCP personalización | Claude Sonnet ($3/$15 per 1M) | LFM2-24B via OpenRouter ($0.03/$0.12) | A |
| --- | --- | --- | --- |
| KB contextualización | Claude Haiku ($0.25/$1.25 per 1M) | LFM2.5-1.2B via OpenRouter ($0.01/$0.02) | B |
| --- | --- | --- | --- |
| Product retrieval | TF-IDF vectorizer (bag-of-words) | LFM2-ColBERT-350M self-hosted ($0/mes) | C |
| --- | --- | --- | --- |
| Intent detection | sklearn TF-IDF + LR (96.26%) | Sin cambios — ya es óptimo | — |
| --- | --- | --- | --- |
| Conversational state | Redis + ConversationStateManager | Sin cambios | — |
| --- | --- | --- | --- |
| KB Knowledge Base | Neon PG + Redis triple-layer cache | Sin cambios | — |
| --- | --- | --- | --- |
| Frontend widget | React 18 UMD bundle | Sin cambios | — |
| --- | --- | --- | --- |

## **0.3 Principios de diseño de esta integración**

-   **Zero breaking changes:** Cada fase usa un feature flag independiente (default: OFF). El sistema en producción no cambia su comportamiento hasta que el flag se activa explícitamente.
-   **Fallback siempre disponible:** Si el cliente LFM falla o el flag está OFF, el sistema cae al comportamiento original (Claude). Nunca HTTP 500 por causa de Liquid AI.
-   **Un cambio a la vez:** Las fases A, B y C son completamente independientes. Se pueden implementar en cualquier orden o no implementar alguna.
-   **Validación antes de commit:** Cada fase incluye un test de calidad obligatorio (A/B) antes de hacer el switch a 100% del tráfico.
-   **Arquitectura existente respetada:** Se extiende claude\_config.py, ServiceFactory y el patrón de dependency injection ya establecidos. No se introduce nueva arquitectura de configuración.

# **1\. Arquitectura de la Integración**

## **1.1 Visión general: tres puntos de integración**

Los tres modelos de Liquid AI entran al sistema por puntos de integración quirúrgicos, sin modificar la arquitectura existente.

| REGLA FUNDAMENTAL: LFM2-24B y LFM2.5-1.2B se acceden vía OpenRouter usando el SDK de openai (API compatible con OpenAI). LFM2-ColBERT-350M se self-hostea en un microservicio Cloud Run separado y se llama vía HTTP interno. Son integraciones independientes con dependencias independientes. |
| --- |

El flujo de decisión con todos los flags activos sería:

| User query (POST /v1/mcp/conversation) |
| --- |
| │ |
| ├─ Intent detection (sklearn — SIN CAMBIOS) |
| │ |
| ├─ TRANSACTIONAL path: |
| │ ├─ HybridRecommender.get_recommendations() |
| │ │ ├─ [FASE C activa] LFM2ColBERTClient.search(query) → product_ids |
| │ │ ├─ TF-IDF (fallback si ColBERT falla) |
| │ │ └─ Google Retail API |
| │ └─ MCPPersonalizationEngine._generate_response() |
| │ ├─ [FASE A activa] OpenRouter → LFM2-24B-A2B |
| │ └─ Anthropic → Claude Haiku (fallback) |
| │ |
| └─ INFORMATIONAL path: |
| ├─ KB lookup (Neon/Redis — SIN CAMBIOS) |
| └─ KBContextualizer.contextualise() |
| ├─ [FASE B activa] OpenRouter → LFM2.5-1.2B |
| └─ Anthropic → Claude Haiku (fallback) |

## **1.2 Arquitectura del LLM client unificado**

La pieza central de las Fases A y B es un nuevo archivo: src/api/core/llm\_client.py — un adaptador que presenta la misma interfaz asíncrona independientemente del proveedor subyacente (Anthropic o OpenRouter).

| # src/api/core/llm_client.py (nuevo archivo — FASE A prerequisito) |
| --- |
|  |
| from anthropic import AsyncAnthropic |
| from openai import AsyncOpenAI |
| import os, logging |
|  |
| log = logging.getLogger(__name__) |
|  |
| class LLMResponse: |
| """Respuesta normalizada, independiente del proveedor.""" |
| def __init__(self, content: str, model: str, input_tokens: int, output_tokens: int): |
| self.content = content |
| self.model = model |
| self.input_tokens = input_tokens |
| self.output_tokens = output_tokens |
|  |
| class UnifiedLLMClient: |
| """ |
| Wrapper que abstrae Anthropic vs OpenRouter. |
| Expone un único método async: complete(system, user) -&gt; LLMResponse |
| El caller nunca sabe qué proveedor se está usando. |
| """ |
|  |
| def __init__(self, provider: str, model: str, max_tokens: int, temperature: float): |
| self.provider = provider # 'anthropic' \| 'openrouter' |
| self.model = model |
| self.max_tokens = max_tokens |
| self.temperature = temperature |
|  |
| if provider == 'openrouter': |
| api_key = os.environ.get('OPENROUTER_API_KEY') |
| if not api_key: |
| raise ValueError('OPENROUTER_API_KEY env var not set') |
| self._client = AsyncOpenAI( |
| base_url='https://openrouter.ai/api/v1', |
| api_key=api_key, |
| # OpenRouter recomienda estos headers opcionales para analytics |
| default_headers={ |
| 'HTTP-Referer': 'https://retail-recommender-lzf2y6pspa-uc.a.run.app', |
| 'X-Title': 'RetailRecommender', |
| } |
| ) |
| else: # 'anthropic' (default) |
| api_key = os.environ.get('ANTHROPIC_API_KEY') |
| self._client = AsyncAnthropic(api_key=api_key) |
|  |
| async def complete(self, system: str, user: str) -&gt; LLMResponse: |
| """ |
| Llama al LLM y devuelve LLMResponse normalizada. |
| Maneja las diferencias de API entre Anthropic y OpenAI internamente. |
| """ |
| if self.provider == 'openrouter': |
| return await self._complete_openrouter(system, user) |
| else: |
| return await self._complete_anthropic(system, user) |
|  |
| async def _complete_openrouter(self, system: str, user: str) -&gt; LLMResponse: |
| resp = await self._client.chat.completions.create( |
| model=self.model, |
| max_tokens=self.max_tokens, |
| temperature=self.temperature, |
| messages=[ |
| {'role': 'system', 'content': system}, |
| {'role': 'user', 'content': user}, |
| ] |
| ) |
| return LLMResponse( |
| content=resp.choices[0].message.content, |
| model=resp.model, |
| input_tokens=resp.usage.prompt_tokens, |
| output_tokens=resp.usage.completion_tokens, |
| ) |
|  |
| async def _complete_anthropic(self, system: str, user: str) -&gt; LLMResponse: |
| resp = await self._client.messages.create( |
| model=self.model, |
| max_tokens=self.max_tokens, |
| temperature=self.temperature, |
| system=system, |
| messages=[{'role': 'user', 'content': user}] |
| ) |
| return LLMResponse( |
| content=resp.content[0].text, |
| model=resp.model, |
| input_tokens=resp.usage.input_tokens, |
| output_tokens=resp.usage.output_tokens, |
| ) |

# **2\. Prerequisitos e Infraestructura**

| Estado inicial confirmado: hybrid_detector.py bug FIXED. Dead code (main_*.py variants) ELIMINADO. main_unified_redis.py es el único entry point activo. Estos prerequisitos ya están cumplidos. |
| --- |

## **2.1 Dependencias de Python**

Agregar al final de requirements.cloudrun.txt:

| # --- Liquid AI integration (agregado Fase A/B) --- |
| --- |
| openai&gt;=1.50.0 |
|  |
| # --- Liquid AI ColBERT service (embedding-service solamente, no monolith) --- |
| pylate&gt;=1.2.0 |
| transformers&gt;=4.55.0 |
| torch&gt;=2.1.0 |

| IMPORTANTE: torch y pylate se agregan SOLO al Dockerfile del embedding-service (Fase C). NO al Dockerfile.cloudrun del monolito principal. Agregar torch al monolito aumentaría la imagen ~2.5GB y el startup time significativamente. |
| --- |

## **2.2 Secretos en GCP Secret Manager**

Ejecutar desde terminal local (requiere permisos en el proyecto retail-recommendations-449216):

| # Crear el secret para OpenRouter |
| --- |
| echo -n 'sk-or-v1-XXXXXXXXXXXX' \| \ |
| gcloud secrets create openrouter-api-key \ |
| --data-file=- \ |
| --project=retail-recommendations-449216 |
|  |
| # Verificar que se creó correctamente |
| gcloud secrets versions access latest \ |
| --secret=openrouter-api-key \ |
| --project=retail-recommendations-449216 \| head -c 20 |

Mapear el secret a una variable de entorno en Cloud Run (mismo proceso que los otros secrets del servicio):

| gcloud run services update retail-recommender \ |
| --- |
| --region us-central1 \ |
| --project retail-recommendations-449216 \ |
| --set-secrets=OPENROUTER_API_KEY=openrouter-api-key:latest |

## **2.3 Upgrade de infraestructura del monolito (prerequisito para Fase C)**

Las Fases A y B no requieren cambios de infraestructura. La Fase C sí, porque lanza un nuevo Cloud Run service. Además, se recomienda hacer este upgrade antes de la Fase C:

| # Upgrade del monolito principal: 1GiB/1vCPU → 2GiB/2vCPU + min=1 |
| --- |
| gcloud run services update retail-recommender \ |
| --region us-central1 \ |
| --project retail-recommendations-449216 \ |
| --memory 2Gi \ |
| --cpu 2 \ |
| --min-instances 1 \ |
| --max-instances 10 |
|  |
| # Verificar el cambio |
| gcloud run services describe retail-recommender \ |
| --region us-central1 \ |
| --project retail-recommendations-449216 \ |
| --format='value(spec.template.spec.containers[0].resources.limits)' |

| Costo del upgrade: ~$30-45/mes adicionales (min-instances=1 mantiene la instancia viva). A cambio: cold start eliminado completamente, headroom para la Fase C, y latencia más estable en horas pico. |
| --- |

| **FASE A — LFM2-24B-A2B via OpenRouter: Personalización MCP** |
| --- |

| Modelo | liquid/lfm-2-24b-a2b |
| --- | --- |
| Acceso | OpenRouter API (OpenAI SDK compatible) |
| --- | --- |
| Costo | $0.03 input / $0.12 output por 1M tokens (vs Sonnet $3.00/$15.00 = 100x ahorro) |
| --- | --- |
| Feature flag | LFM\_MCP\_ENABLED=false (default OFF) |
| --- | --- |
| Archivo afectado | src/api/mcp/engines/mcp\_personalization\_engine.py |
| --- | --- |
| Archivos nuevos | src/api/core/llm\_client.py |
| --- | --- |
| Esfuerzo estimado | 2-3 días (incluye A/B test y validación) |
| --- | --- |
| Riesgo | Bajo — feature flag garantiza zero impact en producción hasta validar |
| --- | --- |

## **3.1 Contexto técnico**

El método \_generate\_claude\_personalized\_response() en mcp\_personalization\_engine.py ya usa self.claude\_config.get\_model\_config() desde la sesión del 21-22/03/2026. El prompt está reducido a ~500 tokens. La latencia real medida en producción con Haiku está en ~966ms.

LFM2-24B-A2B es un modelo MoE (Mixture-of-Experts) con 24B parámetros totales pero solo 2B activos por token. Disponible en OpenRouter a $0.03/$0.12 por 1M tokens. La API es completamente compatible con el SDK de openai (chat.completions.create).

## **3.2 Paso a paso: implementación**

### **Paso A.1 — Crear src/api/core/llm\_client.py**

Crear el archivo con el código exacto de la Sección 1.2 de este documento. Este archivo es el adaptador central para las Fases A y B.

### **Paso A.2 — Agregar LFM model configs a claude\_config.py**

Añadir las configuraciones de los modelos LFM al archivo existente de configuración:

| # En src/api/core/claude_config.py |
| --- |
| # Añadir después de la clase ClaudeModelConfig existente |
|  |
| # ─── LFM Model Configs (OpenRouter) ──────────────────────────────────── |
| # Estos configs siguen el mismo patrón que ClaudeModelConfig |
| # pero los usa UnifiedLLMClient, no el Anthropic SDK directamente. |
|  |
| LFM_MCP_CONFIG = { |
| 'provider': 'openrouter', |
| 'model': 'liquid/lfm-2-24b-a2b', |
| 'max_tokens': 300, |
| 'temperature': 0.7, |
| 'description': 'LFM2-24B MoE — MCP personalization replacement' |
| } |
|  |
| LFM_KB_CONFIG = { |
| 'provider': 'openrouter', |
| 'model': 'liquid/lfm-2.5-1.2b', |
| 'max_tokens': 250, |
| 'temperature': 0.3, |
| 'description': 'LFM2.5-1.2B — KB contextualisation replacement' |
| } |

### **Paso A.3 — Modificar mcp\_personalization\_engine.py**

Modificar el método \_generate\_claude\_personalized\_response() para soportar el flag LFM\_MCP\_ENABLED:

| # En src/api/mcp/engines/mcp_personalization_engine.py |
| --- |
| # Añadir import al inicio del archivo (junto a los imports existentes): |
|  |
| import os |
| from src.api.core.llm_client import UnifiedLLMClient, LLMResponse |
| from src.api.core.claude_config import LFM_MCP_CONFIG |
|  |
| # ───────────────────────────────────────────────────────────────────── |
| # En el método __init__ de MCPPersonalizationEngine, añadir DESPUÉS |
| # de self.claude_config = get_claude_config_service(): |
|  |
| # Leer flag directamente de env (no via lru_cache — lección aprendida 21/03) |
| self._lfm_mcp_enabled = os.environ.get('LFM_MCP_ENABLED', 'false').lower() == 'true' |
| if self._lfm_mcp_enabled: |
| self._lfm_client = UnifiedLLMClient( |
| provider=LFM_MCP_CONFIG['provider'], |
| model=LFM_MCP_CONFIG['model'], |
| max_tokens=LFM_MCP_CONFIG['max_tokens'], |
| temperature=LFM_MCP_CONFIG['temperature'], |
| ) |
| logger.info('LFM MCP personalisation enabled: model=%s', LFM_MCP_CONFIG['model']) |
| else: |
| self._lfm_client = None |
| logger.info('LFM MCP personalisation disabled — using Claude') |

Modificar \_generate\_claude\_personalized\_response() para usar el cliente correcto:

| async def _generate_claude_personalized_response(self, context, personalized_result): |
| --- |
| """ |
| Genera respuesta personalizada usando Claude o LFM2-24B según feature flag. |
| La lógica de prompt (system + user) no cambia — solo el cliente que lo ejecuta. |
| """ |
| system_prompt = self._build_personalized_system_prompt(context) |
| user_prompt = self._build_advanced_personalization_prompt(context, personalized_result) |
|  |
| # ── RUTA LFM (si flag activo) ────────────────────────────────────────── |
| if self._lfm_mcp_enabled and self._lfm_client: |
| try: |
| resp = await asyncio.wait_for( |
| self._lfm_client.complete(system_prompt, user_prompt), |
| timeout=8.0 # LFM-24B puede ser más lento que Haiku en primer request |
| ) |
| logger.info('LFM MCP response: model=%s in=%d out=%d', |
| resp.model, resp.input_tokens, resp.output_tokens) |
| return resp.content |
| except Exception as e: |
| # Fallback automático a Claude si LFM falla |
| logger.warning('LFM MCP call failed, falling back to Claude: %s', e) |
| # La ejecución continúa hacia la ruta Claude a continuación |
|  |
| # ── RUTA CLAUDE (default o fallback) ───────────────────────────────── |
| model_config = self.claude_config.get_model_config() |
| try: |
| claude_response = await asyncio.wait_for( |
| self.claude.messages.create( |
| model=model_config.model_name, |
| max_tokens=model_config.max_tokens, |
| temperature=model_config.temperature, |
| system=system_prompt, |
| messages=[{'role': 'user', 'content': user_prompt}] |
| ), |
| timeout=12.0 |
| ) |
| return claude_response.content[0].text |
| except Exception as e: |
| logger.error('Claude MCP call also failed: %s', e, exc_info=True) |
| return None # El caller ya tiene lógica de fallback sin personalización |

### **Paso A.4 — Agregar variable de entorno en Cloud Run**

| # Agregar LFM_MCP_ENABLED=false inicialmente (flag OFF por defecto) |
| --- |
| gcloud run services update retail-recommender \ |
| --region us-central1 \ |
| --project retail-recommendations-449216 \ |
| --set-env-vars LFM_MCP_ENABLED=false |
|  |
| # Para activar (solo después de A/B test exitoso — ver Sección 6): |
| # gcloud run services update retail-recommender \ |
| # --set-env-vars LFM_MCP_ENABLED=true |

### **Paso A.5 — Deploy y smoke test**

| # Deploy estándar |
| --- |
| gcloud run deploy retail-recommender \ |
| --source . \ |
| --region us-central1 \ |
| --project retail-recommendations-449216 |
|  |
| # Smoke test: verificar que el sistema arranca y el flag está OFF |
| curl -X POST https://retail-recommender-lzf2y6pspa-uc.a.run.app/v1/mcp/conversation \ |
| -H 'X-API-Key: &lt;api_key&gt;' \ |
| -H 'Content-Type: application/json' \ |
| -d '{"query": "busco vestidos elegantes", "market_id": "ES", "language": "es"}' |
|  |
| # Verificar en logs GCP que dice: |
| # LFM MCP personalisation disabled -- using Claude |

| **FASE B — LFM2.5-1.2B via OpenRouter: KB Contextualización** |
| --- |

| Modelo | liquid/lfm-2.5-1.2b |
| --- | --- |
| Acceso | OpenRouter API |
| --- | --- |
| Costo | $0.01/$0.02 por 1M tokens (vs Haiku $0.25/$1.25 = 15x ahorro) |
| --- | --- |
| Feature flag | LFM\_KB\_ENABLED=false (default OFF) |
| --- | --- |
| Archivo afectado | src/api/core/kb\_contextualizer.py |
| --- | --- |
| Esfuerzo estimado | 1-2 días |
| --- | --- |
| Riesgo | Muy bajo — tarea RAG simple, impacto de costo pequeño (~$1-2/mes) |
| --- | --- |

## **4.1 Contexto técnico**

kb\_contextualizer.py es llamado SOLO cuando has\_specific\_entities() devuelve True (~20-30% de las queries informacionales). La tarea es exactamente RAG: dado un documento KB y una query específica, responder en 2-3 frases. LFM2.5-1.2B está explícitamente diseñado y documentado para RAG. El modelo corre en < 1GB de RAM y a $0.01/$0.02 el impacto de costo es mínimo aunque la calidad sea idéntica a Haiku.

## **4.2 Paso a paso: implementación**

### **Paso B.1 — Modificar kb\_contextualizer.py**

El archivo ya usa AsyncAnthropic directamente. Añadir soporte para UnifiedLLMClient con el mismo patrón que la Fase A:

| # En src/api/core/kb_contextualizer.py |
| --- |
| # Añadir imports al inicio: |
|  |
| import os |
| from src.api.core.llm_client import UnifiedLLMClient |
| from src.api.core.claude_config import LFM_KB_CONFIG |
|  |
| # ───────────────────────────────────────────────────────────────────── |
| # Modificar el constructor de KBContextualizer (o la función factory): |
|  |
| class KBContextualizer: |
| def __init__(self, anthropic_client): |
| self._anthropic = anthropic_client |
|  |
| # LFM KB flag — leer directamente de env (no lru_cache) |
| self._lfm_kb_enabled = os.environ.get('LFM_KB_ENABLED', 'false').lower() == 'true' |
| if self._lfm_kb_enabled: |
| self._lfm_client = UnifiedLLMClient( |
| provider=LFM_KB_CONFIG['provider'], |
| model=LFM_KB_CONFIG['model'], |
| max_tokens=LFM_KB_CONFIG['max_tokens'], |
| temperature=LFM_KB_CONFIG['temperature'], |
| ) |
| logger.info('LFM KB contextualiser enabled: model=%s', LFM_KB_CONFIG['model']) |
| else: |
| self._lfm_client = None |
|  |
| # ───────────────────────────────────────────────────────────────────── |
| # Modificar el método generate_contextual_answer() existente: |
|  |
| async def generate_contextual_answer(self, query: str, kb_document: str, sub_intent: str) -&gt; str \| None: |
| """Genera respuesta contextualizada via LFM o Claude Haiku según flag.""" |
|  |
| # El system prompt y user prompt no cambian respecto a la versión original |
| system = ( |
| f'Eres un asistente de e-commerce. Responde en el idioma de la pregunta. ' |
| f'Sé conciso (2-3 frases máximo).' |
| ) |
| user = ( |
| f'Documento de política:\n{kb_document}\n\n' |
| f'Pregunta del cliente: {query}\n\n' |
| f'Responde directamente la pregunta usando el documento:' |
| ) |
|  |
| # Ruta LFM |
| if self._lfm_kb_enabled and self._lfm_client: |
| try: |
| resp = await asyncio.wait_for( |
| self._lfm_client.complete(system, user), |
| timeout=5.0 |
| ) |
| return resp.content |
| except Exception as e: |
| logger.warning('LFM KB call failed, falling back to Haiku: %s', e) |
|  |
| # Ruta Haiku (default/fallback) |
| try: |
| resp = await asyncio.wait_for( |
| self._anthropic.messages.create( |
| model='claude-3-haiku-20240307', |
| max_tokens=250, |
| temperature=0.3, |
| system=system, |
| messages=[{'role': 'user', 'content': user}] |
| ), |
| timeout=3.0 |
| ) |
| return resp.content[0].text |
| except Exception as e: |
| logger.error('Haiku KB call failed: %s', e, exc_info=True) |
| return None # Caller retorna documento KB verbatim |

### **Paso B.2 — Variable de entorno y deploy**

| gcloud run services update retail-recommender \ |
| --- |
| --region us-central1 \ |
| --project retail-recommendations-449216 \ |
| --set-env-vars LFM_KB_ENABLED=false |
|  |
| # Deploy y smoke test igual que Fase A |
| # Activar solo después de validación de calidad (Sección 6) |

| **FASE C — LFM2-ColBERT-350M Self-Hosted: Retrieval Semántico** |
| --- |

| AVISO: Esta es la fase de mayor impacto técnico. Requiere crear un nuevo Cloud Run service independiente. Las Fases A y B son prerequisito recomendado (para validar la integración con OpenRouter antes de añadir infraestructura nueva), pero no son prerequisito estricto. |
| --- |

| Modelo | LiquidAI/LFM2-ColBERT-350M |
| --- | --- |
| Acceso | Self-hosted en Cloud Run (pesos descargados desde HuggingFace) |
| --- | --- |
| Costo del modelo | $0 API tokens (open weights, licencia libre bajo $10M/año revenue) |
| --- | --- |
| Costo infraestructura | Cloud Run 2GiB/1vCPU min=1: ~$40-60/mes adicionales |
| --- | --- |
| Feature flag | LFM\_COLBERT\_ENABLED=false en el monolito |
| --- | --- |
| Archivos nuevos | services/embedding-service/ (nuevo proyecto) |
| --- | --- |
| Archivos modificados | src/api/core/hybrid\_recommender.py |
| --- | --- |
| Esfuerzo estimado | 4-6 días (incluye microservicio + integración + testing) |
| --- | --- |
| Riesgo | Medio — nueva infraestructura, nuevo deployment, requiere más testing |
| --- | --- |

## **5.1 Contexto técnico: ¿Qué es ColBERT y por qué mejora TF-IDF?**

TF-IDF es un modelo de bolsa de palabras: 'vestido azul' y 'prenda azulada' tienen overlap de TF-IDF cercano a cero porque no comparten tokens exactos. LFM2-ColBERT es un late interaction retriever: encode query y documentos por separado (como un bi-encoder), luego calcula similitud a nivel de token individual vía MaxSim. El resultado es que captura semántica sin el costo de cross-attention completo.

Caso de uso crítico para nuestro sistema: el catálogo está en inglés/español pero los usuarios en MX/CL/ES pueden escribir en variantes regionales. ColBERT está específicamente documentado para 'store in English, query in Spanish' con soporte nativo para ES, FR, DE, IT, PT, AR, JA, KO, ZH.

## **5.2 Arquitectura del embedding service**

El embedding service es un FastAPI mínimo que corre en Cloud Run independiente del monolito. El monolito lo llama vía HTTP interno (misma VPC/red de GCP, latencia ~5ms).

### **Paso C.1 — Crear la estructura del embedding service**

| # Estructura de directorios del nuevo servicio |
| --- |
| services/ |
| └── embedding-service/ |
| ├── main.py # FastAPI app |
| ├── colbert_retriever.py # Lógica ColBERT + PLAID index |
| ├── Dockerfile # Image definition |
| ├── requirements.txt # pylate + transformers + torch |
| └── deploy.sh # Script de deploy a Cloud Run |

Contenido de services/embedding-service/main.py:

| # services/embedding-service/main.py |
| --- |
| """ |
| LFM2-ColBERT Embedding Service |
| ================================ |
| Microservicio FastAPI que expone el modelo LFM2-ColBERT-350M |
| para búsqueda semántica de productos. |
|  |
| Endpoints: |
| POST /v1/embed/index — indexar catálogo de productos |
| POST /v1/embed/search — buscar productos por query |
| GET /health — health check |
| """ |
| import os, asyncio, logging, time |
| from contextlib import asynccontextmanager |
| from fastapi import FastAPI, HTTPException |
| from pydantic import BaseModel |
| from typing import List, Optional |
|  |
| log = logging.getLogger(__name__) |
| colbert_retriever = None # Singleton — se carga en startup |
|  |
| # ── Pydantic models ───────────────────────────────────────────────── |
|  |
| class IndexRequest(BaseModel): |
| products: List[dict] # [{id, title, description, tags}, ...] |
|  |
| class SearchRequest(BaseModel): |
| query: str |
| top_k: int = 10 |
|  |
| class SearchResponse(BaseModel): |
| product_ids: List[str] |
| latency_ms: float |
|  |
| # ── Startup / shutdown ────────────────────────────────────────────── |
|  |
| @asynccontextmanager |
| async def lifespan(app: FastAPI): |
| global colbert_retriever |
| log.info('Loading LFM2-ColBERT-350M...') |
| t0 = time.time() |
| from colbert_retriever import LFM2ColBERTRetriever |
| colbert_retriever = LFM2ColBERTRetriever() |
| await colbert_retriever.warmup() |
| log.info('ColBERT ready in %.1fs', time.time() - t0) |
| yield |
| log.info('Embedding service shutdown') |
|  |
| app = FastAPI(title='LFM2-ColBERT Embedding Service', lifespan=lifespan) |
|  |
| # ── Routes ────────────────────────────────────────────────────────── |
|  |
| @app.get('/health') |
| async def health(): |
| return {'status': 'ok', 'model': 'LFM2-ColBERT-350M', |
| 'index_size': colbert_retriever.index_size() if colbert_retriever else 0} |
|  |
| @app.post('/v1/embed/index') |
| async def build_index(req: IndexRequest): |
| """ |
| Recibe el catálogo de productos y construye el PLAID index. |
| Se llama durante el KB sync / catalog update del monolito. |
| Con 3000 productos: ~5-10 segundos. |
| """ |
| if not colbert_retriever: |
| raise HTTPException(503, 'Model not ready') |
| t0 = time.time() |
| count = await colbert_retriever.build_index(req.products) |
| return {'indexed': count, 'latency_ms': round((time.time()-t0)*1000, 1)} |
|  |
| @app.post('/v1/embed/search', response_model=SearchResponse) |
| async def search(req: SearchRequest): |
| """ |
| Busca los productos más relevantes para una query. |
| Soporta queries en español, inglés, francés, alemán nativamente. |
| Latencia warm: 20-40ms. |
| """ |
| if not colbert_retriever: |
| raise HTTPException(503, 'Model not ready') |
| t0 = time.time() |
| ids = await colbert_retriever.search(req.query, req.top_k) |
| return SearchResponse(product_ids=ids, latency_ms=round((time.time()-t0)*1000, 1)) |

Contenido de services/embedding-service/colbert\_retriever.py:

| # services/embedding-service/colbert_retriever.py |
| --- |
| """ |
| LFM2ColBERTRetriever — wrapper sobre pylate + LFM2-ColBERT-350M |
|  |
| Arquitectura del índice: |
| - Los embeddings de documentos se pre-calculan y se guardan en disco |
| (PLAID index) en /tmp/colbert-index/ |
| - El índice persiste mientras el contenedor esté vivo (min=1 garantiza esto) |
| - Si el contenedor se reinicia, se necesita re-indexar (POST /v1/embed/index) |
| - El monolito debe llamar a /v1/embed/index después de cada catalog sync |
| """ |
| import asyncio, logging |
| from typing import List |
| from pathlib import Path |
|  |
| log = logging.getLogger(__name__) |
| INDEX_PATH = Path('/tmp/colbert-index') |
|  |
| class LFM2ColBERTRetriever: |
|  |
| def __init__(self): |
| from pylate import models |
| log.info('Loading LFM2-ColBERT-350M from HuggingFace...') |
| self.model = models.ColBERT( |
| model_name_or_path='LiquidAI/LFM2-ColBERT-350M' |
| ) |
| # eos_token como pad_token — requerido por LFM2-ColBERT |
| self.model.tokenizer.pad_token = self.model.tokenizer.eos_token |
| self._index = None |
| self._indexed_count = 0 |
|  |
| async def warmup(self): |
| """Pre-calcula un forward pass dummy para JIT-compilar el grafo.""" |
| log.info('Running ColBERT warmup...') |
| loop = asyncio.get_event_loop() |
| # Correr en thread pool para no bloquear el event loop |
| await loop.run_in_executor( |
| None, |
| lambda: self.model.encode(['warmup query'], is_query=True) |
| ) |
| log.info('ColBERT warmup complete') |
|  |
| async def build_index(self, products: list) -&gt; int: |
| """ |
| Construye el PLAID index con los productos del catálogo. |
| Combina title + description + tags para richer semantic signal. |
| Diseñado para correr en background, no bloquea el event loop. |
| """ |
| from pylate import indexes |
| loop = asyncio.get_event_loop() |
|  |
| doc_ids = [str(p['id']) for p in products] |
| doc_texts = [ |
| f"{p.get('title','')} {p.get('description','')} {' '.join(p.get('tags', []))}" |
| for p in products |
| ] |
|  |
| def _build(): |
| embeddings = self.model.encode( |
| doc_texts, batch_size=32, is_query=False, show_progress_bar=True |
| ) |
| INDEX_PATH.mkdir(parents=True, exist_ok=True) |
| idx = indexes.PLAID( |
| index_folder=str(INDEX_PATH), index_name='catalog', override=True |
| ) |
| idx.add_documents(documents_ids=doc_ids, documents_embeddings=embeddings) |
| return idx, len(products) |
|  |
| self._index, self._indexed_count = await loop.run_in_executor(None, _build) |
| log.info('PLAID index built: %d products', self._indexed_count) |
| return self._indexed_count |
|  |
| async def search(self, query: str, top_k: int = 10) -&gt; List[str]: |
| """ |
| Encode query y busca en el PLAID index. |
| Cross-lingual: query en ES funciona con productos en EN. |
| Latencia warm: ~20-40ms en CPU. |
| """ |
| if self._index is None: |
| log.warning('ColBERT index not built — returning empty results') |
| return [] |
|  |
| from pylate import retrieve |
| loop = asyncio.get_event_loop() |
|  |
| def _search(): |
| q_emb = self.model.encode([query], is_query=True) |
| retriever = retrieve.ColBERT(index=self._index) |
| results = retriever.retrieve(queries_embeddings=q_emb, top_k=top_k) |
| return [r['id'] for r in results[0]] |
|  |
| return await loop.run_in_executor(None, _search) |
|  |
| def index_size(self) -&gt; int: |
| return self._indexed_count |

### **Paso C.2 — Dockerfile para el embedding service**

| # services/embedding-service/Dockerfile |
| --- |
| FROM python:3.11-slim |
|  |
| WORKDIR /app |
|  |
| # Instalar dependencias del sistema necesarias para torch |
| RUN apt-get update &amp;&amp; apt-get install -y --no-install-recommends \ |
| gcc g++ &amp;&amp; rm -rf /var/lib/apt/lists/* |
|  |
| COPY requirements.txt . |
|  |
| # Instalar en orden: torch CPU-only primero (más liviano que GPU build) |
| RUN pip install --no-cache-dir torch==2.1.0+cpu \ |
| --index-url https://download.pytorch.org/whl/cpu |
|  |
| RUN pip install --no-cache-dir -r requirements.txt |
|  |
| COPY . . |
|  |
| # Pre-descargar el modelo durante el build de la imagen. |
| # Esto evita que el primer startup descargue ~350MB desde HuggingFace. |
| # El modelo se bake en la imagen Docker (~900MB total con torch CPU). |
| RUN python -c " |
| from pylate import models |
| m = models.ColBERT(model_name_or_path='LiquidAI/LFM2-ColBERT-350M') |
| print('Model pre-downloaded successfully')" |
|  |
| ENV PORT=8080 |
| EXPOSE 8080 |
|  |
| CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"] |

Contenido de services/embedding-service/requirements.txt:

| fastapi==0.115.0 |
| --- |
| uvicorn[standard]==0.30.6 |
| pydantic==2.8.2 |
| pylate&gt;=1.2.0 |
| transformers&gt;=4.55.0 |
| # torch se instala separado en Dockerfile (versión CPU-only) |

### **Paso C.3 — Deploy del embedding service**

| # services/embedding-service/deploy.sh |
| --- |
| #!/bin/bash |
| set -e |
|  |
| PROJECT=retail-recommendations-449216 |
| REGION=us-central1 |
| SERVICE_NAME=retail-embedding-service |
| IMAGE=gcr.io/$PROJECT/$SERVICE_NAME |
|  |
| echo '&gt;&gt;&gt; Building Docker image (includes model download ~350MB)...' |
| docker build -t $IMAGE . |
|  |
| echo '&gt;&gt;&gt; Pushing to Container Registry...' |
| docker push $IMAGE |
|  |
| echo '&gt;&gt;&gt; Deploying to Cloud Run...' |
| gcloud run deploy $SERVICE_NAME \ |
| --image $IMAGE \ |
| --region $REGION \ |
| --project $PROJECT \ |
| --memory 2Gi \ |
| --cpu 1 \ |
| --min-instances 1 \ |
| --max-instances 3 \ |
| --timeout 60 \ |
| --no-allow-unauthenticated \\ |
| --ingress internal |
|  |
| echo '&gt;&gt;&gt; Getting service URL...' |
| gcloud run services describe $SERVICE_NAME \ |
| --region $REGION \ |
| --project $PROJECT \ |
| --format='value(status.url)' |
|  |
| echo '&gt;&gt;&gt; Done!' |

### **Paso C.4 — Cliente HTTP en el monolito: LFM2ColBERTClient**

Crear src/api/services/colbert\_client.py para que el monolito llame al embedding service:

| # src/api/services/colbert_client.py |
| --- |
| """ |
| Cliente HTTP para el LFM2-ColBERT embedding microservice. |
| El monolito llama a este cliente cuando LFM_COLBERT_ENABLED=true. |
| """ |
| import os, httpx, asyncio, logging |
| from typing import List, Optional |
|  |
| log = logging.getLogger(__name__) |
|  |
| class LFM2ColBERTClient: |
| """ |
| Thin HTTP client para el embedding-service. |
| Incluye timeout, retry y circuit-breaker básico. |
| """ |
|  |
| def __init__(self): |
| base_url = os.environ.get('COLBERT_SERVICE_URL', '') |
| if not base_url: |
| raise ValueError('COLBERT_SERVICE_URL env var not set') |
| # httpx.AsyncClient con timeout ajustado a latencia esperada (~30ms warm) |
| self._http = httpx.AsyncClient( |
| base_url=base_url, |
| timeout=httpx.Timeout(5.0), # 5s incluye startup si hay cold start |
| headers={'Content-Type': 'application/json'} |
| ) |
| self._consecutive_failures = 0 |
| self._circuit_open = False |
|  |
| async def search(self, query: str, top_k: int = 10) -&gt; Optional[List[str]]: |
| """ |
| Busca productos semánticamente. |
| Returns: lista de product IDs, o None si falla (caller usa fallback TF-IDF). |
| """ |
| if self._circuit_open: |
| log.debug('ColBERT circuit open — skipping') |
| return None |
|  |
| try: |
| resp = await self._http.post( |
| '/v1/embed/search', |
| json={'query': query, 'top_k': top_k} |
| ) |
| resp.raise_for_status() |
| data = resp.json() |
| self._consecutive_failures = 0 # reset on success |
| log.debug('ColBERT search: %d results in %.1fms', |
| len(data['product_ids']), data['latency_ms']) |
| return data['product_ids'] |
| except Exception as e: |
| self._consecutive_failures += 1 |
| if self._consecutive_failures &gt;= 3: |
| self._circuit_open = True |
| log.error('ColBERT circuit OPEN after 3 failures: %s', e) |
| # Reset circuit después de 60s |
| asyncio.get_event_loop().call_later( |
| 60, setattr, self, '_circuit_open', False |
| ) |
| log.warning('ColBERT search failed (attempt %d): %s', |
| self._consecutive_failures, e) |
| return None # Fallback a TF-IDF en el caller |
|  |
| async def index_catalog(self, products: List[dict]) -&gt; bool: |
| """ |
| Llama al endpoint de indexación después de un catalog sync. |
| Llamar desde: ShopifyKBSyncService después de sincronizar productos. |
| """ |
| try: |
| resp = await self._http.post( |
| '/v1/embed/index', |
| json={'products': products}, |
| timeout=120.0 # Indexar 3000 productos toma ~10s |
| ) |
| resp.raise_for_status() |
| data = resp.json() |
| log.info('ColBERT re-indexed: %d products in %.1fms', |
| data['indexed'], data['latency_ms']) |
| return True |
| except Exception as e: |
| log.error('ColBERT index failed: %s', e, exc_info=True) |
| return False |

### **Paso C.5 — Integrar ColBERT en HybridRecommender**

Modificar hybrid\_recommender.py para usar ColBERT como retriever primario cuando está disponible:

| # En src/api/core/hybrid_recommender.py |
| --- |
| # Modificar el constructor para aceptar el cliente ColBERT opcional: |
|  |
| import os |
| from src.api.services.colbert_client import LFM2ColBERTClient |
|  |
| class HybridRecommender: |
| def __init__(self, content_recommender, retail_recommender, |
| content_weight=0.5, product_cache=None): |
| self.content_recommender = content_recommender |
| self.retail_recommender = retail_recommender |
| self.content_weight = content_weight |
| self.product_cache = product_cache |
|  |
| # ColBERT client — inicializar solo si el flag está activo |
| lfm_enabled = os.environ.get('LFM_COLBERT_ENABLED', 'false').lower() == 'true' |
| if lfm_enabled: |
| try: |
| self._colbert = LFM2ColBERTClient() |
| logger.info('LFM2-ColBERT retrieval enabled') |
| except ValueError as e: |
| logger.warning('LFM_COLBERT_ENABLED=true but client init failed: %s', e) |
| self._colbert = None |
| else: |
| self._colbert = None |
|  |
| async def get_recommendations(self, user_id, product_id=None, n=5): |
| """ |
| Obtiene recomendaciones usando ColBERT si está disponible, |
| TF-IDF como fallback, y Google Retail API para collaborative filtering. |
| El orden de prioridad para content-based es: ColBERT &gt; TF-IDF. |
| """ |
| # ── Content-based retrieval ───────────────────────────────────── |
| content_results = [] |
|  |
| if self._colbert and product_id: |
| # ColBERT path: buscar productos semánticamente similares |
| product_ids = await self._colbert.search(product_id, top_k=n*2) |
| if product_ids: |
| # Convertir IDs a dicts con score simulado para combinar con Retail API |
| content_results = [ |
| {'id': pid, 'score': 1.0 - (i * 0.05), 'source': 'colbert'} |
| for i, pid in enumerate(product_ids[:n]) |
| ] |
| logger.debug('ColBERT returned %d results', len(content_results)) |
|  |
| # Fallback a TF-IDF si ColBERT no está disponible o no retornó resultados |
| if not content_results: |
| content_results = await self._get_tfidf_recommendations(product_id, n) |
|  |
| # ── Collaborative filtering (Google Retail API — sin cambios) ── |
| retail_results = await self._get_retail_api_recommendations(user_id, n) |
|  |
| # ── Combinar y diversificar (lógica existente — sin cambios) ──── |
| return self._combine_recommendations(content_results, retail_results, n) |

### **Paso C.6 — Variables de entorno para Fase C**

| # Agregar al monolito: URL del embedding service + feature flag |
| --- |
| gcloud run services update retail-recommender \ |
| --region us-central1 \ |
| --project retail-recommendations-449216 \ |
| --set-env-vars \ |
| LFM_COLBERT_ENABLED=false,\ |
| COLBERT_SERVICE_URL=https://&lt;embedding-service-url&gt; |
|  |
| # NOTA: Obtener la URL del embedding service después de su deploy: |
| # gcloud run services describe retail-embedding-service \ |
| # --region us-central1 --format='value(status.url)' |

# **6\. Testing y Validación de Calidad**

| Regla crítica: Nunca activar un flag al 100% del tráfico sin el A/B test documentado aquí. La calidad del modelo importa más que el ahorro de costo. |
| --- |

## **6.1 Tests de integración (antes de activar flags)**

Ejecutar antes del primer deploy con las nuevas dependencias:

| # tests/integration/test_liquid_integration.py |
| --- |
|  |
| import pytest, asyncio, os |
| from unittest.mock import patch, AsyncMock |
|  |
| class TestUnifiedLLMClient: |
| """Valida que UnifiedLLMClient funciona con ambos providers.""" |
|  |
| async def test_openrouter_client_initializes(self): |
| os.environ['OPENROUTER_API_KEY'] = 'test-key' |
| from src.api.core.llm_client import UnifiedLLMClient |
| client = UnifiedLLMClient('openrouter', 'liquid/lfm-2-24b-a2b', 300, 0.7) |
| assert client.provider == 'openrouter' |
|  |
| async def test_anthropic_fallback_when_openrouter_fails(self): |
| """Si OpenRouter falla, el sistema cae a Claude sin HTTP 500.""" |
| from src.api.mcp.engines.mcp_personalization_engine import MCPPersonalizationEngine |
| with patch.dict(os.environ, {'LFM_MCP_ENABLED': 'true'}): |
| engine = MCPPersonalizationEngine(...) |
| # Simular fallo de OpenRouter |
| engine._lfm_client.complete = AsyncMock(side_effect=Exception('timeout')) |
| result = await engine._generate_claude_personalized_response(...) |
| # Debe retornar respuesta (fallback a Claude, no None/500) |
| assert result is not None |
|  |
| async def test_flag_off_never_calls_openrouter(self): |
| """Con LFM_MCP_ENABLED=false, OpenRouter nunca se llama.""" |
| with patch.dict(os.environ, {'LFM_MCP_ENABLED': 'false'}): |
| # Verificar que self._lfm_client es None |
| ... |
|  |
| # Ejecutar: |
| # pytest tests/integration/test_liquid_integration.py -v |

## **6.2 Protocolo de A/B testing para Fases A y B**

Antes de activar cualquier flag al 100%, realizar el siguiente protocolo de validación manual:

| **#** | **Query de prueba** | **Respuesta esperada (qué validar)** | **Criterio** |
| --- | --- | --- | --- |
| 1 | busco vestidos elegantes para boda | Recomienda 2-3 productos relevantes en español, menciona precio en EUR/MXN según mercado | Idioma correcto |
| --- | --- | --- | --- |
| 2 | I'm looking for casual blue shirts | Responde en inglés, recomienda camisas, no mezcla idiomas | Bilingual OK |
| --- | --- | --- | --- |
| 3 | ropa para clima frío en Chile (mercado CL) | Usa CLP o USD/MXN según config de mercado, no EUR | Market pricing |
| --- | --- | --- | --- |
| 4 | algo similar a lo que me mostraste antes | Diversificación funciona: no repite productos del turn anterior | Multi-turn |
| --- | --- | --- | --- |
| 5 | ¿cuál es la política de devoluciones? | Detecta INFORMATIONAL, no activa el path LFM de personalización, retorna KB verbatim | Intent routing |
| --- | --- | --- | --- |

Para cada query, comparar la respuesta con flag OFF (Claude) vs flag ON (LFM):

-   Idioma correcto según Accept-Language header
-   Menciona al menos un producto de los recomendados por HybridRecommender
-   No contiene texto en formato JSON o strings de error
-   Tono apropiado para e-commerce (no robótico, no excesivamente genérico)
-   Latencia total del endpoint < 3000ms (medir con took\_ms en respuesta)
-   Si algún criterio falla en más del 20% de los casos: NO activar el flag

## **6.3 Validación específica para Fase C (ColBERT)**

| # Script de validación del embedding service |
| --- |
| # Ejecutar después del deploy del microservicio y antes de activar el flag |
|  |
| import httpx, asyncio |
|  |
| EMBEDDING_URL = 'https://&lt;embedding-service-url&gt;' |
|  |
| TEST_QUERIES = [ |
| # (query, expected_relevance_signal) |
| ('vestido elegante azul', 'dress'), |
| ('casual blue shirt men', 'shirt'), |
| ('ropa deportiva correr', 'sport'), |
| ('chaqueta invierno Chile', 'jacket'), |
| ] |
|  |
| async def validate_colbert(): |
| async with httpx.AsyncClient() as client: |
| # 1. Verificar health |
| r = await client.get(f'{EMBEDDING_URL}/health') |
| assert r.status_code == 200, 'Health check failed' |
| print(f'Health OK: {r.json()}') |
|  |
| # 2. Verificar que el índice tiene productos |
| data = r.json() |
| assert data['index_size'] &gt; 0, f'Index empty: {data}' |
| print(f'Index size: {data["index_size"]} products') |
|  |
| # 3. Verificar latencia de búsqueda |
| for query, signal in TEST_QUERIES: |
| r = await client.post(f'{EMBEDDING_URL}/v1/embed/search', |
| json={'query': query, 'top_k': 5}) |
| assert r.status_code == 200 |
| result = r.json() |
| assert result['latency_ms'] &lt; 200, f'Too slow: {result["latency_ms"]}ms' |
| assert len(result['product_ids']) &gt; 0, 'No results' |
| print(f'Query "{query}": {len(result["product_ids"])} results in {result["latency_ms"]}ms') |
|  |
| asyncio.run(validate_colbert()) |

# **7\. Estrategia de Rollback**

Cada fase tiene un rollback de un solo comando: apagar el feature flag. No hay cambios en base de datos, Redis, o el esquema de respuestas.

## **7.1 Rollback Fase A (MCP personalización)**

| # Rollback inmediato — 30 segundos para que tome efecto |
| --- |
| gcloud run services update retail-recommender \ |
| --region us-central1 \ |
| --project retail-recommendations-449216 \ |
| --set-env-vars LFM_MCP_ENABLED=false |
|  |
| # Verificar en GCP logs que aparece: |
| # LFM MCP personalisation disabled -- using Claude |

## **7.2 Rollback Fase B (KB contextualización)**

| gcloud run services update retail-recommender \ |
| --- |
| --region us-central1 \ |
| --project retail-recommendations-449216 \ |
| --set-env-vars LFM_KB_ENABLED=false |

## **7.3 Rollback Fase C (ColBERT retrieval)**

| # 1. Apagar el flag en el monolito |
| --- |
| gcloud run services update retail-recommender \ |
| --region us-central1 \ |
| --project retail-recommendations-449216 \ |
| --set-env-vars LFM_COLBERT_ENABLED=false |
|  |
| # 2. El embedding-service puede quedarse corriendo (min=1) sin causar daño |
| # Solo se puede apagar si se quiere ahorrar los ~$40/mes: |
| # gcloud run services update retail-embedding-service --min-instances 0 |
|  |
| # Nota: el circuit-breaker en LFM2ColBERTClient también protege automáticamente |
| # si el embedding service falla: después de 3 fallos consecutivos, vuelve a TF-IDF. |

# **8\. Proyección de Costos**

Basado en 4,500 conversaciones/mes (midpoint de tienda mediana: 500-2000 visitantes/día, 8-12% chat engagement, 3 turns/conversación, 40% transaccional / 60% informacional).

| **Línea de costo** | **Setup actual** | **A+B activos** | **A+B+C activos** |
| --- | --- | --- | --- |
| Claude Sonnet (MCP) | $15–40/mes | $0.50–2/mes (LFM2-24B) | $0.50–2/mes |
| --- | --- | --- | --- |
| Claude Haiku (KB) | $0.50–1.80/mes | $0.05–0.15/mes (LFM2.5) | $0.05–0.15/mes |
| --- | --- | --- | --- |
| Cloud Run monolito | $2–8/mes (min=0) | $25–45/mes (min=1, 2GiB) | $25–45/mes |
| --- | --- | --- | --- |
| Cloud Run embedding svc | — | — | $40–60/mes (min=1, 2GiB) |
| --- | --- | --- | --- |
| Redis Cloud | $10–30/mes | $10–30/mes | $10–30/mes |
| --- | --- | --- | --- |
| Neon PostgreSQL | $19–25/mes | $19–25/mes | $19–25/mes |
| --- | --- | --- | --- |
| Google Retail API | $0.50–2.50/mes | $0.50–2.50/mes | $0.50–2.50/mes |
| --- | --- | --- | --- |
| TOTAL ESTIMADO | $47–107/mes | $55–105/mes | $95–165/mes |
| --- | --- | --- | --- |
| Ahorro en API AI | — | ~90% en API costs | ~90% en API costs |
| --- | --- | --- | --- |

| Observación: La Fase C (ColBERT self-hosted) añade $40-60/mes de infraestructura, que offset el ahorro de $0 en API (ya es TF-IDF gratuito). El valor de la Fase C no es ahorro de costo sino mejora de calidad semántica: español multilingual, cross-lingual, mejor relevancia. Si el presupuesto es la prioridad, Fases A+B son suficientes. |
| --- |

# **9\. Referencia de Variables de Entorno**

| **Variable** | **Default** | **Valores posibles** | **Descripción** |
| --- | --- | --- | --- |
| OPENROUTER\_API\_KEY | (required) | sk-or-v1-... | API key de OpenRouter. Via Secret Manager. |
| --- | --- | --- | --- |
| LFM\_MCP\_ENABLED | false | true | false | Activa LFM2-24B para personalización MCP (Fase A) |
| --- | --- | --- | --- |
| LFM\_KB\_ENABLED | false | true | false | Activa LFM2.5-1.2B para KB contextualización (Fase B) |
| --- | --- | --- | --- |
| LFM\_COLBERT\_ENABLED | false | true | false | Activa LFM2-ColBERT retrieval (Fase C) |
| --- | --- | --- | --- |
| COLBERT\_SERVICE\_URL | (required si C) | https://... | URL del embedding-service Cloud Run. Solo para Fase C. |
| --- | --- | --- | --- |
| CLAUDE\_MODEL\_TIER | HAIKU | HAIKU | SONNET | OPUS | Tier de Claude para el fallback. Existente. |
| --- | --- | --- | --- |
| ANTHROPIC\_API\_KEY | (required) | sk-ant-... | API key Anthropic (fallback). Existente. |
| --- | --- | --- | --- |
| ENABLE\_INTENT\_DETECTION | true | true | false | Intent detection sklearn. Sin cambios. |
| --- | --- | --- | --- |
| ML\_INTENT\_ENABLED | true | true | false | ML fallback en hybrid\_detector. Sin cambios. |
| --- | --- | --- | --- |

# **10\. Cronograma y Responsabilidades**

| **Semana** | **Fase** | **Tareas** | **Criterio de éxito** |
| --- | --- | --- | --- |
| 1 | Prerequisitos | 1\. Crear OPENROUTER\_API\_KEY en Secret Manager 2. Upgrade Cloud Run a 2GiB/2vCPU + min=1 3. Agregar openai>=1.50.0 a requirements.cloudrun.txt | Sistema arranca sin errores post-upgrade. Smoke test pasa. |
| --- | --- | --- | --- |
| 2 | A | 1\. Crear llm\_client.py 2. Modificar mcp\_personalization\_engine.py 3. Deploy con LFM\_MCP\_ENABLED=false 4. A/B test manual (5 queries comparativas) 5. Activar al 100% si test pasa | Fallback a Claude funciona. Calidad LFM >= Claude en 4/5 queries. |
| --- | --- | --- | --- |
| 3 | B | 1\. Modificar kb\_contextualizer.py 2. Deploy con LFM\_KB\_ENABLED=false 3. A/B test: 3 queries con entidades específicas 4. Activar si test pasa | Respuestas en idioma correcto. Latencia < 3s. |
| --- | --- | --- | --- |
| 4-5 | C | 1\. Crear services/embedding-service/ 2. Build Docker + pre-download model 3. Deploy a Cloud Run (no-auth, internal) 4. Validar /health + latencia + index 5. Integrar LFM2ColBERTClient en monolito 6. Modificar HybridRecommender 7. Deploy monolito con LFM\_COLBERT\_ENABLED=false 8. Test de relevancia: comparar ColBERT vs TF-IDF 9. Activar si test pasa | Embedding service healthy, index\_size > 0. ColBERT retorna resultados relevantes. Latencia search < 100ms. |
| --- | --- | --- | --- |
| 6 | Monitoreo | 1\. Revisar GCP logs durante 1 semana con flags activos 2. Verificar que no hay aumentos de error rate 3. Confirmar latencias estables 4. Documentar ahorro de costos real en DCT de cierre | Error rate < 0.5%. P95 latencia < 3s. Costos API reducidos >80%. |
| --- | --- | --- | --- |

## **10.1 Resumen del plan**

-   **Fase A — máximo impacto, mínimo riesgo:** 3 líneas de código nuevo (llm\_client.py) + modificación quirúrgica en mcp\_personalization\_engine.py. Ahorro ~95% en la línea de costo dominante. Feature flag garantiza zero riesgo hasta validar.
-   **Fase B — quick win:** Igual que Fase A pero en kb\_contextualizer.py. Impacto de costo pequeño (~$1-2/mes) pero valida el patrón OpenRouter para uso futuro.
-   **Fase C — mejora de calidad:** La más compleja pero la más valiosa técnicamente. ColBERT resuelve el problema de retrieval cross-lingual que TF-IDF no puede manejar. Requiere nuevo microservicio y más testing.

**LFM2 licensing reminder:** Los modelos LFM son libres para uso comercial para empresas con <$10M/año de revenue. Si una tienda cliente supera este umbral, Liquid AI requiere un acuerdo comercial. Monitorear este límite conforme crecen los clientes.

*Retail Recommender System v2.1.0 · Plan de Integración Liquid AI · Abril 2026*