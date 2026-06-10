# Claude Haiku vs GPT-4o-mini — Análisis Comparativo
## Retail Recommender System v2.1.0 — Junio 2026

> **Contexto:** Este análisis responde directamente a la pregunta: ¿GPT-4o-mini es la mejor  
> opción para reemplazar Claude Haiku como fallback? Incluye costos reales de warm-up y  
> keepalive extraídos del código de `main_unified_redis.py` (PASO 8.5 y PASO 8.6).  
> **Base del análisis histórico revisada:** `docs/0_plans/Claude_Haiku_VS_Gemini2.5.md`

---

## 0. Hallazgo crítico: hay DOS modelos Claude activos en el código

Antes de cualquier comparativa de costos, es fundamental corregir un dato que el análisis  
histórico no podía conocer: **`claude_config.py` y `main_unified_redis.py` apuntan a  
versiones diferentes de Haiku**.

| Punto de uso | Modelo hardcodeado | Versión | Pricing |
|---|---|---|---|
| `claude_config.py` → `ClaudeModelTier.HAIKU` | `claude-3-haiku-20240307` | **Haiku 3** | $0.25/$1.25 por 1M |
| `main_unified_redis.py` PASO 8.5 (warm-up) | `claude-haiku-4-5-20251001` | **Haiku 4.5** | $1.00/$5.00 por 1M |
| `main_unified_redis.py` PASO 8.6 (keepalive) | `claude-haiku-4-5-20251001` | **Haiku 4.5** | $1.00/$5.00 por 1M |

**Consecuencia directa:** Las inferencias de fallback reales (el 99% del costo) se facturan  
a precio de Haiku 3. El warm-up y el keepalive (si se reactivaran) se facturarían a precio  
de Haiku 4.5, que es **4x más caro por token**. Esta inconsistencia debe resolverse  
independientemente de la decisión de migrar.

---

## 1. Estado del sistema al momento del análisis

| Componente | Estado | Impacto en análisis |
|---|---|---|
| LFM2-24B (primario MCP) | ✅ Activo, `LFM_MCP_ENABLED=true` | 95-97% de las llamadas LLM |
| LFM2.5-1.2B (primario KB) | ✅ Activo, `LFM_KB_ENABLED=true` | KB conversaciones informacionales |
| LFM keepalive (PASO 8.7) | ✅ Activo, 300s interval | Mantiene OpenRouter connection warm |
| Claude warm-up (PASO 8.5) | 🔴 Activo pero **fallando** — credits agotados | Latencia adicional en cold-start |
| Claude keepalive (PASO 8.6) | ⚫ **COMENTADO** — no corre | Costo = $0 actualmente |
| Claude fallback (inferencia) | 🔴 **Inaccessible** — credits agotados | Fallback chain rota |
| Bugs (price_clp, diversif., currency) | ✅ Corregidos (Sprint 29/05) | Sistema estable |
| GCP FinOps actions | ✅ Ejecutadas (06-09/06) | CHF ~1,020/año ahorrado |

---

## 2. Modelo de costos detallado — Parámetros base

Extraídos de `GCP_Cost_Analysis_Retail_Recommender_v2_1_09062026.docx` y código:

```
Conversaciones/mes:       4,500  (midpoint tienda mediana)
Turns/conversación:       3
Total llamadas LLM/mes:   13,500
Tasa de fallo LFM:        ~5%    (circuit-breaker abre tras 3 fallos → fallback real < 5%)
Fallback calls/mes:       ~675   calls
Input tokens/call:        ~650   (system ~500 + user ~150)
Output tokens/call:       ~200   (max_tokens=300, respuesta típica más corta)
Cold starts/mes:          ~60    (2/día promedio, min-instances=0)
Tokens/warm-up call:      ~10 input + 1 output
Tokens/keepalive call:    ~10 input + 1 output
Keepalive interval:       90s → 40 pings/h × 24h × 30d = 28,800 pings/mes
LFM keepalive interval:   300s → 8,640 pings/mes (ya incluido en OpenRouter connection)
```

---

## 3. Tabla de costos — Desglose por componente

### 3.1 Escenario A — Estado actual sin cambios (keepalive OFF, credits agotados)

| Componente | Modelo activo | Calls/mes | Input tokens | Output tokens | Precio input | Precio output | Costo/mes |
|---|---|---|---|---|---|---|---|
| **Inferencia fallback** | claude-3-haiku-20240307 | 675 | 438,750 | 135,000 | $0.25/M | $1.25/M | **$0.279** |
| **Warm-up startup** | claude-haiku-4-5-20251001 | 60 | 600 | 60 | $1.00/M | $5.00/M | **$0.0009** |
| **Keepalive** (OFF) | — | 0 | — | — | — | — | **$0.000** |
| **TOTAL CLAUDE HAIKU** | | | | | | | **$0.280/mes** |

> **Nota:** Con credits agotados, el costo real HOY es $0 pero el fallback está roto.  
> La pregunta correcta es: ¿cuánto costaría si recargamos créditos vs. si migramos?

---

### 3.2 Escenario B — Claude Haiku restaurado con keepalive reactivado (modo producción completo)

Si se recargan créditos Y se descomenta el bloque del PASO 8.6:

| Componente | Calls/mes | Input tokens | Output tokens | Costo input | Costo output | **Total** |
|---|---|---|---|---|---|---|
| Inferencia fallback (Haiku 3) | 675 | 438,750 | 135,000 | $0.110 | $0.169 | $0.279 |
| Warm-up (Haiku 4.5) | 60 | 600 | 60 | $0.0006 | $0.0003 | $0.0009 |
| **Keepalive (Haiku 4.5, si ON)** | 28,800 | 288,000 | 28,800 | $0.288 | $0.144 | **$0.432** |
| **TOTAL con keepalive** | | | | | | **$0.712/mes** |

> ⚠️ **El keepalive representa el 61% del costo total de Claude si se reactiva.**  
> Y está usando Haiku 4.5 ($1.00/$5.00), no Haiku 3, para pings mínimos de 10 tokens.  
> Esto es una ineficiencia que no tiene equivalente en el escenario GPT-4o-mini.

---

### 3.3 Escenario C — GPT-4o-mini via OpenRouter (reemplazo propuesto)

| Componente | Modelo | Calls/mes | Input tokens | Output tokens | Precio input | Precio output | Costo/mes |
|---|---|---|---|---|---|---|---|
| Inferencia fallback | gpt-4o-mini | 675 | 438,750 | 135,000 | $0.15/M | $0.60/M | **$0.147** |
| Warm-up | ❌ No necesario\* | 0 | — | — | — | — | **$0.000** |
| Keepalive | ❌ No necesario\*\* | 0 | — | — | — | — | **$0.000** |
| **TOTAL GPT-4o-mini** | | | | | | | **$0.147/mes** |

\* *El LFM keepalive (PASO 8.7, 300s interval) ya mantiene la conexión a OpenRouter activa.  
   GPT-4o-mini usa la misma infraestructura de conexión → warm TCP garantizado sin costo extra.*  
\*\* *Mismo razonamiento: OpenRouter connection management cubre ambos modelos  
    (LFM y GPT-4o-mini) con una sola conexión pooled. No se necesita un loop separado.*

---

## 4. Comparativa de costos consolidada

| Escenario | Costo mensual | Costo anual | vs. GPT-4o-mini |
|---|---|---|---|
| Claude Haiku (keepalive OFF) | $0.280 | $3.36 | +$1.60/año |
| Claude Haiku (keepalive ON) | $0.712 | $8.54 | +$6.78/año |
| **GPT-4o-mini via OpenRouter** | **$0.147** | **$1.76** | baseline |

> **Conclusión del modelo económico:** El ahorro en costos de API es modesto (~$1.60–6.78/año).  
> La razón primaria para migrar **no es el ahorro de costos** — es la simplificación operacional.

---

## 5. Comparativa técnica profunda

### 5.1 Calidad conversacional para el caso de uso real

El fallback se invoca para una sola tarea: generar 2-3 frases conversacionales en español/inglés recomendando productos de moda. El prompt tiene ~500 tokens de system prompt bien definido.

| Dimensión | Claude Haiku 3 | GPT-4o-mini | Ventaja |
|---|---|---|---|
| Naturalidad en español | ⭐⭐⭐⭐⭐ Excelente | ⭐⭐⭐⭐½ Muy buena | Claude (+0.5) |
| Naturalidad en inglés | ⭐⭐⭐⭐⭐ Excelente | ⭐⭐⭐⭐⭐ Excelente | Empate |
| Tono fashion/e-commerce | ⭐⭐⭐⭐½ Muy bueno | ⭐⭐⭐⭐ Bueno | Claude (+0.5) |
| Seguimiento de instrucciones | ⭐⭐⭐⭐⭐ Muy alto | ⭐⭐⭐⭐⭐ Muy alto | Empate |
| Respuestas concisas (2-3 frases) | ⭐⭐⭐⭐⭐ Consistente | ⭐⭐⭐⭐ Bueno | Claude (+1) |
| Multi-turn coherence | ⭐⭐⭐⭐½ | ⭐⭐⭐⭐ | Claude (+0.5) |
| Multilingüe ES/EN/FR/DE | ⭐⭐⭐⭐⭐ Excelente | ⭐⭐⭐⭐⭐ Excelente | Empate |
| Mercados CL/MX/CH/ES | ⭐⭐⭐⭐½ Calibrado | ⭐⭐⭐⭐ Bueno | Claude (+0.5) |

**Evaluación de calidad:** Claude Haiku mantiene ventaja marginal (+3 puntos sobre 40)  
para prompts cortos de e-commerce fashion en español. La diferencia es real pero **no es  
perceptible en el contexto de un fallback** que ocurre el 5% de las veces.

> **Principio arquitectónico:** Un fallback no necesita ser mejor que el modelo principal.  
> Necesita ser "suficientemente bueno" para no degradar la experiencia del usuario cuando  
> el primario falla. GPT-4o-mini supera ese umbral.

---

### 5.2 Capacidades técnicas

| Capacidad | Claude Haiku 3 | GPT-4o-mini | Relevancia para este sistema |
|---|---|---|---|
| Context window | 200K tokens | 128K tokens | ⚠️ Baja — prompts son ~650 tokens |
| JSON structured output | ✅ Muy confiable | ✅ Muy confiable | No se usa en fallback (solo texto) |
| Tool calling | ✅ Confiable | ✅ Muy confiable | No se usa en fallback |
| System prompt separado | ✅ Nativo | ✅ Vía `{"role":"system"}` | Handled por UnifiedLLMClient |
| Prompt caching | ✅ 90% descuento | ✅ Auto prefix cache | System prompt repetido → caching activo |
| Max output tokens | 4,096 | 16,384 | No relevante — max_tokens=300 |
| stop_reason format | `stop_reason` | `finish_reason` | ✅ Abstraído por UnifiedLLMClient |
| Respuesta format | `.content[0].text` | `.choices[0].message.content` | ✅ Abstraído por UnifiedLLMClient |

**Conclusión técnica:** Todas las diferencias de API relevantes ya están **abstraídas por  
`UnifiedLLMClient`**, que fue diseñado exactamente para este propósito. El fallback a  
GPT-4o-mini reutiliza la misma infraestructura que LFM sin modificaciones.

---

### 5.3 Rendimiento y latencia

| Métrica | Claude Haiku 3 | GPT-4o-mini via OpenRouter | Fuente |
|---|---|---|---|
| TTFT (time to first token) | ~300–600ms | ~200–500ms | Artificial Analysis 2026 |
| Throughput (tokens/s) | ~90–120 t/s | ~100–130 t/s | OpenRouter benchmarks |
| Latencia total p50 (prompt ~650 tokens) | ~800–1,200ms | ~600–900ms | Estimado desde métricas producción |
| Latencia en producción medida | **966ms** (Haiku, log real) | ~700–800ms (estimado) | DCT 21/03/2026 |
| Variabilidad (jitter p95) | Media | Baja–Media | OpenRouter load balancing |
| Disponibilidad (SLA) | 99.9%+ | 99.9%+ (OpenRouter multi-provider) | Providers' SLAs |

> **Ventaja latencia:** GPT-4o-mini via OpenRouter tiene ventaja estimada de ~150–250ms  
> en latencia total. Para un fallback que ya está en el caso degradado, esta mejora es  
> bienvenida aunque no crítica.

---

### 5.4 Integración con la arquitectura actual

| Aspecto | Claude Haiku | GPT-4o-mini via OpenRouter | Delta de esfuerzo |
|---|---|---|---|
| Cliente SDK | `AsyncAnthropic` (SDK propio) | `openai.AsyncOpenAI` (ya en uso para LFM) | **0h** (mismo SDK) |
| API key | `ANTHROPIC_API_KEY` (Secret Manager) | `OPENROUTER_API_KEY` (ya existe) | **0h** (ya configurado) |
| Config entry | `ClaudeModelTier.HAIKU` (claude_config.py) | Nueva entrada en `claude_config.py` | **15 min** |
| `mcp_personalization_engine.py` | Ruta `claude` existente | Misma ruta, distinto `UnifiedLLMClient` | **30 min** |
| `kb_contextualizer.py` | Mismo patrón | Mismo patrón | **30 min** |
| Tests | Existentes para Claude path | Adaptar 2 tests, añadir 1 nuevo | **45 min** |
| Warm-up PASO 8.5 | Mantener como está o desactivar | Puede eliminarse (LFM cubre) | **15 min** |
| Keepalive PASO 8.6 | No aplica (ya comentado) | No aplica (OpenRouter ya warm) | **0h** |
| **Esfuerzo total estimado** | — | — | **~2 horas** |

**Plantilla exacta** (reutiliza 100% el patrón de Fase A del LiquidAI plan):

```python
# src/api/core/claude_config.py — añadir:
GPT4O_MINI_FALLBACK_CONFIG = {
    'provider': 'openrouter',
    'model': 'openai/gpt-4o-mini',
    'max_tokens': 300,
    'temperature': 0.7,
    'description': 'GPT-4o-mini via OpenRouter — fallback MCP/KB'
}

# Variable de entorno nueva:
# GPT4O_MINI_FALLBACK_ENABLED=false  (activar tras A/B test)

# src/api/mcp/engines/mcp_personalization_engine.py — añadir en __init__:
self._gpt_fallback_enabled = os.environ.get('GPT4O_MINI_FALLBACK_ENABLED', 'false').lower() == 'true'
if self._gpt_fallback_enabled:
    self._gpt_fallback_client = UnifiedLLMClient(
        provider=GPT4O_MINI_FALLBACK_CONFIG['provider'],
        model=GPT4O_MINI_FALLBACK_CONFIG['model'],
        max_tokens=GPT4O_MINI_FALLBACK_CONFIG['max_tokens'],
        temperature=GPT4O_MINI_FALLBACK_CONFIG['temperature'],
    )

# En _generate_claude_personalized_response():
# LFM path (existente) → falla → GPT-4o-mini path (nuevo) → falla → sin personalización
```

---

### 5.5 Operacional y gestión de créditos

| Dimensión | Claude Haiku | GPT-4o-mini via OpenRouter |
|---|---|---|
| Proveedor de facturación | Anthropic (separado) | OpenRouter (mismo que LFM) |
| API keys a gestionar | `ANTHROPIC_API_KEY` + `OPENROUTER_API_KEY` | Solo `OPENROUTER_API_KEY` |
| Monitoreo de créditos | Cuenta Anthropic separada | Dashboard OpenRouter unificado |
| Credit exhaustion risk | ⚠️ Ya ocurrió — rompe warm-up y fallback | Compartido con LFM → agotamiento mucho más visible y manejable |
| Billing alerts | Requiere configurar en Anthropic Console | Existente en OpenRouter dashboard |
| Rollback ante problemas | `CLAUDE_MODEL_TIER` secret → Haiku | `GPT4O_MINI_FALLBACK_ENABLED=false` |

**El problema real que resuelve la migración:** El sistema lleva tiempo con fallback roto  
porque los créditos de Anthropic se agotaron silenciosamente. Con OpenRouter, un solo  
límite de gasto controla tanto el primario (LFM) como el fallback (GPT-4o-mini). La  
probabilidad de que ambos fallen por saldo es la misma, pero es **un solo sistema de alerta**  
en lugar de dos cuentas de billing que monitorear.

---

## 6. Análisis de riesgos del cambio

| Riesgo | Probabilidad | Impacto | Mitigación disponible |
|---|---|---|---|
| Degradación de calidad conversacional en ES | Media | Bajo (es fallback, no primario) | A/B test antes de activar; flag OFF por defecto |
| Comportamiento diferente del modelo ante el prompt actual | Media-Baja | Bajo | Testar 5 queries del protocolo de Fase A (LiquidAI plan) |
| OpenRouter intermittence afecta LFM y fallback simultáneamente | Baja | Medio | Graceful degradation: respuesta sin personalización (ya implementado) |
| `system` prompt silently lost | ❌ No aplica | — | UnifiedLLMClient ya lo maneja para LFM — misma conversión para GPT-4o-mini |
| `stop_reason` vs `finish_reason` incompatibility | ❌ No aplica | — | Abstraído por UnifiedLLMClient |
| Rate limit distinto | Baja | Bajo | 675 calls/mes = 22 calls/día — irrelevante para cualquier rate limit |
| Model deprecation risk | Baja | Bajo | GPT-4o-mini es modelo estable; fallback se puede cambiar con 1 env var |

**El riesgo más importante del análisis histórico** ("diferencia en el parámetro `system`")  
ya está mitigado: `UnifiedLLMClient` fue construido precisamente para normalizar estas  
diferencias entre proveedores. Es el mismo adaptador que ya funciona en producción  
con LFM2-24B.

---

## 7. Resolución de la inconsistencia detectada en el código

Independientemente de la decisión de migrar, se recomienda resolver la inconsistencia  
entre los dos modelos Claude activos:

### Opción A — Unificar en Haiku 3 (si se mantiene Claude)

```python
# main_unified_redis.py, líneas 1316 y 1435:
# Cambiar de:
model="claude-haiku-4-5-20251001"
# A:
model="claude-3-haiku-20240307"  # consistente con ClaudeModelTier.HAIKU
```

**Impacto en costo keepalive (si se reactiva):** Cae de $0.432/mes a $0.108/mes (-75%).

### Opción B — Migrar a GPT-4o-mini (reemplaza el problema de raíz)

El warm-up y el keepalive desaparecen como conceptos separados para el fallback.  
OpenRouter gestiona la conexión pool de forma transparente para todos sus modelos.

---

## 8. Recomendación

### ¿Es GPT-4o-mini la mejor opción?

**Sí**, con la siguiente precisión: GPT-4o-mini es la mejor opción **dado el contexto  
arquitectónico actual** (OpenRouter ya integrado, UnifiedLLMClient existente, LFM como  
primario). No es la mejor opción en abstracto — Claude Haiku tiene mejor calidad para  
esta tarea específica. El trade-off está bien calibrado para el rol de fallback.

### Razones principales (en orden de importancia)

1. **Operacional:** Elimina la segunda cuenta de billing (Anthropic) y consolida todo en OpenRouter. El credit exhaustion de Claude es el síntoma de un problema de gestión de dos proveedores.
2. **Arquitectónico:** Costo de implementación = ~2 horas. El patrón está documentado, el SDK está instalado, la API key existe.
3. **Keepalive eliminado:** No se necesita el PASO 8.6. El LFM keepalive cubre la conexión OpenRouter para todos los modelos. Se simplifica el código del lifespan.
4. **Warm-up simplificado:** El PASO 8.5 puede eliminarse o convertirse en un simple verificador de que `mcp_recommender.client` está disponible, sin costo de API.
5. **Económico:** $0.147/mes vs $0.280/mes (keepalive OFF) — diferencia modesta pero en la dirección correcta.

### Plan de implementación (2 horas)

```
Hora 1:
  1. Añadir GPT4O_MINI_FALLBACK_CONFIG en claude_config.py
  2. Modificar mcp_personalization_engine.py (patrón idéntico a Fase A LFM)
  3. Modificar kb_contextualizer.py (mismo patrón)
  4. Desplegar con GPT4O_MINI_FALLBACK_ENABLED=false
  5. Verificar que el sistema arranca sin errores

Hora 2:
  1. A/B test: 5 queries del protocolo de validación de Fase A
  2. Comparar respuesta LFM (activo) vs GPT-4o-mini (forzado manualmente)
  3. Activar al 100%: GPT4O_MINI_FALLBACK_ENABLED=true
  4. Comentar/eliminar el PASO 8.5 (warm-up Claude) — ya no necesario
  5. Confirmar en logs que LFM keepalive mantiene OpenRouter warm (ya funciona)

Trabajo adicional opcional (30 min, después del deploy):
  - Resolver inconsistencia claude_config.py: eliminar ClaudeModelTier o mantener como legacy
  - Añadir nota en main_unified_redis.py explicando que PASO 8.6 está deprecado
```

### Nota sobre el futuro: GPT-5.4 nano

En la familia OpenAI de junio 2026, existe GPT-5.4 nano ($0.20/$1.25) con mejor  
calidad que GPT-4o-mini a precio similar. Si en algún momento la calidad del fallback  
se vuelve un KPI relevante, migrar de GPT-4o-mini a GPT-5.4 nano es un cambio de  
**una línea** en `claude_config.py`:

```python
'model': 'openai/gpt-5.4-nano',  # en lugar de 'openai/gpt-4o-mini'
```

---

## Apéndice: Estado de los flujos conversacionales afectados

| Flujo | Archivo | Uso de Claude | Impacto del cambio |
|---|---|---|---|
| MCP Personalization (TRANSACTIONAL) | `mcp_personalization_engine.py` | Fallback si LFM falla | 1 modificación quirúrgica |
| KB Contextualization (INFORMATIONAL) | `kb_contextualizer.py` | Fallback si LFM falla | 1 modificación quirúrgica |
| Warm-up startup (PASO 8.5) | `main_unified_redis.py` | TCP/TLS pre-warming | Puede eliminarse |
| Keep-alive (PASO 8.6) | `main_unified_redis.py` | Pool TCP maintenance | Ya comentado — no acción |
| Intent detection | `hybrid_detector.py` | ❌ No usa Claude | Sin impacto |
| Product retrieval | `hybrid_recommender.py` | ❌ No usa Claude | Sin impacto |
| Visual search | `visual_search_router.py` | ❌ No usa Claude | Sin impacto |
| Outfit completion | `visual_search_router.py` | ❌ No usa Claude | Sin impacto |

**Componentes con cero impacto:** 5 de 8 flujos conversacionales no tocan Claude en absoluto.  
El cambio es quirúrgico en exactamente 2 archivos de inferencia.

---

*Análisis generado: 09 de junio de 2026*  
*Sistema: Retail Recommender v2.1.0 · Referencia: `331cfd3fcb2881588cfbff02aadce3a8`*  
*Archivos revisados: `main_unified_redis.py` (PASO 8.5, 8.6, 8.7), `claude_config.py`,  
`LiquidAI_Integration_Plan_16042026.docx`, `GCP_Cost_Analysis_Retail_Recommender_v2_1_09062026.docx`,  
`DCT_Sprint_Fix_29052026.md`, `docs/0_plans/Claude_Haiku_VS_Gemini2.5.md`*
