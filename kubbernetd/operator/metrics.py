from prometheus_client import Counter, Histogram, start_http_server

from kubbernetd.common.config import OperatorConfig


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
        start_http_server(config.metrics_port)

    def record_scale(self, namespace: str, deployment: str, to_zero: bool):
        direction = "to_zero" if to_zero else "from_zero"
        self.scale_events.labels(namespace=namespace, deployment=deployment, direction=direction).inc()