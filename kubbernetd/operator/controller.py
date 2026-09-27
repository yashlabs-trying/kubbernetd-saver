import time
import threading
from enum import Enum, auto

import structlog
from kubernetes import client

from kubbernetd.common.types import OperatorConfig
from kubbernetd.monitor.idle_detector import IdleDetector
from kubbernetd.operator.scaler import Scaler
from kubbernetd.operator.metrics import MetricsExporter

log = structlog.get_logger()


class ServicePhase(Enum):
    UNKNOWN = auto()
    RUNNING = auto()
    SCALING_DOWN = auto()
    SCALING_UP = auto()
    STOPPED = auto()
    ERROR = auto()


class Controller:
    def __init__(self, config: OperatorConfig):
        self.config = config
        self.apps_api = client.AppsV1Api()
        self.core_api = client.CoreV1Api()
        self.idle_detector = IdleDetector(config)
        self.scaler = Scaler(self.apps_api)
        self.metrics = MetricsExporter(config)
        self._lock = threading.RLock()
        self._services: dict[tuple[str, str], dict] = {}
        self._in_flight: dict[tuple[str, str], int] = {}
        self._crd_to_deployment: dict[tuple[str, str], tuple[str, str]] = {}
        self._tick_count = 0
        self._ready = False

    def mark_ready(self):
        self._ready = True

    def sync_from_cluster(self):
        try:
            deps = self.apps_api.list_deployment_for_all_namespaces().items
            log.info("synced deployment count from cluster", count=len(deps))
        except Exception as e:
            log.warning("initial cluster sync failed, will retry", error=str(e))

    def register_service(self, name: str, namespace: str, spec: dict, crd_name: str = None):
        idle_timeout = spec.get("idleTimeout", self.config.idle_timeout_seconds)
        min_replicas = spec.get("minReplicas", 0)
        max_replicas = spec.get("maxReplicas", 10)
        shadow_pods = spec.get("shadowPods", self.config.shadow_pods)

        current_replicas = self._resolve_initial_replicas(namespace, name)

        with self._lock:
            self._services[(name, namespace)] = {
                "name": name,
                "namespace": namespace,
                "spec": spec,
                "idle_timeout": idle_timeout,
                "min_replicas": min_replicas,
                "max_replicas": max_replicas,
                "shadow_pods": shadow_pods,
                "current_replicas": current_replicas,
                "previous_replicas": current_replicas,
                "phase": ServicePhase.RUNNING if current_replicas > 0 else ServicePhase.STOPPED,
                "last_error_at": None,
                "error_count": 0,
            }
            if crd_name:
                self._crd_to_deployment[(crd_name, namespace)] = (name, namespace)
        self.idle_detector.watch(namespace, name)
        log.info("registered service", name=name, namespace=namespace,
                 timeout=idle_timeout, replicas=current_replicas)

    def remove_service_by_crd(self, namespace: str, crd_name: str):
        with self._lock:
            key = self._crd_to_deployment.pop((crd_name, namespace), None)
        if key:
            self.remove_service(key[0], key[1])
        else:
            self.idle_detector.unwatch(namespace, crd_name)

    def _resolve_initial_replicas(self, namespace: str, name: str) -> int:
        try:
            return self.scaler.current_replicas(namespace, name)
        except client.exceptions.ApiException as e:
            if e.status == 404:
                log.error("deployment not found on register", name=name, namespace=namespace)
            return 0
        except Exception as e:
            log.warning("could not resolve initial replicas", name=name, error=str(e))
            return 0

    def update_service(self, name: str, namespace: str, spec: dict):
        with self._lock:
            svc = self._services.get((name, namespace))
            if svc is None:
                self.register_service(name, namespace, spec)
                return
            svc["spec"] = spec
            svc["idle_timeout"] = spec.get("idleTimeout", self.config.idle_timeout_seconds)
            svc["min_replicas"] = spec.get("minReplicas", 0)
            svc["max_replicas"] = spec.get("maxReplicas", 10)
            svc["shadow_pods"] = spec.get("shadowPods", self.config.shadow_pods)
        log.info("updated service", name=name, namespace=namespace)

    def remove_service(self, name: str, namespace: str):
        with self._lock:
            self._services.pop((name, namespace), None)
        self.idle_detector.unwatch(namespace, name)
        log.info("removed service", name=name, namespace=namespace)

    def _get_service(self, name: str, namespace: str):
        with self._lock:
            return self._services.get((name, namespace))

    def track_in_flight(self, namespace: str, name: str, delta: int):
        with self._lock:
            key = (name, namespace)
            current = self._in_flight.get(key, 0)
            self._in_flight[key] = max(0, current + delta)

    def in_flight_count(self, namespace: str, name: str) -> int:
        with self._lock:
            return self._in_flight.get((name, namespace), 0)

    def tick(self):
        self._tick_count += 1

        if self._tick_count % 10 == 0:
            self.idle_detector.cleanup_stale(max_age_seconds=self.config.stale_cleanup_age)

        with self._lock:
            services_snapshot = list(self._services.keys())

        for name, namespace in services_snapshot:
            self._process_service(name, namespace)

    def _process_service(self, name: str, namespace: str):
        svc = self._get_service(name, namespace)
        if svc is None:
            return

        if svc.get("idle_timeout", 0) <= 0:
            return

        self._reconcile_actual_replicas(name, namespace, svc)

        idle_seconds = self.idle_detector.idle_seconds(namespace, name)
        if idle_seconds is None:
            return

        now = time.monotonic()
        cooldown_remaining = self._cooldown_remaining(svc, now)
        if cooldown_remaining > 0:
            return

        current = svc["current_replicas"]
        timeout = svc["idle_timeout"]
        min_r = svc["min_replicas"]
        max_r = svc["max_replicas"]
        phase = svc["phase"]
        in_flight = self.in_flight_count(namespace, name)

        should_scale_down = (
            in_flight == 0
            and current > min_r
            and idle_seconds > timeout
            and phase in (ServicePhase.RUNNING, ServicePhase.ERROR)
        )
        should_scale_up = (
            current < min(1, max_r)
            and idle_seconds < timeout
            and phase in (ServicePhase.STOPPED, ServicePhase.ERROR)
        )

        if should_scale_down:
            previous = current
            target = max(min_r, 0)
            self._do_scale(name, namespace, target, svc, now, "idle_timeout")
            if target == 0 and previous != target:
                with self._lock:
                    svc["previous_replicas"] = previous
                    if svc.get("previous_replicas_set_by_user") is None:
                        svc["previous_replicas_set_by_user"] = previous

        elif should_scale_up:
            prev = svc.get("previous_replicas_set_by_user") or svc.get("previous_replicas", 1)
            target = min(prev, max_r) if prev > 0 else min(1, max_r)
            self._do_scale(name, namespace, target, svc, now, "traffic_detected")

    def _reconcile_actual_replicas(self, name: str, namespace: str, svc: dict):
        try:
            actual = self.scaler.current_replicas(namespace, name)
            cached = svc["current_replicas"]
            if actual != cached:
                log.info("replica drift detected", name=name, namespace=namespace,
                         cached=cached, actual=actual)
                with self._lock:
                    svc["current_replicas"] = actual
                    svc["phase"] = ServicePhase.RUNNING if actual > 0 else ServicePhase.STOPPED
        except Exception:
            pass

    def _cooldown_remaining(self, svc: dict, now: float) -> float:
        last_error = svc.get("last_error_at")
        if last_error is None:
            return 0
        errors = svc.get("error_count", 0)
        backoff = min(2 ** errors, 60)
        elapsed = now - last_error
        return max(0.0, backoff - elapsed)

    def _do_scale(self, name: str, namespace: str, target: int,
                  svc: dict, now: float, reason: str):
        try:
            self.scaler.scale_to(namespace, name, target)
            self.metrics.record_scale(namespace, name, to_zero=(target == 0))
            with self._lock:
                svc["current_replicas"] = target
                svc["phase"] = ServicePhase.STOPPED if target == 0 else ServicePhase.RUNNING
                svc["last_error_at"] = None
                svc["error_count"] = 0
            log.info("scale succeeded", name=name, namespace=namespace,
                     replicas=target, reason=reason)
        except client.exceptions.ApiException as e:
            log.warning("scale failed (API)", name=name, namespace=namespace,
                        replicas=target, status=e.status, reason=str(e))
            self._record_error(svc, now)
        except Exception as e:
            log.warning("scale failed (unexpected)", name=name,
                        namespace=namespace, error=str(e))
            self._record_error(svc, now)

    def _record_error(self, svc: dict, now: float):
        with self._lock:
            svc["last_error_at"] = now
            svc["error_count"] = svc.get("error_count", 0) + 1
            svc["phase"] = ServicePhase.ERROR