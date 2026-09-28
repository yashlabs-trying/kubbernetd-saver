import os
import socket
import time
import structlog
from kubernetes import client

log = structlog.get_logger()


def _resolve_pod_name() -> str:
    name = os.environ.get("HOSTNAME")
    if name:
        return name
    try:
        with open("/etc/hostname") as f:
            name = f.read().strip()
        if name:
            return name
    except FileNotFoundError:
        pass
    return socket.gethostname()


class StatusReporter:
    def __init__(self):
        self.pod_name = _resolve_pod_name()
        self.namespace = self._read_namespace()
        self.core_api = client.CoreV1Api()
        self._ready = False
        self._max_retries = 3

    def _read_namespace(self) -> str:
        path = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
        try:
            with open(path) as f:
                return f.read().strip()
        except FileNotFoundError:
            return "default"

    def mark_ready(self):
        self._ready = True
        self._update_annotation("kubbernetd.io/agent-status", "ready")
        log.info("agent marked as ready")

    def mark_stopped(self):
        self._ready = False
        self._update_annotation("kubbernetd.io/agent-status", "stopped")
        log.info("agent marked as stopped")

    def report_stage(self, key: str, value: str):
        self._update_annotation(f"kubbernetd.io/{key}", value)

    def report_last_request(self, timestamp: float):
        self._update_annotation("kubbernetd.io/last-request", str(timestamp))

    def report_active_sequences(self, count: int):
        self._update_annotation("kubbernetd.io/active-sequences", str(count))

    def _update_annotation(self, key: str, value: str):
        for attempt in range(self._max_retries):
            try:
                pod = self.core_api.read_namespaced_pod(
                    name=self.pod_name,
                    namespace=self.namespace,
                )
                annotations = pod.metadata.annotations or {}
                annotations[key] = value
                body = {"metadata": {"annotations": annotations}}
                self.core_api.patch_namespaced_pod(
                    name=self.pod_name,
                    namespace=self.namespace,
                    body=body,
                )
                return
            except client.exceptions.ApiException as e:
                if e.status == 409 and attempt < self._max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                log.warning("failed to update annotation", key=key, error=str(e))
                return
            except Exception as e:
                log.warning("failed to update annotation", key=key, error=str(e))
                return