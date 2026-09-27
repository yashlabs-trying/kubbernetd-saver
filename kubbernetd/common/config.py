from dataclasses import dataclass, field
from os import environ
from typing import Optional


@dataclass
class OperatorConfig:
    idle_timeout_seconds: int = int(environ.get("KUBBERNETD_IDLE_TIMEOUT", "300"))
    check_interval_seconds: int = int(environ.get("KUBBERNETD_CHECK_INTERVAL", "30"))
    namespace: Optional[str] = environ.get("KUBBERNETD_NAMESPACE", None)
    metrics_port: int = int(environ.get("KUBBERNETD_METRICS_PORT", "8080"))


@dataclass
class AgentConfig:
    report_interval_seconds: int = int(environ.get("KUBBERNETD_AGENT_REPORT_INTERVAL", "15"))
    warmup_command: Optional[str] = environ.get("KUBBERNETD_WARMUP_CMD", None)


@dataclass
class ProxyConfig:
    listen_port: int = int(environ.get("KUBBERNETD_PROXY_PORT", "8080"))
    upstream_timeout_seconds: int = int(environ.get("KUBBERNETD_UPSTREAM_TIMEOUT", "30"))
    max_buffer_size: int = int(environ.get("KUBBERNETD_MAX_BUFFER", "256"))