
## Plan de Acción F-08 — Discusión detallada

### Lo que la investigación confirma

La infraestructura está production-ready y battle-tested desde el 07/05/2026. Nada en el embedding-service necesita modificarse para la Fase A. Lo que tenemos:

- **FashionSigLIP** vectoriza imágenes en 768 dimensiones entendiendo moda: color, silueta, textura, ocasión — cruzando categorías Shopify
- **`search_by_image(bytes)`** → product_ids por similitud visual — sin filtro de categoría
- **`search_outfit_by_image(bytes, categories, alpha=0.5)`** → `{dress:[...], top:[...], accessory:[...]}` por composite embedding
- **`id_index[pid].image_url`** → lookup O(1) en memoria para la URL de imagen de cualquier producto
- **`category_map`** en FAISS → sabe a qué categoría outfit pertenece cada posición del índice
- **`OutfitPanel`** en el widget React → ya construido, lista para recibir datos del chat

### Las 4 fases explicadas

**Fase A — Similitud visual en Turn 1** (sin modificar embedding-service)

Es el cambio con mejor ratio esfuerzo/impacto. Cuando el usuario está en una página de producto y hace una query con "similar/parecido/como este", el handler hoy llama `hybrid_recommender.get_recommendations(product_id)` → TF-IDF sobre texto. Con Fase A:

```
1. query contiene r'\b(similar(?:es)?|parecido[sa]?|como.*este)\b'  AND  product_ctx existe
2. image_url = tfidf_rec.id_index[product_ctx["id"]].get("image_url")
3. image_bytes = await http_client.get(image_url)   ← ~200ms, async, paralelo con TF-IDF
4. visual_ids  = await colbert.search_by_image(image_bytes, top_k=30)   ← ~435ms
5. filtered    = [pid for pid in visual_ids
                  if id_index[pid]["product_type"].upper() == product_ctx["product_type"].upper()]
6. usar filtered como recomendaciones, fallback a TF-IDF si falla
```

La clave de la paralelización: el CDN fetch (200ms) + FashionSigLIP (435ms) se lanzan como `asyncio.Task` mientras TF-IDF (50ms) ya terminó. El LFM tarda 1.4s. La búsqueda visual completa en ~635ms, dentro del presupuesto de tiempo.

**Fase A.5 — `search_by_product_id` en embedding-service** (0.5 sesión)

El insight más importante: para productos ya en FAISS, su vector ya existe. Un nuevo endpoint `POST /v1/embed/search-by-id` que reciba `product_id`, busque su posición en `id_map`, y devuelva los `top_k` vecinos más cercanos en el índice — sin re-encodear, sin CDN fetch. Latencia: ~50ms en vez de ~635ms. Transforma F-08 de "una operación lenta que paralellizamos" a "prácticamente transparente en latencia".

**Fase B — Outfit completion en el chat** (1-2 sesiones)

Nuevo sub-intent `OUTFIT_COMPLETION` en `intent_detection.py`:

```python
TransactionalSubIntent.OUTFIT_COMPLETION: {
    "keywords": [
        r"\b(complet(?:a|ar|o).*outfit|armar.*look|completar.*look)\b",
        r"\b(combin[ao]|qué.*va.*con|qué.*combina)\b",
        r"\b(complementar|complemento|complementa)\b",
        r"\b(qué.*poner|with.*what|goes.*with)\b",
    ]
}
```

Con product_ctx disponible, el handler llama `search_outfit_by_image(alpha=0.5)` en vez de `smart_fallback`. El resultado (dict por categoría) se convierte en el tipo de respuesta `outfit` → el widget ya tiene `OutfitPanel` que sabe renderizar columnas por categoría. **El frontend no necesita trabajo adicional**.

Nota crítica de S1: **alpha=0.5** (igual peso imagen/texto), no 0.7. Con alpha=0.7 y una imagen de vestido, todas las categorías devuelven vestidos porque el embedding visual domina. Con 0.5, el texto ("accessory", "top", "bag") tiene suficiente peso para diversificar.

**Fase C — Diversificación visual coherente en Turn 2+** (1 sesión, prerrequisito: A.5)

El cambio de mayor impacto a largo plazo. Hoy el Turn 2+ es `random.sample()`. Con Fase C:

```
visual_pool = await colbert.search_by_product_id(product_ctx["id"], top_k=50)
pool_in_category = [pid for pid in visual_pool 
                    if id_index[pid]["product_type"] == target_category]
recommendations = pool_in_category[:8] if pool_in_category else random.sample(...)
```

Cada turn nuevo que pide "más similares" recibe productos visualmente coherentes con el que el usuario está mirando — no productos aleatorios de la misma categoría.

---

### Tabla de decisiones abiertas para discutir

| Decisión | Opción A | Opción B | Recomendación |
|----------|----------|----------|---------------|
| Orden de fases | A → A.5 → B → C | A → B → A.5 → C | A → A.5 → B → C — la latencia de A.5 beneficia a B y C |
| Umbral de activación | Solo "similar/parecido" | Toda query con product_ctx | Solo cuando hay patrón explícito de similitud — menos ruido |
| Categoría en Fase A | Filtrar a misma categoría | Sin filtro (cross-category) | Misma categoría como default; cross-category como opción de query ("vestidos largos similares") |
| Alpha en Fase B | 0.5 | Configurable por categoría | 0.5 general; 0.7 para "outfit completo" donde dominar con imagen es aceptable |
| Paralelización Fase A | Lanzar visual task async | Sequential antes de TF-IDF | Async task — visual completa dentro del presupuesto LFM |

---

### 📚 Learning opportunity

El patrón de **composite embedding** `alpha×img + (1-alpha)×text` que ya usa `search_outfit_by_image` es una técnica de fusión de embeddings multimodal. Con alpha=1 obtienes búsqueda puramente visual (qué se parece físicamente); con alpha=0 obtienes búsqueda semántica textual (qué se llama igual). Los valores intermedios crean un espacio de búsqueda que combina ambas señales. La calibración de alpha es domain-specific: en moda, 0.5 resultó óptimo en producción porque "top que combine con este vestido" requiere tanto que se parezca visualmente (color, estilo) como que sea un "top" (no otro vestido). Esto es directamente análogo al trade-off precision/recall en clasificación.

---
