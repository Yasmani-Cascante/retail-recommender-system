"""
shopify_rate_limiter.py
========================
FIX (22/09/2026): limitador de tasa COMPARTIDO para la API GraphQL Admin de
Shopify, coordinado entre todos los procesos en background que corren dentro
de esta misma instancia de Cloud Run.

Por que hace falta:
    Shopify aplica el throttling a nivel de TIENDA (el shop entero comparte
    un unico "bucket" de presupuesto), no por conexion ni por proceso. Antes
    de este modulo, dos procesos en background -- el rebuild del catalogo
    TF-IDF (shopify_client.py::get_products_with_shopify_prices) y el
    enriquecimiento de colecciones (main_unified_redis.py::PASO 4.6 BG) --
    corrian en el MISMO event loop de asyncio (mismo proceso, misma
    instancia de Cloud Run) sin saber nada el uno del otro. Cada uno llevaba
    su propia cuenta LOCAL del throttleStatus que Shopify le devolvia a EL,
    ciego al consumo del otro -- asi que cada uno podia creer que tenia
    presupuesto de sobra justo cuando el otro ya lo habia agotado.

    Confirmado con evidencia real (17-22/09/2026): la practica totalidad de
    los fallos de throttling observados en el rebuild coincidieron
    temporalmente con PASO 4.6 BG corriendo en paralelo; en la unica corrida
    donde los dos NO se solaparon (22/09/2026), el rebuild tuvo CERO fallos
    de throttling (REST fallbacks: 0).

Alcance deliberado:
    Este limitador coordina los DOS procesos en BACKGROUND identificados con
    evidencia real (rebuild de catalogo, enriquecimiento de colecciones).
    NO se conecta a las llamadas Shopify que sirven al chat en vivo
    (get_product_context_by_handle, get_prices_for_products) -- esas son
    sensibles a latencia (el usuario esta esperando una respuesta) y de bajo
    volumen; forzarlas a esperar por un presupuesto compartido introduciria
    un riesgo de UX nuevo para resolver un problema que la evidencia no
    muestra que causen. Si en el futuro aparece evidencia de que si
    contribuyen a la contencion, extender el alcance es sencillo -- misma
    interfaz publica (wait_for_budget / report_response).

Limite conocido:
    Coordina dentro de UNA instancia de Cloud Run (un solo proceso Python,
    un solo event loop). Si el servicio alguna vez escala a mas de una
    instancia concurrente Y ambas corren estos procesos al mismo tiempo,
    cada instancia tiene su propio limitador independiente -- no hay
    coordinacion entre instancias. No hay evidencia hoy de que esto ocurra
    (PASO 4.6 BG solo corre una vez por arranque en frio; el rebuild vive
    detras de un endpoint disparado por un unico Cloud Scheduler). Si
    aparece esa evidencia, la solucion natural es mover este estado a Redis
    (ya se usa extensamente en el proyecto) en vez de a memoria de proceso
    -- la interfaz publica de este modulo no tendria que cambiar para ese
    upgrade.
"""
import asyncio
import time
import logging
from typing import Optional


class ShopifyRateLimiter:
    """
    Estado compartido del presupuesto de throttling de la API GraphQL Admin
    de Shopify, consultado y actualizado por todos los procesos en
    background que corren dentro de este proceso.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._available: Optional[float] = None
        self._restore_rate: Optional[float] = None
        self._max_available: Optional[float] = None
        self._last_updated: float = 0.0  # time.monotonic()

    def _project_available(self) -> Optional[float]:
        """
        Proyecta cuanto presupuesto hay AHORA, extrapolando desde la ultima
        actualizacion real segun restoreRate. None si nunca se actualizo
        (primera query de la corrida -- no hay dato todavia, no hay nada
        que esperar).
        """
        if self._available is None or self._restore_rate is None:
            return None
        elapsed = max(time.monotonic() - self._last_updated, 0.0)
        projected = self._available + elapsed * self._restore_rate
        if self._max_available is not None:
            projected = min(projected, self._max_available)
        return projected

    async def wait_for_budget(
        self,
        estimated_cost: float,
        max_wait: float = 10.0,
        caller: str = "",
    ) -> None:
        """
        Espera, si hace falta, antes de que el llamador dispare su proxima
        query GraphQL. Mantiene el lock durante toda la espera a proposito:
        con solo dos llamadores conocidos (ambos en background, ambos poco
        frecuentes), serializar sus decisiones de pacing es mas simple y
        mas robusto que arriesgar que los dos esperen en paralelo y disparen
        juntos de todas formas.
        """
        async with self._lock:
            projected = self._project_available()
            if projected is None:
                return
            deficit = estimated_cost - projected
            if deficit <= 0:
                return
            wait_s = min(deficit / self._restore_rate, max_wait)
            if wait_s > 0.05:
                if caller:
                    logging.info(
                        f"[ShopifyRateLimiter] {caller} espera {wait_s:.1f}s "
                        f"(presupuesto compartido proyectado: {projected:.0f}, "
                        f"necesita: {estimated_cost:.0f})"
                    )
                await asyncio.sleep(wait_s)

    async def report_response(self, throttle_status: dict, caller: str = "") -> None:
        """
        Actualiza el estado compartido con el throttleStatus REAL devuelto
        por la ultima respuesta de Shopify -- venga de quien venga. Cualquier
        llamador puede reportar, incluso si nunca llama a wait_for_budget.
        """
        if not throttle_status:
            return
        async with self._lock:
            available = throttle_status.get("currentlyAvailable")
            restore_rate = throttle_status.get("restoreRate")
            max_available = throttle_status.get("maximumAvailable")
            if available is not None:
                self._available = float(available)
            if restore_rate is not None:
                self._restore_rate = float(restore_rate)
            if max_available is not None:
                self._max_available = float(max_available)
            self._last_updated = time.monotonic()


# Singleton a nivel de modulo -- todos los llamadores dentro de este proceso
# importan y usan la MISMA instancia (mismo patron que _shopify_httpx_client
# en shopify_client.py).
_shopify_rate_limiter = ShopifyRateLimiter()


def get_shopify_rate_limiter() -> ShopifyRateLimiter:
    """Devuelve el limitador de tasa compartido de este proceso."""
    return _shopify_rate_limiter


class ShopifyRebuildPriority:
    """
    FIX (23/09/2026): senal de prioridad -- cuando el rebuild del catalogo
    esta activo, PASO 4.6 BG cede el paso -- deja de competir por el
    presupuesto de Shopify y se pausa hasta que el rebuild termina.

    Por que esta prioridad y no al reves, ni "negociar mejor" con
    ShopifyRateLimiter (arriba):
        Confirmado con evidencia real (23/09/2026): incluso con
        ShopifyRateLimiter coordinando ambas esperas de forma informada,
        cuando los dos procesos demandan presupuesto AL MISMO TIEMPO, la
        demanda conjunta supera lo que Shopify repone -- el rebuild sufrio
        60 REST fallbacks (vs 0 en aislamiento) y PASO 4.6 BG tardo casi el
        doble y sufrio su primer fallo permanente de batch. ShopifyRateLimiter
        resuelve "competir a ciegas" -> "competir informado"; esta clase
        resuelve "competir informado" -> "no competir en absoluto". El
        rebuild es critico para el negocio (Cloud Scheduler, presupuesto de
        reintentos limitado, alimenta todo el catalogo). PASO 4.6 BG es una
        mejora de calidad que "degrada graciosamente" si tarda mas -- su
        propio docstring (main_unified_redis.py) ya lo dice.

    Por que contador y no un booleano simple:
        Si en algun momento dos rebuilds corrieran solapados (ej. un disparo
        manual mientras el automatico de las 4am sigue en curso), un
        booleano simple se "liberaria" en cuanto el primero terminara,
        aunque el segundo siguiera activo -- dejando a PASO 4.6 BG competir
        de nuevo prematuramente. El contador solo libera cuando llega a 0.

    Alcance: igual que ShopifyRateLimiter -- en memoria de proceso, dentro
    de una instancia de Cloud Run. Mismas razones, mismo limite conocido.
    """

    def __init__(self):
        self._active_rebuilds = 0
        self._clear_to_proceed: Optional[asyncio.Event] = None  # lazy: necesita un event loop

    def _get_event(self) -> asyncio.Event:
        if self._clear_to_proceed is None:
            self._clear_to_proceed = asyncio.Event()
            self._clear_to_proceed.set()  # arranca "libre" -- sin rebuild activo
        return self._clear_to_proceed

    def mark_rebuild_started(self) -> None:
        """
        Llamar al INICIO de la porcion de un rebuild que usa la API de
        Shopify -- no hace falta envolver fit()/upload a GCS, que no
        compiten por el mismo presupuesto.
        """
        self._active_rebuilds += 1
        self._get_event().clear()

    def mark_rebuild_finished(self) -> None:
        """
        Llamar SIEMPRE al terminar esa porcion, incluso si fallo -- el
        caller debe usar try/finally para garantizarlo.
        """
        self._active_rebuilds = max(0, self._active_rebuilds - 1)
        if self._active_rebuilds == 0:
            self._get_event().set()

    async def wait_if_rebuild_active(self, caller: str = "") -> None:
        """
        PASO 4.6 BG llama esto antes de CADA batch (no solo una vez al
        inicio) -- si un rebuild arranca a mitad de su ejecucion, se pausa
        en el siguiente batch en vez de seguir compitiendo por toda la
        duracion del rebuild.
        """
        event = self._get_event()
        if not event.is_set():
            logging.info(
                f"[ShopifyRebuildPriority] {caller} cede el paso -- "
                f"rebuild de catalogo en curso"
            )
            await event.wait()


_shopify_rebuild_priority = ShopifyRebuildPriority()


def get_shopify_rebuild_priority() -> ShopifyRebuildPriority:
    """Devuelve la senal de prioridad de rebuild compartida de este proceso."""
    return _shopify_rebuild_priority
