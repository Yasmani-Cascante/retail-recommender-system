## Plan de Implementación: Indexar Imagen de Detalle para Accesorios

**Fecha:** 03/07/2026
**Relacionado:** `DCT — Propagación Fix F-08C → F-08 Fase A (Category Expansion Turn 1) — 03/07/2026` (Notion)
**Complementa a:** el fix de expansión de categorías ya aplicado (filtra mejor lo que hay); este plan mejora *lo que hay* desde el origen.

---

### Hallazgos clave de la investigación

**1. El array `images[]` completo de Shopify ya viaja por el pipeline — solo se descarta en un punto.**

`tfidf_recommender.py::_normalize_product_price()` lee `product.get("images")` (la lista completa que devuelve la API de Shopify) pero solo aplana `images[0]` a un campo `image_url` de nivel raíz. El resto del array se preserva en el dict del producto (por el spread `{**product, ...}`), pero **ningún consumidor downstream lo usa** — todos leen únicamente `image_url`.

```python
# tfidf_recommender.py — estado actual
image_url = product.get("image_url") or product.get("imageUrl")
if not image_url:
    images = product.get("images") or []
    if images and isinstance(images, list):
        first = images[0]                    # ← SOLO la primera imagen
        ...
        image_url = first.get("src") or ...
```

**2. Un solo punto de choke alimenta los 3 caminos de indexación al embedding-service.**

```
tfidf_recommender.product_data (image_url = images[0])
        │
        ├─→ visual_index_sync_job.py (OPM-1, incremental cada 6h)
        ├─→ visual_search_router.py :: trigger_visual_indexation (rebuild completo)
        └─→ visual_search_router.py :: trigger_incremental_indexation (/index/update)
                        │
                        ▼
        embedding-service recibe {"id", "title", "image_url", "product_type"}
        y descarga exactamente esa URL para generar el embedding FashionSigLIP
```

Ningún código en `embedding-service/` necesita saber que existe un concepto de "imagen de detalle" — solo descarga la URL que se le manda. Esto significa que la solución completa vive en el monolito, sin tocar el embedding-service.

**3. La categorización de "accesorio pequeño" ya existe en el código — no hay que inventarla.**

`visual_retriever.py::SHOPIFY_TYPE_TO_OUTFIT_CATEGORY` ya mapea exactamente los 9 tipos de la colección Complementos de Shopify (confirmado contra el screenshot de Shopify Admin del 03/07/2026) a las categorías `accessory` y `bag`:

```python
"accessory": ["BRAZALETE", "BRAZALETES", "ALAS DE NOVIA", "AROMAS", "AROS",
              "COLLARES", "CINTURONES", "TOCADOS"]
"bag":       ["CARTERAS", "CLUTCH"]
```

Reutilizamos este mismo set como el trigger de "preferir imagen de detalle" — sin duplicar la lista de categorías en un segundo lugar del código.

**4. No tocar `image_url` — crear un campo nuevo, separado.**

`image_url` se usa también para las tarjetas de producto en el widget de chat (frontend). Si sustituyéramos `image_url` directamente por la imagen de detalle (ej. un primer plano extremo de un arete en una oreja), el grid de "Recomendado para ti" mostraría fotos inconsistentes con el resto del catálogo — el usuario espera la foto de cuerpo completo como miniatura de producto, no un macro shot. La solución usa un campo **nuevo y separado**, consumido únicamente por los 3 endpoints de indexación — cero impacto en frontend, cero impacto en cualquier otro consumidor de `image_url`.

---

### Arquitectura de la solución

```
_normalize_product_price() [tfidf_recommender.py]
  │
  ├─ image_url             = images[0]["src"]           (SIN CAMBIOS — frontend, UI)
  │
  └─ visual_index_image_url = (NUEVO CAMPO)
        si product_type in ACCESSORY_DETAIL_TYPES
           y len(images) >= 2:
              → images[1]["src"]   (imagen de detalle)
        si no:
              → image_url          (mismo comportamiento actual, sin cambios)

Los 3 endpoints de indexación leen:
  image_url_para_indexar = p.get('visual_index_image_url') or p.get('image_url', '')
```

**Por qué "swap completo" y no "promedio de embeddings" (image[0] + image[1]):**
Promediar el embedding de la foto de cuerpo completo con el de detalle diluiría la señal — seguiría estando "medio dominado" por el vestido. El objetivo es que el vector del producto se aleje lo más posible de "vestido" y se acerque a "arete/accesorio" — un swap completo a la imagen de detalle es más directo y más fácil de razonar. Si tras la validación (Fase 3) el swap resulta insuficiente, promediar es una mejora incremental a considerar después, no el punto de partida.

---

### Fases de implementación

```
FASE 0  Auditoría de la hipótesis          [~30 min]
FASE 1  Flattening del campo nuevo          [~30 min]
FASE 2  Actualizar los 3 call sites         [~20 min]
FASE 3  Rebuild completo + validación       [~40 min, incluye espera]
```

---

### FASE 0 — Auditoría de la hipótesis (antes de tocar código)

**Por qué esta fase existe:** Yasmani confirmó manualmente que el patrón "segunda foto = imagen de detalle" se cumple para la categoría **AROS** específicamente. Antes de aplicar el mismo heurístico a las 8 categorías restantes (BRAZALETE(S), ALAS DE NOVIA, AROMAS, COLLARES, CINTURONES, TOCADOS, CARTERAS, CLUTCH), hay que confirmar que el patrón se sostiene — no todas las categorías de Complementos necesariamente siguen la misma convención fotográfica.

**Script de auditoría** (ejecutar localmente, sin necesidad de deploy):

```python
# audit_accessory_images.py
# Ejecutar desde la raíz del repo: python audit_accessory_images.py

import pickle
from collections import defaultdict

ACCESSORY_DETAIL_TYPES = {
    "BRAZALETE", "BRAZALETES", "ALAS DE NOVIA", "AROMAS", "AROS",
    "COLLARES", "CINTURONES", "TOCADOS", "CARTERAS", "CLUTCH",
}

with open("data/tfidf_model.pkl", "rb") as f:
    data = pickle.load(f)
products = data["product_data"]

by_type = defaultdict(list)
for p in products:
    ptype = str(p.get("product_type", "")).upper().strip()
    if ptype in ACCESSORY_DETAIL_TYPES:
        images = p.get("images") or []
        by_type[ptype].append({
            "title": p.get("title", ""),
            "n_images": len(images),
            "image_0": images[0].get("src") if images and len(images) > 0 else None,
            "image_1": images[1].get("src") if images and len(images) > 1 else None,
        })

for ptype, items in sorted(by_type.items()):
    n_with_2plus = sum(1 for i in items if i["n_images"] >= 2)
    print(f"\n=== {ptype} ({len(items)} productos, {n_with_2plus} con ≥2 imágenes) ===")
    for item in items[:3]:  # muestra de 3 por tipo
        print(f"  {item['title']}")
        print(f"    [0] {item['image_0']}")
        print(f"    [1] {item['image_1']}")
```

**Criterio de éxito de Fase 0:** revisar visualmente (abrir las URLs impresas) una muestra de 3 productos por cada una de las 9 categorías. Confirmar que `images[1]` es consistentemente más representativo del accesorio que `images[0]` en al menos 7 de las 9 categorías. Categorías donde el patrón no se sostenga se excluyen de `ACCESSORY_DETAIL_TYPES` en la Fase 1 (no se fuerza el heurístico donde no aplica).

**Nota:** si alguna categoría tiene productos con solo 1 imagen (`n_images < 2`), el fallback a `image_url` (comportamiento actual) ya cubre ese caso sin necesidad de lógica adicional.
sxcasdfv
---

### FASE 1 — Flattening del campo nuevo en `tfidf_recommender.py`

**Archivo a modificar:** `src/recommenders/tfidf_recommender.py`, método `_normalize_product_price()`.

```python
# Set de categorías confirmado en Fase 0 (puede ser subset de las 9 originales
# si la auditoría descarta alguna categoría).
ACCESSORY_DETAIL_TYPES = {
    "BRAZALETE", "BRAZALETES", "ALAS DE NOVIA", "AROMAS", "AROS",
    "COLLARES", "CINTURONES", "TOCADOS", "CARTERAS", "CLUTCH",
}

# ... dentro de _normalize_product_price(), después de calcular image_url ...

# NUEVO (03/07/2026): imagen de detalle para indexación visual de accesorios.
#
# Por qué: el embedding visual (FashionSigLIP) de productos de accesorios
# pequeños (aros, collares, etc.) queda dominado por la foto de cuerpo
# completo (vestido/modelo) en vez del accesorio mismo — confirmado con
# evidencia real: pool de 30 vecinos visuales de un producto AROS solo
# tenía 1 vecino AROS, 29 vestidos (sesión 03/07/2026).
#
# Este campo es SEPARADO de image_url (que sigue apuntando a images[0]
# para todo lo demás — frontend, tarjetas de producto). Solo lo consumen
# los 3 endpoints de indexación al embedding-service.
#
# Fallback: si el producto no es de categoría accesorio, o solo tiene 1
# imagen, visual_index_image_url = image_url (comportamiento actual,
# sin cambios).
product_type_upper = str(product.get("product_type", "")).upper().strip()
visual_index_image_url = image_url  # default: mismo que siempre

if product_type_upper in ACCESSORY_DETAIL_TYPES:
    images = product.get("images") or []
    if images and isinstance(images, list) and len(images) >= 2:
        second = images[1]
        detail_url = None
        if isinstance(second, str):
            detail_url = second
        elif isinstance(second, dict):
            detail_url = second.get("src") or second.get("url") or second.get("originalSrc")
        if detail_url:
            visual_index_image_url = detail_url

# ... en el return final, añadir el campo nuevo junto a los existentes:
return {
    **product,
    "price": price,
    **({"image_url": image_url} if image_url else {}),
    **({"visual_index_image_url": visual_index_image_url} if visual_index_image_url else {}),
}
```

---

### FASE 2 — Actualizar los 3 call sites

**2.1 — `src/api/services/visual_index_sync_job.py`** (OPM-1, reconciliación cada 6h)

```python
# ANTES:
products_with_image = [
    {
        "id": str(p.get("id", "")),
        "title": str(p.get("title", "")),
        "image_url": str(p.get("image_url", "")),
        "product_type": str(p.get("product_type", "")),
    }
    for p in product_catalog
    if p.get("image_url") and str(p.get("image_url", "")).startswith("http")
]

# DESPUÉS — único cambio: usar visual_index_image_url si existe
products_with_image = [
    {
        "id": str(p.get("id", "")),
        "title": str(p.get("title", "")),
        "image_url": str(p.get("visual_index_image_url") or p.get("image_url", "")),
        "product_type": str(p.get("product_type", "")),
    }
    for p in product_catalog
    if p.get("image_url") and str(p.get("image_url", "")).startswith("http")
    # nota: el filtro de existencia sigue usando image_url (garantiza que el
    # producto tiene AL MENOS una imagen válida); el campo que se ENVÍA usa
    # visual_index_image_url si está disponible.
]
```

**2.2 — `src/api/routers/visual_search_router.py :: trigger_visual_indexation`** (rebuild completo)

```python
# Mismo patrón — cambiar solo la línea de "image_url" en el dict:
products_for_indexation = [
    {
        'id':           str(p.get('id', '')),
        'title':        p.get('title', ''),
        'image_url':    str(p.get('visual_index_image_url') or p.get('image_url', '')),
        'product_type': p.get('product_type', ''),
    }
    for p in tfidf_recommender.product_data
    if p.get('image_url')
]
```

**2.3 — `src/api/routers/visual_search_router.py :: trigger_incremental_indexation`** (`/index/update`)

Mismo cambio que 2.2, aplicado al bloque `all_products` de esa función.

**Nota importante:** el campo que se envía al embedding-service se sigue llamando `"image_url"` en el payload — el embedding-service no necesita saber nada sobre la existencia de `visual_index_image_url`. Solo cambia CUÁL URL se le manda bajo esa misma clave, en el monolito, antes de enviar el request.

---

### FASE 3 — Rebuild completo y validación

**Por qué rebuild completo, no incremental:** los productos de accesorios YA están indexados con la imagen equivocada (`images[0]`). El endpoint incremental (`/index/update`) solo añade productos que faltan — no re-procesa los que ya existen en el índice FAISS. Hace falta el rebuild completo (`POST /v1/mcp/visual-search/index`) para que los ~700 productos de Complementos se re-descarguen y re-encodeen con la nueva URL.

```bash
curl -X POST \
  -H "X-API-Key: $API_KEY" \
  https://retail-recommender-178362262166.us-central1.run.app/v1/mcp/visual-search/index
```

Tiempo estimado: ~25-30 min (mismo orden de magnitud que el rebuild de S1, ~29 min para 3056 productos completos).

**Validación cuantitativa post-rebuild:**

```python
# validate_accessory_pool.py — ejecutar contra el embedding-service tras el rebuild
import requests

EMBED_URL = "https://retail-embedding-service-178362262166.us-central1.run.app"
TOKEN = "..."  # gcloud auth print-identity-token

# IDs de muestra: 3-5 productos AROS conocidos del catálogo
sample_aros_ids = ["9978624672053", "..."]

for pid in sample_aros_ids:
    resp = requests.get(
        f"{EMBED_URL}/v1/embed/search-by-id",
        params={"product_id": pid, "top_k": 30},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    # Contar cuántos de los 30 vecinos son también accesorios/AROS
    # (requiere cruzar con tfidf_recommender.id_index para obtener product_type)
    print(f"{pid}: {resp.json()}")
```

**Criterio de éxito:** para una muestra de 5 productos AROS, el `pool=30` de vecinos visuales debe contener significativamente más de 1 producto de categoría accesorio (idealmente ≥8, suficiente para que ni siquiera haga falta la expansión de categorías hermanas del fix anterior).

**Validación funcional (repetir T3 exacta):**
1. Sesión nueva de chat, primera consulta: "muéstrame artículos similares" sobre un producto AROS.
2. Confirmar en logs `F-08 visual_similarity: ... filtered=N` con `N` sustancialmente mayor a 1.
3. Confirmar visualmente en el widget que los resultados son mayoritariamente accesorios, no vestidos.

---

### Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El heurístico "images[1] = detalle" no se sostiene en todas las categorías | Fase 0 audita las 9 categorías antes de tocar código; categorías que no cumplan se excluyen del set |
| Rebuild completo compite por CPU con tráfico real (~25-30 min) | Ejecutar en horario de bajo tráfico; el circuit breaker visual ya protege contra saturación durante el rebuild |
| Algún producto de accesorio solo tiene 1 imagen | Fallback automático a `image_url` (comportamiento actual) — sin excepciones ni crashes |
| El swap a `images[1]` empeora accidentalmente algún producto donde `images[0]` YA era representativo | Bajo riesgo — Fase 0 es precisamente la salvaguarda contra esto; adicionalmente, el fix de expansión de categorías hermanas (ya en producción) sigue actuando como red de seguridad aunque el pool de accesorios mejore solo parcialmente |

---

### Fuera de alcance (evaluado y descartado)

**Segmentación de objetos (YOLO/SAM) para recortar la prenda antes de encodar.** Ya evaluado y descartado explícitamente para el caso de outfit search en `Búsqueda_x_Outfit_Plan_de_Implementación_12052026.md` — el razonamiento aplica igual aquí: +100MB RAM, +200ms latencia, modelo adicional que mantener, para resolver algo que ya existe manualmente en el catálogo (una foto de detalle correctamente encuadrada). Se preferiría reconsiderar esto solo si, tras este plan, persistieran productos sin ninguna imagen representativa disponible en su galería.

**Composite Embedding (imagen + texto de categoría) aplicado a `search_by_product_id`.** Técnica ya usada en `search_outfit_by_image()` (Composite Embedding con `alpha`). Podría aplicarse también a la búsqueda de "productos similares" (no solo outfit), como refuerzo adicional. Se deja como mejora complementaria a evaluar en una sesión futura si este plan (indexación de imagen de detalle) no es suficiente por sí solo.

---

### Resumen de archivos a modificar

| Archivo | Cambio |
|---|---|
| `src/recommenders/tfidf_recommender.py` | Nuevo campo `visual_index_image_url` en `_normalize_product_price()` |
| `src/api/services/visual_index_sync_job.py` | Usar `visual_index_image_url` al construir el payload para OPM-1 |
| `src/api/routers/visual_search_router.py` | Usar `visual_index_image_url` en `trigger_visual_indexation` y `trigger_incremental_indexation` |

Cero cambios en `embedding-service/` (main.py, visual_retriever.py) — reciben el mismo formato de payload de siempre.
