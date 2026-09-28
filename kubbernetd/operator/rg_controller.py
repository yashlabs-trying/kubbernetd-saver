import time
import threading
import structlog
from kubernetes import client

from kubbernetd.common.types import (
    GroupPhase, SleepDepth, ReplicaGroupState, ReplicaGroupStatus,
    WakeStages, OperatorConfig,
)
from kubbernetd.operator.metrics import MetricsExporter

log = structlog.get_logger()


TRANSITIONS = {
    GroupPhase.UNKNOWN: [GroupPhase.RUNNING, GroupPhase.SLEEPING],
    GroupPhase.RUNNING: [GroupPhase.DRAINING, GroupPhase.ERROR],
    GroupPhase.DRAINING: [GroupPhase.SCALING_DOWN, GroupPhase.RUNNING],
    GroupPhase.SCALING_DOWN: [GroupPhase.SLEEPING, GroupPhase.ERROR],
    GroupPhase.SLEEPING: [GroupPhase.ALLOCATING, GroupPhase.ERROR],
    GroupPhase.ALLOCATING: [GroupPhase.STARTING, GroupPhase.SLEEPING, GroupPhase.ERROR],
    GroupPhase.STARTING: [GroupPhase.LOADING_WEIGHTS, GroupPhase.ALLOCATING, GroupPhase.ERROR],
    GroupPhase.LOADING_WEIGHTS: [GroupPhase.INITIALIZING, GroupPhase.STARTING, GroupPhase.ERROR],
    GroupPhase.INITIALIZING: [GroupPhase.WARMING, GroupPhase.LOADING_WEIGHTS, GroupPhase.ERROR],
    GroupPhase.WARMING: [GroupPhase.RUNNING, GroupPhase.INITIALIZING, GroupPhase.ERROR],
    GroupPhase.ERROR: [GroupPhase.SLEEPING, GroupPhase.ALLOCATING, GroupPhase.ERROR],
}


class ReplicaGroupController:
    def __init__(self, config: OperatorConfig, metrics: MetricsExporter = None):
        self.config = config
        self.apps_api = client.AppsV1Api()
        self.core_api = client.CoreV1Api()
        self.custom_api = client.CustomObjectsApi()
        self.metrics = metrics
        self._lock = threading.RLock()
        self._groups: dict[tuple[str, str], ReplicaGroupState] = {}
        self._tick_count = 0

    def register_group(self, name: str, namespace: str, spec: dict):
        spec_model = spec.get("model", {})
        state = ReplicaGroupState(
            name=name,
            namespace=namespace,
            spec=spec,
            phase=self._initial_phase(spec),
        )
        with self._lock:
            self._groups[(name, namespace)] = state
        self._write_status(name, namespace, state)
        log.info("registered replicagroup", name=name, namespace=namespace,
                 model=spec_model.get("name", "unknown"),
                 workers=spec_model.get("workers", 1))

    def _initial_phase(self, spec: dict) -> GroupPhase:
        target = spec.get("targetRef", {})
        kind = target.get("kind", "Deployment")
        name = target.get("name", "")
        if not name:
            return GroupPhase.UNKNOWN
        return GroupPhase.RUNNING

    def remove_group(self, name: str, namespace: str):
        with self._lock:
            self._groups.pop((name, namespace), None)
        log.info("removed replicagroup", name=name, namespace=namespace)

    def update_group(self, name: str, namespace: str, spec: dict):
        with self._lock:
            state = self._groups.get((name, namespace))
            if state is None:
                self.register_group(name, namespace, spec)
                return
            state.spec = spec
        log.info("updated replicagroup", name=name, namespace=namespace)

    def get_group(self, name: str, namespace: str) -> ReplicaGroupState:
        with self._lock:
            return self._groups.get((name, namespace))

    def tick(self):
        self._tick_count += 1
        with self._lock:
            keys = list(self._groups.keys())
        for name, namespace in keys:
            state = self.get_group(name, namespace)
            if state is None:
                continue
            self._process_group(name, namespace, state)

    def _process_group(self, name: str, namespace: str, state: ReplicaGroupState):
        phase = state.phase
        now = time.monotonic()

        if phase == GroupPhase.RUNNING:
            self._handle_running(name, namespace, state, now)
        elif phase == GroupPhase.DRAINING:
            self._handle_draining(name, namespace, state, now)
        elif phase == GroupPhase.SCALING_DOWN:
            self._handle_scaling_down(name, namespace, state, now)
        elif phase == GroupPhase.SLEEPING:
            self._handle_sleeping(name, namespace, state, now)
        elif phase == GroupPhase.ALLOCATING:
            self._handle_allocating(name, namespace, state, now)
        elif phase == GroupPhase.STARTING:
            self._handle_starting(name, namespace, state, now)
        elif phase == GroupPhase.LOADING_WEIGHTS:
            self._handle_loading_weights(name, namespace, state, now)
        elif phase == GroupPhase.INITIALIZING:
            self._handle_initializing(name, namespace, state, now)
        elif phase == GroupPhase.WARMING:
            self._handle_warming(name, namespace, state, now)
        elif phase == GroupPhase.ERROR:
            self._handle_error(name, namespace, state, now)

    def _transition(self, name: str, namespace: str, state: ReplicaGroupState, target: GroupPhase):
        if target not in TRANSITIONS.get(state.phase, []):
            log.warning("invalid transition", name=name, namespace=namespace,
                        from_phase=state.phase.value, to=target.value)
            return
        old = state.phase
        state.phase = target
        state.stage_started_at = time.monotonic()
        self._record_transition_metric(name, namespace, old, target)
        self._write_status(name, namespace, state)
        log.info("state transition", name=name, namespace=namespace,
                 from_phase=old.value, to=target.value)

    def _record_transition_metric(self, name: str, namespace: str, old: GroupPhase, new: GroupPhase):
        if self.metrics:
            self.metrics.record_state_transition(namespace, name, old.value, new.value)

    def _write_status(self, name: str, namespace: str, state: ReplicaGroupState):
        try:
            body = {
                "status": {
                    "phase": state.phase.value,
                    "observedGeneration": state.status.observedGeneration,
                    "readyReplicas": state.status.readyReplicas,
                    "readyWorkers": state.status.readyWorkers,
                    "conditions": [c.__dict__ for c in state.status.conditions],
                    "lastWakeDuration": state.status.lastWakeDuration,
                    "gpuHoursSaved": state.status.gpuHoursSaved,
                    "requestLoss": state.status.requestLoss,
                }
            }
            self.custom_api.patch_namespaced_custom_object_status(
                group="kubbernetd.io",
                version="v1",
                namespace=namespace,
                plural="replicagroups",
                name=name,
                body=body,
            )
        except client.exceptions.ApiException as e:
            if e.status == 404:
                log.warning("replicagroup not found for status write", name=name)
            else:
                log.warning("failed to write status", name=name, error=str(e))
        except Exception as e:
            log.warning("failed to write status", name=name, error=str(e))

    def _set_condition(self, state: ReplicaGroupState, cond_type: str, status: str, reason: str, message: str = ""):
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        for c in state.status.conditions:
            if c.type == cond_type:
                c.status = status
                c.reason = reason
                c.message = message
                c.lastTransitionTime = now
                return
        from kubbernetd.common.types import ReplicaGroupCondition
        state.status.conditions.append(ReplicaGroupCondition(
            type=cond_type, status=status, reason=reason, message=message, lastTransitionTime=now,
        ))

    def _handle_running(self, name: str, namespace: str, state: ReplicaGroupState, now: float):
        spec = state.spec
        sleep_policy = spec.get("sleepPolicy", {})
        idle_timeout = sleep_policy.get("idleTimeout", self.config.idle_timeout_seconds)
        if idle_timeout <= 0:
            return
        self._reconcile_worker_count(name, namespace, state)
        if state.current_workers == 0:
            self._transition(name, namespace, state, GroupPhase.SLEEPING)
            return
        self._set_condition(state, "Ready", "True", "Serving", f"{state.current_workers} workers running")
        self._write_status(name, namespace, state)

    def _handle_draining(self, name: str, namespace: str, state: ReplicaGroupState, now: float):
        self._set_condition(state, "Draining", "True", "WaitingForSequences", "draining active requests")
        self._write_status(name, namespace, state)
        self._transition(name, namespace, state, GroupPhase.SCALING_DOWN)

    def _handle_scaling_down(self, name: str, namespace: str, state: ReplicaGroupState, now: float):
        try:
            target = state.spec.get("targetRef", {}).get("name", "")
            kind = state.spec.get("targetRef", {}).get("kind", "Deployment")
            if kind == "Deployment" and target:
                self.apps_api.patch_namespaced_deployment_scale(
                    name=target, namespace=namespace, body={"spec": {"replicas": 0}},
                )
            state.current_workers = 0
            state.status.readyReplicas = 0
            state.status.readyWorkers = []
            if self.metrics:
                self.metrics.set_worker_count(namespace, name, 0)
            self._transition(name, namespace, state, GroupPhase.SLEEPING)
        except client.exceptions.ApiException as e:
            log.warning("scale-down failed", name=name, error=str(e))
            self._transition(name, namespace, state, GroupPhase.ERROR)

    def _handle_sleeping(self, name: str, namespace: str, state: ReplicaGroupState, now: float):
        self._set_condition(state, "Ready", "False", "Sleeping", "zero replicas, waiting for wake")
        self._write_status(name, namespace, state)

    def _handle_allocating(self, name: str, namespace: str, state: ReplicaGroupState, now: float):
        self._set_condition(state, "Ready", "False", "Allocating", "scheduling GPUs and starting workers")
        self._write_status(name, namespace, state)
        try:
            target = state.spec.get("targetRef", {}).get("name", "")
            kind = state.spec.get("targetRef", {}).get("kind", "Deployment")
            spec_model = state.spec.get("model", {})
            workers = spec_model.get("workers", 1)
            if kind == "Deployment" and target:
                self.apps_api.patch_namespaced_deployment_scale(
                    name=target, namespace=namespace, body={"spec": {"replicas": workers}},
                )
            if self.metrics:
                self.metrics.set_worker_count(namespace, name, workers)
            state.current_workers = workers
            self._transition(name, namespace, state, GroupPhase.STARTING)
        except client.exceptions.ApiException as e:
            log.warning("scale-up failed during allocate", name=name, error=str(e))
            self._transition(name, namespace, state, GroupPhase.ERROR)

    def _handle_starting(self, name: str, namespace: str, state: ReplicaGroupState, now: float):
        self._set_condition(state, "Ready", "False", "Starting", "containers starting")
        running_workers = self._count_running_pods(namespace, state.spec.get("targetRef", {}).get("name", ""))
        state.status.readyReplicas = running_workers
        self._write_status(name, namespace, state)
        spec_model = state.spec.get("model", {})
        workers = spec_model.get("workers", 1)
        if running_workers >= workers:
            self._transition(name, namespace, state, GroupPhase.LOADING_WEIGHTS)

    def _handle_loading_weights(self, name: str, namespace: str, state: ReplicaGroupState, now: float):
        self._set_condition(state, "Ready", "False", "LoadingWeights", "loading model shards to GPU")
        self._write_status(name, namespace, state)
        all_loaded = self._check_agent_annotation(namespace, state.spec.get("targetRef", {}).get("name", ""), "kubbernetd.io/weight-status", "loaded")
        if all_loaded:
            state.wake_stages.weightLoading = time.monotonic() - state.stage_started_at
            self._transition(name, namespace, state, GroupPhase.INITIALIZING)

    def _handle_initializing(self, name: str, namespace: str, state: ReplicaGroupState, now: float):
        self._set_condition(state, "Ready", "False", "Initializing", "CUDA + NCCL + engine init")
        cuda_ready = self._check_agent_annotation(namespace, state.spec.get("targetRef", {}).get("name", ""), "kubbernetd.io/cuda-status", "ready")
        nccl_ready = self._check_agent_annotation(namespace, state.spec.get("targetRef", {}).get("name", ""), "kubbernetd.io/nccl-status", "ready")
        if cuda_ready and nccl_ready:
            self._transition(name, namespace, state, GroupPhase.WARMING)

    def _handle_warming(self, name: str, namespace: str, state: ReplicaGroupState, now: float):
        self._set_condition(state, "Ready", "False", "Warming", "running warmup probe")
        engine_ready = self._check_agent_annotation(namespace, state.spec.get("targetRef", {}).get("name", ""), "kubbernetd.io/engine-status", "ready")
        if engine_ready:
            state.wake_stages.warmup = time.monotonic() - state.stage_started_at
            elapsed = time.monotonic() - state.wake_started_at
            state.status.lastWakeDuration = elapsed
            self._set_condition(state, "Ready", "True", "Running", "all workers ready and serving")
            self._write_status(name, namespace, state)
            self._transition(name, namespace, state, GroupPhase.RUNNING)

    def _handle_error(self, name: str, namespace: str, state: ReplicaGroupState, now: float):
        self._set_condition(state, "Ready", "False", "Error", f"error_count={state.error_count}")
        self._write_status(name, namespace, state)
        error_backoff = min(2 ** state.error_count, 30)
        if now - state.last_error_at > error_backoff:
            state.error_count += 1
            state.last_error_at = now
            self._transition(name, namespace, state, GroupPhase.SLEEPING)

    def _reconcile_worker_count(self, name: str, namespace: str, state: ReplicaGroupState):
        try:
            target = state.spec.get("targetRef", {}).get("name", "")
            if not target:
                return
            dep = self.apps_api.read_namespaced_deployment(name=target, namespace=namespace)
            actual = dep.spec.replicas or 0
            if actual != state.current_workers:
                log.info("worker count drift corrected", name=name, cached=state.current_workers, actual=actual)
                state.current_workers = actual
        except client.exceptions.ApiException:
            pass
        except Exception:
            pass

    def _count_running_pods(self, namespace: str, deployment_name: str) -> int:
        try:
            pods = self.core_api.list_namespaced_pod(
                namespace=namespace,
                label_selector=f"app={deployment_name}",
            )
            return sum(1 for p in pods.items if p.status.phase == "Running")
        except Exception:
            return 0

    def _check_agent_annotation(self, namespace: str, deployment_name: str, annotation_key: str, expected: str) -> bool:
        try:
            pods = self.core_api.list_namespaced_pod(
                namespace=namespace,
                label_selector=f"app={deployment_name}",
            )
            for pod in pods.items:
                if pod.status.phase != "Running":
                    return False
                annotations = pod.metadata.annotations or {}
                if annotations.get(annotation_key) != expected:
                    return False
            return len(pods.items) > 0
        except Exception:
            return False