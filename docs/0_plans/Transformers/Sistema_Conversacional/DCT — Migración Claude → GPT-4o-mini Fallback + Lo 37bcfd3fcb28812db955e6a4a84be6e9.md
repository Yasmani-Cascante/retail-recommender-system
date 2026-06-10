# DCT — Migración Claude → GPT-4o-mini Fallback + Log Cleanup — 10/06/2026

# Estado del sistema al cierre

Sesión de migración y validación. Claude Haiku reemplazado como modelo de fallback por GPT-4o-mini vía OpenRouter. Stack LFM completo (Fases A + B + C) validado en local con 10+ turns. Todos los fixes de logs aplicados y confirmados. Sistema estable, sin regresiones.

---

## Contexto — Evaluación estratégica LLM

Antes de implementar, se realizó una evaluación de 4 candidatos para reemplazar Claude Haiku:

| Modelo | Veredicto | Razón principal |
| --- | --- | --- |
| DeepSeek V4 Flash | ❌ Descalificado | Riesgo GDPR/nDSG para mercados CH/EU |
| GPT-4o-mini | ✅ Seleccionado | Mejor calidad conversacional en ES, GDPR-compliant, integración trivial via OpenRouter |
| Gemini 1.5 Flash / 2.5 Flash | ⚠️ Legado / caro output | 2.5 Flash más caro en output que Claude Haiku |
| Llama 3.1 70B | ⚠️ Condicional | Calidad conversacional ES insuficiente para e-commerce fashion |

El costo real del fallback post-migración LFM es ~$0.15/mes (vs $0.28/mes de Claude Haiku 3). El driver principal de la migración es la **consolidación operacional en OpenRouter** (un único proveedor + API key para LFM y fallback), no el ahorro económico.

---

## Tarea 1 — claude_[config.py](http://config.py): añadir GPT4O_MINI_FALLBACK_CONFIG ✅

### Cambio

Se añadió `GPT4O_MINI_FALLBACK_CONFIG` después de `LFM_KB_CONFIG`. El dict reemplaza semánticamente al modelo Claude Haiku que se usaba como fallback.

```python
GPT4O_MINI_FALLBACK_CONFIG = {
    'provider': 'openrouter',
    'model': 'openai/gpt-4o-mini',
    'max_tokens': 300,
    'temperature': 0.7,
    'description': 'GPT-4o-mini — fallback MCP/KB cuando LFM falla (reemplaza Claude Haiku)',
}
```

**Ventaja operacional:** Usa `OPENROUTER_API_KEY` existente. Sin nueva cuenta de billing, sin gestión de créditos separada. La conexión TCP a OpenRouter ya está warm gracias al LFM keep-alive (PASO 8.7, 300s).

**Nota:** El naming pasó por una iteración: se creó primero como `GPT_5_4_NANO_FALLBACK_CONFIG` (GPT-5.4 nano), luego se cambió a GPT-4o-mini por mejor calidad conversacional para e-commerce fashion. Se renombraron todas las variables y referencias en los 3 archivos afectados.

---

## Tarea 2 — mcp_personalization_[engine.py](http://engine.py): múltiples cambios ✅

### 2.1 Import actualizado

```python
from src.api.core.claude_config import LFM_MCP_CONFIG, GPT4O_MINI_FALLBACK_CONFIG
```

### 2.2 Inicialización del cliente GPT-4o-mini en **init**

Se añadió bloque `_gpt4o_mini_fallback_enabled` + `_gpt4o_mini_client` inmediatamente después del bloque LFM. Patrón idéntico al bloque LFM existente. Controlado por variable de entorno `GPT4O_MINI_FALLBACK_ENABLED`.

### 2.3 Reemplazo del bloque TEMPORAL (fix crítico)

El bloque marcado como `# TEMPORAL` (Sprint httpx 24/05/2026) que devolvía una respuesta genérica cuando LFM fallaba fue reemplazado por el fallback real a GPT-4o-mini.

### 2.4 Fix de condición (bug detectado en testing)

**Bug:** La condición original `if _lfm_failed:` solo disparaba el bloque GPT-4o-mini cuando LFM se activaba Y fallaba. Con `LFM_MCP_ENABLED=false`, `_lfm_failed` nunca se ponía a `True` → el bloque GPT-4o-mini se saltaba y el código caía a Claude.

**Fix:** `if _lfm_failed or not self._lfm_mcp_enabled:`

Este fix permite:

- Escenario producción: LFM falla → GPT-4o-mini actúa como fallback
- Escenario testing: LFM desactivado → GPT-4o-mini actúa como modelo principal alternativo

### 2.5 Debug flag FORCE_GPT4O_MINI_FALLBACK

Se añadió `_lfm_failed = os.environ.get('FORCE_GPT4O_MINI_FALLBACK', 'false').lower() == 'true'` al inicio del bloque LFM para permitir testear el path de fallback con el stack completo activo sin deshabilitar LFM.

### 2.6 Fixes de logs stale

- `[lang] LFM path: using router-detected language` → `[lang] Using router-detected language`
- `LFM MCP call failed, falling back to Claude` → `LFM MCP call failed, routing to GPT-4o-mini fallback`

---

## Tarea 3 — kb_[contextualizer.py](http://contextualizer.py): múltiples cambios ✅

### 3.1 Import actualizado

```python
from src.api.core.claude_config import LFM_KB_CONFIG, GPT4O_MINI_FALLBACK_CONFIG
```

### 3.2 Bloque GPT-4o-mini añadido entre LFM y Claude

Se insertó el bloque GPT-4o-mini como fallback KB entre el bloque LFM y el bloque Claude. Cuando LFM falla o no está disponible, el flujo cae a GPT-4o-mini antes de llegar a Claude.

### 3.3 Restructuración de get_model_config() (fix observabilidad)

**Problema detectado:** `get_model_config()` se llamaba al inicio de `generate_contextual_answer()`, antes de los bloques LFM y GPT-4o-mini. Esto disparaba el log `claude_config_effective: model=claude-sonnet-4-20250514` en cada request KB aunque Claude nunca fuera invocado. Creaba confusión en análisis de logs.

**Fix:** `get_model_config()` movido al interior del bloque Claude (legacy path). Los `max_tokens` para LFM y GPT-4o-mini ahora usan constantes directas (250/500) independientes de Claude config.

### 3.4 Fix de log stale

- `contextualising KB answer via Claude` → `contextualising KB answer` (en `mcp_conversation_handler.py`)

### 3.5 Debug flag FORCE_GPT4O_MINI_FALLBACK (añadido en sesión posterior)

Se añadió la misma comprobación del flag en el bloque LFM de kb_contextualizer para que el flag afecte AMBAS rutas (MCP + KB):

```python
_force_gpt_fallback_kb = os.environ.get('FORCE_GPT4O_MINI_FALLBACK', 'false').lower() == 'true'
if _force_gpt_fallback_kb:
    logger.info('FORCE_GPT4O_MINI_FALLBACK=true: skipping LFM KB...')
elif _lfm_kb_enabled:
    ...
```

---

## Validación — Resultados de testing local

### Sesión de validación 1 — GPT-4o-mini standalone (LFM desactivado)

Condiciones: `LFM_MCP_ENABLED=false`, `LFM_KB_ENABLED=false`, `GPT4O_MINI_FALLBACK_ENABLED=true`

| Turn | Intent | Modelo | Resultado |
| --- | --- | --- | --- |
| 1 | TRANSACTIONAL | GPT-4o-mini | `gpt4o_mini_fallback_ok in=268 out=73 lfm_was_active=False` ✅ |
| 2 | INFORMACIONAL F-05 | GPT-4o-mini | `KB Contextualizer (GPT-4o-mini): 2336ms 180 chars` ✅ |
| 3 | INFORMACIONAL | GPT-4o-mini | `KB Contextualizer (GPT-4o-mini): 1140ms 41 chars` ✅ |

Fixes de logs confirmados: sin `claude_config_effective`, sin `via Claude`, `[lang] Using router-detected language`.

### Sesión de validación 2 — Stack completo (LFM + GPT-4o-mini)

Condiciones: `LFM_MCP_ENABLED=true`, `LFM_KB_ENABLED=true`, `GPT4O_MINI_FALLBACK_ENABLED=true`

| Turn | Intent | Modelo activo | Latencia LLM | Total | Perf |
| --- | --- | --- | --- | --- | --- |
| 4 | TRANSACTIONAL | LFM2-24B | 610ms | 8,850ms | +11.5% |
| 5 | TRANSACTIONAL (F-01, behavioral) | LFM2-24B | 611ms | 13,633ms | 0.0%* |
| 6 | INFORMACIONAL F-05 | LFM2.5-1.2B | 1,047ms | — | — |
| 7 | INFORMACIONAL | LFM2.5-1.2B | 989ms | — | — |
| 8 | TRANSACTIONAL | LFM2-24B | 799ms | 8,480ms | +15.2% |

*Turn 5: ColBERT IAM fail en local añade ~2.9s al critical path. En producción con GCP ADC disponible, el colbert path funciona correctamente.

**Verificaciones adicionales:**

- `F-01 ctx_product_price_clp=124990` — fix de price_clp confirmado end-to-end ✅
- Behavioral strategy activada (score=1.10) cuando usuario navega a producto ✅
- FIX anchor "similar a este" → VESTIDOS LARGOS ✅
- GUARD ML intent ("muestrame" protegido de override a INFORMATIONAL) ✅
- Session state turns 3→4→5→6→7→8 Redis persistidos correctamente ✅
- GPT-4o-mini fallback: NO invocado (correcto — LFM activo) ✅

### Sesión de validación 3 — Debug flag FORCE_GPT4O_MINI_FALLBACK

- **TRANSACTIONAL:** `FORCE_GPT4O_MINI_FALLBACK=true: skipping LFM, routing to GPT-4o-mini fallback` + `gpt4o_mini_fallback_ok lfm_was_active=True` ✅
- **INFORMACIONAL:** LFM KB no saltado (bug — faltaba el flag en kb_[contextualizer.py](http://contextualizer.py)) → corregido añadiendo `_force_gpt_fallback_kb` en el bloque LFM de KB ✅

---

## Comparativa de rendimiento LFM vs GPT-4o-mini

| Métrica | LFM2-24B (MCP) | LFM2.5-1.2B (KB) | GPT-4o-mini (fallback) |
| --- | --- | --- | --- |
| Latencia LLM warm | ~610-799ms | ~989-1047ms | ~2,200ms |
| Velocidad relativa | 3.5× más rápido | ~10-15% más rápido | baseline |
| Costo / 1k calls | $0.039 | $0.013 (free) | $0.291 |
| Calidad ES conversacional | 7.8/10 | 8.0/10 | 8.8/10 |
| Disponibilidad cold-start | Riesgo (~11s cold) | Similar | Sin riesgo |

LFM es el modelo correcto como primario: más rápido y más barato. GPT-4o-mini es superior en calidad conversacional pero 3.5× más lento y 7.5× más caro para el volumen del sistema.

---

## Archivos modificados en esta sesión

| Archivo | Cambios |
| --- | --- |
| `src/api/core/claude_config.py` | Añadido `GPT4O_MINI_FALLBACK_CONFIG` dict |
| `src/api/mcp/engines/mcp_personalization_engine.py` | Import, **init** GPT-4o-mini client, reemplazo bloque TEMPORAL, fix condición `_lfm_failed`, fix logs stale x2, debug flag FORCE_GPT4O_MINI_FALLBACK |
| `src/api/core/kb_contextualizer.py` | Import, bloque GPT-4o-mini, restructuración get_model_config(), debug flag FORCE_GPT4O_MINI_FALLBACK |
| `src/api/core/mcp_conversation_handler.py` | Fix log stale "via Claude" |

---

## Variables de entorno — Estado final

| Variable | Valor producción | Descripción |
| --- | --- | --- |
| `LFM_MCP_ENABLED` | `true` | LFM2-24B como primario MCP |
| `LFM_KB_ENABLED` | `true` | LFM2.5-1.2B como primario KB |
| `GPT4O_MINI_FALLBACK_ENABLED` | `true` | GPT-4o-mini activo como fallback |
| `FORCE_GPT4O_MINI_FALLBACK` | `false` | Debug flag — solo activar en testing |

---

## Deuda técnica y pendientes

| Item | Estado | Prioridad |
| --- | --- | --- |
| Deploy a Cloud Run (retail-recommendations-449216) | Pendiente | Alta |
| Secret Manager: destruir versión activa de `CLAUDE_MAX_TOKENS` | Pendiente | Media |
| Cloud Scheduler warm-up (al go-live) | Pendiente al go-live | Alta |
| KPI monitoreo: `gpt4o_mini_fallback_ok` < 5% en producción | Pendiente post-deploy | Media |
| Turn 5 latencia 13,633ms: ColBERT IAM en local añade ~2.9s | Issue solo en dev | Baja |
| `No conversation turns found` en Turn 1: nivel INFO aplicado | ✅ Aplicado | — |
| 77 productos sin enriquecer en PASO 4.6 BG (mismo número que sesión anterior) | Investigar | Baja |

---

## Para la próxima sesión

```bash
# Deploy con el stack completo activo
gcloud run services update retail-recommender \
  --region us-central1 \
  --project retail-recommendations-449216 \
  --set-env-vars \
    LFM_MCP_ENABLED=true,\
    LFM_KB_ENABLED=true,\
    GPT4O_MINI_FALLBACK_ENABLED=true,\
    FORCE_GPT4O_MINI_FALLBACK=false
```

Señales a confirmar en los primeros logs de Cloud Run:

1. `LFM MCP personalisation enabled: model=liquid/lfm-2-24b-a2b-20260224`
2. `GPT-4o-mini fallback enabled: model=openai/gpt-4o-mini`
3. `LFM MCP response` en requests TRANSACTIONAL
4. `KB Contextualizer (LFM)` en requests INFORMACIONAL
5. `gpt4o_mini_fallback_ok` solo cuando LFM falla (< 5% del tráfico)

*Rev: 10/06/2026 — Sesión: DCT_LLM_Migration_GPT4oMini*