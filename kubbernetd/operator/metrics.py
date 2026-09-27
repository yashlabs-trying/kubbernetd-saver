from prometheus_client import Counter, Histogram, Gauge, start_http_server

from kubbernetd.common.types import OperatorConfig


class MetricsExporter:
    def __init__(self, config: OperatorConfig):
        self.scale_events = Counter(
            "kubbernetd_scale_events_total",
            "Scale events",
            ["namespace", "deployment", "direction"],
        )
        self.idle_seconds = Histogram(
            "kubbernetd_idle_seconds",
            "Idle duration before scale-to-zero",
            ["namespace", "deployment"],
        )
        self.current_replicas = Gauge(
            "kubbernetd_current_replicas",
            "Current replicas per deployment",
            ["namespace", "deployment"],
        )
        self.scale_errors = Counter(
            "kubbernetd_scale_errors_total",
            "Scale errors",
            ["namespace", "deployment"],
        )
        self.watched_services = Gauge(
            "kubbernetd_watched_services",
            "Number of services being watched",
        )
        start_http_server(config.metrics_port)

    def record_scale(self, namespace: str, deployment: str, to_zero: bool):
        direction = "to_zero" if to_zero else "from_zero"
        self.scale_events.labels(namespace=namespace, deployment=deployment, direction=direction).inc()
        self.current_replicas.labels(namespace=namespace, deployment=deployment).set(0 if to_zero else 1)

    def record_error(self, namespace: str, deployment: str):
        self.scale_errors.labels(namespace=namespace, deployment=deployment).inc()

    def set_watched_count(self, count: int):
        self.watched_services.set(count)