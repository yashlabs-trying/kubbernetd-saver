from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from os import environ
from typing import Optional


class PodStatus(Enum):
    RUNNING = "running"
    IDLE = "idle"
    STOPPED = "stopped"
    STARTING = "starting"


@dataclass
class ServiceState:
    name: str
    namespace: str
    current_replicas: int
    target_replicas: int
    status: PodStatus
    last_request_at: Optional[datetime] = None
    idle_since: Optional[datetime] = None
    savings_estimate: float = 0.0


@dataclass
class ScaleEvent:
    timestamp: datetime
    deployment: str
    namespace: str
    from_replicas: int
    to_replicas: int
    reason: str


@dataclass
class OperatorConfig:
    idle_timeout_seconds: int = int(environ.get("KUBBERNETD_IDLE_TIMEOUT", "300"))
    check_interval_seconds: int = int(environ.get("KUBBERNETD_CHECK_INTERVAL", "30"))
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
    upstream_timeout_seconds: int = int(environ.get("KUBBERNETD_UPSTREAM_TIMEOUT", "30"))
    max_buffer_size: int = int(environ.get("KUBBERNETD_MAX_BUFFER", "256"))