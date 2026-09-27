from kubernetes import client

from kubbernetd.common.types import OperatorConfig
from kubbernetd.monitor.idle_detector import IdleDetector
from kubbernetd.operator.scaler import Scaler
from kubbernetd.operator.metrics import MetricsExporter


class Controller:
    def __init__(self, config: OperatorConfig):
        self.config = config
        self.apps_api = client.AppsV1Api()
        self.core_api = client.CoreV1Api()
        self.idle_detector = IdleDetector(config)
        self.scaler = Scaler(self.apps_api)
        self.metrics = MetricsExporter(config)
        self.services = {}
        self._tick_count = 0

    def register_service(self, name: str, namespace: str, spec: dict):
        self.services[(name, namespace)] = {
            "name": name,
            "namespace": namespace,
            "spec": spec,
            "idle_timeout": spec.get("idleTimeout", 300),
            "current_replicas": 1,
        }
        self.idle_detector.watch(namespace, name)

    def update_service(self, name: str, namespace: str, spec: dict):
        self.services[(name, namespace)]["spec"] = spec
        self.services[(name, namespace)]["idle_timeout"] = spec.get("idleTimeout", 300)

    def remove_service(self, name: str, namespace: str):
        self.services.pop((name, namespace), None)
        self.idle_detector.unwatch(namespace, name)

    def tick(self):
        self._tick_count += 1

        if self._tick_count % 10 == 0:
            self.idle_detector.cleanup_stale()

        for (name, namespace), svc in list(self.services.items()):
            idle_seconds = self.idle_detector.idle_seconds(namespace, name)
            timeout = svc["idle_timeout"]
            if idle_seconds is None:
                continue
            if idle_seconds > timeout and svc["current_replicas"] > 0:
                self.scaler.scale_to(namespace, name, 0)
                svc["current_replicas"] = 0
                self.metrics.record_scale(namespace, name, to_zero=True)
            elif idle_seconds == 0 and svc["current_replicas"] == 0:
                self.scaler.scale_to(namespace, name, 1)
                svc["current_replicas"] = 1
                self.metrics.record_scale(namespace, name, to_zero=False)