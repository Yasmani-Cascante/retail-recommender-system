# src/api/core/llm_intent_router.py
"""
Capa de rescate del enrutado de intencion con un LLM (R-32 M4, 27/11/2026)
=========================================================================

Problema que resuelve
---------------------
Cuando el detector hibrido (reglas + sklearn + MiniLM) concluye que un mensaje es
INFORMATIVO pero no sabe de que tema (sub_intent = "unknown"), el chat responde con
el menu generico de ayuda. Muchos de esos mensajes tenian una pagina que los
responde ("¿cubre la garantia una cremallera rota?") o eran compras ("ideas de
regalo para mi padre, menos de 40"). Medido el 27/11 (DCT_Fidelidad_Reformulacion_KB_
23112026.md, 7.21-7.27): de 369 consultas de prueba, 79 acaban hoy en el menu.

Que hace
--------
SOLO para los mensajes que hoy acabarian en el menu de ayuda (disparador "T1"):
1. Pregunta a un LLM pequeno (gpt-4.1-mini por defecto en env-vars.yaml) que pagina
   de ayuda responde el mensaje, con una lista cerrada de 13 etiquetas.
2. Si responde un tema -> el mensaje va a esa pagina de la base de conocimiento.
   Si responde "product_search" -> el mensaje va a la busqueda de productos.
   Si responde "none", una etiqueta desconocida, tarda demasiado o falla ->
   se mantiene el menu de ayuda (el comportamiento de antes; nunca peor que hoy).

Por que solo T1 (y no "el LLM decide siempre")
----------------------------------------------
Se midieron cinco formas de usar el LLM con tres versiones del prompt. Las que
dejan decidir al LLM casi todo acertaban mas (97 %), pero en un conjunto de
validacion nunca usado para ajustar perdian compras que hoy van bien ("un bikini
que me llegue antes del sabado" -> envios). T1 no puede empeorar nada: solo actua
donde hoy se entrega el menu. Criterio y resultados: DCT, 7.26 y 7.27.

El prompt
---------
Es EXACTAMENTE el prompt "v3" medido en el laboratorio (sha256 8691b753...). La
prueba unitaria compara el hash: cambiar una coma del prompt sin volver a medir
hace fallar las pruebas. Para cambiarlo: medir en el laboratorio, actualizar el
hash esperado de la prueba y documentarlo en el DCT.

Garantias de diseno
-------------------
- NUNCA lanza excepciones hacia el handler: cualquier fallo -> se mantiene el menu.
- Limite de tiempo propio (INTENT_ROUTER_TIMEOUT_S, 3 s por defecto; p95 medido
  1,2 s): un LLM lento no puede bloquear la respuesta mas que eso.
- Interruptor INTENT_ROUTER_ENABLED (apagado por defecto en el codigo; encendido en
  env-vars.yaml): se puede desactivar sin reconstruir la imagen.
- Corte automatico (circuit breaker, 28/11/2026): tras INTENT_ROUTER_BREAKER_FAILURES
  fallos SEGUIDOS (tiempo agotado o error; 3 por defecto) deja de llamar al LLM durante
  INTENT_ROUTER_BREAKER_COOLDOWN_S segundos (60 por defecto): esos mensajes reciben el
  menu al instante en vez de esperar 3 s cada uno. Pasado ese tiempo deja pasar UNA
  llamada de prueba: si responde, se cierra el corte; si falla, se vuelve a abrir.
  "none" o una etiqueta no valida NO cuentan como fallo (el LLM respondio).
  El estado es por instancia de Cloud Run (memoria del proceso), sin Redis: cada
  instancia descubre la caida por su cuenta con como mucho 3 esperas.
- Cada decision se cuenta en recommender_llm_route_total{use="intent_router"} y se
  registra en el log con un token fijo (`intent_llm_router`) para poder contarla.
- La clave de OpenRouter la lee UnifiedLLMClient de OPENROUTER_API_KEY (secreto);
  este modulo nunca la toca ni la escribe en logs.
"""

import asyncio
import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Optional

from src.api.core.intent_types import IntentDetectionResult, IntentType
from src.api.core.llm_routes import (
    ROUTE_ROUTER_BREAKER_OPEN,
    ROUTE_ROUTER_FAILED,
    ROUTE_ROUTER_NO_LABEL,
    ROUTE_ROUTER_PRODUCT_SEARCH,
    ROUTE_ROUTER_TOPIC,
    USE_INTENT_ROUTER,
    record_llm_route,
)

logger = logging.getLogger(__name__)

# ─── Prompt v3 (laboratorio, 27/11/2026) ────────────────────────────────────────
# Una linea por pagina de ayuda de la tienda: resume el CONTENIDO de la pagina, no las
# preguntas de prueba. El orden importa (forma parte del prompt y de su hash).
# Las 11 primeras etiquetas son valores de InformationalSubIntent (paginas de la base
# de conocimiento); "product_search" y "none" son las dos salidas que no son paginas.
ROUTER_TOPICS = {
    "policy_return": "Returns and refunds: how to return a product, the 30-day return window, prepaid return label, refund processing time, refund to the original payment method.",
    "policy_shipping": "Shipping: destinations, delivery times and prices (standard, express, priority), free-shipping threshold, shipping contact.",
    "policy_payment": "Payment: accepted cards, PayPal, Apple Pay, Google Pay, bank transfer, interest-free installments, currencies, billing.",
    "policy_warranty": "Warranty and defects: what the quality warranty covers (manufacturing defects, faulty seams or materials), coverage period by product type, how to claim for an item that broke or arrived defective.",
    "policy_privacy": "Privacy and personal data: which personal data the store collects, how it is used and protected, cookies, data rights.",
    "product_material": "Materials and fabrics: characteristics of natural, synthetic and sustainable materials, blends, certifications, which fabric suits which use.",
    "product_sizing": "Size guide: how to measure, size charts and size conversions for clothing and shoes, fit advice.",
    "product_care": "Product care: washing, drying, ironing, storing and removing stains, by material and for shoes.",
    "product_availability": "Stock policy: when sold-out items or sizes are restocked, back-in-stock alerts, how stock is updated. Not for asking whether the store has a kind of product in some size or color (that is product_search).",
    "account_orders": "Orders: tracking an order and its status, processing times, what to do if an order is late or has a problem, time limits to modify or cancel an order.",
    "account_modifications": "Changing or cancelling an order: time limits, how to request a change (size, address, items) or a cancellation, refunds for cancellations.",
    "product_search": "The customer wants to find, browse or buy products, including 'do you have X (in size/color Y)?', outfit or styling advice ('what goes with X?', 'what should I wear to...?'), gift ideas, and product requests with conditions such as size, color, price, occasion or fast delivery. Not a question about a store policy.",
    "none": "None of the above (greetings, unrelated messages).",
}

# Etiquetas que NO son paginas de la base de conocimiento
LABEL_PRODUCT_SEARCH = "product_search"
LABEL_NONE = "none"
LABEL_INVALID = "invalid"   # respuesta que no es ninguna etiqueta (no la produce el modelo: la pone parse_router_label)

# Temas de pagina = todas las etiquetas menos las dos que no son paginas
ROUTER_KB_TOPICS = frozenset(label for label in ROUTER_TOPICS if label not in (LABEL_PRODUCT_SEARCH, LABEL_NONE))

# Misma plantilla que el laboratorio (r32_m4_llm.py, build_prompt): cabecera + "- etiqueta: definicion"
ROUTER_SYSTEM_PROMPT = (
    "You route messages from customers of an online fashion store to the help page that answers them.\n"
    "Messages can be in any language. Reply with exactly one label from this list and nothing else:\n"
    + "\n".join(f"- {label}: {description}" for label, description in ROUTER_TOPICS.items())
)
ROUTER_PROMPT_SHA256 = hashlib.sha256(ROUTER_SYSTEM_PROMPT.encode("utf-8")).hexdigest()

# Limite de tiempo por defecto (segundos). p50 medido 0,86 s y p95 1,2 s (27/11, 2 x 840 llamadas).
DEFAULT_TIMEOUT_S = 3.0

# Cliente reutilizado entre peticiones (mismo patron que kb_contextualizer: un singleton
# conserva el pool TCP/TLS y evita pagar la conexion en cada mensaje).
_router_client = None

# ─── Corte automatico (circuit breaker) ─────────────────────────────────────────
# Tres estados, como en el patron clasico:
#   cerrado     -> se llama al LLM normalmente; se cuentan los fallos seguidos.
#   abierto     -> no se llama al LLM hasta _breaker_open_until (respuesta: el menu).
#   semiabierto -> paso el tiempo de espera: UNA llamada de prueba decide si se cierra
#                  (respondio) o se vuelve a abrir (fallo). Mientras esa prueba esta en
#                  curso, el resto de mensajes no llaman (evita una avalancha de esperas).
# Todo ocurre en el bucle de asyncio de un proceso (un solo hilo): no hacen falta locks.
DEFAULT_BREAKER_FAILURES = 3        # fallos seguidos que abren el corte
DEFAULT_BREAKER_COOLDOWN_S = 60.0   # segundos sin llamar al LLM una vez abierto

_breaker_consecutive_failures = 0   # fallos seguidos desde la ultima respuesta del LLM
_breaker_open_until = 0.0           # instante (reloj monotono) hasta el que no se llama; 0 = cerrado
_breaker_trial_in_flight = False    # hay una llamada de prueba (semiabierto) en curso


@dataclass(frozen=True)
class RouterDecision:
    """Lo que decidio la capa de rescate para un mensaje."""
    label: str           # etiqueta normalizada (tema, product_search, none, invalid) o "" si no hubo respuesta
    route: str           # camino de la metrica: ROUTE_ROUTER_* (topic, product_search, no_label, failed)
    elapsed_ms: float    # tiempo de la llamada al LLM (0 si no se llamo)
    model: str = ""      # modelo que respondio (para el log)
    error: str = ""      # tipo de error si fallo (nunca el mensaje completo: puede llevar datos)


def is_router_enabled() -> bool:
    """Interruptor INTENT_ROUTER_ENABLED, leido en cada llamada (sin caches: leccion del 21/03/2026)."""
    return os.environ.get("INTENT_ROUTER_ENABLED", "false").strip().lower() in ("true", "1", "yes")


def _router_timeout_s() -> float:
    """INTENT_ROUTER_TIMEOUT_S (segundos). Un valor no numerico o <= 0 usa el valor por defecto."""
    raw = (os.environ.get("INTENT_ROUTER_TIMEOUT_S") or "").strip()
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_S
    return value if value > 0 else DEFAULT_TIMEOUT_S


def _env_number(name: str, default: float, minimum: float) -> float:
    """Lee un numero de la variable `name`; no numerico o menor que `minimum` -> `default`."""
    raw = (os.environ.get(name) or "").strip()
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value >= minimum else default


def _breaker_failure_limit() -> int:
    """INTENT_ROUTER_BREAKER_FAILURES: fallos seguidos que abren el corte (entero >= 1; 3 por defecto)."""
    return int(_env_number("INTENT_ROUTER_BREAKER_FAILURES", DEFAULT_BREAKER_FAILURES, 1))


def _breaker_cooldown_s() -> float:
    """INTENT_ROUTER_BREAKER_COOLDOWN_S: segundos con el corte abierto (> 0; 60 por defecto)."""
    return _env_number("INTENT_ROUTER_BREAKER_COOLDOWN_S", DEFAULT_BREAKER_COOLDOWN_S, 0.001)


def _now() -> float:
    """Reloj monotono (no salta con cambios de hora). Funcion aparte para que las pruebas lo controlen."""
    return time.monotonic()


def reset_breaker() -> None:
    """Vuelve al estado cerrado (pruebas y arranque)."""
    global _breaker_consecutive_failures, _breaker_open_until, _breaker_trial_in_flight
    _breaker_consecutive_failures = 0
    _breaker_open_until = 0.0
    _breaker_trial_in_flight = False


def _breaker_allows_call() -> bool:
    """
    ¿Se puede llamar al LLM ahora? Marca la llamada de prueba si toca (semiabierto).

    - Cerrado (_breaker_open_until == 0): si.
    - Abierto y aun dentro del tiempo de espera: no.
    - Tiempo de espera cumplido: si, pero solo UNA (la de prueba); las demas, no,
      hasta que esa prueba termine.
    """
    global _breaker_trial_in_flight
    if _breaker_open_until == 0.0:
        return True
    if _now() < _breaker_open_until or _breaker_trial_in_flight:
        return False
    _breaker_trial_in_flight = True
    logger.info("intent_llm_router_breaker state=half_open (llamada de prueba)")
    return True


def _breaker_record(success: bool) -> None:
    """
    Registra el resultado de una llamada real al LLM.

    success=True  -> el LLM respondio (cualquier etiqueta): se cierra el corte y el contador vuelve a 0.
    success=False -> tiempo agotado o error: +1 fallo seguido; al llegar al limite (o si fallo la
                     llamada de prueba) se abre el corte durante el tiempo de espera.
    """
    global _breaker_consecutive_failures, _breaker_open_until, _breaker_trial_in_flight
    was_trial = _breaker_trial_in_flight
    _breaker_trial_in_flight = False
    if success:
        if _breaker_open_until != 0.0:
            logger.info("intent_llm_router_breaker state=closed (el LLM vuelve a responder)")
        _breaker_consecutive_failures = 0
        _breaker_open_until = 0.0
        return
    _breaker_consecutive_failures += 1
    if was_trial or _breaker_consecutive_failures >= _breaker_failure_limit():
        cooldown = _breaker_cooldown_s()
        _breaker_open_until = _now() + cooldown
        # WARNING: es un estado degradado que alguien debe poder ver (y contar) en Cloud Logging
        logger.warning(
            "intent_llm_router_breaker state=open failures=%d cooldown_s=%.0f trial=%s",
            _breaker_consecutive_failures, cooldown, was_trial,
        )


def parse_router_label(text: Optional[str]) -> str:
    """
    Normaliza la respuesta del modelo a una etiqueta conocida, o "invalid".

    Identica a parse_label del laboratorio (r32_m4_llm.py), para que produccion lea
    las respuestas igual que se midieron:
      1. Quita espacios, comillas, acentos graves y puntos de los extremos; minusculas.
      2. Si es exactamente una etiqueta -> esa etiqueta.
      3. Si una (y solo una) etiqueta aparece como palabra suelta ("label: policy_return")
         -> esa etiqueta. Si aparecen varias o ninguna -> "invalid".
    """
    normalized = (text or "").strip().strip("`'\".").lower()
    if normalized in ROUTER_TOPICS:
        return normalized
    found = [label for label in ROUTER_TOPICS if re.search(rf"\b{re.escape(label)}\b", normalized)]
    return found[0] if len(found) == 1 else LABEL_INVALID


def should_rescue(intent_result: Optional[IntentDetectionResult], effective_threshold: float) -> bool:
    """
    ¿Este resultado acabaria hoy en el menu de ayuda? (disparador T1)

    Es la misma condicion con la que el handler entrega el menu: intencion INFORMATIVA,
    tema "unknown" y confianza suficiente para entrar en la rama informativa. Con
    confianza por debajo del umbral el mensaje ya va a productos y no se toca.
    """
    if intent_result is None:
        return False
    return (
        intent_result.primary_intent == IntentType.INFORMATIONAL
        and intent_result.sub_intent == "unknown"
        and intent_result.confidence >= effective_threshold
    )


def apply_router_decision(intent_result: IntentDetectionResult, decision: RouterDecision) -> IntentDetectionResult:
    """
    Devuelve el resultado de intencion que el handler debe usar despues del rescate.

    - Tema de pagina  -> INFORMATIONAL con ese sub_intent (misma confianza: sigue
                         entrando en la rama informativa, ahora con su pagina).
    - product_search  -> TRANSACTIONAL / product_search (misma convencion que usa el
                         detector hibrido cuando el ML cambia la intencion a compra).
    - Cualquier otra cosa (none, invalid, fallo) -> el MISMO objeto, sin cambios
                         (el menu de ayuda, como antes).
    Nunca modifica el objeto recibido (model_copy crea uno nuevo).
    """
    if decision.route == ROUTE_ROUTER_TOPIC and decision.label in ROUTER_KB_TOPICS:
        return intent_result.model_copy(update={
            "sub_intent": decision.label,
            "reasoning": f"LLM router (R-32 M4): topic={decision.label}; antes: {intent_result.reasoning}",
        })
    if decision.route == ROUTE_ROUTER_PRODUCT_SEARCH:
        return intent_result.model_copy(update={
            "primary_intent": IntentType.TRANSACTIONAL,
            "sub_intent": LABEL_PRODUCT_SEARCH,
            "reasoning": f"LLM router (R-32 M4): product_search; antes: {intent_result.reasoning}",
        })
    return intent_result


def _get_router_client():
    """Crea (una vez) el cliente OpenRouter con la configuracion propia de este uso."""
    global _router_client
    if _router_client is None:
        # Imports locales: este modulo se importa en el handler y no debe arrastrar
        # openai/anthropic si la capa esta apagada.
        from src.api.core.claude_config import get_intent_router_llm_config
        from src.api.core.llm_client import UnifiedLLMClient
        config = get_intent_router_llm_config()
        _router_client = UnifiedLLMClient(
            provider=config["provider"],
            model=config["model"],
            max_tokens=config["max_tokens"],
            temperature=config["temperature"],
        )
        logger.info(
            "intent_llm_router client created (use=%s model=%s model_source=%s max_tokens=%d "
            "temperature=%.1f prompt_sha256=%s)",
            config["use"], config["model"], config["model_source"], config["max_tokens"],
            config["temperature"], ROUTER_PROMPT_SHA256[:12],
        )
    return _router_client


async def classify_unknown_route(query: str) -> RouterDecision:
    """
    Pregunta al LLM que pagina responde `query`. NUNCA lanza excepciones.

    Devuelve un RouterDecision y cuenta la decision en la metrica. El texto del
    cliente no se escribe en el log (solo su longitud): puede contener datos personales.
    """
    start = time.perf_counter()
    if not _breaker_allows_call():
        # Corte abierto: sin llamada (el menu al instante). Se cuenta y se registra igual
        # que el resto de decisiones para que el tiempo con el corte abierto sea visible.
        decision = RouterDecision(label="", route=ROUTE_ROUTER_BREAKER_OPEN, elapsed_ms=0.0)
        record_llm_route(USE_INTENT_ROUTER, decision.route)
        logger.info(
            "intent_llm_router route=%s label=- ms=0 model=- error=- query_chars=%d",
            decision.route, len(query or ""),
        )
        return decision
    try:
        client = _get_router_client()
        response = await asyncio.wait_for(
            client.complete(ROUTER_SYSTEM_PROMPT, query),
            timeout=_router_timeout_s(),
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        label = parse_router_label(response.content)
        if label in ROUTER_KB_TOPICS:
            route = ROUTE_ROUTER_TOPIC
        elif label == LABEL_PRODUCT_SEARCH:
            route = ROUTE_ROUTER_PRODUCT_SEARCH
        else:
            route = ROUTE_ROUTER_NO_LABEL   # none o invalid: se mantiene el menu
        decision = RouterDecision(label=label, route=route, elapsed_ms=elapsed_ms, model=response.model or "")
    except Exception as error:  # noqa: BLE001 -- la capa de rescate nunca rompe la respuesta
        elapsed_ms = (time.perf_counter() - start) * 1000
        # asyncio.TimeoutError no tiene mensaje: el tipo basta para distinguir tiempo agotado y error
        decision = RouterDecision(label="", route=ROUTE_ROUTER_FAILED, elapsed_ms=elapsed_ms,
                                  error=type(error).__name__)

    # El corte solo cuenta tiempo agotado y errores; "none"/"invalid" son respuestas del LLM
    _breaker_record(success=decision.route != ROUTE_ROUTER_FAILED)
    record_llm_route(USE_INTENT_ROUTER, decision.route)
    # Token fijo `intent_llm_router` para contar en Cloud Logging (como kb_unavailable_reply)
    logger.info(
        "intent_llm_router route=%s label=%s ms=%.0f model=%s error=%s query_chars=%d",
        decision.route, decision.label or "-", decision.elapsed_ms, decision.model or "-",
        decision.error or "-", len(query or ""),
    )
    return decision


async def rescue_if_unknown(intent_result: Optional[IntentDetectionResult], query: str,
                            effective_threshold: float) -> Optional[IntentDetectionResult]:
    """
    Punto de entrada del handler: si el mensaje iba a acabar en el menu de ayuda y la
    capa esta encendida, pregunta al LLM y devuelve el resultado corregido. En cualquier
    otro caso devuelve `intent_result` tal cual (sin llamar al LLM).
    """
    if not should_rescue(intent_result, effective_threshold) or not is_router_enabled():
        return intent_result
    decision = await classify_unknown_route(query)
    return apply_router_decision(intent_result, decision)
