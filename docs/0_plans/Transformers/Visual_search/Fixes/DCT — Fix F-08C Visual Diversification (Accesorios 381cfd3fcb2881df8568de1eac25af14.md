# DCT — Fix F-08C Visual Diversification (Accesorios) — 16/06/2026

# Fix F-08C — Visual Diversification para Accesorios

**Fecha:** 16/06/2026  

**Archivo modificado:** `src/api/core/mcp_conversation_handler.py`  

**Revisión anterior:** `retail-recommender-00211-p29`

---

## Contexto

Validación de producción completada (4 turns, sesión nueva). Todos los fixes anteriores confirmados. Gap identificado: F-08C visual_diversification no activa cuando el producto actual es un accesorio (AROS, COLLARES, CLUTCH, etc.).

---

## Root cause

El bloque F-08C construye un pool visual con FAISS (`search_by_product_id`, top_k=50) y lo filtra por categoría antes de devolver resultados. El problema estaba en el fallback de categoría:

```python
# ANTES (problemático):
if not _c08_query_cats:
    _c08_ctx_type = mcp_context.current_product_context.get("product_type", "")
    if _c08_ctx_type:
        _c08_query_cats = [_c08_ctx_type]   # ← solo "AROS"
```

**Por qué falla para AROS:**

- FAISS devuelve 50 vecinos visuales de un AROS: mezcla de AROS + COLLARES + BRAZALETES + CLUTCH (todos visualmente similares al accesorio pequeño).
- Filtro `product_type.upper() in ["AROS"]` → muy pocos pasan (solo los clasificados exactamente como AROS).
- `len(_c08_candidates) < 8` → F-08C no activa → cae a smart_fallback.

**Por qué funciona para VESTIDOS CORTOS:**

- FAISS devuelve muchos VESTIDOS CORTOS entre los 50 vecinos (catálogo ~300+ vestidos cortos).
- `len(_c08_candidates) >= 8` → F-08C activa correctamente.

---

## Fix aplicado

Bloque `if not _c08_query_cats` expandido para incluir los hermanos del mismo padre categorial usando `get_parent_categories()` (ya importado en scope en la sección de diversificación de arriba):

```python
# DESPUÉS (fix):
if not _c08_query_cats:
    _c08_ctx_type = mcp_context.current_product_context.get("product_type", "")
    if _c08_ctx_type:
        try:
            _c08_parent_map = get_parent_categories()
            _c08_siblings = next(
                (
                    subs
                    for subs in _c08_parent_map.values()
                    if _c08_ctx_type.upper() in [s.upper() for s in subs]
                ),
                None,
            )
            _c08_query_cats = _c08_siblings if _c08_siblings else [_c08_ctx_type]
            if _c08_siblings:
                logger.info(
                    f"F-08C category expansion: "
                    f"'{_c08_ctx_type}' -> {_c08_query_cats} "
                    f"({len(_c08_query_cats)} types from parent group)"
                )
        except Exception as _c08_expand_err:
            _c08_query_cats = [_c08_ctx_type]   # fallback al tipo exacto
            logger.debug(f"F-08C category expansion failed (using exact type): {_c08_expand_err}")
```

---

## Efecto del fix

| Producto actual | Antes | Después |
| --- | --- | --- |
| AROS | `["AROS"]` → pocos candidatos → F-08C no activa | `["AROS", "COLLARES", "BRAZALETES", "CLUTCH", "CINTURONES", "CARTERAS", "TOCADOS", "BRALETTES"]` → suficientes candidatos → F-08C activa |
| VESTIDOS CORTOS | `["VESTIDOS CORTOS"]` → suficientes → activa ✅ | `["VESTIDOS CORTOS", "VESTIDOS LARGOS", "VESTIDOS MIDIS"]` → sigue funcionando ✅ |
| Categoría sin padre | `["TIPO"]` → comportamiento anterior | `["TIPO"]` → fallback idéntico al anterior ✅ |

**Coherencia semántica preservada:** todos los hermanos pertenecen al mismo grupo visual (complementos pequeños, vestidos, etc.). No se cruzan categorías no relacionadas.

---

## Log esperado en producción

Cuando F-08C activa para AROS:

```
F-08C category expansion: 'AROS' -> ['AROS', 'COLLARES', 'BRAZALETES', 'CLUTCH', 'CINTURONES', 'CARTERAS', 'TOCADOS', 'BRALETTES'] (8 types from parent group)
F-08C visual_diversification: 8 productos (pool=50, cats=['AROS', 'COLLARES', ...], candidates=N)
```

---

## Validación necesaria

1. Abrir página de producto AROS en el widget
2. Hacer click en "Voir des produits similaires" (action bar) → Turn 1: search-by-id + similitud visual AROS
3. Volver a hacer click en "Voir des produits similaires" → Turn 2: debe aparecer `F-08C category expansion` y `F-08C visual_diversification` en logs
4. Confirmar precios en rango de accesorios (9-36 CHF), no vestidos (70-209 CHF)

**Condición de éxito:** `len(_c08_candidates) >= 8` → log `F-08C visual_diversification: 8 productos`

---

## Notas técnicas

- `get_parent_categories()` ya estaba importado en el mismo `from ... import` block de la sección de diversificación superior — no se añadió ningún import nuevo.
- El `try/except` garantiza degradación graceful: si falla la expansión por cualquier razón, se usa `[_c08_ctx_type]` (comportamiento anterior).
- El fix no modifica la condición de entrada de F-08C ni el pool FAISS — solo amplía el filtro de categorías.
- `next(..., None)` evita `StopIteration` cuando la categoría no tiene padre en el mapa.