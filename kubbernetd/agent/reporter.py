import os
import socket
import time

import structlog
from kubernetes import client

log = structlog.get_logger()


class StatusReporter:
    def __init__(self):
        self.hostname = socket.gethostname()
        self.namespace = self._read_namespace()
        self.core_api = client.CoreV1Api()
        self._ready = False

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
        self._update_annotation("kubbernetd.io/agent-status", "stopped")
        log.info("agent marked as stopped")

    def report_heartbeat(self):
        self._update_annotation("kubbernetd.io/last-heartbeat", str(time.time()))

    def report_last_request(self, timestamp: float):
        self._update_annotation("kubbernetd.io/last-request", str(timestamp))

    def _update_annotation(self, key: str, value: str):
        try:
            pod = self.core_api.read_namespaced_pod(
                name=self.hostname,
                namespace=self.namespace,
            )
            annotations = pod.metadata.annotations or {}
            annotations[key] = value
            body = {"metadata": {"annotations": annotations}}
            self.core_api.patch_namespaced_pod(
                name=self.hostname,
                namespace=self.namespace,
                body=body,
            )
        except Exception as e:
            log.warning("failed to update annotation", key=key, error=str(e))