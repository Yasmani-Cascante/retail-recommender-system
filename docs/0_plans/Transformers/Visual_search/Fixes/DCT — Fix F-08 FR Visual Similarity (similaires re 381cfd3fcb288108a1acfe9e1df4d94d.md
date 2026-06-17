# DCT — Fix F-08 FR Visual Similarity (similaires regex) — 16/06/2026

# Estado al cierre

Dos bugs identificados y corregidos que bloqueaban toda la cadena F-08 (A y C) para usuarios con queries en francés.

---

## Diagnóstico de producción

### Bug A — Intent detection: "Voir des produits similaires" → INFORMATIONAL

Evidencia en logs (Turn 16, 10:50:31):

```
⚠️ No clear pattern match, defaulting to TRANSACTIONAL
ML fallback: intent=INFORMATIONAL confidence=0.592 (rule-based was 0.500)
ML changed intent → informational, sub_intent=unknown
miniml: label=informational/product_material sim=0.495  ← sub-intent incorrecto!
Detected Intent: INFORMATIONAL (method: ml_fallback, confidence: 0.59)
→ KB response → recommendations_provided: []
```

Turnos afectados: T10 ("Voir des articles similaires"), T12, T16 ("Voir des produits similaires") → todos con 0 recomendaciones.

**Root cause:**

- `similar(?:es)?` matchea ES/EN pero NO francés: "similaires" = s-i-m-i-l-a-**i**-r-e-s (letra 6 = 'i') vs "similares" = s-i-m-i-l-a-**r**-e-s (letra 6 = 'r'). Diferencia de UN carácter.
- Sin patrón rule-based: GUARD no activa → ML override a INFORMATIONAL libre.
- `_detected_method = "ml_fallback"` → `_is_multilang_informational = True` → threshold baja a 0.5 → 0.592 >= 0.5 → KB path.

### Bug B — `_is_visual_similarity_query` siempre False para "similaires"

El mismo regex roto bloqueaba F-08A (Turn 1) y F-08C (Turn 2+) para TODA query FR de similitud. Turnos T15, T18, T19 ("Montrez-moi des produits similaires à celui-ci") eran TRANSACTIONAL vía "montrez" pero caían a `smart_fallback` en lugar de FAISS visual.

---

## Fixes aplicados

### Fix A — `src/api/core/intent_detection.py`

Añadida nueva línea en `TRANSACTIONAL_PATTERNS[PRODUCT_SEARCH]["keywords"]`:

```python
# FIX (16/06/2026 — FR visual similarity):
r"\b(similaires?|simil[ei]\w*)\b",   # FR: similaire/similaires · IT: simile/simili
```

Efecto:

- "Voir des produits similaires" → "similaires" matchea → rule score=0.5 → GUARD activo → TRANSACTIONAL
- ML ya no puede hacer override a INFORMATIONAL
- Log esperado: `✅ Detected TRANSACTIONAL: product_search (confidence: 0.50)` con `patterns=['similaires?']`

### Fix B — `src/api/core/mcp_conversation_handler.py`

Expandido `_F08_VISUAL_SIMILARITY_RE`:

```python
# ANTES (roto para FR/IT):
_F08_VISUAL_SIMILARITY_RE = re.compile(
    r'\b(similar(?:es)?|parecido[sa]?|como.*este|como.*esta|like.*this)\b',
    re.IGNORECASE,
)

# DESPUÉS (cubre ES/EN/FR/IT):
_F08_VISUAL_SIMILARITY_RE = re.compile(
    r'\b('
    r'similar(?:es)?'      # ES/EN
    r'|similaires?'        # FR: similaire, similaires
    r'|simil[ei]\w*'       # IT: simile, simili
    r'|parecido[sa]?'      # ES
    r'|como\s+este'
    r'|como\s+esta'
    r'|like\s+this'        # EN
    r')',
    re.IGNORECASE,
)
```

Efecto: F-08A y F-08C se activan para queries FR con "similaires".

---

## Logs esperados después del deploy

### "Voir des produits similaires" en página de VESTIDOS CORTOS (Turn 2+):

```
✅ Detected TRANSACTIONAL: product_search (confidence: 0.50)
   Reasoning: Rule-based TRANSACTIONAL protected from ML override
F-08C category expansion: 'VESTIDOS CORTOS' -> ['VESTIDOS CORTOS', 'VESTIDOS LARGOS', 'VESTIDOS MIDIS'] (3 types from parent group)
F-08C visual_diversification: 8 productos (pool=50, cats=['VESTIDOS CORTOS', ...], candidates=N)
```

### "Montrez-moi des produits similaires" en página de AROS (Turn 2+):

```
✅ Detected TRANSACTIONAL: product_search (confidence: 0.50)  [rule score=1.0: similaires+montrez]
F-08C category expansion: 'AROS' -> ['AROS', 'COLLARES', 'BRAZALETES', 'CLUTCH', ...] (8 types from parent group)
F-08C visual_diversification: 8 productos (pool=50, cats=['AROS', ...], candidates=N)
```

---

## Archivos modificados

| Archivo | Líneas | Cambio |
| --- | --- | --- |
| `src/api/core/intent_detection.py` | +12 líneas | Nueva regex `similaires?\ |
| `src/api/core/mcp_conversation_handler.py` | +23 líneas | `_F08_VISUAL_SIMILARITY_RE` expandido con FR/IT |

---

## Cadena de bugs descubierta

```
ChatWidget FR → query "Voir des produits similaires"
    ↓ intent_detection.py: "similaires" ≠ "similares" → sin match
    ↓ GUARD inactivo → ML override a INFORMATIONAL
    ↓ KB response, 0 productos  ← Bug A

ChatWidget FR → query "Montrez-moi des produits similaires"
    ↓ intent_detection.py: "montrez" matchea → TRANSACTIONAL
    ↓ _is_visual_similarity_query: "similaires" ≠ "similares" → False
    ↓ F-08C no activa → smart_fallback en lugar de FAISS  ← Bug B
```

Amplitud del impacto: TODOS los usuarios con browser FR afectados. Queries ES ("Recoméndame productos similares a este") funcionaban porque "similares" sí matchea `similar(?:es)?`.

---

## Aprendizajes

**Un carácter de diferencia entre idiomas puede romper todo el pipeline.** "similaires" (FR) vs "similares" (ES) solo difieren en posición 6: 'i' vs 'r'. Este tipo de diferencia es invisible en un code review rápido pero tiene impacto total en el usuario.

**El patrón `_F08_VISUAL_SIMILARITY_RE` gatea tanto F-08A (Turn 1) como F-08C (Turn 2+).** Una sola regex en la línea 50 del handler controla ambas fases. Al añadir un idioma nuevo al widget, también hay que actualizar esta regex.

**Regla de extensión:** Cada vez que se añade un idioma a ChatWidget `_SIMILAR_QUERIES`, hay que actualizar en paralelo:

1. `intent_detection.py` TRANSACTIONAL keywords (para GUARD)
2. `mcp_conversation_handler.py` `_F08_VISUAL_SIMILARITY_RE` (para F-08A/C)