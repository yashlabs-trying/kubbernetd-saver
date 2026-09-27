from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
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