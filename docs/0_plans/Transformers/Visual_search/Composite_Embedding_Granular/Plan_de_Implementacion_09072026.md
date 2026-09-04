## Plan de Implementación: Composite Embedding Granular (Gap C)

**Fecha:** 09/07/2026
**Relacionado:**
- `DCT — Propagación Fix F-08C → F-08 Fase A` (Notion) — documenta el Gap C original
- `Indexacion_Imagen_Detalle_Accesorios/Plan_de_Implementacion_03072026.md` — plan **pausado** tras Fase 0 (hipótesis refutada para CARTERAS/BRAZALETES); este plan es la vía alternativa que ese mismo documento ya anticipaba en su sección "Fuera de alcance"
- Propuesta de reorganización en 3 modos (Inspiración / Completar outfit / Obtener outfit completo) — ver relación en la sección final

**Complementa a:** los fixes de expansión de categorías (F-08/F-08C/F-08B) ya aplicados — esos filtran mejor lo que el pool visual trae; este plan mejora la **calidad del pool desde el origen**, sin depender de que el catálogo tenga mejores fotos.

---

### Por qué este plan, y no el de reindexación de fotos

El plan de indexar la imagen de detalle (03/07) asumía que la causa del problema era "la foto equivocada está indexada" — y que bastaba con indexar `images[1]` en vez de `images[0]`. La Fase 0 de ese plan (auditoría real de nombres de archivo) refutó esa hipótesis para varias categorías: en CARTERAS y parte de BRAZALETES, **ninguna** de las fotos de la galería aísla el accesorio — toda la sesión de fotos está organizada alrededor de un vestido/outfit. No hay ninguna imagen "correcta" esperando a ser indexada.

Composite Embedding no depende de que exista una foto mejor. En vez de intentar arreglar **qué imagen se indexa**, cambia **cómo se construye la consulta de búsqueda** — combinando el vector de imagen (el que hay, sea bueno o mediocre) con un vector de texto que ancla semánticamente hacia la categoría real del producto. Es la misma técnica que ya usa `search_outfit_by_image()` en producción desde hace semanas — aquí se trata de extenderla a los otros dos consumidores que hoy no la usan.

---

### Recordatorio del mecanismo real (confirmado contra `visual_retriever.py`, no asumido)

FashionSigLIP expone dos codificadores separados en el mismo espacio vectorial: `encode_image()` y `encode_text()`. `search_outfit_by_image()` ya combina ambos:

```python
composite = alpha * image_np + (1.0 - alpha) * text_np
```

Donde `text_np` viene de `CATEGORY_TEXT_PROMPTS`, un diccionario **pre-calculado en el warmup** con **un solo prompt genérico por bucket de outfit-category** (9 buckets: dress, top, bottom, shoes, bag, accessory, outerwear, conjunto, enterito). El bucket `"accessory"` mezcla aros, collares, brazaletes, cinturones y tocados en una sola frase — no hay forma de pedir "aros específicamente".

**Los otros dos consumidores de búsqueda visual no usan esta técnica en absoluto:**
- `search_by_product_id()` (F-08/F-08C, "similar a este producto") — búsqueda pura de imagen, sin ningún componente de texto.
- Es la ruta que origina Hallazgo 1 (T3: Aros Antonieta devolviendo vestidos) y Hallazgo T8 (ranking sin prioridad de tipo exacto).

---

### Diseño de la solución

**Dos piezas nuevas, ninguna toca lo ya validado:**

#### Pieza 1 — Prompts de texto por tipo Shopify específico (no solo por bucket)

Nuevo diccionario en `visual_retriever.py`, junto a `CATEGORY_TEXT_PROMPTS` (mismo patrón, mismo mecanismo de pre-cacheo en warmup):

```python
# Prompts MAS ESPECIFICOS que CATEGORY_TEXT_PROMPTS["accessory"] -- uno por
# cada tipo real de la colección Complementos, en vez de un solo prompt
# genérico compartido por los 9 tipos. Reutiliza el mismo patrón de
# pre-cacheo en warmup que CATEGORY_TEXT_PROMPTS (ver _warmup_category_prompts).
SHOPIFY_TYPE_TEXT_PROMPTS = {
    "AROS":           "earrings aros pendientes arete jewelry mujer",
    "COLLARES":       "necklace collar cadena gargantilla chain jewelry mujer",
    "BRAZALETES":     "bracelet brazalete pulsera jewelry mujer",
    "BRAZALETE":      "bracelet brazalete pulsera jewelry mujer",
    "CINTURONES":     "belt cinturon correa mujer",
    "TOCADOS":        "headpiece tocado diadema corona hair accessory mujer",
    "ALAS DE NOVIA":  "bridal wings alas de novia veil wedding mujer",
    "CARTERAS":       "handbag cartera bolso purse mujer",
    "CLUTCH":         "clutch bag purse mujer",
}
```

Costo de warmup: 9 encodes de texto adicionales (~150ms cada uno si no están cacheados) — se agregan al **mismo batch async** que ya calienta `CATEGORY_TEXT_PROMPTS`, no como paso secuencial adicional. Impacto esperado en cold-start: marginal (~0, si el batch ya es paralelo) a ~1.3s (si por alguna razón hay que serializarlo) — a confirmar en Fase 2.

#### Pieza 2 — Nueva función de búsqueda con boost de categoría, opt-in

**No se modifica `search_by_product_id()` existente** — se agrega una función nueva, y el caller decide cuándo usarla:

```python
async def search_by_product_id_with_category_boost(
    self,
    product_id: str,
    boost_category: str,      # tipo Shopify exacto, ej. "AROS"
    alpha: float = 0.6,       # mismo default que search_outfit_by_image
    top_k: int = 30,
) -> List[str]:
    """
    Igual que search_by_product_id(), pero combina el vector de imagen
    precomputado del producto ancla con un vector de texto anclado a su
    categoria real (SHOPIFY_TYPE_TEXT_PROMPTS), antes de buscar en FAISS.

    Por que: cuando la imagen indexada del producto esta dominada por
    otra prenda (ej. un vestido en la foto de unos aros), el vector de
    imagen puro empuja la busqueda hacia esa prenda dominante. Mezclar
    con un vector de texto de la categoria real del PRODUCTO (no de lo
    que la foto muestra) corrige el sesgo sin necesitar una foto mejor.
    """
    pos = self._id_to_pos.get(product_id)
    if pos is None:
        return []
    image_vec = self._faiss_index.reconstruct(pos)        # ya existe, ~50ms

    text_prompt = SHOPIFY_TYPE_TEXT_PROMPTS.get(boost_category.upper())
    if not text_prompt:
        # Categoria sin prompt especifico -- degradar a busqueda pura de imagen
        # (comportamiento identico a search_by_product_id existente).
        _, indices = self._faiss_index.search(image_vec, top_k + 1)
        return [self._pos_to_id[i] for i in indices[0] if i != pos]

    text_vec = self._get_cached_text_embedding(text_prompt)  # pre-cacheado en warmup
    composite = alpha * image_vec + (1.0 - alpha) * text_vec

    _, indices = self._faiss_index.search(composite, top_k + 1)
    return [self._pos_to_id[i] for i in indices[0] if i != pos]
```

**Dónde se activa (en el monolito, `mcp_conversation_handler.py`):** solo cuando el tipo del producto ancla pertenece a la familia ACCESSORIES (el mismo set de 9 tipos ya corregido en `get_parent_categories()["ACCESSORIES"]` — reutilizado, no duplicado). Para cualquier otro tipo (vestidos, tops, etc.), F-08/F-08C siguen llamando a `search_by_product_id()` sin cambios — **cero riesgo de regresión fuera de accesorios**.

```python
# En F-08 Fase A y F-08C, antes de la llamada actual a search_by_product_id:
if _f08_type_upper in ACCESSORY_FAMILY_TYPES:  # reutiliza el set ya existente
    _f08_visual_ids = await _f08_colbert.search_by_product_id_with_category_boost(
        _f08_pid, boost_category=_f08_type_upper, top_k=30,
    )
else:
    _f08_visual_ids = await _f08_colbert.search_by_product_id(_f08_pid, top_k=30)
```

---

### Fases de implementación

```
FASE 0  Prueba de concepto aislada (sin tocar produccion)   [~30 min]
FASE 1  Prompts + funcion nueva en embedding-service          [~40 min]
FASE 2  Deploy embedding-service + warmup + medicion latencia [~20 min]
FASE 3  Integracion opt-in en F-08/F-08C                      [~30 min]
FASE 4  Validacion comparativa (plain vs composite)            [~30 min]
```

### FASE 0 — Prueba de concepto aislada

Antes de tocar el embedding-service en producción: un script standalone que cargue el modelo FashionSigLIP localmente (o pegue contra el embedding-service ya desplegado usando un endpoint de debug temporal), calcule el composite vector para Aros Antonieta con `alpha=0.6` y el prompt de AROS, y compare manualmente los top-10 resultados contra los que ya tenemos documentados de la búsqueda pura de imagen (pool de 30 con solo 1 AROS real). Esto confirma **antes de escribir código de producción** que la técnica realmente mueve la aguja para este caso concreto, con datos reales, no solo con el razonamiento teórico de arriba.

**Criterio de éxito de Fase 0:** el top-10 del composite vector debe contener sensiblemente más productos AROS que el top-10 de la búsqueda pura de imagen (que hoy es prácticamente 0-1).

### FASE 1 — Prompts + función nueva

Implementar `SHOPIFY_TYPE_TEXT_PROMPTS` y `search_by_product_id_with_category_boost()` en `visual_retriever.py`, siguiendo el diseño de arriba. Añadir el warmup de los 9 prompts nuevos al mismo batch async que ya calienta `CATEGORY_TEXT_PROMPTS`.

### FASE 2 — Deploy + medición de latencia real

Deploy del embedding-service. Medir en logs reales:
- Tiempo de warmup con los 9 prompts nuevos (comparar contra el baseline sin ellos).
- Latencia de `search_by_product_id_with_category_boost()` en producción (debería ser marginalmente mayor que `search_by_product_id()` plano — un lookup de texto pre-cacheado, no un encode en vivo).

### FASE 3 — Integración opt-in en F-08/F-08C

Modificar `mcp_conversation_handler.py` para llamar a la nueva función solo cuando el tipo del ancla está en la familia ACCESSORIES. Un solo `if/else` en cada uno de los 2 bloques (Fase A, Fase C) — sin tocar la lógica de expansión a hermanas ni el mecanismo de relleno restringido, que siguen funcionando exactamente igual sobre el pool que ahora llega mejor curado.

### FASE 4 — Validación comparativa

Repetir la consulta T3 original (Aros Antonieta, Turn 1) y comparar:
- **Antes** (solo expansión + relleno, sin composite): `filtered=1` de 30, resto vía relleno restringido a hermanas.
- **Después** (composite + expansión + relleno): idealmente `filtered` sube significativamente por sí solo, y el relleno a hermanas se necesita menos — el pool de 30 debería tener más AROS reales desde el inicio, no solo mejor filtrados.

También repetir la consulta de Hallazgo T8 (Collar pequeño, Turn 2+) para confirmar si el composite embedding, combinado con la priorización de tipo exacto ya aplicada, reduce aún más la necesidad de esa partición manual.

---

### Alpha — valor de partida y validación empírica pendiente

`search_outfit_by_image()` usa `alpha=0.6` (60% imagen, 40% texto), ya validado en producción para outfit completion. Se propone el mismo valor como punto de partida para `search_by_product_id_with_category_boost()`, pero **no se asume que sea óptimo para este caso** — el uso es distinto: outfit completion combina imagen de un look completo con el prompt de una categoría *ausente* en la foto (busca lo que falta); aquí se combina la imagen de un producto con el prompt de su **propia** categoría (busca refinar/corregir el sesgo de la imagen). Fase 0 debe probar al menos `alpha=0.6` y `alpha=0.4` (más peso al texto) para decidir con datos reales cuál da mejores resultados antes de fijar el valor en Fase 1.

---

### Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El composite embedding no mejora lo suficiente para categorías con fotos genuinamente sin accesorio visible (CARTERAS, ver plan pausado) | Fase 0 lo revela con datos reales antes de invertir en Fases 1-4. Si no mejora, el mecanismo de relleno restringido (ya en producción) sigue siendo la red de seguridad |
| Latencia adicional en el warmup del embedding-service | Los 9 prompts nuevos se agregan al mismo batch async existente — medir en Fase 2 antes de asumir que es despreciable |
| Alpha mal calibrado empeora resultados en vez de mejorarlos | Fase 0 prueba 2 valores con datos reales antes de fijar ninguno en código de producción |
| Cambio afecta categorías fuera de accesorios por error de scope | La activación es opt-in explícito por tipo (`if _f08_type_upper in ACCESSORY_FAMILY_TYPES`) — vestidos, tops, etc. siguen exactamente igual, sin tocar ese código |

---

### Relación con la propuesta de 3 modos (Inspiración / Completar outfit / Obtener outfit completo)

Este plan mejora la **calidad de búsqueda** (qué tan relevantes son los resultados), no la **estructura de presentación** (cómo se agrupan/muestran). Son ejes independientes, pero se refuerzan:

- **"Completar outfit" (refinado, propuesto):** si ese modo llega a mostrar categorías de Complementos por separado (ej. un carrusel de "Aros" y otro de "Collares", en vez de un bucket combinado de "accesorios"), los prompts específicos de este plan (`SHOPIFY_TYPE_TEXT_PROMPTS`) serían directamente reutilizables para alimentar cada carrusel con su propio Composite Embedding — la pieza técnica quedaría lista de antemano.
- **"Obtener outfit completo":** no se beneficia directamente de este plan — su caso de uso ya usa el nivel de granularidad de los 9 buckets de outfit-category de forma consistente, que es exactamente para lo que `search_outfit_by_image()` fue diseñado originalmente.
- **"Inspiración":** sin relación — mantiene el comportamiento de mezcla libre actual, sin necesidad de mayor precisión de categoría.

No hay dependencia bloqueante en ninguna dirección — este plan puede implementarse antes, después, o independientemente de la decisión sobre los 3 modos.

---

### Fuera de alcance (por ahora)

**Aplicar composite embedding a categorías fuera de accesorios** (vestidos, tops, etc.) — no hay evidencia de que esas categorías sufran el mismo problema de dominancia visual; aplicar la técnica ahí sin evidencia sería una complejidad sin beneficio demostrado.

**Prompts de texto para modificadores libres** (color, estilo — ej. "vestido verde") — ya discutido en sesión anterior: requeriría encoding de texto en vivo (no pre-cacheable), con un costo de latencia distinto (~150ms por consulta) que amerita su propio análisis de trade-offs, separado de este plan.

---

### Resumen de archivos a modificar

| Archivo | Cambio |
|---|---|
| `src/api/services/embedding-service/visual_retriever.py` | Nuevo `SHOPIFY_TYPE_TEXT_PROMPTS`, nueva función `search_by_product_id_with_category_boost()`, extensión del warmup batch |
| `src/api/core/mcp_conversation_handler.py` | F-08 Fase A y F-08C: `if/else` opt-in hacia la nueva función cuando el tipo del ancla es de la familia ACCESSORIES |

Cero cambios en `tfidf_recommender.py`, `visual_index_sync_job.py`, ni en el pipeline de indexación — este plan no depende de qué imagen está indexada, a diferencia del plan pausado del 03/07.
