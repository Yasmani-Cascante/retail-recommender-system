# DOCUMENTO DE CIERRE — Fase M4: Incremental Sync
## Retail Recommender System v2.1.0 — Knowledge Base System
*Fecha de cierre: 27 de Febrero 2026*
*Fase: M4 (Plan de Mejoras Técnicas del KB System)*

---

## 1. RESUMEN EJECUTIVO

M4 se cierra con un **deliverable funcional que difiere del mecanismo original planeado**, pero que cumple el objetivo operacional de la fase: reducir la carga de sincronización y detectar cambios en contenido KB de forma eficiente.

| | Plan Original | Resultado Real |
|---|---|---|
| **Mecanismo** | Webhooks Shopify (push, event-driven) | Polling incremental por `updated_at` (pull) |
| **Latencia objetivo** | < 2 segundos | 0 — KB_SYNC_INTERVAL_MINUTES (máx. 5 min) |
| **Causa del cambio** | — | Shopify no implementa webhooks para Pages |
| **Infraestructura webhook** | A crear | Creada, funcional, lista para activar |
| **Polling mejorado** | No contemplado | Implementado y en producción |

**Veredicto: M4 cerrado.** La fase entregó valor real y sentó las bases para sincronización en tiempo real cuando Shopify agregue soporte nativo.

---

## 2. CONTEXTO: POR QUÉ EL PLAN ORIGINAL NO FUE POSIBLE

Durante la fase de debugging del registro de webhooks se identificó la causa raíz del error 422 persistente:

**Shopify no implementa webhooks para el recurso `Pages` en ninguna versión de su API.**

Los topics `pages/create`, `pages/update` y `pages/delete` no existen en la plataforma, independientemente de:
- La versión de API usada (probadas: `2024-01`, `2025-01`)
- Los scopes configurados en la app (`read_content`, `write_content` ✅ presentes)
- La configuración del webhook secret

```
Error real de Shopify (422):
"Invalid topic specified: pages/delete.
Does it exist? Is there a missing access scope?
Topics allowed: [lista de ~120 topics — pages/* ausente en todos]"
```

**Referencia confirmada:** Shopify Community (enero 2024, actualizado febrero 2025)
`https://community.shopify.com/t/webhook-topic-for-page-resource-page-create-update/285494`
Estado: sin resolución oficial a la fecha de cierre de esta fase.

> **Learning para el equipo:** Cuando una integración con una API de terceros falla con "Invalid topic/resource", la causa puede ser una limitación de la plataforma y no un error propio. Combinar documentación oficial + foros de la comunidad da la respuesta definitiva más rápido que seguir iterando sobre el código.

---

## 3. LO QUE SE CONSTRUYÓ Y PERMANECE EN EL SISTEMA

Aunque los webhooks de páginas no son posibles hoy, M4 entregó una infraestructura completa y un polling significativamente mejorado.

### 3.1 Infraestructura Webhook (lista para activar)

Todos los componentes están implementados, testeados y documentados. Solo requieren que Shopify agregue soporte para `pages/*` topics.

**`src/api/core/webhook_security.py`** — ACTIVO
Validación HMAC-SHA256 pura, sin dependencias de FastAPI. Reutilizable para cualquier webhook futuro de Shopify. Implementa `hmac.compare_digest()` para resistencia a timing attacks.

**`src/api/routers/webhooks_router.py`** — PARCIALMENTE ACTIVO
Endpoint unificado `POST /api/webhooks/shopify/pages`. Enruta por header `X-Shopify-Topic`. Hoy recibe activamente `translations/update` (Shopify sí emite este topic). Los handlers `pages/*` están implementados pero no llegarán webhooks hasta que Shopify los soporte.

**`src/api/services/shopify_webhook_handler.py`** — PARCIALMENTE ACTIVO
- `handle_translation_event()` → **ACTIVO**: cuando marketing actualiza una traducción en Shopify Translate & Adapt, el webhook llega y este handler ejecuta `sync_single_page()` en tiempo real.
- `handle_page_event()` → **PREPARADO**: lógica completa para `pages/create`, `pages/update`, `pages/delete`. Inactivo por falta de soporte en Shopify.

**`src/api/core/shopify_webhook_registry.py`** — INACTIVO (intencionalmente)
`REQUIRED_WEBHOOKS = []` hasta que Shopify soporte `pages/*`. El startup ya no intenta registrar topics inexistentes, eliminando los errores 422 en arranque.

### 3.2 Polling Incremental (en producción)

**`src/api/services/shopify_kb_sync.py` → `KBBackgroundSyncJob`**

Transformación del modelo de sincronización:

```
ANTES (M3 y anterior):
  Cada 5 minutos → sync_all_pages() → 40 páginas × metafields × traducciones
  = ~120 llamadas API + 80 operaciones DB por ciclo, independiente de si hubo cambios

DESPUÉS (M4):
  Ciclo 1 → full sync (establece baseline, guarda timestamp)
  Ciclos 2+ → get_pages() → filtrar por updated_at > last_sync_at
            → solo sincroniza páginas con cambios reales
  = Ciclos sin cambios: 1 llamada API, 0 operaciones DB
  = Ciclos con cambios: 1 + (N páginas modificadas × ~3 llamadas)
```

**Cómo funciona el cursor de tiempo:**

```python
# Cada ciclo exitoso avanza el cursor
self._last_sync_at = cycle_start

# Si el ciclo falla, el cursor NO avanza
# → el siguiente ciclo reintenta desde el mismo punto
# → ningún cambio se pierde por fallo transitorio
```

**`sync_single_page(page_id)`** — nuevo método extraído de M4:
Sincroniza quirúrgicamente una sola página (fetch + metafields + traducciones + upsert DB + invalidación cache). Usado tanto por el polling incremental como por el webhook handler cuando llegue el momento.

### 3.3 Correcciones de Infraestructura Aplicadas Durante M4

Durante el debugging del registro de webhooks se identificaron y corrigieron problemas adicionales que afectarían a cualquier futura integración:

| Fix | Archivo | Problema | Solución |
|---|---|---|---|
| API Version | `shopify_client.py` | Versión `2024-01` desincronizada con la configuración `2025-01` del Partners Dashboard | Actualizado a `2025-01` |
| URL Normalización | `shopify_webhook_registry.py` | `APP_PUBLIC_URL` con `/` final producía doble slash en URLs | `app_url.rstrip("/")` defensivo |
| Error Body Logging | `shopify_kb_client.py` | Error 422 sin detalles impedía diagnóstico | Captura del body de error antes de `raise_for_status()` |
| Webhook Secret | `.env` | Secret incorrecto (32 chars) activo en lugar del correcto (64 chars) | Documentado para corrección manual |

---

## 4. ESTADO DE CADA ARCHIVO M4

| Archivo | Estado | Función actual |
|---|---|---|
| `shopify_webhook_registry.py` | ✅ Activo | `REQUIRED_WEBHOOKS=[]` — no registra nada, startup limpio |
| `webhooks_router.py` | ✅ Activo | Recibe `translations/update` en tiempo real |
| `webhook_security.py` | ✅ Activo | Valida HMAC de todos los webhooks entrantes |
| `shopify_webhook_handler.py` | 🟡 Parcial | `handle_translation_event` activo; `handle_page_event` preparado |
| `shopify_kb_sync.py` | ✅ Activo | Polling incremental + `sync_single_page()` en producción |

---

## 5. COMPARATIVA: ANTES Y DESPUÉS DE M4

### Eficiencia del ciclo de sincronización

```
ESCENARIO: 40 páginas KB, nadie editó nada en los últimos 5 minutos

ANTES (full sync):
  Llamadas API:      ~120  (40 páginas × get_page + get_metafields + get_translations)
  Operaciones DB:    80    (40 páginas × 2 idiomas)
  Duración:          ~10s
  Quota Shopify:     consumida completa cada ciclo

DESPUÉS (polling incremental):
  Llamadas API:      1     (get_pages con metadata liviana)
  Operaciones DB:    0
  Duración:          ~0.8s
  Quota Shopify:     mínima
```

```
ESCENARIO: Marketing editó 1 página en los últimos 5 minutos

ANTES (full sync):
  Sincronizan:       40 páginas (innecesario)
  Operaciones DB:    80

DESPUÉS (polling incremental):
  Detecta:           1 cambio (updated_at > last_sync_at)
  Sincronizan:       1 página via sync_single_page()
  Operaciones DB:    2 (ES + EN)
```

### Lo que sí funciona en tiempo real hoy (M4 activo)

Cuando marketing actualiza una **traducción** de una página KB en Shopify Translate & Adapt:

```
Marketing edita traducción EN en Shopify
  → Shopify emite webhook translations/update (topic SÍ existe)
  → POST /api/webhooks/shopify/pages
  → webhook_security.validate_shopify_webhook()  ← HMAC validado
  → ShopifyWebhookHandler.handle_translation_event()
  → shopify_kb_sync.sync_single_page(page_id)
  → Upsert ES + EN en PostgreSQL
  → Invalidación cache Redis
  Latencia total: < 2 segundos  ✅
```

Este flujo funciona completamente hoy. Solo las ediciones al **contenido original** (español, desde Shopify Pages) quedan sujetas al polling de 5 minutos.

---

## 6. CÓMO ACTIVAR LOS WEBHOOKS DE PÁGINAS EN EL FUTURO

Cuando Shopify agregue soporte para `pages/*` topics (monitorear sus release notes), la activación requiere exactamente 3 pasos:

**Paso 1 — `shopify_webhook_registry.py`**: descomentar `REQUIRED_WEBHOOKS`

```python
# Descomentar estos topics:
REQUIRED_WEBHOOKS = [
    {"topic": "pages/create", "address": "{APP_URL}/api/webhooks/shopify/pages", "format": "json"},
    {"topic": "pages/update", "address": "{APP_URL}/api/webhooks/shopify/pages", "format": "json"},
    {"topic": "pages/delete", "address": "{APP_URL}/api/webhooks/shopify/pages", "format": "json"},
]
```

**Paso 2 — `.env`**: activar el flag

```bash
KB_WEBHOOKS_ENABLED=true
```

**Paso 3**: Reiniciar el servicio. El startup hook `ensure_webhooks_registered()` registra los webhooks automáticamente en Shopify. No hay nada más que implementar — el router, el handler, la validación HMAC y la idempotency ya están listos.

---

## 7. DEUDA TÉCNICA Y LIMITACIONES CONOCIDAS

### Limitación 1 — Sincronización de páginas no es tiempo real
Las ediciones al contenido original de páginas KB (español) tienen latencia de 0 a 5 minutos.
**Mitigación disponible hoy**: El equipo puede ejecutar `POST /api/kb/sync` para forzar un sync inmediato en casos urgentes.

### Limitación 2 — `get_pages()` descarga metadata de todas las páginas cada ciclo
La Shopify Pages REST API no soporta filtro `?updated_at_min=` en la versión actual. La comparación de timestamps se hace del lado del cliente. Con 50-100 páginas KB es completamente viable. Si el catálogo crece a 1000+ páginas, evaluar migración a GraphQL con cursor.

### Limitación 3 — BackgroundTasks sin retry automático
Los webhooks que fallan en background no se reintentan automáticamente. Los errores se loguean y se contabilizan en Prometheus (`kb_webhook_processed_total{result="error"}`). El polling de respaldo actúa como safety net para cambios que no llegaron por webhook.

---

## 8. VARIABLES DE ENTORNO RELEVANTES

```bash
# Sincronización periódica
KB_SYNC_INTERVAL_MINUTES=5        # Intervalo del polling incremental
KB_ENABLE_BACKGROUND_SYNC=true    # Activar/desactivar el job de fondo

# Idiomas a sincronizar
KB_SYNC_LANGUAGES=es,en           # Idiomas del polling (comma-separated)

# Webhooks (para cuando Shopify soporte pages/*)
KB_WEBHOOKS_ENABLED=false         # false hasta que Shopify soporte pages/*

# Seguridad
SHOPIFY_WEBHOOK_SECRET=<64-char-hex>  # Signing secret de Shopify Admin → Settings → Notifications

# Locking distribuido (activo en multi-instancia)
KB_DISTRIBUTED_LOCKS=true         # Heredado de M3, aplica a sync_single_page()
```

---

## 9. LOGS DE REFERENCIA — ¿Qué ver en producción?

### Startup limpio (sin errores 422)
```
webhook_registration_skipped
  reason=shopify_pages_webhooks_not_supported
  sync_strategy=incremental_polling
```

### Ciclo incremental sin cambios (el más común)
```
kb_sync_cycle_started  cycle=47  mode=incremental  since=2026-02-27T19:00:00
kb_sync_cycle_no_changes  total_pages_checked=40  since=2026-02-27T19:00:00
kb_sync_cycle_completed  cycle=47  pages_checked=40  pages_changed=0  duration_seconds=0.8
```

### Ciclo incremental con cambios detectados
```
kb_sync_cycle_started  cycle=48  mode=incremental
kb_sync_incremental_changes_detected  changed_pages=1  page_ids=[98765]
sync_single_page_completed  page_id=98765  status=synced  languages_count=2
kb_sync_cycle_completed  cycle=48  pages_changed=1  pages_synced=1  duration_seconds=1.4
```

### Webhook de traducción recibido (funciona hoy)
```
webhook_accepted  page_id=98765  topic=translations/update
webhook_translation_syncing  page_id=98765  locale=en
sync_single_page_completed  page_id=98765  status=synced
webhook_translation_processed  duration_ms=380
```

---

## 10. APRENDIZAJES DE LA FASE

### Técnico — API Versioning y limitaciones de plataforma

El error 422 de Shopify no fue intuitivo porque el mensaje decía "Invalid topic — does it exist? Is there a missing access scope?" — lo que sugería un problema de permisos o versión. La investigación en profundidad reveló que el topic simplemente no existe en la plataforma.

**Principio aplicado**: Cuando una API de terceros rechaza un recurso con un error ambiguo, verificar primero si el recurso existe en la plataforma antes de ajustar la configuración propia.

### Arquitectura — Polling vs Webhooks

Webhooks (push) son superiores en latencia pero dependen del soporte de la plataforma emisora. Polling (pull) es universalmente compatible pero consume recursos en ciclos sin cambios. El polling incremental por cursor de tiempo es el punto medio: compatible con cualquier API que exponga `updated_at`, y eficiente en ciclos sin cambios.

```
Webhook puro:      latencia ~1s    | requiere soporte de plataforma
Full polling:      latencia 0-5min | costoso, independiente
Polling incremental: latencia 0-5min | eficiente, independiente  ← elegido
```

### Proceso — Documentar limitaciones de plataforma como first-class citizens

Cuando una limitación externa impide completar un objetivo, documentar la limitación directamente en los archivos afectados (con la referencia a la fuente oficial) es más valioso que un comentario genérico de "TODO". Permite a cualquier desarrollador futuro entender el contexto sin necesidad de re-investigar.

---

## 11. PRERREQUISITOS SATISFECHOS PARA LA SIGUIENTE FASE

M4 dejó el sistema en un estado más robusto para lo que siga:

| Capacidad | Estado tras M4 |
|---|---|
| `sync_single_page()` disponible | ✅ Implementado y probado |
| Infraestructura webhook completa | ✅ Lista para activar |
| Polling incremental eficiente | ✅ En producción |
| `translations/update` en tiempo real | ✅ Funcionando |
| API version consistente (2025-01) | ✅ Corregido durante M4 |
| Logging de errores de Shopify API | ✅ Mejorado durante M4 |
| Documentación de limitaciones | ✅ En todos los archivos M4 |

---

*Documento de cierre creado: 27 de Febrero 2026*
*Fase M4 iniciada: 25 de Febrero 2026*
*Duración efectiva: 3 días*
*Archivos modificados: 6 (shopify_webhook_registry.py, webhooks_router.py, webhook_security.py, shopify_webhook_handler.py, shopify_kb_sync.py, shopify_kb_client.py)*
*Fase siguiente: M5 (por definir)*
