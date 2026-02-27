# PLAN DE DISEÑO — M4: Incremental Sync (Webhooks)
## Knowledge Base System — Retail Recommender v2.1.0
*Fecha: 2026-02-25 | Fase: M4 (Plan de Mejoras Técnicas)*

---

## RESUMEN EJECUTIVO

M4 transforma el sistema de sincronización de Knowledge Base de un modelo **batch/polling** (sync completo cada N minutos) a un modelo **event-driven** (sync granular disparado por Shopify Webhooks en tiempo real).

**Antes de M4**: Una actualización en Shopify tarda entre 0 y 5 minutos en reflejarse en la KB de producción.
**Después de M4**: La misma actualización se refleja en menos de 2 segundos.

---

## PRERREQUISITOS CONFIRMADOS

| Dependencia | Estado | Relevancia para M4 |
|-------------|--------|-------------------|
| M1: Optimize Sync Performance | ✅ Completado | Sync de página individual <400ms |
| M2: Prometheus Metrics | ✅ Completado | Observabilidad de webhooks |
| M3: Distributed Locking | ✅ Completado | Evita doble-procesamiento de webhooks |
| Redis disponible en producción | ✅ Sí | Idempotency key store |

Todos los prerrequisitos están satisfechos. **M4 puede iniciarse.**

---

## 1. ANÁLISIS DEL PROBLEMA ACTUAL

### 1.1 Flujo Actual (Full Sync / Polling)

```
Shopify CMS                   Backend                        PostgreSQL KB
────────────                  ───────                        ─────────────
[Admin edita página]
        │
        │   (espera hasta próximo scheduled job)
        │   ↕ latencia: 0 - 5 minutos
        │
        └──────────────────── Cron Job ─────────────────────►
                              sync_all_pages()
                              ├── GET /pages (todas)     ──►
                              ├── Para cada página:
                              │   GET /translations      ──►
                              │   GET /metafields        ──►
                              │   _upsert_kb_content()   ──────────────────►
                              └── 13 páginas × 2 idiomas
                                  = 26 upserts = ~10.4s
```

**Problemas:**
1. **Latencia inaceptable**: Cambios urgentes (ej. actualización de política de devoluciones) tardan hasta 5 minutos en estar disponibles para el chatbot.
2. **Ineficiencia**: 26 upserts aunque solo 1 página cambió.
3. **Carga innecesaria en Shopify API**: Rate limit consumption aunque no hay cambios.

### 1.2 Flujo Objetivo (Incremental Sync / Webhooks)

```
Shopify CMS                   Backend                        PostgreSQL KB
────────────                  ───────                        ─────────────
[Admin edita página]
        │
        │   POST /api/webhooks/shopify/page-updated
        │   (Shopify envía automáticamente)
        │   ↕ latencia: <2 segundos
        │
        └──────────────────────────────────────────────────►
                              WebhookHandler
                              ├── Validar HMAC             (seguridad)
                              ├── Check idempotency key    (Redis, dedup)
                              ├── Extraer page_id
                              ├── sync_single_page(id)
                              │   ├── GET /pages/{id}    ──►
                              │   ├── GET /translations  ──►
                              │   └── _upsert_kb_content ──────────────────►
                              └── 1 página × N idiomas
                                  = 2-3 upserts = <400ms
```

---

## 2. ARQUITECTURA DE M4

### 2.1 Visión General de Componentes

```
┌──────────────────────────────────────────────────────────────────────┐
│                     SHOPIFY ADMIN                                    │
│         Editar página → Shopify envía webhook automáticamente        │
└─────────────────────────────┬────────────────────────────────────────┘
                              │ POST (HTTPS + HMAC-SHA256)
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  WEBHOOK ENDPOINT (FastAPI)                          │
│  POST /api/webhooks/shopify/page-updated                             │
│                                                                      │
│  1. Validate HMAC signature    ← seguridad: rechaza requests falsos  │
│  2. Extract payload (page_id)                                        │
│  3. Check idempotency key      ← Redis: evita doble-procesamiento    │
│  4. Return 200 OK              ← ACK rápido a Shopify (<5s)          │
│  5. Dispatch background task   ← procesamiento asíncrono             │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ asyncio.create_task() / BackgroundTasks
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  WEBHOOK PROCESSOR (Background)                      │
│                                                                      │
│  1. sync_single_page(page_id)                                        │
│     ├── Fetch page from Shopify                                      │
│     ├── Validate KB metadata (metafields)                            │
│     ├── For each language:                                           │
│     │   └── _upsert_kb_content() ← M3 distributed lock              │
│     └── Invalidate Redis cache for affected keys                     │
│                                                                      │
│  2. Record Prometheus metrics (webhook_processed, latency, etc.)     │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 Componentes Nuevos a Crear

```
src/api/
├── routers/
│   └── webhooks_router.py          ← NUEVO: endpoint FastAPI
│
├── services/
│   └── shopify_webhook_handler.py  ← NUEVO: lógica de procesamiento
│
└── core/
    └── webhook_security.py         ← NUEVO: validación HMAC

tests/
├── unit/
│   └── test_webhook_handler.py     ← NUEVO: tests unitarios
│
└── integration/
    └── webhooks/
        └── test_webhook_e2e.py     ← NUEVO: tests end-to-end
```

### 2.3 Componentes Existentes Modificados

```
src/api/
├── main_unified_redis.py           ← Registrar webhooks_router
├── core/
│   └── prometheus_metrics.py       ← Añadir métricas de webhooks
└── services/
    └── shopify_kb_sync.py          ← Extraer sync_single_page()
```

---

## 3. DISEÑO DETALLADO POR COMPONENTE

### 3.1 `webhook_security.py` — Validación HMAC

**Por qué es crítico**: Sin validación HMAC, cualquier actor malicioso puede enviar requests falsos al endpoint y forzar syncs o contaminar la KB.

```python
# src/api/core/webhook_security.py

import hmac
import hashlib
import base64
from typing import Optional

def validate_shopify_webhook(
    payload_bytes: bytes,
    shopify_hmac_header: str,
    webhook_secret: str,
) -> bool:
    """
    Valida la firma HMAC-SHA256 del webhook de Shopify.
    
    Shopify firma cada webhook con:
      HMAC = base64(SHA256(payload, secret))
    
    El header es: X-Shopify-Hmac-Sha256
    
    IMPORTANTE:
    - La validación DEBE hacerse sobre los bytes RAW del body,
      antes de cualquier parsing JSON.
    - Usar hmac.compare_digest() para comparación segura
      (previene timing attacks).
    
    Args:
        payload_bytes: Body raw del request (bytes, no str)
        shopify_hmac_header: Valor del header X-Shopify-Hmac-Sha256
        webhook_secret: Secreto configurado en Shopify Partners Dashboard
    
    Returns:
        True si la firma es válida, False en caso contrario
    
    Ejemplo:
        if not validate_shopify_webhook(body, hmac_header, secret):
            raise HTTPException(status_code=401, detail="Invalid HMAC")
    """
    computed = base64.b64encode(
        hmac.new(
            webhook_secret.encode("utf-8"),
            payload_bytes,
            digestmod=hashlib.sha256,
        ).digest()
    ).decode("utf-8")
    
    # compare_digest: tiempo constante, no vulnerable a timing attacks
    return hmac.compare_digest(computed, shopify_hmac_header)
```

**Lección de seguridad**: Usar `hmac.compare_digest()` en lugar de `==` para comparar hashes. La comparación `==` en Python puede terminar early cuando encuentra el primer byte diferente, lo que permite a un atacante medir el tiempo de respuesta para deducir bytes del HMAC correcto (timing attack). `compare_digest` siempre toma el mismo tiempo independiente del punto de diferencia.

### 3.2 `webhooks_router.py` — Endpoint FastAPI

```python
# src/api/routers/webhooks_router.py

import structlog
import asyncio
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Header
from typing import Optional
import json

from src.api.core.webhook_security import validate_shopify_webhook
from src.api.services.shopify_webhook_handler import ShopifyWebhookHandler
from src.api.core.config import settings

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post(
    "/shopify/page-updated",
    status_code=200,
    summary="Shopify Pages Webhook",
    description="Recibe notificaciones de Shopify cuando una página es creada/actualizada."
)
async def handle_page_updated(
    request: Request,
    background_tasks: BackgroundTasks,
    x_shopify_hmac_sha256: Optional[str] = Header(default=None),
    x_shopify_shop_domain: Optional[str] = Header(default=None),
    x_shopify_topic: Optional[str] = Header(default=None),
):
    """
    Endpoint receptor de webhooks de Shopify para páginas.
    
    FLUJO:
    1. Leer body raw (antes de parsing — necesario para HMAC)
    2. Validar firma HMAC (seguridad)
    3. Check idempotency (Redis — evita doble procesamiento)
    4. ACK rápido a Shopify (< 5s obligatorio)
    5. Procesar en background (sync page, update DB, invalidate cache)
    
    IMPORTANTE - Requisito de Shopify:
    Si el endpoint no responde en 5 segundos, Shopify lo considera fallido
    y hace retry (hasta 19 veces en 48 horas). Por eso el procesamiento
    real va en background_tasks.
    
    Args:
        request: FastAPI Request (para leer body raw)
        background_tasks: FastAPI BackgroundTasks (procesamiento asíncrono)
        x_shopify_hmac_sha256: Header de firma HMAC
        x_shopify_shop_domain: Header con dominio de la tienda
        x_shopify_topic: Header con topic del webhook (ej: "pages/update")
    """
    # ── 1. Leer body raw ──────────────────────────────────────────────────
    # CRÍTICO: Leer bytes antes de JSON parsing. La validación HMAC
    # necesita exactamente los bytes que Shopify firmó.
    body_bytes = await request.body()
    
    # ── 2. Validar HMAC ───────────────────────────────────────────────────
    if not x_shopify_hmac_sha256:
        logger.warning(
            "webhook_missing_hmac",
            shop=x_shopify_shop_domain,
            topic=x_shopify_topic,
        )
        raise HTTPException(status_code=401, detail="Missing HMAC header")
    
    if not validate_shopify_webhook(
        payload_bytes=body_bytes,
        shopify_hmac_header=x_shopify_hmac_sha256,
        webhook_secret=settings.SHOPIFY_WEBHOOK_SECRET,
    ):
        logger.warning(
            "webhook_invalid_hmac",
            shop=x_shopify_shop_domain,
            topic=x_shopify_topic,
        )
        raise HTTPException(status_code=401, detail="Invalid HMAC signature")
    
    # ── 3. Parse payload ──────────────────────────────────────────────────
    try:
        payload = json.loads(body_bytes)
        page_id = payload.get("id")
        page_handle = payload.get("handle", "unknown")
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("webhook_invalid_payload", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    if not page_id:
        logger.warning("webhook_missing_page_id", payload_keys=list(payload.keys()))
        raise HTTPException(status_code=400, detail="Missing page ID in payload")
    
    # ── 4. Check idempotency ──────────────────────────────────────────────
    # Shopify puede enviar el mismo webhook más de una vez (at-least-once delivery).
    # El idempotency key en Redis evita procesar la misma actualización dos veces.
    # Ver ShopifyWebhookHandler.is_duplicate_event() para implementación.
    
    logger.info(
        "webhook_received",
        page_id=page_id,
        page_handle=page_handle,
        topic=x_shopify_topic,
        shop=x_shopify_shop_domain,
    )
    
    # ── 5. Dispatch background processing ─────────────────────────────────
    # ACK a Shopify aquí (return 200), procesar después.
    # Esto garantiza respuesta en <5s independiente del tiempo de sync.
    background_tasks.add_task(
        _process_page_webhook,
        page_id=page_id,
        page_handle=page_handle,
        topic=x_shopify_topic or "pages/update",
    )
    
    return {
        "status": "accepted",
        "page_id": page_id,
        "message": "Webhook received, processing in background"
    }


async def _process_page_webhook(
    page_id: int,
    page_handle: str,
    topic: str,
) -> None:
    """
    Procesamiento real del webhook en background.
    
    Esta función se ejecuta DESPUÉS de que el endpoint respondió 200 a Shopify.
    Errores aquí no afectan la respuesta al webhook.
    
    Args:
        page_id: ID de la página Shopify a sincronizar
        page_handle: Handle (slug) de la página, para logging
        topic: Topic del webhook (pages/create, pages/update, pages/delete)
    """
    handler = ShopifyWebhookHandler()
    await handler.handle_page_event(
        page_id=page_id,
        page_handle=page_handle,
        topic=topic,
    )
```

### 3.3 `shopify_webhook_handler.py` — Lógica de Procesamiento

```python
# src/api/services/shopify_webhook_handler.py

import structlog
import time
from typing import Optional

logger = structlog.get_logger(__name__)

# TTL del idempotency key en Redis (5 minutos)
# Shopify no reintenta con menos de 5 minutos de diferencia en condiciones normales
IDEMPOTENCY_TTL_SECONDS = 300

# Prefijo para idempotency keys en Redis
IDEMPOTENCY_KEY_PREFIX = "webhook:idempotency:"


class ShopifyWebhookHandler:
    """
    Maneja el procesamiento de webhooks de Shopify.
    
    Responsabilidades:
    1. Idempotency check (evitar doble procesamiento)
    2. Routing por topic (create/update/delete)
    3. Sync de página individual
    4. Invalidación de cache Redis
    5. Métricas de observabilidad
    
    Diseño:
    - Stateless: cada instancia se crea por request
    - Depends on: RedisService (idempotency), ShopifyKBSyncService (sync logic)
    - Integra con M3 (distributed_lock) vía _upsert_kb_content()
    """
    
    def __init__(self):
        # Dependencias se resuelven lazy para facilitar testing
        self._redis = None
        self._sync_service = None
    
    async def _get_redis(self):
        """Lazy init de RedisService (singleton)."""
        if not self._redis:
            from src.api.core.redis_service import get_redis_service
            self._redis = await get_redis_service()
        return self._redis
    
    async def _get_sync_service(self):
        """Lazy init de ShopifyKBSyncService."""
        if not self._sync_service:
            from src.api.services.shopify_kb_sync import ShopifyKBSyncService
            self._sync_service = ShopifyKBSyncService()
        return self._sync_service
    
    async def is_duplicate_event(
        self,
        page_id: int,
        topic: str,
        timestamp_ms: Optional[int] = None,
    ) -> bool:
        """
        Verifica si este evento ya fue procesado recientemente.
        
        Shopify garantiza at-least-once delivery, lo que significa que el
        mismo webhook puede llegar 2+ veces. Usamos Redis como store de
        idempotency keys para detectar duplicados.
        
        Key format: webhook:idempotency:{topic}:{page_id}
        Ejemplo:    webhook:idempotency:pages/update:12345
        
        Args:
            page_id: ID de la página
            topic: Topic del webhook (pages/create, pages/update, pages/delete)
            timestamp_ms: Timestamp del evento (opcional, para key más específica)
        
        Returns:
            True si el evento ya fue procesado (es duplicado)
            False si es nuevo y debe procesarse
        """
        redis = await self._get_redis()
        key = f"{IDEMPOTENCY_KEY_PREFIX}{topic}:{page_id}"
        
        # SET NX: solo setea si NO existe (operación atómica)
        # Si ya existe → duplicado (devuelve False en SETNX)
        # Si no existe → nuevo evento (setea y devuelve True en SETNX)
        existing = await redis.get(key)
        
        if existing:
            logger.info(
                "webhook_duplicate_detected",
                page_id=page_id,
                topic=topic,
                idempotency_key=key,
            )
            return True
        
        # Registrar que vamos a procesar este evento
        await redis.set(key, "processing", ttl=IDEMPOTENCY_TTL_SECONDS)
        return False
    
    async def handle_page_event(
        self,
        page_id: int,
        page_handle: str,
        topic: str,
    ) -> None:
        """
        Dispatcher principal para eventos de páginas.
        
        Mapea topic a handler específico:
        - pages/create → handle_page_upsert()
        - pages/update → handle_page_upsert()
        - pages/delete → handle_page_delete()
        
        Args:
            page_id: ID de la página afectada
            page_handle: Handle (slug), para logging y cache invalidation
            topic: Topic del webhook de Shopify
        """
        start_time = time.time()
        
        try:
            # ── Idempotency check ─────────────────────────────────────────
            if await self.is_duplicate_event(page_id, topic):
                return  # Ya procesado, salir silenciosamente
            
            # ── Routing por topic ─────────────────────────────────────────
            if topic in ("pages/create", "pages/update"):
                await self._handle_page_upsert(page_id, page_handle)
            elif topic == "pages/delete":
                await self._handle_page_delete(page_id, page_handle)
            else:
                logger.warning(
                    "webhook_unknown_topic",
                    topic=topic,
                    page_id=page_id,
                )
                return
            
            # ── Métricas ──────────────────────────────────────────────────
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                "webhook_processed_successfully",
                page_id=page_id,
                topic=topic,
                duration_ms=round(elapsed_ms, 2),
            )
            
            try:
                from src.api.core.prometheus_metrics import (
                    kb_webhook_processed_total,
                    kb_webhook_processing_seconds,
                )
                kb_webhook_processed_total.labels(topic=topic, result="success").inc()
                kb_webhook_processing_seconds.observe(elapsed_ms / 1000)
            except ImportError:
                pass
        
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(
                "webhook_processing_failed",
                page_id=page_id,
                topic=topic,
                error=str(e),
                duration_ms=round(elapsed_ms, 2),
            )
            try:
                from src.api.core.prometheus_metrics import kb_webhook_processed_total
                kb_webhook_processed_total.labels(topic=topic, result="error").inc()
            except ImportError:
                pass
            raise
    
    async def _handle_page_upsert(self, page_id: int, page_handle: str) -> None:
        """
        Sincroniza una página específica (create o update).
        
        Este método es el corazón del incremental sync:
        en lugar de sync_all_pages(), solo sincroniza la página afectada.
        
        Args:
            page_id: ID de la página a sincronizar
            page_handle: Handle, para cache invalidation
        """
        sync_service = await self._get_sync_service()
        
        logger.info(
            "webhook_syncing_page",
            page_id=page_id,
            page_handle=page_handle,
        )
        
        # sync_single_page() es el nuevo método que extraeremos de
        # sync_all_pages() en ShopifyKBSyncService
        await sync_service.sync_single_page(page_id)
        
        # Invalidar cache Redis para esta página
        await self._invalidate_page_cache(page_id, page_handle)
    
    async def _handle_page_delete(self, page_id: int, page_handle: str) -> None:
        """
        Elimina el contenido de KB para una página eliminada en Shopify.
        
        Args:
            page_id: ID de la página eliminada
            page_handle: Handle, para cache invalidation
        """
        sync_service = await self._get_sync_service()
        
        logger.info(
            "webhook_deleting_page",
            page_id=page_id,
            page_handle=page_handle,
        )
        
        await sync_service.delete_kb_for_page(page_id)
        await self._invalidate_page_cache(page_id, page_handle)
    
    async def _invalidate_page_cache(self, page_id: int, page_handle: str) -> None:
        """
        Invalida las entradas de cache Redis relacionadas con esta página.
        
        Args:
            page_id: ID de la página
            page_handle: Handle/slug de la página
        """
        redis = await self._get_redis()
        
        cache_patterns = [
            f"kb:page:{page_id}:*",
            f"kb:handle:{page_handle}:*",
            f"kb:sync:status:page:{page_id}",
        ]
        
        for pattern in cache_patterns:
            try:
                await redis.delete(pattern)
                logger.debug(
                    "cache_invalidated",
                    pattern=pattern,
                    page_id=page_id,
                )
            except Exception as e:
                # La invalidación de cache no debe bloquear el sync
                logger.warning(
                    "cache_invalidation_failed",
                    pattern=pattern,
                    error=str(e),
                )
```

### 3.4 Extracción de `sync_single_page()` en `ShopifyKBSyncService`

Este es el cambio más importante en código existente: extraer la lógica de sincronización de una página individual desde `sync_all_pages()`.

```python
# En src/api/services/shopify_kb_sync.py — NUEVO MÉTODO

async def sync_single_page(self, page_id: int) -> dict:
    """
    Sincroniza una única página de Shopify a la KB.
    
    Extraído desde sync_all_pages() para soportar incremental sync via webhooks.
    La lógica es idéntica a como se procesa cada página en sync_all_pages(),
    pero aplicada a una sola página.
    
    Protegido por M3 (distributed_lock) si KB_DISTRIBUTED_LOCKS=true.
    
    Args:
        page_id: ID de la página Shopify a sincronizar
    
    Returns:
        dict con resultado: {"status": "synced"|"skipped"|"error", "languages": [...]}
    
    Raises:
        ValueError: Si page_id no corresponde a una página KB válida
        ShopifyAPIError: Si falla la llamada a Shopify API
    """
    logger.info("sync_single_page_started", page_id=page_id)
    
    # 1. Fetch página desde Shopify
    page = await self.shopify.get_page(page_id)
    if not page:
        logger.warning("sync_single_page_not_found", page_id=page_id)
        raise ValueError(f"Page {page_id} not found in Shopify")
    
    # 2. Validar metafields KB
    metafields = await self.shopify.get_page_metafields(page_id)
    kb_metadata = self.metadata_parser.parse(metafields)
    
    if not kb_metadata.get("sub_intent"):
        logger.info(
            "sync_single_page_skipped_no_metadata",
            page_id=page_id,
            handle=page.handle,
        )
        return {"status": "skipped", "reason": "no_kb_metadata"}
    
    # 3. Para cada idioma configurado, sincronizar
    synced_languages = []
    errors = []
    
    for language in self._configured_languages:  # ["es", "en", ...]
        try:
            # Fetch traducción para este idioma
            translated_content = await self.shopify.get_page_translation(
                page_id, language
            )
            translated_title = await self.shopify.get_page_title_translation(
                page_id, language
            )
            
            # Upsert en DB (protegido por distributed_lock si activo)
            await self._upsert_kb_content(
                sub_intent=kb_metadata["sub_intent"],
                language=language,
                category=kb_metadata.get("category"),
                content=translated_content.text,
                content_html=translated_content.html,
                title=translated_title or page.title,
                shopify_page_id=page_id,
                shopify_url=page.url,
                shopify_handle=page.handle,
            )
            synced_languages.append(language)
            
        except Exception as e:
            logger.error(
                "sync_single_page_language_error",
                page_id=page_id,
                language=language,
                error=str(e),
            )
            errors.append({"language": language, "error": str(e)})
    
    result = {
        "status": "synced" if not errors else "partial",
        "page_id": page_id,
        "handle": page.handle,
        "languages_synced": synced_languages,
        "errors": errors,
    }
    
    logger.info("sync_single_page_completed", page_id=page_id, **result)
    return result
```

---

## 4. CONFIGURACIÓN DE WEBHOOKS EN SHOPIFY

### 4.1 Registro del Webhook (Shopify Admin API)

Los webhooks deben registrarse programáticamente o desde el dashboard de Shopify Partners. Para el sistema, se registran via API al startup:

```python
# src/api/core/shopify_webhook_registry.py (NUEVO)

REQUIRED_WEBHOOKS = [
    {
        "topic": "pages/create",
        "address": "{APP_URL}/api/webhooks/shopify/page-updated",
        "format": "json",
    },
    {
        "topic": "pages/update",
        "address": "{APP_URL}/api/webhooks/shopify/page-updated",
        "format": "json",
    },
    {
        "topic": "pages/delete",
        "address": "{APP_URL}/api/webhooks/shopify/page-updated",
        "format": "json",
    },
]

async def ensure_webhooks_registered(shopify_client, app_url: str):
    """
    Verifica que los webhooks estén registrados en Shopify.
    Registra los que falten. Idempotente (seguro llamar múltiples veces).
    """
    existing = await shopify_client.get_webhooks()
    existing_topics = {w["topic"] for w in existing}
    
    for webhook_config in REQUIRED_WEBHOOKS:
        if webhook_config["topic"] not in existing_topics:
            await shopify_client.create_webhook({
                **webhook_config,
                "address": webhook_config["address"].replace("{APP_URL}", app_url),
            })
            logger.info(
                "webhook_registered",
                topic=webhook_config["topic"],
                app_url=app_url,
            )
```

### 4.2 Variables de Entorno Nuevas

| Variable | Ejemplo | Descripción |
|----------|---------|-------------|
| `SHOPIFY_WEBHOOK_SECRET` | `whsec_abc123...` | Secreto para validar HMAC (desde Shopify Partners Dashboard) |
| `APP_PUBLIC_URL` | `https://mi-app.run.app` | URL pública para registro de webhooks |
| `KB_WEBHOOK_IDEMPOTENCY_TTL` | `300` | TTL en segundos para idempotency keys (default: 300) |
| `KB_WEBHOOKS_ENABLED` | `true` | Feature flag para activar webhook processing |

---

## 5. MÉTRICAS PROMETHEUS NUEVAS

```python
# Añadir a prometheus_metrics.py

# ── Webhooks ──────────────────────────────────────────────────────────────
kb_webhook_received_total = Counter(
    "kb_webhook_received_total",
    "Total webhooks recibidos de Shopify",
    ["topic"],
)

kb_webhook_processed_total = Counter(
    "kb_webhook_processed_total",
    "Total webhooks procesados (con resultado)",
    ["topic", "result"],  # result: success | error | duplicate | skipped
)

kb_webhook_processing_seconds = Histogram(
    "kb_webhook_processing_seconds",
    "Tiempo de procesamiento de webhook de page sync",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

kb_webhook_hmac_failures_total = Counter(
    "kb_webhook_hmac_failures_total",
    "Webhooks rechazados por HMAC inválido (potencial ataque)",
)
```

**Alertas recomendadas:**
```promql
# Tasa de fallos HMAC (posible ataque)
rate(kb_webhook_hmac_failures_total[5m]) > 5

# Webhook latency P95 > 2s (fuera del SLA)
histogram_quantile(0.95, rate(kb_webhook_processing_seconds_bucket[5m])) > 2

# Tasa de error > 5%
rate(kb_webhook_processed_total{result="error"}[5m])
  / rate(kb_webhook_processed_total[5m]) > 0.05
```

---

## 6. PLAN DE IMPLEMENTACIÓN

### Semana 1 — Core Implementation (3-4 días)

**Día 1: Seguridad y Endpoint**
- [ ] Crear `webhook_security.py` con `validate_shopify_webhook()`
- [ ] Crear `webhooks_router.py` con el endpoint POST
- [ ] Registrar router en `main_unified_redis.py`
- [ ] Tests unitarios de validación HMAC

**Día 2: Webhook Handler y sync_single_page()**
- [ ] Crear `shopify_webhook_handler.py`
- [ ] Extraer `sync_single_page()` de `sync_all_pages()` en `shopify_kb_sync.py`
- [ ] Añadir `delete_kb_for_page()` en `shopify_kb_sync.py`
- [ ] Tests unitarios del handler

**Día 3: Idempotency + Métricas**
- [ ] Implementar `is_duplicate_event()` con Redis
- [ ] Añadir métricas Prometheus a `prometheus_metrics.py`
- [ ] Tests integración de idempotency

**Día 4: Registro en Shopify + e2e tests**
- [ ] Crear `shopify_webhook_registry.py`
- [ ] Hook de registro al startup de la app
- [ ] Tests e2e completos
- [ ] Documentación

### Semana 2 — Hardening y Validación (2-3 días)

**Día 5: Retry handling**
- [ ] Implementar retry queue con Redis para webhooks fallidos
- [ ] Dead letter queue para webhooks que fallan consistentemente
- [ ] Alertas Prometheus

**Día 6-7: Testing en staging**
- [ ] Desplegar en Cloud Run staging
- [ ] Configurar webhook real en Shopify (staging store)
- [ ] Validar latencia end-to-end (<2s)
- [ ] Load test: 100 webhooks simultáneos

---

## 7. ESTRATEGIA DE TESTING

### Tests Unitarios

```python
# tests/unit/test_webhook_handler.py

class TestWebhookSecurity:
    def test_valid_hmac_accepted(self)
    def test_invalid_hmac_rejected(self)
    def test_timing_attack_resistance(self)  # compare_digest
    def test_empty_payload(self)

class TestWebhookIdempotency:
    async def test_first_event_processed(self)
    async def test_duplicate_event_skipped(self)
    async def test_ttl_expiry_allows_reprocessing(self)
    async def test_different_topics_same_page_not_confused(self)

class TestWebhookRouting:
    async def test_pages_create_routes_to_upsert(self)
    async def test_pages_update_routes_to_upsert(self)
    async def test_pages_delete_routes_to_delete(self)
    async def test_unknown_topic_logged_not_crashed(self)
```

### Tests de Integración

```python
# tests/integration/webhooks/test_webhook_e2e.py

class TestWebhookEndpoint:
    async def test_valid_webhook_returns_200(self)
    async def test_invalid_hmac_returns_401(self)
    async def test_missing_hmac_returns_401(self)
    async def test_duplicate_webhook_returns_200_but_skips(self)
    async def test_page_synced_after_webhook(self)    # DB verifica el sync
    async def test_cache_invalidated_after_sync(self) # Redis verifica invalidación

class TestWebhookConcurrency:
    async def test_concurrent_webhooks_same_page_no_corruption(self)
    async def test_concurrent_webhooks_different_pages_all_processed(self)
```

### Simulación de Webhook Shopify en Tests

```python
def build_shopify_webhook_request(
    page_id: int,
    page_handle: str,
    topic: str,
    secret: str,
) -> dict:
    """
    Construye un request de webhook de Shopify simulado con HMAC válido.
    Útil para tests de integración.
    """
    import json, hmac, hashlib, base64
    
    payload = {"id": page_id, "handle": page_handle}
    body_bytes = json.dumps(payload).encode("utf-8")
    
    hmac_value = base64.b64encode(
        hmac.new(secret.encode(), body_bytes, hashlib.sha256).digest()
    ).decode()
    
    return {
        "body": body_bytes,
        "headers": {
            "X-Shopify-Hmac-Sha256": hmac_value,
            "X-Shopify-Topic": topic,
            "X-Shopify-Shop-Domain": "test-store.myshopify.com",
            "Content-Type": "application/json",
        }
    }
```

---

## 8. CONSIDERACIONES DE RIESGO

### Riesgo 1: At-Least-Once Delivery de Shopify

**Riesgo**: Shopify puede enviar el mismo webhook múltiples veces si no recibe ACK en 5s.
**Mitigación**: Idempotency keys en Redis (implementado en §3.3).
**Probabilidad**: Alta (comportamiento normal de Shopify).
**Impacto**: Sin mitigación → doble procesamiento, posible duplicación de logs.

### Riesgo 2: Shopify Rate Limits en sync_single_page()

**Riesgo**: Si llegan 50 webhooks en 1 minuto (por una importación masiva), sync_single_page() hará 50 × 3 llamadas API = 150 requests a Shopify.
**Mitigación**: 
1. Feature flag `KB_WEBHOOKS_ENABLED=false` para rollback inmediato.
2. Debouncing: Si se reciben >N webhooks para el mismo page_id en 30s, colapsar en un solo sync.
3. Fallback: Para bulk imports, usar full sync en lugar de webhooks.

### Riesgo 3: Webhook Secret Leak

**Riesgo**: Si `SHOPIFY_WEBHOOK_SECRET` se expone, cualquiera puede forjar webhooks.
**Mitigación**:
1. Almacenar en Google Secret Manager, nunca en código o logs.
2. Rotar el secreto si se sospecha compromiso (Shopify permite múltiples secretos activos).
3. Monitorear `kb_webhook_hmac_failures_total` — picos indican ataque o configuración incorrecta.

### Riesgo 4: Background Task Silently Fails

**Riesgo**: Las `BackgroundTasks` de FastAPI no tienen retry automático. Si `_process_page_webhook()` falla, el webhook se pierde.
**Mitigación**:
1. Logging comprehensivo de todos los errores.
2. Prometheus alert en `kb_webhook_processed_total{result="error"}`.
3. Fase 2 (hardening): Redis-backed retry queue para fallos.
4. Full sync semanal como safety net para pages que se perdieron.

---

## 9. COMPATIBILIDAD CON ARQUITECTURA EXISTENTE

### Coexistencia Full Sync + Webhook Sync

M4 no elimina el full sync periódico — **los complementa**:

```
Webhook Sync (M4):
  → Reactividad: cambios individuales en <2s
  → Evento: pages/create, pages/update, pages/delete

Full Sync (existente):
  → Safety net: captura cambios que perdió el webhook
  → Frecuencia: 1 vez/día o manual
  → Caso de uso: deployments, Redis outages, bulk imports
```

**Configuración recomendada en producción:**
```
ENABLE_WEBHOOKS=true          # M4: sync real-time
SYNC_CRON_SCHEDULE="0 2 * * *"  # Full sync a las 2am como backup
```

### Integración con M3 (Distributed Locking)

`sync_single_page()` llama a `_upsert_kb_content()`, que ya incluye el distributed lock de M3. No se requiere ningún cambio adicional — la protección cross-instance aplica automáticamente.

```
Webhook recibido (Cloud Run instancia A)
  └── sync_single_page(123)
      └── _upsert_kb_content("policy_return", "es", "general")
          └── async with redis.distributed_lock("kb_sync:lock:policy_return:es:general")
              └── await conn.execute(UPSERT_QUERY)
                                          ▲
                                          M3 garantiza que si instancia B también
                                          recibe el mismo webhook, espera aquí.
```

---

## 10. LEARNING OPPORTUNITIES ANTICIPADAS

### Seguridad: HMAC-SHA256 y Timing Attacks

La validación de webhooks enseña por qué la comparación de hashes no puede hacerse con `==`:

```python
# VULNERABLE a timing attack
if computed == received:  # ← termina early si hay diferencia

# SEGURO
import hmac
if hmac.compare_digest(computed, received):  # ← siempre tarda lo mismo
```

**Valor pedagógico**: Este es un patrón que aparece en tokens JWT, API keys, signatures, y cualquier validación criptográfica.

### Arquitectura: At-Least-Once vs Exactly-Once Delivery

Shopify (como la mayoría de sistemas de mensajería) garantiza **at-least-once** delivery: el mensaje llegará al menos una vez, posiblemente más. Los sistemas que requieren exactly-once deben implementar idempotency en el receptor.

**Patrón del sistema**:
```
Shopify (at-least-once)
    → Backend (idempotency key en Redis)
    → DB (UPSERT: insert or update, no duplica)
    = Comportamiento effectively exactly-once
```

### FastAPI: BackgroundTasks vs asyncio.create_task()

```python
# BackgroundTasks: gestionado por FastAPI, ejecuta DESPUÉS de enviar response
background_tasks.add_task(mi_funcion, arg1, arg2)

# create_task: Python nativo, puede ejecutar ANTES o DURANTE la response
asyncio.create_task(mi_funcion(arg1, arg2))
```

Para webhooks, `BackgroundTasks` es el patrón correcto porque garantiza que el 200 OK llega a Shopify antes de cualquier procesamiento.

---

## CHECKLIST PRE-IMPLEMENTACIÓN

- [ ] Verificar que `SHOPIFY_WEBHOOK_SECRET` está disponible en Secret Manager
- [ ] Confirmar URL pública del servicio Cloud Run para registro de webhooks
- [ ] Crear staging store en Shopify para pruebas end-to-end
- [ ] Verificar que Redis está disponible y `KB_DISTRIBUTED_LOCKS=true` en staging
- [ ] Confirmar que `sync_single_page()` puede extraerse sin romper `sync_all_pages()`
- [ ] Revisar Shopify rate limits para el plan actual (páginas/min)
- [ ] Definir qué topics de webhook registrar (pages solamente, o también metafields)

---

*Plan creado: 2026-02-25*
*Prerrequisitos confirmados: M1 ✅ M2 ✅ M3 ✅*
*Estimación: 6-7 días de implementación + 2-3 días de hardening*
*Siguiente documento: DCT_M4_IMPLEMENTACION.md (al iniciar la fase)*
