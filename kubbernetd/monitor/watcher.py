import structlog
from kubernetes import client, watch

from kubbernetd.monitor.idle_detector import IdleDetector

log = structlog.get_logger()


class PodWatcher:
    def __init__(self, idle_detector: IdleDetector):
        self.core_api = client.CoreV1Api()
        self.idle_detector = idle_detector

    def watch_pods(self, namespace: str, label_selector: str = ""):
        w = watch.Watch()
        for event in w.stream(
            self.core_api.list_namespaced_pod,
            namespace=namespace,
            label_selector=label_selector,
        ):
            yield event

    def detect_deployment_pods(
        self, namespace: str, deployment: str, label_selector: str
    ):
        w = watch.Watch()
        for event in w.stream(
            self.core_api.list_namespaced_pod,
            namespace=namespace,
            label_selector=label_selector,
        ):
            pod = event["object"]
            pod_name = pod.metadata.name
            phase = pod.status.phase

            if phase == "Running":
                self.idle_detector.touch(namespace, deployment)
                log.debug("pod running, touched idle timer", pod=pod_name, deployment=deployment)

            annotations = pod.metadata.annotations or {}
            last_request_str = annotations.get("kubbernetd.io/last-request")
            if last_request_str:
                try:
                    ts = float(last_request_str)
                    self.idle_detector._last_request[(namespace, deployment)] = ts
                except ValueError:
                    pass