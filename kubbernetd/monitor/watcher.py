import structlog
from kubernetes import client, watch

log = structlog.get_logger()


class Watcher:
    def __init__(self):
        self.core_api = client.CoreV1Api()

    def watch_pod_events(self, namespace: str, label_selector: str = ""):
        w = watch.Watch()
        for event in w.stream(
            self.core_api.list_namespaced_pod,
            namespace=namespace,
            label_selector=label_selector,
        ):
            yield event