from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from os import environ
from typing import Optional


class GroupPhase(Enum):
    UNKNOWN = "UNKNOWN"
    RUNNING = "RUNNING"
    DRAINING = "DRAINING"
    SCALING_DOWN = "SCALING_DOWN"
    SLEEPING = "SLEEPING"
    ALLOCATING = "ALLOCATING"
    STARTING = "STARTING"
    LOADING_WEIGHTS = "LOADING_WEIGHTS"
    INITIALIZING = "INITIALIZING"
    WARMING = "WARMING"
    ERROR = "ERROR"


class SleepDepth(Enum):
    FULL = "full"
    WARM = "warm"
    TEPID = "tepid"
    COLD = "cold"


class ModelEngine(Enum):
    VLLM = "vLLM"
    SGLANG = "SGLang"
    TGI = "TGI"


@dataclass
class ModelSpec:
    name: str
    engine: ModelEngine = ModelEngine.VLLM
    precision: str = "bf16"
    tensorParallel: int = 1
    pipelineParallel: int = 1
    gpuPerWorker: int = 1
    workers: int = 1
    weightShards: int = 1
    shardPattern: str = "model-rank-{rank}-part-*.safetensors"

    @property
    def total_gpus(self) -> int:
        return self.workers * self.gpuPerWorker


@dataclass
class WeightCacheConfig:
    nodeNVMe: bool = True
    cpuRAM: bool = False
    gpuVRAM: bool = False


@dataclass
class TargetRef:
    kind: str = "Deployment"
    name: str = ""


@dataclass
class BootstrapConfig:
    enabled: bool = False
    bootstrapModel: str = ""
    cpuRAM: str = "0"


@dataclass
class SleepPolicy:
    sleepDepth: SleepDepth = SleepDepth.FULL
    idleTimeout: int = 300
    activeSequenceThreshold: int = 0


@dataclass
class WakeStages:
    scheduling: float = 0.0
    containerStart: float = 0.0
    weightLoading: float = 0.0
    cudaInit: float = 0.0
    ncclInit: float = 0.0
    engineInit: float = 0.0
    warmup: float = 0.0


@dataclass
class ReplicaGroupCondition:
    type: str = ""
    status: str = "Unknown"
    reason: str = ""
    message: str = ""
    lastTransitionTime: str = ""


@dataclass
class ReplicaGroupSpec:
    model: ModelSpec
    weightCache: WeightCacheConfig = field(default_factory=WeightCacheConfig)
    targetRef: TargetRef = field(default_factory=TargetRef)
    wakeSLO: int = 30
    coldStartTimeout: int = 300
    bootstrap: BootstrapConfig = field(default_factory=BootstrapConfig)
    sleepPolicy: SleepPolicy = field(default_factory=SleepPolicy)


@dataclass
class ReplicaGroupStatus:
    phase: GroupPhase = GroupPhase.UNKNOWN
    observedGeneration: int = 0
    readyReplicas: int = 0
    readyWorkers: list = field(default_factory=list)
    conditions: list = field(default_factory=list)
    lastWakeDuration: float = 0.0
    lastWakeStages: WakeStages = field(default_factory=WakeStages)
    gpuHoursSaved: float = 0.0
    requestLoss: int = 0


@dataclass
class ReplicaGroupState:
    name: str
    namespace: str
    spec: dict
    phase: GroupPhase = GroupPhase.UNKNOWN
    status: ReplicaGroupStatus = field(default_factory=ReplicaGroupStatus)
    current_workers: int = 0
    ready_worker_indices: list = field(default_factory=list)
    last_error_at: float = 0.0
    error_count: int = 0
    wake_started_at: float = 0.0
    stage_started_at: float = 0.0
    wake_stages: WakeStages = field(default_factory=WakeStages)


@dataclass
class OperatorConfig:
    idle_timeout_seconds: int = int(environ.get("KUBBERNETD_IDLE_TIMEOUT", "300"))
    check_interval_seconds: int = int(environ.get("KUBBERNETD_CHECK_INTERVAL", "10"))
    namespace: Optional[str] = environ.get("KUBBERNETD_NAMESPACE", None)
    metrics_port: int = int(environ.get("KUBBERNETD_METRICS_PORT", "8080"))
    shadow_pods: int = int(environ.get("KUBBERNETD_SHADOW_PODS", "1"))
    stale_cleanup_age: int = int(environ.get("KUBBERNETD_STALE_CLEANUP_AGE", "86400"))


@dataclass
class AgentConfig:
    warmup_command: Optional[str] = environ.get("KUBBERNETD_WARMUP_CMD", None)
    model_path: Optional[str] = environ.get("KUBBERNETD_MODEL_PATH", None)
    shadow_mode: bool = environ.get("KUBBERNETD_SHADOW_MODE", "false").lower() == "true"


@dataclass
class ProxyConfig:
    listen_port: int = int(environ.get("KUBBERNETD_PROXY_PORT", "8080"))
    upstream_port: int = int(environ.get("KUBBERNETD_UPSTREAM_PORT", "8080"))
    upstream_timeout_seconds: int = int(environ.get("KUBBERNETD_UPSTREAM_TIMEOUT", "300"))
    max_buffer_size: int = int(environ.get("KUBBERNETD_MAX_BUFFER", "256"))
    request_ttl_seconds: int = int(environ.get("KUBBERNETD_REQUEST_TTL", "30"))
    cleanup_interval_seconds: int = int(environ.get("KUBBERNETD_CLEANUP_INTERVAL", "60"))