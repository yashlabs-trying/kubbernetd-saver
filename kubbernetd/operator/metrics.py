import structlog
from prometheus_client import Counter, Histogram, Gauge, start_http_server
from prometheus_client.registry import REGISTRY, DuplicateTimeseries

from kubbernetd.common.types import OperatorConfig

log = structlog.get_logger()


class MetricsExporter:
    def __init__(self, config: OperatorConfig, skip_server: bool = False):
        self.scale_events = self._counter("kubbernetd_scale_events_total", "Scale events", ["namespace", "deployment", "direction"])
        self.idle_seconds = self._histogram("kubbernetd_idle_seconds", "Idle duration before scale-to-zero", ["namespace", "deployment"])
        self.current_replicas = self._gauge("kubbernetd_current_replicas", "Current replicas per deployment", ["namespace", "deployment"])
        self.scale_errors = self._counter("kubbernetd_scale_errors_total", "Scale errors", ["namespace", "deployment"])
        self.watched_services = self._gauge("kubbernetd_watched_services", "Number of services being watched", [])
        if not skip_server:
            start_http_server(config.metrics_port)

    @staticmethod
    def _counter(name, doc, labels):
        try:
            return Counter(name, doc, labels)
        except DuplicateTimeseries:
            return REGISTRY._names_to_collectors[name]

    @staticmethod
    def _histogram(name, doc, labels):
        try:
            return Histogram(name, doc, labels)
        except DuplicateTimeseries:
            return REGISTRY._names_to_collectors[name]

    @staticmethod
    def _gauge(name, doc, labels):
        try:
            return Gauge(name, doc, labels)
        except DuplicateTimeseries:
            return REGISTRY._names_to_collectors[name]

    def record_scale(self, namespace: str, deployment: str, to_zero: bool):
        direction = "to_zero" if to_zero else "from_zero"
        self.scale_events.labels(namespace=namespace, deployment=deployment, direction=direction).inc()
        self.current_replicas.labels(namespace=namespace, deployment=deployment).set(0 if to_zero else 1)

    def record_error(self, namespace: str, deployment: str):
        self.scale_errors.labels(namespace=namespace, deployment=deployment).inc()

    def set_watched_count(self, count: int):
        self.watched_services.set(count)