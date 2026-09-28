import structlog
from prometheus_client import Counter, Histogram, Gauge, start_http_server
from prometheus_client.registry import REGISTRY, DuplicateTimeseries

from kubbernetd.common.types import OperatorConfig

log = structlog.get_logger()


class MetricsExporter:
    def __init__(self, config: OperatorConfig, skip_server: bool = False):
        self.state_transitions = self._counter("kubbernetd_state_transitions_total", "State transitions", ["namespace", "group", "from_state", "to_state"])
        self.cold_ttft = self._histogram("kubbernetd_cold_ttft_seconds", "Cold start time-to-first-token", ["namespace", "group"])
        self.wake_stage_duration = self._histogram("kubbernetd_wake_stage_duration_seconds", "Wake stage duration", ["namespace", "group", "stage"])
        self.group_phase = self._gauge("kubbernetd_group_phase", "Current phase per group (0-10)", ["namespace", "group"])
        self.worker_count = self._gauge("kubbernetd_worker_count", "Current workers per group", ["namespace", "group"])
        self.ready_workers = self._gauge("kubbernetd_ready_workers", "Ready workers per group", ["namespace", "group"])
        self.gpu_hours_saved = self._counter("kubbernetd_gpu_hours_saved_total", "GPU hours saved", ["namespace", "group"])
        self.request_loss = self._counter("kubbernetd_request_loss_total", "Requests lost during transitions", ["namespace", "group"])
        self.watched_services = self._gauge("kubbernetd_watched_services", "Number of ReplicaGroups being watched", [])
        self.scale_errors = self._counter("kubbernetd_scale_errors_total", "Scale errors", ["namespace", "group"])
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

    def record_state_transition(self, namespace: str, group: str, from_state: str, to_state: str):
        self.state_transitions.labels(namespace=namespace, group=group, from_state=from_state, to_state=to_state).inc()
        phase_map = {
            "UNKNOWN": 0, "RUNNING": 1, "DRAINING": 2, "SCALING_DOWN": 3,
            "SLEEPING": 4, "ALLOCATING": 5, "STARTING": 6,
            "LOADING_WEIGHTS": 7, "INITIALIZING": 8, "WARMING": 9, "ERROR": 10,
        }
        self.group_phase.labels(namespace=namespace, group=group).set(phase_map.get(to_state, 0))

    def record_cold_ttft(self, namespace: str, group: str, seconds: float):
        self.cold_ttft.labels(namespace=namespace, group=group).observe(seconds)

    def record_wake_stage(self, namespace: str, group: str, stage: str, seconds: float):
        self.wake_stage_duration.labels(namespace=namespace, group=group, stage=stage).observe(seconds)

    def set_worker_count(self, namespace: str, group: str, count: int):
        self.worker_count.labels(namespace=namespace, group=group).set(count)

    def set_ready_workers(self, namespace: str, group: str, count: int):
        self.ready_workers.labels(namespace=namespace, group=group).set(count)

    def record_gpu_hours_saved(self, namespace: str, group: str, hours: float):
        self.gpu_hours_saved.labels(namespace=namespace, group=group).inc(hours)

    def record_request_loss(self, namespace: str, group: str):
        self.request_loss.labels(namespace=namespace, group=group).inc()

    def record_scale_error(self, namespace: str, group: str):
        self.scale_errors.labels(namespace=namespace, group=group).inc()

    def set_watched_count(self, count: int):
        self.watched_services.set(count)