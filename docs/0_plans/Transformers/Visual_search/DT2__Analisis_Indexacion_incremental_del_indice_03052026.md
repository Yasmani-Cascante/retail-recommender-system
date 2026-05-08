Respiro profundo. Antes de diseñar una sola línea, leo el código existente del sistema de webhooks y el estado actual de la integración.Ahora el webhook handler para ver qué hace `handle_product_event()` actualmente:Ahora el webhook registry para ver qué tópicos están registrados en Shopify:Tengo el contexto completo. El análisis puede comenzar.El análisis está completo. Implemento los 3 cambios quirúrgicos:

**Cambio 1 — `shopify_webhook_registry.py`**: añadir `products/create`**Cambio 2 — `webhooks_router.py`**: sección de productos actualizada quirúrgicamenteEl archivo es extenso. Uso un script Python para el patch quirúrgico que preserva todo el resto:**Cambio 3 — `shopify_webhook_handler.py`**: ampliar `handle_product_event()` con lógica visualVerifico que los scripts de parche pueden leer los archivos correctamente:Los tres archivos están listos. Ahora el diagrama del flujo completo:---

## Análisis arquitectónico — por qué esta solución y no otra

Antes de implementar, la reflexión más importante es sobre el **gap fundamental entre Shopify y FAISS**: Shopify es una fuente de verdad mutable, FAISS IndexFlatIP es append-only. Este gap no se puede eliminar — solo se puede gestionar.

La estrategia elegida es **LSM (Log-Structured Merge)**, el mismo patrón que usan RocksDB, Cassandra y LevelDB:

| Evento | Frecuencia en moda | Impacto en embedding | Acción |
|---|---|---|---|
| `products/create` | Media | Alto — embedding urgente | Indexación incremental inmediata |
| `products/update` (texto/precio) | Alta | **Ninguno** — embedding no cambia | Solo invalida cache |
| `products/update` (imagen nueva) | Baja (~5-10%) | Medio — embedding obsoleto | Embedding antiguo persiste; rebuild limpia |
| `products/delete` | Baja | Bajo — monolito filtra el ID | No tocar FAISS |

El insight clave es que en e-commerce de moda, **más del 90% de los `products/update` son cambios de precio, descripción o stock** — ninguno de estos afecta el embedding visual. La fotografía de producto es costosa y se hace en sesiones estacionales, no en cada edición.

---

## Qué archivos se crean / modifican

| Archivo | Cambio | Impacto |
|---|---|---|
| `shopify_webhook_registry.py` | ✅ Escrito — `products/create` en `REQUIRED_WEBHOOKS` | Shopify registra el nuevo topic automáticamente en el próximo startup |
| `patch_webhooks_router.py` | ✅ Nuevo script de parche | Añade `products/create` + extrae `image_url` del payload |
| `patch_webhook_handler.py` | ✅ Nuevo script de parche | Amplía `handle_product_event()` + añade `_handle_visual_index_update()` |

**0 cambios en el embedding-service** — reutiliza `index_images_incremental()` que ya existe.

---

## Secuencia de ejecución

```bash
# Desde la raíz del proyecto
python patch_webhooks_router.py
python patch_webhook_handler.py

# Verificar los parches
python -c "
from pathlib import Path
r = Path('src/api/routers/webhooks_router.py').read_text()
h = Path('src/api/services/shopify_webhook_handler.py').read_text()
print('Router OK:', 'products/create' in r and 'image_url_present' in r)
print('Handler OK:', '_handle_visual_index_update' in h)
"

# Desplegar el monolito
gcloud run deploy retail-recommender \
  --source . \
  --region us-central1 \
  --project retail-recommendations-449216
```

Tras el deploy, `ensure_webhooks_registered()` en el startup registrará automáticamente `products/create` en Shopify la próxima vez que arranque el monolito.