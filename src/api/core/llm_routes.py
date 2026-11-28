# src/api/core/llm_routes.py
"""
Registro de QUE CAMINO produjo el texto de cada uso de LLM (paso 1, 25/11/2026)
==============================================================================

Por que existe este modulo
--------------------------
Tres usos del sistema generan texto con un LLM y cada uno tiene una cascada de
"escalones" que se prueban en orden hasta que uno responde:

    Uso                     Escalones (en orden)                         Ultimo recurso sin LLM
    ----------------------  -------------------------------------------  -----------------------------
    kb_reformulation        lfm -> main_model -> claude                  document_as_is (el documento KB tal cual)
                            (+ template: respuesta fija sin LLM para
                             producto agotado)
    product_redactor        lfm -> main_model -> claude                  generic_message ("Te ayudo a encontrar...")
    visual_search_message   lfm -> main_model                            no_message (el frontend usa su plantilla)

R-32 M4 (27/11/2026) anade un cuarto uso que no produce texto sino una DECISION de
enrutado: intent_router (llm_intent_router.py). Sus "caminos" dicen que decidio:
topic (una pagina de ayuda), product_search (busqueda de productos), no_label (el
modelo dijo "none" o algo que no es una etiqueta: se mantiene el menu) y failed
(tiempo agotado o error: se mantiene el menu) y breaker_open (corte automatico
abierto tras fallos seguidos: no se llama al LLM y se mantiene el menu, 28/11/2026).

Hasta hoy solo se podia saber que escalon respondio leyendo logs sueltos, con
nombres distintos en cada fichero. Con LFM apagado y Claude apuntando a un modelo
retirado (R-11), "main_model" responde el 100 % del trafico, pero nadie lo podia
comprobar con una cifra. Al cambiar el modelo principal (paso 2) necesitamos ver,
por uso, cuantas respuestas salen de cada escalon antes y despues del cambio.

Que hace
--------
- Define los nombres de uso y de camino como constantes (un error tipografico en
  un llamador falla en las pruebas, no en produccion).
- `record_llm_route(use, route)` incrementa el contador Prometheus
  `recommender_llm_route_total{use, route}` (definido en prometheus_metrics.py).
  El prefijo `recommender_` hace que gcp_metrics_exporter.py lo exporte a Cloud
  Monitoring sin tocar el exportador.

Garantias de diseno
-------------------
- NUNCA lanza excepciones: medir no puede romper una respuesta al cliente. Si
  prometheus_client no esta disponible o el contador falla, se registra un aviso
  y se sigue.
- Solo acepta combinaciones (uso, camino) conocidas: evita que un valor
  inesperado cree series nuevas sin control (cardinalidad) en Cloud Monitoring.
- No importa prometheus_metrics al cargar el modulo (import perezoso dentro de
  la funcion), igual que el resto del repo (redis_service.py, webhooks_router.py):
  asi este modulo no anade dependencias de import a quien lo use.
"""

import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

# ─── Usos ──────────────────────────────────────────────────────────────────────
USE_KB_REFORMULATION = "kb_reformulation"            # kb_contextualizer.generate_contextual_answer
USE_PRODUCT_REDACTOR = "product_redactor"            # MCPPersonalizationEngine._generate_claude_personalized_response
USE_VISUAL_SEARCH_MESSAGE = "visual_search_message"  # visual_search_router._generate_visual_search_message
USE_INTENT_ROUTER = "intent_router"                  # llm_intent_router.classify_unknown_route (R-32 M4)

# ─── Caminos ───────────────────────────────────────────────────────────────────
ROUTE_LFM = "lfm"                          # modelo Liquid (LFM_KB_ENABLED / LFM_MCP_ENABLED)
ROUTE_MAIN_MODEL = "main_model"            # modelo principal de OpenRouter del uso (hoy GPT-4o-mini)
ROUTE_CLAUDE = "claude"                    # respaldo Anthropic (CLAUDE_MODEL_TIER)
ROUTE_TEMPLATE = "template"                # texto fijo sin LLM (KB: producto agotado)
ROUTE_DOCUMENT_AS_IS = "document_as_is"    # KB: ningun LLM respondio; se sirve el documento tal cual
ROUTE_GENERIC_MESSAGE = "generic_message"  # redactor: ningun LLM respondio; mensaje generico
ROUTE_NO_MESSAGE = "no_message"            # busqueda visual: ningun LLM respondio; plantilla del frontend
# Caminos del enrutado con LLM (R-32 M4): que decidio la capa de rescate
ROUTE_ROUTER_TOPIC = "topic"                    # el LLM eligio una pagina de ayuda
ROUTE_ROUTER_PRODUCT_SEARCH = "product_search"  # el LLM dijo que es una compra -> busqueda de productos
ROUTE_ROUTER_NO_LABEL = "no_label"              # "none" o respuesta no valida -> se mantiene el menu
ROUTE_ROUTER_FAILED = "failed"                  # tiempo agotado o error -> se mantiene el menu
ROUTE_ROUTER_BREAKER_OPEN = "breaker_open"      # corte automatico abierto: sin llamada -> se mantiene el menu

# Combinaciones validas (uso -> caminos posibles). Es la unica fuente de verdad:
# prometheus_metrics.py la usa para pre-inicializar las series a 0 y
# record_llm_route() para rechazar combinaciones desconocidas.
LLM_ROUTES_BY_USE: Dict[str, Tuple[str, ...]] = {
    USE_KB_REFORMULATION: (
        ROUTE_LFM, ROUTE_MAIN_MODEL, ROUTE_CLAUDE, ROUTE_TEMPLATE, ROUTE_DOCUMENT_AS_IS,
    ),
    USE_PRODUCT_REDACTOR: (
        ROUTE_LFM, ROUTE_MAIN_MODEL, ROUTE_CLAUDE, ROUTE_GENERIC_MESSAGE,
    ),
    USE_VISUAL_SEARCH_MESSAGE: (
        ROUTE_LFM, ROUTE_MAIN_MODEL, ROUTE_NO_MESSAGE,
    ),
    USE_INTENT_ROUTER: (
        ROUTE_ROUTER_TOPIC, ROUTE_ROUTER_PRODUCT_SEARCH, ROUTE_ROUTER_NO_LABEL, ROUTE_ROUTER_FAILED,
        ROUTE_ROUTER_BREAKER_OPEN,
    ),
}


def record_llm_route(use: str, route: str) -> None:
    """
    Cuenta una respuesta del uso `use` producida por el camino `route`.

    Se llama exactamente una vez por cada texto (o ausencia de texto) que el uso
    entrega a su llamador. No lanza nunca: cualquier problema se registra como aviso.
    """
    # 1. Validar la combinacion ANTES de tocar Prometheus (control de cardinalidad).
    if route not in LLM_ROUTES_BY_USE.get(use, ()):
        logger.warning("llm_route_unknown_combination use=%s route=%s (no se cuenta)", use, route)
        return
    # 2. Incrementar el contador. Import perezoso: ver docstring del modulo.
    try:
        from src.api.core.prometheus_metrics import llm_route_total
        llm_route_total.labels(use=use, route=route).inc()
    except Exception as metric_error:  # noqa: BLE001 -- medir nunca rompe la respuesta
        logger.warning("llm_route_metric_error use=%s route=%s error=%s", use, route, metric_error)
