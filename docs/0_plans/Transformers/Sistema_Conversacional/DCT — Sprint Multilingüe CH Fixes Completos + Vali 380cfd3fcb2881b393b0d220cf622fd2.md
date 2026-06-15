# DCT — Sprint Multilingüe CH: Fixes Completos + Validación — 15/06/2026

Sesión de bugfix multilingüe para mercado CH. 8 fixes aplicados y validados en 5 turns de prueba. Sistema estable, todos los casos objetivo resueltos.

---

## Resultados de validación (5 turns, sesión nueva)

| Turn | Query | Resultado | Estado |
| --- | --- | --- | --- |
| T1 | Montrez-moi des robes courtes | ['VESTIDOS CORTOS'] × 8 — 72-119 CHF | ✅ Fix 1 validado |
| T2 | Quels accessoires vont avec cette robe? | ['AROS','CLUTCH','CINTURONES'] — 14-33 CHF | ✅ Fix 2 validado |
| T3 | Montrez-moi des produits similaires à celui-ci (AROS) | ['AROS','COLLARES'] — 9-18 CHF | ✅ Correcto |
| T4 | Est-il disponible dans d'autres tailles? | 📚 KB informational — out_of_stock template | ✅ Fix 3 validado |
| T5 | Montrez-moi des robes longues | ['VESTIDOS LARGOS'] × 8 — 79-209 CHF | ✅ Bonus validado |

---

## Fixes de sesiones anteriores validados hoy

### Fix 1 — VESTIDOS CORTOS/LARGOS/MIDIS keywords FR/DE/IT

**Archivo:** `src/recommenders/improved_fallback_exclude_seen.py`

**Root cause:** VESTIDOS CORTOS solo tenía keywords ES/EN. "courtes" no matcheaba ninguna categoría concreta → Change 1 no podía suprimir hermanas → distribución 3:3:2.

**Fix:** Keywords FR/DE/IT con 2+ palabras (specificity=2 > 0.5) a VESTIDOS CORTOS, LARGOS y MIDIS:

- VESTIDOS CORTOS: "robe courte", "robes courtes", "mini robe", "kurzes kleid", "vestito corto"
- VESTIDOS LARGOS: "robe longue", "robes longues", "robe maxi", "langes kleid", "vestito lungo", "abito lungo"
- VESTIDOS MIDIS: "robe mi-longue", "robe midi", "midi kleid", "vestito midi"

**Mecánica:** "robes courtes" (specificity=2) → VESTIDOS CORTOS concrete=2. Change 1: _concrete_high=[VESTIDOS CORTOS] → suprime VESTIDOS LARGOS/MIDIS (specificity=0.5). Resultado: ['VESTIDOS CORTOS'] única categoría.

### Fix 2 — outfit_completion: suprimir user_query en smart_fallback

**Archivo:** `src/api/core/mcp_conversation_handler.py`

**Root cause:** F-08B.2 ponía user_events=[AROS,COLLARES,CLUTCH] correctamente, pero smart_fallback(user_query="...cette robe...") activaba PRIORIDAD 1 que detectaba "robe" → VESTIDOS → sobreescribía.

**Fix:** Cuando _b08_sub_intent=="outfit_completion" y source=="outfit_complement_f08b2", se pasa user_query=None → PRIORIDAD 1 bypassed → PRIORIDAD 2 usa user_events=[AROS,COLLARES,...]

**Logs validación:**

```
F-08B.2 outfit_completion: overriding user_events for type='VESTIDOS CORTOS': ['AROS', 'CLUTCH', 'CINTURONES', 'BRAZALETES']
F-08B.2 query suppressed: outfit_complement_f08b2 activo
Preferred categories: ['AROS', 'CLUTCH', 'CINTURONES']
Price sample: [14.0, 14.0, 18.0, 33.0, 14.0, 14.0, 27.0, 12.0]
```

### Fix 3 — _detected_method: capturar antes de conversión a intent_result

**Archivo:** `src/api/core/mcp_conversation_handler.py`

**Root cause:** `getattr(intent_result, "method", "")` siempre `""` porque `IntentDetectionResult` (de `to_intent_detection_result()`) no tiene atributo `method`. Esto hacía `_is_multilang_informational = False` → threshold permanecía en 0.7 → 0.67 < 0.7 → productos.

**Fix:** `_detected_method = hybrid_result.method_used` capturado ANTES de la conversión. Con `_detected_method = "miniml_semantic"`, la condición `_is_multilang_informational = True` → threshold=0.5 → 0.67 >= 0.5 → KB.

**Logs validación:**

```
miniml_predict: label=informational/product_availability conf=0.666
Detected Intent: IntentType.INFORMATIONAL (method: miniml_semantic, confidence: 0.67)
📚 INFORMATIONAL intent detected - using Knowledge Base v2
KB out_of_stock template (fr, no LLM called): sizes=S, XS
Handler response type: informational
```

---

## Fixes aplicados en esta sesión (15/06/2026)

### Fix Tooltip — ProductCard.tsx multilingüe

**Archivo:** `src/frontend/src/components/ProductCard.tsx`

**Root cause:** Tooltips de la barra de acciones hardcodeados en español ("Ver productos similares", "Hablar sobre este producto", "Añadir al carrito"). Usuario CH con browser FR veía tooltips en español al hacer hover.

**Fix:** Dict `_ACTION_TOOLTIPS` con ES/FR/DE/IT/EN. Resuelto una vez al load del módulo con `navigator.language`. Los 3 botones usan `title={_T.showSimilar}` etc.

**Cobertura:**

- FR: "Voir des produits similaires" / "Parler de ce produit" / "Ajouter au panier"
- DE: "Ähnliche Produkte" / "Über dieses Produkt sprechen" / "In den Warenkorb"
- IT: "Vedi prodotti simili" / "Parla di questo prodotto" / "Aggiungi al carrello"
- EN: "Show similar products" / "Chat about this item" / "Add to cart"

### Fix EN→FR — language_[detection.py](http://detection.py) patrones EN cortos

**Archivo:** `src/api/utils/language_detection.py`

**Root cause:** "It's available?" tenía EN=0 porque:

1. "available" no estaba en `_EN_PATTERNS`
2. "it" / "its" no estaban en el patrón de function words

Resultado: None → body "fr" → LFM respondía en francés.

**Fix:** Dos adiciones al patrón EN:

- `"it|its"` añadido al patrón de function words existente
- Nueva línea: `r"\b(available|availability|in\s+stock|out\s+of\s+stock)\b"`

**Validación:**

- "It's available?" → EN=2 ("it" + "available") → high-conf → "en" ✅
- "Is it in stock?" → EN=2 ("is" + "it") → high-conf → "en" ✅
- "Quels accessoires vont avec cette robe?" → EN=0 FR=0 → None → body "fr" ✅
- "Montrez-moi des robes courtes" → EN=0 FR=0 → None → body "fr" ✅
- "Est-il disponible dans d'autres tailles?" → FR=4 → high-conf → "fr" ✅

**Nota:** El router (`mcp_router.py`) ya tenía el fix text-first (13/06/2026). El problema subsistente era solo que los patrones EN no cubrían estas queries cortas.

---

## Archivos modificados en esta sesión

| Archivo | Cambio |
| --- | --- |
| `src/frontend/src/components/ProductCard.tsx` | Dict `_ACTION_TOOLTIPS`  • `_navLang`  • `_T` — tooltips multilingüe en 3 botones |
| `src/api/utils/language_detection.py` | "it", "its", "available", "in stock", "out of stock" → `_EN_PATTERNS` |

## Archivos modificados en sesiones anteriores (validados hoy)

| Archivo | Cambio |
| --- | --- |
| `src/recommenders/improved_fallback_exclude_seen.py` | Keywords FR/DE/IT en VESTIDOS CORTOS/LARGOS/MIDIS; keywords FR/DE/IT en ACCESSORIES |
| `src/api/core/mcp_conversation_handler.py` | Fix 2 (query suppression), Fix 3 (_detected_method), Fix F-08B.2 (outfit_complement_map), Fix F-08B.2 (vont avec patterns) |
| `src/api/core/intent_detection.py` | Patrones FR/DE/IT OUTFIT_COMPLETION (qui va avec, vont avec, quelque chose qui, etc.) |

---

## Estado pendiente

| Item | Estado |
| --- | --- |
| Secret Manager: destruir versión activa CLAUDE_MAX_TOKENS | Pendiente |
| Artifact Registry lifecycle policy (keep last 5 images) | Pendiente |
| Cloud Scheduler warm-up al go-live | Pendiente |
| Claude fallback replacement (GPT-4o-mini vía OpenRouter) | Pendiente |
| Gift Card (0.01 CHF) en cold-start diverse fallback | Pendiente — min precio filter en get_diverse_category_products |
| Deploy a Cloud Run con todos los fixes acumulados | Pendiente |

---

## Aprendizajes técnicos clave

**IntentDetectionResult no hereda method:** `to_intent_detection_result()` convierte `HybridResult` pero descarta `method_used`. Siempre capturar el método ANTES de convertir.

**Change 1 depende de specificity:** El filtro de supresión de hermanas solo activa cuando specificity > 0.5. Un keyword de 1 palabra (concrete) da specificity=1 > 0.5. Un keyword de 2 palabras da specificity=2. La expansión del padre siempre da specificity=0.5. Por eso los keywords FR deben ser de 2+ palabras ("robe courte") para que Change 1 funcione.

**PRIORIDAD 1 en smart_fallback anula F-08B.2:** Cuando outfit_completion pone user_events con accesorios, PRIORIDAD 1 puede sobrescribir si la query contiene palabras de vestidos ("robe"). La solución es pasar user_query=None para forzar PRIORIDAD 2.

**Lax mode en language detection:** score=1, other=0 → acepta el idioma sin threshold de 2. Esto permite detectar "Is it in stock?" (EN=1 de "Is") como inglés aunque sea corto.