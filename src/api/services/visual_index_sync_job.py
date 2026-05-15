# src/api/services/visual_index_sync_job.py
"""
OPM-1 (08/05/2026) — Visual Index Incremental Sync Job
==========================================================

Cierra la brecha entre webhooks y el índice FAISS del visual search.

PROBLEMA QUE RESUELVE:
─────────────────────────────────────────────────────────────────────
Los webhooks products/create y products/update ya llaman a
colbert_client.index_images_incremental() para cada producto individual.
Sin embargo, pueden quedar productos sin indexar por:
  1. Webhook perdido (Shopify garantiza at-least-once, no exactly-once)
  2. Productos en el catálogo antes del deploy de Visual Search
  3. Cold start del monolito durante un products/create

JERARQUÍA DE MECANISMOS DE INDEXACIÓN:
  Webhooks products/create/update → index_images_incremental()  (inmediato, < 1min)
  Este job → reconciliación cada N horas                        (fallback, 6h default)
  Cloud Scheduler → rebuild completo semanal (Lunes 02:00)      (mantenimiento)

DISEÑO:
  1. Lee el catálogo TF-IDF en memoria (sin llamadas a Shopify)
  2. Filtra productos con image_url válida
  3. Envía al embedding-service via index_images_incremental()
     → el embedding-service filtra IDs ya en FAISS (idempotente)
     → solo indexa los que faltan

FEATURE FLAGS:
  VISUAL_SEARCH_ENABLED=false           → ciclo se salta sin trabajo
  PRODUCT_VISUAL_SYNC_INTERVAL_HOURS=6  → intervalo entre ciclos (default: 6h)
  PRODUCT_VISUAL_SYNC_INITIAL_DELAY_S=120 → delay post-startup (default: 2min)

INTEGRACIÓN EN main_unified_redis.py:
  Ver instrucciones en apply_opm1_to_main.py
"""

import os
import time
import asyncio
import logging
import structlog

logger = structlog.get_logger(__name__)


async def run_visual_index_sync_job(product_catalog: list) -> None:
    """
    Background task: reconciliación periódica del índice FAISS con el catálogo TF-IDF.

    Args:
        product_catalog: Lista de dicts del catálogo TF-IDF en memoria.
                         Compartida por referencia — cambios en el catálogo
                         (ej. enriquecimiento de colecciones post-startup)
                         son visibles automáticamente en el siguiente ciclo
                         sin necesidad de reiniciar el job.
    """
    # ── Configuración desde env vars ───────────────────────────────────────────
    interval_hours   = int(os.getenv("PRODUCT_VISUAL_SYNC_INTERVAL_HOURS", "6"))
    interval_seconds = interval_hours * 3600

    # Delay inicial: esperar a que el warm-up de Claude, el enriquecimiento
    # de precios y colecciones terminen antes de añadir carga al embedding-service.
    initial_delay = int(os.getenv("PRODUCT_VISUAL_SYNC_INITIAL_DELAY_S", "120"))

    logger.info(
        "opm1_visual_sync_job_started",
        initial_delay_seconds=initial_delay,
        interval_hours=interval_hours,
        catalog_size=len(product_catalog),
        note="FAISS gap reconciliation active — complements product webhooks",
    )

    # Espera inicial antes del primer ciclo
    await asyncio.sleep(initial_delay)

    cycle = 0
    while True:
        cycle += 1

        # ── Feature flag: releer en cada ciclo ────────────────────────────────
        # Puede cambiar sin redeploy con: gcloud run services update --set-env-vars
        if os.environ.get("VISUAL_SEARCH_ENABLED", "false").lower() != "true":
            logger.debug(
                "opm1_visual_sync_cycle_skipped",
                cycle=cycle,
                reason="VISUAL_SEARCH_ENABLED=false",
            )
            await asyncio.sleep(interval_seconds)
            continue

        t0 = time.time()
        logger.info(
            "opm1_visual_sync_cycle_started",
            cycle=cycle,
            catalog_size=len(product_catalog),
        )

        try:
            # ── Paso 1: Extraer productos con image_url del catálogo TF-IDF ──
            # El catálogo ya está en memoria — sin llamadas adicionales a Shopify.
            # Formato requerido por index_images_incremental():
            #   [{id: str, title: str, image_url: str}]
            #
            # Filtramos URLs que empiezan con "http" para descartar placeholders
            # vacíos o rutas relativas que causarían errores en el embedding-service.
            products_with_image = [
                {
                    "id":           str(p.get("id", "")),
                    "title":        str(p.get("title", "")),
                    "image_url":    str(p.get("image_url", "")),
                    # S1: product_type para poblar category_map en indexación incremental
                    "product_type": str(p.get("product_type", "")),
                }
                for p in product_catalog
                if p.get("image_url") and str(p.get("image_url", "")).startswith("http")
            ]

            if not products_with_image:
                # Puede ocurrir durante los primeros minutos del startup si el
                # enriquecimiento de colecciones/precios aún no ha terminado.
                logger.warning(
                    "opm1_visual_sync_no_images_in_catalog",
                    cycle=cycle,
                    total_products=len(product_catalog),
                    note="image_url field may not be populated yet in TF-IDF catalog",
                )
                await asyncio.sleep(interval_seconds)
                continue

            logger.info(
                "opm1_visual_sync_sending_to_embedding_service",
                cycle=cycle,
                products_with_image=len(products_with_image),
                total_in_catalog=len(product_catalog),
                without_image=len(product_catalog) - len(products_with_image),
                note="embedding-service will filter already-indexed IDs automatically",
            )

            # ── Paso 2: Llamar al embedding-service ───────────────────────────
            # index_images_incremental() filtra internamente los IDs ya presentes
            # en el índice FAISS — solo indexa los que faltan.
            # Completamente idempotente: llamarlo con todos los productos no duplica
            # embeddings existentes.
            #
            # NOTA: No usamos _colbert_client_singleton del visual_search_router
            # porque es un módulo distinto con su propio scope de módulo.
            # LFM2ColBERTClient es liviano — el estado relevante (token IAM) viene
            # del metadata server de GCP en cada renovación, no de la instancia.
            from src.api.services.colbert_client import LFM2ColBERTClient
            _client = LFM2ColBERTClient()
            accepted = await _client.index_images_incremental(products_with_image)

            elapsed_ms = (time.time() - t0) * 1000

            if accepted:
                logger.info(
                    "opm1_visual_sync_cycle_completed",
                    cycle=cycle,
                    products_submitted=len(products_with_image),
                    elapsed_ms=round(elapsed_ms, 0),
                    note="embedding-service indexing new products in background (~seconds)",
                )
            else:
                # Dos causas posibles:
                #   a) El índice base FAISS no existe todavía:
                #      → Ejecutar POST /v1/mcp/visual-search/index (build completo)
                #   b) Circuit-breaker visual abierto (3 fallos seguidos):
                #      → Se cierra automáticamente en 60s
                logger.warning(
                    "opm1_visual_sync_cycle_rejected",
                    cycle=cycle,
                    elapsed_ms=round(elapsed_ms, 0),
                    possible_causes=[
                        "base FAISS index does not exist yet",
                        "visual circuit-breaker open (auto-resets in 60s)",
                    ],
                    action="run POST /v1/mcp/visual-search/index if base index missing",
                )

        except asyncio.CancelledError:
            # El lifespan de FastAPI está haciendo shutdown limpio (SIGTERM).
            # CancelledError se propaga para terminar el loop correctamente.
            logger.info(
                "opm1_visual_sync_job_cancelled",
                cycles_completed=cycle,
                reason="clean_shutdown_via_lifespan",
            )
            break

        except Exception as e:
            # Non-fatal: webhooks y Cloud Scheduler siguen activos.
            # Logueamos con exc_info para diagnóstico completo y continuamos.
            # El job intenta el siguiente ciclo después de dormir.
            logger.error(
                "opm1_visual_sync_cycle_error",
                cycle=cycle,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
                note=f"non_fatal_retrying_in_{interval_hours}h",
            )

        # ── Dormir hasta el siguiente ciclo ───────────────────────────────────
        await asyncio.sleep(interval_seconds)