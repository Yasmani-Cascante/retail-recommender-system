# src/api/core/gcp_metrics_exporter.py
"""
GCP Cloud Monitoring Metrics Exporter — M3 Push Integration
============================================================

PROBLEMA RESUELTO:
  GCP Cloud Run NO hace scraping automático del endpoint /metrics de Prometheus.
  Solo recopila métricas nativas de Cloud Run (run.googleapis.com/...).

  Este módulo implementa el patrón "push" como background task del lifespan:
    Prometheus Registry → (cada 60s) → Cloud Monitoring API (custom.googleapis.com/)

ARQUITECTURA:
  ┌──────────────────────────────────────────────────────────────────┐
  │  FastAPI Lifespan                                                │
  │    └── asyncio.create_task(_export_loop())  [background task]   │
  │          └── cada EXPORT_INTERVAL_SECONDS                       │
  │                └── _collect_from_registry()                     │
  │                      └── iterate prometheus_client.REGISTRY     │
  │                └── _push_to_cloud_monitoring()                  │
  │                      └── MetricServiceClient.create_time_series │
  └──────────────────────────────────────────────────────────────────┘

MÉTRICAS EXPORTADAS (solo las custom del proyecto):
  - recommender_requests_total         (Counter  → CUMULATIVE)
  - recommender_duration_seconds_*     (Histogram → _sum/_count como CUMULATIVE)
  - recommender_errors_total           (Counter  → CUMULATIVE)
  - kb_sync_operations_total           (Counter  → CUMULATIVE)
  - kb_sync_duration_seconds_*         (Histogram → _sum/_count como CUMULATIVE)
  - kb_sync_semaphore_size             (Gauge    → GAUGE)
  - google_retail_api_calls_total      (Counter  → CUMULATIVE)
  - kb_distributed_lock_acquisitions_* (Counter  → CUMULATIVE)
  - kb_webhook_*                       (Counter  → CUMULATIVE)

MÉTRICAS EXCLUIDAS (ya manejadas por GCP o sin valor operacional):
  - python_* / process_* / gc_*  → overhead de runtime, no custom business metrics
  - http_request_*               → duplicadas con run.googleapis.com/request_count

NAMESPACE EN CLOUD MONITORING:
  custom.googleapis.com/<metric_name>
  Ejemplo: custom.googleapis.com/recommender_requests_total

COMPORTAMIENTO EN LOCAL (GCP_MONITORING_ENABLED=false):
  El exporter se inicializa pero NO inicia el loop de exportación.
  Cero overhead, cero errores en desarrollo local.

DEPENDENCIA:
  google-cloud-monitoring>=2.0.0  (añadir a requirements.txt)

Author: Senior Architecture Team
Version: 1.0.0 — M3 GCP Metrics Push Integration
Date: 10/03/2026
"""

import asyncio
import math
import os
import time
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DEL EXPORTER
# ─────────────────────────────────────────────────────────────────────────────

# Intervalo de exportación en segundos. 60s es el mínimo recomendado por GCP
# para evitar exceder la cuota de escritura (429 Too many requests).
EXPORT_INTERVAL_SECONDS = int(os.getenv("GCP_METRICS_EXPORT_INTERVAL", "60"))

# ID del proyecto GCP para construir el nombre del recurso monitoreado.
GCP_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID", "retail-recommendations-449216")

# Nombre del servicio — aparece como label en todas las métricas exportadas.
SERVICE_NAME = os.getenv("SERVICE_NAME", "retail-recommender")

# Versión del servicio — útil para correlacionar métricas con deploys.
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "2.1.0")

# Feature flag: solo exporta si está en true. En local debe ser false (default).
GCP_MONITORING_ENABLED = os.getenv("GCP_MONITORING_ENABLED", "false").lower() == "true"

# Prefijos de métricas de Prometheus que exportamos a GCP.
# Ignoramos python_*, process_*, gc_* y http_request_* porque:
#   - Las métricas de runtime Python no tienen valor operacional en este contexto.
#   - Las métricas HTTP ya están cubiertas por run.googleapis.com/request_count.
METRIC_PREFIXES_TO_EXPORT = (
    "recommender_",       # Motor de recomendaciones (negocio)
    "kb_sync_",           # Knowledge Base sync
    "kb_distributed_",    # Distributed locking M3
    "kb_webhook_",        # Webhooks M4
    "google_retail_",     # Llamadas a Google Retail API
)


# ─────────────────────────────────────────────────────────────────────────────
# CLASE PRINCIPAL: GCPMetricsExporter
# ─────────────────────────────────────────────────────────────────────────────

class GCPMetricsExporter:
    """
    Exporta métricas Prometheus a GCP Cloud Monitoring vía push (API directa).

    Ciclo de vida:
      1. __init__()     — configura el exporter, no bloquea ni falla
      2. start()        — crea el asyncio task del loop de exportación
      3. _export_loop() — corre indefinidamente cada EXPORT_INTERVAL_SECONDS
      4. stop()         — cancela el task limpiamente en el shutdown del lifespan

    Uso en el lifespan de FastAPI:
      exporter = get_gcp_metrics_exporter()
      await exporter.start()    # en la sección startup
      yield                     # app corriendo
      await exporter.stop()     # en la sección shutdown
    """

    def __init__(self):
        # Task de asyncio — guardamos referencia para cancelarlo en shutdown.
        self._task: Optional[asyncio.Task] = None

        # Flag de parada — se activa en stop() para terminar el loop limpiamente.
        self._should_stop: bool = False

        # Contadores de diagnóstico para el endpoint /health.
        self.export_count: int = 0
        self.export_error_count: int = 0
        self.last_export_time: float = 0.0

        # Cliente de Cloud Monitoring — se inicializa lazy en start().
        self._monitoring_client = None

        # Indica si el SDK de GCP está instalado y disponible.
        self._sdk_available: bool = False

        logger.info(
            "gcp_metrics_exporter_created",
            enabled=GCP_MONITORING_ENABLED,
            project=GCP_PROJECT_ID,
            interval_seconds=EXPORT_INTERVAL_SECONDS,
            service=SERVICE_NAME,
        )

    async def start(self) -> bool:
        """
        Inicia el exporter. Retorna True si se inició correctamente.

        Retorna False sin lanzar excepción si:
          - GCP_MONITORING_ENABLED=false (entorno local)
          - google-cloud-monitoring no está instalado
          - No se puede inicializar el cliente de GCP

        El sistema funciona correctamente sin exportación de métricas —
        simplemente no habrá datos en Cloud Monitoring.
        """
        if not GCP_MONITORING_ENABLED:
            logger.info(
                "gcp_metrics_exporter_disabled",
                reason="GCP_MONITORING_ENABLED=false",
                note="Set GCP_MONITORING_ENABLED=true in Cloud Run to enable",
            )
            return False

        # Intentar importar el SDK de GCP — puede no estar en entornos de desarrollo.
        try:
            from google.cloud import monitoring_v3
            self._monitoring_client = monitoring_v3.MetricServiceClient()
            self._sdk_available = True
            logger.info(
                "gcp_monitoring_sdk_loaded",
                client_type=type(self._monitoring_client).__name__,
            )
        except ImportError:
            logger.warning(
                "gcp_monitoring_sdk_not_available",
                reason="google-cloud-monitoring not installed",
                fix="pip install 'google-cloud-monitoring>=2.0.0'",
                impact="Prometheus metrics will NOT appear in GCP Cloud Monitoring",
            )
            return False
        except Exception as e:
            logger.error(
                "gcp_monitoring_client_init_failed",
                error=str(e),
                impact="Prometheus metrics will NOT appear in GCP Cloud Monitoring",
            )
            return False

        # Crear el background task. asyncio.create_task() es no-bloqueante —
        # programa la corutina para el event loop sin esperar su resultado.
        self._should_stop = False
        self._task = asyncio.create_task(
            self._export_loop(),
            name="gcp_metrics_export_loop",  # Nombre visible en asyncio debug mode
        )

        logger.info(
            "gcp_metrics_exporter_started",
            interval_seconds=EXPORT_INTERVAL_SECONDS,
            project=GCP_PROJECT_ID,
            service=SERVICE_NAME,
            version=SERVICE_VERSION,
            m3_phase="active",
        )
        return True

    async def stop(self) -> None:
        """
        Detiene el loop de exportación limpiamente.
        Llamar en la sección shutdown del lifespan de FastAPI.
        """
        self._should_stop = True

        if self._task and not self._task.done():
            # cancel() lanza CancelledError en la siguiente await del task.
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # Esperado — el task fue cancelado correctamente.

        logger.info(
            "gcp_metrics_exporter_stopped",
            total_exports=self.export_count,
            total_errors=self.export_error_count,
        )

    async def _export_loop(self) -> None:
        """
        Loop principal. Corre hasta que _should_stop=True o el task sea cancelado.

        Patrón: esperar → exportar → esperar → exportar → ...

        Nota: esperamos ANTES del primer export para que la app termine de
        inicializarse y genere tráfico real antes de enviar valores a GCP.
        Si exportáramos inmediatamente, los counters estarían en 0.
        """
        logger.info(
            "gcp_metrics_export_loop_started",
            first_export_in_seconds=EXPORT_INTERVAL_SECONDS,
        )

        # Esperar el primer intervalo antes de exportar.
        await asyncio.sleep(EXPORT_INTERVAL_SECONDS)

        while not self._should_stop:
            try:
                metrics = self._collect_from_registry()

                if metrics:
                    exported_count = await self._push_to_cloud_monitoring(metrics)
                    self.export_count += 1
                    self.last_export_time = time.time()

                    logger.info(
                        "gcp_metrics_exported",
                        metrics_count=exported_count,
                        total_exports=self.export_count,
                        m3_phase="active",
                    )
                else:
                    logger.debug(
                        "gcp_metrics_export_skipped",
                        reason="no_metrics_collected",
                    )

            except asyncio.CancelledError:
                # Task cancelado desde stop() — salimos limpiamente.
                break
            except Exception as e:
                # Error de exportación — loguear y continuar. No queremos que un
                # error de métricas derribe la aplicación principal.
                self.export_error_count += 1
                logger.warning(
                    "gcp_metrics_export_error",
                    error=str(e),
                    error_type=type(e).__name__,
                    total_errors=self.export_error_count,
                )

            # Esperar hasta el siguiente ciclo.
            # asyncio.sleep es cancelable — si stop() cancela durante el sleep,
            # la CancelledError se captura en el try/except superior.
            try:
                await asyncio.sleep(EXPORT_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                break

    def _collect_from_registry(self) -> List[Dict[str, Any]]:
        """
        Lee el registry de Prometheus y extrae las métricas custom del proyecto.

        prometheus_client.REGISTRY.collect() retorna objetos Metric con:
          - .name:           str  (nombre base, ej: "recommender_requests_total")
          - .type:           str  ("counter", "gauge", "histogram", "summary")
          - .documentation:  str  (texto del HELP)
          - .samples:        list de Sample(name, labels, value, timestamp, exemplar)

        Los samples tienen nombres con sufijos para histogramas:
          recommender_duration_seconds_sum
          recommender_duration_seconds_count
          recommender_duration_seconds_bucket  ← ignoramos estos
        """
        from prometheus_client import REGISTRY

        collected = []

        for metric_family in REGISTRY.collect():
            # Filtrar: solo nuestras métricas custom
            if not any(
                metric_family.name.startswith(p) for p in METRIC_PREFIXES_TO_EXPORT
            ):
                continue

            # Extraer samples válidos
            samples = []
            for sample in metric_family.samples:
                samples.append({
                    "name": sample.name,           # Nombre completo con sufijo
                    "labels": dict(sample.labels),  # Dict de etiquetas
                    "value": float(sample.value),   # Valor numérico actual
                })

            if samples:
                collected.append({
                    "name": metric_family.name,
                    "type": metric_family.type,
                    "help": metric_family.documentation,
                    "samples": samples,
                })

        return collected

    async def _push_to_cloud_monitoring(self, metrics: List[Dict[str, Any]]) -> int:
        """
        Envía métricas a GCP Cloud Monitoring vía create_time_series.

        Retorna el número de series temporales enviadas exitosamente.

        LÍMITE DE LA API: create_time_series acepta máximo 200 TimeSeries por
        llamada. Hacemos batches automáticamente si superamos ese límite.

        SIMPLIFICACIÓN INTENCIONAL para histogramas:
        No exportamos los buckets (_bucket) — solo _sum y _count.
        Esto es suficiente para calcular latencia promedio en Cloud Monitoring
        y evita crear demasiadas series temporales (cada bucket = 1 serie).

        IMPORTANTE sobre start_time para CUMULATIVE:
        Cloud Monitoring requiere un intervalo con start_time y end_time para
        métricas CUMULATIVE. Usamos (now - interval) como start_time, lo que
        representa el período del último ciclo de exportación.

        NOTA sobre enumeraciones MetricKind / ValueType (google-cloud-monitoring >= 2.0.0):

        monitoring_v3.MetricDescriptor NO existe — lanza AttributeError.
        monitoring_v3.types.MetricDescriptor tampoco está exportado en __init__.py.

        El origen correcto y estable para los enums es google.api.metric_pb2,
        que es la librería base de Google API Client donde viven los tipos protobuf
        de métricas. Verificado con google-cloud-monitoring 2.29.1:

          MetricKind.GAUGE       = 1
          MetricKind.CUMULATIVE  = 3
          ValueType.DOUBLE       = 3   (IMPORTANTE: es 3, no 4)
          ValueType.INT64        = 2
        """
        from google.cloud import monitoring_v3
        from google.api import metric_pb2 as _metric_pb2
        from google.protobuf import timestamp_pb2

        # Alias corto para acceder a los enums de MetricDescriptor
        _MD = _metric_pb2.MetricDescriptor

        project_name = f"projects/{GCP_PROJECT_ID}"
        time_series_list = []

        # Timestamps para todos los puntos de este export
        now_ts = time.time()
        now_seconds = int(now_ts)
        now_nanos = int((now_ts % 1) * 1e9)
        start_seconds = now_seconds - EXPORT_INTERVAL_SECONDS  # Para CUMULATIVE

        for metric in metrics:
            metric_type_str = metric["type"]

            for sample in metric["samples"]:
                sample_name = sample["name"]
                sample_value = sample["value"]
                sample_labels = sample["labels"]

                # Saltar buckets de histogram — ver nota en docstring
                if sample_name.endswith("_bucket"):
                    continue

                # Saltar valores no finitos — Cloud Monitoring los rechaza con 400
                if not math.isfinite(sample_value):
                    continue

                # ── Construir TimeSeries ──────────────────────────────────────

                series = monitoring_v3.TimeSeries()

                # El tipo de métrica en Cloud Monitoring usa el nombre del sample
                # (con sufijo _sum, _count, etc.) para distinguir las partes del
                # histogram. Cloud Monitoring crea un MetricDescriptor automáticamente
                # la primera vez que recibe cada tipo.
                series.metric.type = f"custom.googleapis.com/{sample_name}"

                # generic_task es el tipo de recurso más flexible para Cloud Run
                # cuando no usamos GMP. Requiere estos 5 labels exactamente.
                series.resource.type = "generic_task"
                series.resource.labels["project_id"] = GCP_PROJECT_ID
                series.resource.labels["location"] = os.getenv(
                    "CLOUD_RUN_REGION", "us-central1"
                )
                series.resource.labels["namespace"] = SERVICE_NAME
                series.resource.labels["job"] = SERVICE_NAME
                series.resource.labels["task_id"] = SERVICE_VERSION

                # Labels de la métrica (market, strategy, status, etc.)
                # Limitamos a 10 para no exceder el límite de GCP (64 máximo,
                # pero 10 es más que suficiente para nuestras métricas).
                for k, v in list(sample_labels.items())[:10]:
                    series.metric.labels[str(k)] = str(v)

                # ── MetricKind ────────────────────────────────────────────────
                # GAUGE      → valor instantáneo (no acumulativo)
                # CUMULATIVE → valor que solo crece (counters, _sum, _count)
                # Fuente: google.api.metric_pb2.MetricDescriptor (API correcta)
                if metric_type_str == "gauge":
                    series.metric_kind = _MD.MetricKind.GAUGE
                else:
                    series.metric_kind = _MD.MetricKind.CUMULATIVE

                # ValueType.DOUBLE = 3 en google.api.metric_pb2
                series.value_type = _MD.ValueType.DOUBLE

                # ── Point ─────────────────────────────────────────────────────
                point = monitoring_v3.Point()
                point.value.double_value = sample_value

                # end_time: requerido para GAUGE y CUMULATIVE
                end_time = timestamp_pb2.Timestamp()
                end_time.seconds = now_seconds
                end_time.nanos = now_nanos
                point.interval.end_time = end_time

                # start_time: requerido SOLO para CUMULATIVE
                if series.metric_kind == _MD.MetricKind.CUMULATIVE:
                    start_time = timestamp_pb2.Timestamp()
                    start_time.seconds = start_seconds
                    start_time.nanos = 0
                    point.interval.start_time = start_time

                series.points = [point]
                time_series_list.append(series)

        if not time_series_list:
            return 0

        # ── Enviar en batches de máximo 200 ──────────────────────────────────
        BATCH_SIZE = 200
        exported_count = 0

        # Timeout explícito para create_time_series.
        # El default del SDK es no-determinista y puede causar 504 DeadlineExceeded
        # durante cold starts (primera llamada a GCP APIs tras un despliegue).
        # 30s es generoso para una llamada HTTP simple y cubre la latencia de red
        # del cold start sin bloquear el event loop demasiado tiempo.
        CALL_TIMEOUT_SECONDS = 30

        for i in range(0, len(time_series_list), BATCH_SIZE):
            batch = time_series_list[i : i + BATCH_SIZE]
            try:
                # La librería google-cloud-monitoring es síncrona.
                # asyncio.to_thread() la ejecuta en un thread pool para no
                # bloquear el event loop de FastAPI durante la llamada HTTP.
                # Disponible desde Python 3.9 — equivalente a loop.run_in_executor().
                await asyncio.to_thread(
                    self._monitoring_client.create_time_series,
                    name=project_name,
                    time_series=batch,
                    timeout=CALL_TIMEOUT_SECONDS,
                )
                exported_count += len(batch)
            except Exception as batch_error:
                logger.warning(
                    "gcp_metrics_batch_error",
                    batch_index=i // BATCH_SIZE,
                    batch_size=len(batch),
                    error=str(batch_error),
                    error_type=type(batch_error).__name__,
                )

        return exported_count

    def get_status(self) -> Dict[str, Any]:
        """
        Retorna el estado del exporter. Útil para incluir en /health.
        """
        return {
            "enabled": GCP_MONITORING_ENABLED,
            "sdk_available": self._sdk_available,
            "running": self._task is not None and not self._task.done(),
            "export_count": self.export_count,
            "export_error_count": self.export_error_count,
            "last_export_time": self.last_export_time,
            "export_interval_seconds": EXPORT_INTERVAL_SECONDS,
            "project_id": GCP_PROJECT_ID,
            "service_name": SERVICE_NAME,
        }


# ─────────────────────────────────────────────────────────────────────────────
# SINGLETON — una sola instancia en toda la app
# ─────────────────────────────────────────────────────────────────────────────

_exporter_instance: Optional[GCPMetricsExporter] = None


def get_gcp_metrics_exporter() -> GCPMetricsExporter:
    """
    Factory function que retorna el singleton del exporter.
    Patrón consistente con get_observability_manager() y get_claude_config_service().
    """
    global _exporter_instance
    if _exporter_instance is None:
        _exporter_instance = GCPMetricsExporter()
    return _exporter_instance
