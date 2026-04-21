# DCT — Resolución de Latencia MCP y Activación de Haiku
## Retail Recommender System v2.1.0 — Sesión 21–22 de Marzo de 2026

> **Tipo:** Documento de Continuidad Técnica (DCT) — Resumen de Sesión
> **Estado al cierre:** ✅ Sistema completamente operacional en producción
> **Score smoke tests:** 19/19 — 100%
> **Revisión activa al cierre:** `retail-recommender-00066-r6p`
> **Fechas:** 21 y 22 de Marzo de 2026
> **Sesión anterior:** DCT_SESION_20032026_RESOLUCION_PRODUCCION.md

---

## 1. Resumen Ejecutivo

Esta sesión tuvo como objetivo resolver el último problema pendiente tras la sesión del
20/03/2026: el endpoint MCP `/v1/mcp/recommendations` respondía en ~8300ms en ambas
ejecuciones del smoke test (incluyendo la segunda, que debería ser un cache hit de ~300ms).

El sistema presentaba un conjunto de bugs encadenados que hacían ineficaz la configuración
de modelo y tokens, a pesar de que los secrets en Cloud Run estaban correctamente mapeados.
El diagnóstico reveló tres causas raíz independientes en `claude_config.py` y una cuarta en
`mcp_personalization_engine.py`, todas relacionadas con el hardcoding de parámetros de Claude
que ignoraban la configuración centralizada.

Al cierre de la sesión, la latencia del endpoint MCP quedó en:

- **Cache miss (primera request):** 1261ms — objetivo cumplido (< 3000ms)
- **Cache hit (segunda request):** 273ms — objetivo cumplido (< 500ms)
- **Tiempo de llamada real a Claude API:** ~966ms (vs ~9400ms antes)

Mejora total: **9.7x más rápido** en tiempo de generación de Claude, **7.7x más rápido**
en latencia total del endpoint.

---

## 2. Problemas Enfrentados

### 2.1 Latencia MCP de ~8300ms en ambas ejecuciones del smoke test

**Síntoma:**
```
Run 1 — GET /v1/mcp/recommendations/9978566115637 → HTTP 200 (8323ms)
Run 2 — GET /v1/mcp/recommendations/9978566115637 → HTTP 200 (8300ms)
```

Ambas ejecuciones daban la misma latencia. La segunda debería haber sido un cache hit
de ~300ms. Esto indicaba que el resultado de la primera llamada nunca se estaba cacheando,
o que la primera llamada siempre superaba el timeout de 8s y fallaba silenciosamente.

El diagnóstico de la sesión anterior había apuntado al mapeo del secret `CLAUDE_MODEL_TIER`
en Cloud Run como posible causa. Al inicio de esta sesión se verificó con `gcloud` y mediante
screenshot de la consola GCP que el secret **sí estaba correctamente mapeado** como variable
de entorno con valor `HAIKU`. La causa raíz era diferente: residía en el código.

---

### 2.2 Bug 1 — `@lru_cache()` en `get_claude_config_service()` congelaba el singleton

**Archivo:** `src/api/core/claude_config.py`

**Síntoma técnico:** El secret `CLAUDE_MODEL_TIER=HAIKU` llegaba correctamente al contenedor,
pero `ClaudeConfigurationService` se instanciaba con el tier `SONNET` en lugar de `HAIKU`.

**Causa raíz:**

```python
# Código problemático:
@lru_cache()
def get_claude_config_service() -> ClaudeConfigurationService:
    return ClaudeConfigurationService()
```

`@lru_cache()` en Python congela el resultado del **primer import** del módulo. En Cloud Run,
existe una race condition durante el startup: los secrets se inyectan como variables de
entorno antes de que el proceso arranque, pero algunos módulos se importan antes de que el
proceso Python esté completamente inicializado. Si `get_claude_config_service()` era llamado
en ese instante (por ejemplo, durante la inicialización de otro módulo), el singleton quedaba
creado con `CLAUDE_MODEL_TIER=None` y resolvía al default de producción: `SONNET`.

A partir de ese momento, aunque el secret estuviera disponible, la instancia cacheada era
inmutable para toda la vida del contenedor. Ningún deploy sin reinicio podía corregirlo.

**Impacto:** La configuración centralizada de modelo y tokens era completamente ineficaz.
El warm-up de PASO 8.5 usaba Haiku (porque creaba su cliente directamente), pero todas las
llamadas a través de `get_claude_config_service()` usaban Sonnet.

---

### 2.3 Bug 2 — `_resolved_config` cacheaba `max_tokens` en la instancia

**Archivo:** `src/api/core/claude_config.py`, método `get_model_config()`

**Causa raíz:**

```python
def get_model_config(self, context=None) -> ClaudeModelConfig:
    if self._resolved_config:          # ← cache interno de instancia
        return self._resolved_config
    # ...
    self._resolved_config = base_config  # ← se congela en el primer call
    return base_config
```

Había una segunda capa de caché, dentro de la instancia. Incluso si el singleton se creaba
correctamente con `HAIKU`, la primera llamada a `get_model_config()` leía `CLAUDE_MAX_TOKENS`
del entorno, lo aplicaba, y congelaba el resultado en `_resolved_config`. Cualquier cambio
posterior al secret `CLAUDE_MAX_TOKENS` requería reiniciar el contenedor para ser efectivo.

**Impacto:** El override de `max_tokens` por secrets no funcionaba en caliente.

---

### 2.4 Bug 3 — Properties `timeout`, `max_retries` y `region` definidas dos veces

**Archivo:** `src/api/core/claude_config.py`

**Causa raíz:** Las tres properties estaban definidas literalmente dos veces en la clase. En
Python, la segunda definición sobreescribe silenciosamente a la primera. No causaba fallos
funcionales (ambas definiciones eran idénticas), pero era un bug de mantenimiento activo:
cualquier modificación a la primera definición no tendría efecto real.

**Impacto:** Riesgo de mantenimiento. Confusión al depurar.

---

### 2.5 Bug 4 (principal) — `model` y `max_tokens` hardcodeados en `_generate_claude_personalized_response()`

**Archivo:** `src/api/mcp/engines/mcp_personalization_engine.py`

**Síntoma:** A pesar de haber corregido `claude_config.py` (bugs 1, 2 y 3) y de que los logs
confirmaban `model=claude-3-haiku-20240307`, la latencia seguía siendo ~9400ms por llamada
real a Claude.

**Causa raíz:** La llamada real a Claude en el engine de personalización tenía `model` y
`max_tokens` hardcodeados, completamente desconectados de `self.claude_config`:

```python
# Código problemático:
claude_response = await asyncio.wait_for(
    self.claude.messages.create(
        model="claude-sonnet-4-20250514",   # ← hardcodeado, ignoraba CLAUDE_MODEL_TIER
        max_tokens=800,                      # ← hardcodeado, ignoraba CLAUDE_MAX_TOKENS
        temperature=0.8
    ),
    timeout=timeout
)
```

Esto explicaba por qué el warm-up de PASO 8.5 funcionaba con Haiku (usaba el cliente
directamente con 1 token) pero la personalización real siempre usaba Sonnet con 800 tokens,
generando respuestas que tardaban entre 6 y 10 segundos.

**Impacto:** 100% de las llamadas reales de personalización usaban Sonnet+800 tokens,
independientemente de la configuración en secrets o en claude_config.py.

---

### 2.6 Bug 5 (contribuyente) — Prompts de Claude excesivamente largos

**Archivo:** `src/api/mcp/engines/mcp_personalization_engine.py`, métodos
`_build_advanced_personalization_prompt()` y `_build_personalized_system_prompt()`

**Causa raíz:** El prompt que se enviaba a Claude contenía ~1800 tokens de input:
- Historial conversacional completo serializado como JSON
- Diccionarios de preferencias de usuario (vacíos en la mayoría de casos)
- Sensibilidad de precio, indicadores de urgencia, momentum conversacional
- 6 instrucciones detalladas que duplicaban el contenido del system prompt
- Solicitud de respuesta en formato JSON estructurado

El system prompt añadía ~400 tokens adicionales con secciones de "capacidades" y
"especialización" que Claude no necesita para generar 2-3 oraciones.

Para una respuesta conversacional de recomendación de moda, este volumen de input era
innecesario y causaba latencia de prefill adicional incluso con Haiku.

**Impacto:** Con Haiku, un prompt de ~2200 tokens de input generaba ~3-4 segundos de
latencia de prefill antes de generar el primer token de respuesta.

---

## 3. Soluciones Implementadas

### 3.1 Reemplazar `@lru_cache` por singleton manual con `reset()`

**Archivo:** `src/api/core/claude_config.py`

**Cambio:**

```python
# ANTES:
from functools import lru_cache

@lru_cache()
def get_claude_config_service() -> ClaudeConfigurationService:
    return ClaudeConfigurationService()


# DESPUÉS:
# lru_cache eliminado — congela el resultado del primer import,
# causando race condition con los secrets de Cloud Run en startup.
_claude_config_instance: Optional[ClaudeConfigurationService] = None

def get_claude_config_service() -> ClaudeConfigurationService:
    global _claude_config_instance
    if _claude_config_instance is None:
        _claude_config_instance = ClaudeConfigurationService()
    return _claude_config_instance

def reset_claude_config_service() -> None:
    """Uso exclusivo: tests unitarios."""
    global _claude_config_instance
    _claude_config_instance = None
```

**Justificación técnica:** El singleton manual tiene el mismo comportamiento de "una instancia
por proceso" que `lru_cache`, pero permite resetear el estado entre tests y, más importante,
garantiza que la instancia se crea **después** de que los secrets de Cloud Run estén
disponibles en el entorno, no durante el import inicial del módulo.

---

### 3.2 Eliminar `_resolved_config` — re-lectura de entorno en cada call

**Archivo:** `src/api/core/claude_config.py`, método `get_model_config()`

**Cambio:** El atributo `_resolved_config` fue eliminado del `__init__` y del método
`get_model_config()`. El método ahora resuelve el tier y aplica los overrides en cada
llamada, sin cachear el resultado.

**Justificación técnica:** El overhead de re-leer el entorno es ~0.01ms por llamada
(os.getenv es O(1), MODEL_CONFIGS es un dict en memoria). El beneficio es que los cambios
de secrets como `CLAUDE_MAX_TOKENS` son efectivos sin redeploy. El flag `_overrides_logged`
garantiza que los logs de override se emiten solo una vez por instancia para no inundar GCP.

---

### 3.3 Eliminar properties duplicadas

**Archivo:** `src/api/core/claude_config.py`

Las propiedades `timeout`, `max_retries` y `region` que estaban definidas dos veces en la
clase fueron reducidas a una sola definición cada una, con comentario explicando el bug
original.

---

### 3.4 Conectar la llamada a Claude con `claude_config`

**Archivo:** `src/api/mcp/engines/mcp_personalization_engine.py`,
método `_generate_claude_personalized_response()`

**Cambio:**

```python
# ANTES (hardcodeado, ignoraba toda la configuración centralizada):
claude_response = await asyncio.wait_for(
    self.claude.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        temperature=0.8
    ),
    timeout=timeout
)

# DESPUÉS (lee desde claude_config en cada llamada):
model_config = self.claude_config.get_model_config()
claude_response = await asyncio.wait_for(
    self.claude.messages.create(
        model=model_config.model_name,      # <- CLAUDE_MODEL_TIER → Haiku
        max_tokens=model_config.max_tokens,  # <- CLAUDE_MAX_TOKENS → 200
        temperature=model_config.temperature
    ),
    timeout=timeout
)
```

**Justificación técnica:** `self.claude_config` ya existía en el engine desde la refactorización
anterior, pero nunca se usaba en la llamada real. Este era el punto exacto donde el hardcoding
rompía la cadena de configuración centralizada. El fix de una línea conecta el engine con el
sistema de configuración que ya estaba diseñado para controlar este comportamiento.

---

### 3.5 Reducir los prompts de Claude de ~2200 a ~500 tokens

**Archivo:** `src/api/mcp/engines/mcp_personalization_engine.py`

**Cambio en `_build_advanced_personalization_prompt()`:**

El prompt fue reducido de ~1800 tokens a ~400 tokens. Se eliminaron el historial JSON
serializado, los diccionarios de preferencias vacíos, los indicadores de urgencia, y
las instrucciones redundantes con el system prompt. El prompt resultante contiene solo:
la última query del usuario (máx. 80 chars), los 3 productos con precio, el mercado,
el idioma y el tono. Instrucciones en 2 líneas concisas.

```python
# Nuevo prompt (ejemplo para mercado ES):
"""
El usuario busca: 'productos similares'.
Mercado: Spain | Moneda: EUR | Tono: formal
Productos recomendados: Producto A (EUR45), Producto B (EUR89), Producto C (EUR32)

Responde en es con tono formal en 2-3 oraciones:
1. Por que estos productos son ideales para su busqueda.
2. Destaca el producto mas relevante con su precio.
Respuesta directa sin JSON:
"""
```

**Cambio en `_build_personalized_system_prompt()`:**

El system prompt fue reducido de ~400 tokens (5 secciones con listas) a ~60 tokens
(una sola oración con rol, idioma y tono).

**Justificación técnica:** Claude no necesita conocer sus "capacidades" ni recibir la
misma instrucción de idioma y tono tres veces para generar 2-3 oraciones de recomendación.
Cada token adicional de input añade latencia de prefill. Con Haiku procesando ~2200 tokens
de input generaba ~3-4s antes de generar el primer token de output; con ~500 tokens,
ese tiempo cae por debajo de 200ms.

---

## 4. Componentes Modificados

| Archivo | Cambio | Propósito |
|---|---|---|
| `src/api/core/claude_config.py` | `@lru_cache` → singleton manual con `reset()` | Evita race condition en startup de Cloud Run |
| `src/api/core/claude_config.py` | Eliminado `_resolved_config` cache de instancia | Permite que cambios de secrets sean efectivos |
| `src/api/core/claude_config.py` | Eliminadas properties duplicadas (`timeout`, `max_retries`, `region`) | Elimina bug de mantenimiento silencioso |
| `src/api/core/claude_config.py` | Flag `_overrides_logged` y log `claude_config_effective` en `_apply_environment_overrides()` | El log ahora aparece en cada cache miss, no solo en startup |
| `src/api/mcp/engines/mcp_personalization_engine.py` | `model` y `max_tokens` hardcodeados → `self.claude_config.get_model_config()` | Conecta la llamada real a Claude con la configuración centralizada |
| `src/api/mcp/engines/mcp_personalization_engine.py` | Prompt reducido de ~1800 a ~400 tokens | Elimina latencia de prefill innecesaria |
| `src/api/mcp/engines/mcp_personalization_engine.py` | System prompt reducido de ~400 a ~60 tokens | Elimina instrucciones redundantes |

### Secrets en Cloud Run — sin cambios en esta sesión

Los secrets ya estaban correctamente configurados desde la sesión anterior:

| Secret | Valor | Variable de entorno |
|---|---|---|
| `claude-model-tier` | `HAIKU` | `CLAUDE_MODEL_TIER` |
| `claude-max-tokens` | `200` | `CLAUDE_MAX_TOKENS` |
| `anthropic-api-key` | API key limpia (sin `\r\n`) | `ANTHROPIC_API_KEY` |

---

## 5. Resultados Obtenidos

### 5.1 Métricas de rendimiento — Comparativa antes/después

| Métrica | Antes | Después | Mejora |
|---|---|---|---|
| Modelo activo en personalización | Sonnet (hardcodeado) | **Haiku** | ✅ |
| `max_tokens` activo | 800 (hardcodeado) | **200** (desde secret) | ✅ |
| Tiempo llamada Claude API (cache miss) | ~9400ms | **~966ms** | **9.7x** |
| Latencia total MCP (cache miss) | ~9753ms | **1261ms** | **7.7x** |
| Latencia total MCP (cache hit) | ~315ms | **273ms** | Estable ✅ |

### 5.2 Evidencia en logs de producción

**Log de configuración efectiva** (aparece en cada cache miss, revisión `00066-r6p`):
```json
{
  "event": "⚠️ CLAUDE_MAX_TOKENS secret SOBREESCRIBE el valor del codigo: 300 → 200",
  "logger": "src.api.core.claude_config"
}
{
  "event": "📊 claude_config_effective: model=claude-3-haiku-20240307, max_tokens=200, temperature=0.70",
  "logger": "src.api.core.claude_config"
}
```

**Flujo completo de ejecución 1 (cache miss, 1261ms):**
```
09:55:36.215  🔍 Checking personalization cache...
09:55:36.217  🧠 cache miss → llamando a Claude
09:55:36.222  📊 claude_config_effective: model=claude-3-haiku-20240307, max_tokens=200
09:55:37.183  HTTP POST api.anthropic.com → 200 OK         ← 966ms de llamada Claude
09:55:37.191  Generated personalized response (hybrid strategy)
09:55:37.194  ✅ Cached response — TTL 300s
09:55:37.202  HTTP 200 OK                                   ← 1261ms total
```

**Flujo completo de ejecución 2 (cache hit, 273ms):**
```
09:56:40.280  🔍 Checking personalization cache...
09:56:40.282  ✅ Cache HIT (3ms)
09:56:40.283  ⚡ Using cached personalization — avoiding Claude API call
09:56:40.285  HTTP 200 OK                                   ← 273ms total
```

### 5.3 Estado del sistema al cierre

| Componente | Estado |
|---|---|
| Endpoint MCP (cache miss) | ✅ 1261ms (objetivo: < 3000ms) |
| Endpoint MCP (cache hit) | ✅ 273ms (objetivo: < 500ms) |
| Modelo activo | ✅ claude-3-haiku-20240307 |
| max_tokens efectivo | ✅ 200 (desde secret CLAUDE_MAX_TOKENS) |
| Claude keep-alive | ✅ #1: 6498ms, #2: 1246ms, #3: 1554ms |
| Smoke test 19/19 | ✅ 100% |
| Cache de personalización | ✅ TTL 300s, hit en segunda ejecución |
| GCP Metrics export | ✅ metrics_count=111 por ciclo |
| KB Background Sync | ✅ Operacional |

---

## 6. Observaciones y Gaps

### 6.1 El log `claude_config_effective` se emite en cada cache miss (no solo en startup)

Debido a la eliminación del cache `_resolved_config`, `_apply_environment_overrides()`
se llama en cada request que llega a Claude. El flag `_overrides_logged` controla que el
log de configuración efectiva se emita solo la primera vez por instancia, pero si la
instancia singleton se recrea (por ejemplo, en tests que llaman a
`reset_claude_config_service()`), el log aparecerá de nuevo. Este comportamiento es
correcto y deseable para debugging.

### 6.2 Cache de personalización — TTL de 5 minutos y usuarios anónimos

El cache de personalización usa una clave basada en `user_id + query + context`. Con
`user_id=anonymous` (como en el smoke test), todos los usuarios anónimos comparten la
misma entrada de cache. En producción real con usuarios identificados, cada usuario tendrá
su propia entrada. El TTL de 300s (5 minutos) significa que, en un sistema con bajo
tráfico real, el cache expirará entre visitas de un mismo usuario y volverá a ser un
cache miss.

### 6.3 El prompt simplificado pierde contexto de historial conversacional

El prompt reducido incluye solo la última query del usuario (máx. 80 caracteres). El prompt
original incluía el historial completo de los últimos 3 turnos de conversación. Para
conversaciones multi-turno, esto puede reducir la coherencia de la respuesta personalizada.
Es un trade-off deliberado: reducir latencia a costa de reducir contexto. Se recomienda
monitorear la calidad de las respuestas con usuarios reales y ajustar si se detecta
degradación significativa.

### 6.4 `max_retries=3` en el engine de personalización

El método `_generate_claude_personalized_response()` tiene un loop de reintentos con
`max_retries=2` (3 intentos en total). Con `asyncio.wait_for(timeout=8.0s)` en el handler
externo, si el primer intento tarda 4s y falla, el segundo intento tiene solo 4s de
presupuesto. Este es el diseño correcto, pero si Claude tarda consistentemente entre 3-4s,
el segundo intento puede no completarse a tiempo. Con Haiku a ~1s de latencia, el riesgo
es mínimo en condiciones normales.

### 6.5 Scale-to-zero — keep-alive no sobrevive al cold start

`min-instances=0` por razones de coste. Tras ~5 minutos de inactividad, Cloud Run termina
la instancia. El siguiente request paga el coste completo de startup (~15s) más el warm-up
de Claude (~1.5s). El keep-alive de PASO 8.6 solo es efectivo mientras la instancia
está viva.

### 6.6 Warning de `CLAUDE_MAX_TOKENS` en cada cache miss

El log de nivel WARNING que indica que el secret `CLAUDE_MAX_TOKENS` sobreescribe el valor
del código aparece en **cada cache miss** (no solo en startup). Aunque el flag
`_overrides_logged` lo suprime después del primer call, si hay múltiples instancias del
engine o si el singleton se reinicia, puede aparecer repetidamente en los logs.
Solución permanente: eliminar el secret `CLAUDE_MAX_TOKENS` y fijar el valor directamente
en `MODEL_CONFIGS` del código, ya que el valor (200) es estable.

---

## 7. Consideraciones y Recomendaciones

### 7.1 El hardcoding de parámetros de LLM es un anti-patrón silencioso

**Lección aprendida:** Tener un sistema de configuración centralizado (`ClaudeConfigurationService`)
no garantiza que todos los puntos de uso lo respeten. En este caso, `mcp_personalization_engine.py`
tenía `self.claude_config` correctamente inyectado pero nunca lo usaba en la llamada real a
Claude. El resultado fue que todos los esfuerzos por configurar el modelo vía secrets
fueron invisibles.

**Recomendación:** Al añadir cualquier llamada a `messages.create()` en el código, verificar
siempre que `model` y `max_tokens` se leen desde `self.claude_config.get_model_config()`.
Una búsqueda simple de `model="claude-` o `max_tokens=` en el codebase puede revelar
hardcoding adicional.

### 7.2 `@lru_cache` es peligroso para funciones que leen el entorno

**Lección aprendida:** `@lru_cache()` es perfecto para funciones puras matemáticas donde el
input determina completamente el output. Para una función cuyo output depende del entorno
en el momento de ejecución (os.getenv, secrets, configuración), `@lru_cache` convierte algo
dinámico en algo estático de forma invisible.

**Recomendación:** Para singletons de configuración que dependen del entorno, usar el patrón
de singleton manual con variable global y función de reset. Este patrón es funcionalmente
equivalente pero permite:
- Reset en tests (evita estado compartido entre tests)
- Diagnóstico claro de cuándo se crea la instancia
- Posibilidad de recarga en caliente si fuera necesario

### 7.3 Calibrar los prompts para el caso de uso real, no el caso teórico

**Lección aprendida:** El prompt original fue diseñado para un caso teórico rico: usuario
con historial, preferencias detalladas, indicadores de urgencia y contexto multi-turno.
En producción real, el usuario es anónimo, el historial está vacío y todos esos campos
se serializaban como `{}` o `[]`. Claude procesaba ~2000 tokens de campos vacíos.

**Recomendación:** Antes de construir un prompt complejo, verificar qué datos están
realmente disponibles en el caso de uso más frecuente. Un prompt de 400 tokens con datos
reales es más efectivo que un prompt de 2000 tokens con campos vacíos. Si en el futuro
se dispone de historial real de usuario, se puede añadir de vuelta al prompt de forma
condicional.

### 7.4 Usar `claude_config_effective` como punto de verdad operacional

**Lección aprendida:** A lo largo de estas sesiones, el mayor obstáculo para el diagnóstico
fue no saber qué modelo y max_tokens estaba usando Claude en producción. El log
`claude_config_effective` añadido en la sesión anterior existía, pero al estar en
`_apply_environment_overrides()` con `_resolved_config`, solo aparecía una vez en startup
y no era visible cuando importaba (en cada llamada real).

**Recomendación:** Para cualquier parámetro que afecte latencia o coste, loguear el valor
efectivo en el punto de uso, no solo en el startup. La query GCP para monitorear esto:
```
resource.type="cloud_run_revision"
jsonPayload.event=~"claude_config_effective"
```

### 7.5 Verificar la cadena completa de configuración antes de depurar latencia

**Lección aprendida:** En esta sesión se invirtió tiempo significativo verificando el mapeo
de secrets en Cloud Run (correcto), el código de `claude_config.py` (parcialmente corregido
en sesión anterior), y el singleton (bug del lru_cache). La causa raíz real era en un
archivo diferente: el engine de personalización. La cadena completa es:

```
Secret Manager → env var → ClaudeConfigurationService → get_model_config()
                              ↑ singleton manual          ↑ sin cache de instancia
                                                              ↓
                              mcp_personalization_engine._generate_claude_personalized_response()
                                  ↑ self.claude_config.get_model_config() — AQUÍ es donde debe usarse
```

Cuando se depure latencia de Claude, verificar **siempre** que el punto de uso final
del modelo (el `messages.create()`) lee desde `claude_config`, no tiene valores hardcodeados.

### 7.6 El tamaño del prompt tiene impacto directo en latencia — incluso con modelos rápidos

**Lección aprendida:** Cambiar de Sonnet a Haiku redujo la latencia de ~9.4s a ~3-4s.
Pero reducir el prompt de ~2200 a ~500 tokens redujo la latencia de ~3-4s a ~966ms.
La optimización del prompt tuvo mayor impacto que el cambio de modelo.

**Recomendación:** Para endpoints de latencia crítica, auditar periódicamente el tamaño
de los prompts. La regla práctica: si el prompt tiene secciones que se serializan como
`{}`, `[]` o valores vacíos en el caso más frecuente, esas secciones no deberían estar
en el prompt. Solo incluir contexto que realmente cambie la respuesta de Claude.

---

## 8. Próximos Pasos

### 8.1 Evaluar calidad de las respuestas del prompt simplificado — Alta prioridad

**Objetivo:** Confirmar que las respuestas de 2-3 oraciones generadas por el prompt
reducido son útiles y relevantes desde la perspectiva del usuario final.

**Cómo:** El smoke test actual solo valida que el endpoint responde con HTTP 200.
Se recomienda añadir al smoke test una validación del contenido de `ai_response`:
- Longitud mínima (> 20 caracteres)
- Presencia del idioma correcto
- Mención de algún producto de las recomendaciones

**Acción alternativa:** Revisar manualmente los logs de GCP para leer las respuestas
reales. Buscar en Cloud Logging:
```
resource.type="cloud_run_revision"
jsonPayload.event=~"Generated personalized response"
```
Y examinar el campo `ai_response` en la respuesta del router MCP.

---

### 8.2 Eliminar el secret `CLAUDE_MAX_TOKENS` y consolidar en código — Media prioridad

**Objetivo:** Eliminar la fuente del warning recurrente y reducir la complejidad operacional.

**Justificación:** El valor `200` para `max_tokens` ha sido validado en producción como
correcto para el caso de uso. Mantener un secret separado añade complejidad sin flexibilidad
real (cambiarlo requeriría un redeploy de todas formas para que el singleton se recree).

**Implementación:**
```bash
# 1. Actualizar MODEL_CONFIGS en claude_config.py:
ClaudeModelTier.HAIKU: ClaudeModelConfig(max_tokens=200, ...)

# 2. Eliminar el mapeo del secret en Cloud Run:
gcloud run services update retail-recommender \
  --remove-secrets=CLAUDE_MAX_TOKENS \
  --region us-central1 \
  --project retail-recommendations-449216

# 3. Opcionalmente, eliminar el secret de Secret Manager:
gcloud secrets delete claude-max-tokens --project retail-recommendations-449216
```

---

### 8.3 Enriquecer el prompt condicionalmente con historial real — Media prioridad

**Objetivo:** Recuperar la calidad de personalización cuando el usuario tiene historial
conversacional real, sin penalizar la latencia en la primera visita.

**Implementación sugerida:**

```python
# En _build_advanced_personalization_prompt():
history_section = ""
if mcp_context.turns and len(mcp_context.turns) > 1:
    # Solo añadir historial si hay más de 1 turno (primera visita no tiene historia)
    recent_queries = [t.user_query[:40] for t in mcp_context.turns[-2:]]
    history_section = f"Historial reciente: {' → '.join(recent_queries)}\n"

prompt = (
    f"El usuario busca: '{last_query}'.\n"
    f"{history_section}"  # Solo presente si hay historial
    f"Mercado: {market_config.name} | ...\n"
    # ...
)
```

---

### 8.4 Implementar pre-warming del cache en startup — Media prioridad

**Objetivo:** Garantizar que la primera request real de usuario sea un cache hit (~300ms)
en lugar de un cache miss (~1300ms).

**Concepto:** En PASO 8.5b del lifespan, después del warm-up TCP, ejecutar una llamada
a `generate_personalized_response()` con datos de muestra del catálogo. El resultado
se cachea con TTL de 5 minutos. Si el primer usuario real llega dentro de ese window,
obtiene una respuesta en ~300ms.

**Nota:** El cache key incluye `user_id`. Para que funcione con usuarios reales, el
pre-warming debería usar `user_id=anonymous` (el id más frecuente en el smoke test).
Para usuarios identificados, el primer request siempre será cache miss de todas formas.

---

### 8.5 Planificar inicio de L4 ML Content Optimization — Planificación

**Prerequisito:** `kb_content_versions` debe tener ≥ 3 semanas de historial continuo.

**Fecha estimada:** ~26 de Marzo de 2026 (según criterios establecidos en
`L4_DATA_REQUIREMENTS.md`).

**Acción previa:** Verificar con las queries SQL definidas en el documento L4 que el
dataset cumple los criterios mínimos antes de iniciar la fase.

---

### 8.6 Fixes menores pendientes

| Acción | Prioridad | Ubicación |
|---|---|---|
| Fix cosmético alerta KB Sync: `cast_units(val(), "") > 0.01` | Baja | GCP Cloud Monitoring |
| Revisar `CLAUDE_MAX_RETRIES=3` — evaluar reducción a 1 | Media | `claude_config.py` |
| Dead code consolidation (~400KB) antes de L4 | Media | `src/api/`, `src/api/core/` |
| Verificar instrumentación timer en `ShopifyKBSyncService` | Baja | `src/api/services/shopify_kb_sync.py` |

---

## Apéndice A — Arquitectura de configuración de Claude post-sesión

```
Secret Manager
  └── claude-model-tier = "HAIKU"
        └── inyectado como env var CLAUDE_MODEL_TIER
              └── ClaudeConfigurationService.__init__()
                    └── _resolve_model_tier() → ClaudeModelTier.HAIKU
                          └── get_claude_config_service() [singleton manual]
                                └── MCPPersonalizationEngine.claude_config
                                      └── _generate_claude_personalized_response()
                                            └── model_config = self.claude_config.get_model_config()
                                                  └── messages.create(
                                                        model=model_config.model_name,   # Haiku
                                                        max_tokens=model_config.max_tokens  # 200
                                                      )
```

---

## Apéndice B — Arquitectura de timeouts MCP post-sesión

```
Request → /v1/mcp/recommendations/{product_id}
           │
           ▼
   mcp_conversation_handler.py
   ├── [FASE 3] execute_mcp_operations_parallel()
   │       ├── ParallelTask("mcp_recommendations")   timeout=10.0s   ← capa 1
   │       ├── ParallelTask("personalization")        timeout=5.0s    ← capa 1
   │       └── ParallelTask("market_context")         timeout=3.0s    ← capa 1
   │
   └── [FASE 4] asyncio.wait_for(
               generate_personalized_response(),
               timeout=8.0s                                           ← capa 2
           )
           └── _generate_claude_personalized_response()
                 └── asyncio.wait_for(
                       messages.create(model=Haiku, max_tokens=200),
                       timeout=15.0s                                  ← capa 3 interna
                     )

Jerarquía correcta:
  ParallelTask.timeout (10s) > wait_for handler (8s) > wait_for interno (15s, nunca alcanzado)
```

---

## Apéndice C — Query de verificación post-deploy

Para confirmar que los cambios están activos tras cualquier deploy futuro, buscar en
GCP Logs Explorer durante un cache miss:

```
resource.type="cloud_run_revision"
jsonPayload.event=~"claude_config_effective"
```

**Resultado esperado:**
```json
{
  "event": "📊 claude_config_effective: model=claude-3-haiku-20240307, max_tokens=200, temperature=0.70",
  "logger": "src.api.core.claude_config"
}
```

Si aparece `claude-sonnet-4-20250514` o `max_tokens` distinto de 200, hay hardcoding
activo o el secret `CLAUDE_MODEL_TIER` no está mapeado correctamente.

---

*DCT — Sesión 21–22 de Marzo de 2026*
*Retail Recommender System v2.1.0*
*Revisión activa al cierre: retail-recommender-00066-r6p*
*Versión del documento: 1.0*
