import subprocess
import structlog
from typing import Optional

from kubbernetd.common.config import AgentConfig

log = structlog.get_logger()


class ModelWarmer:
    def __init__(self, config: AgentConfig):
        self.config = config

    def warm_up(self):
        cmd = self.config.warmup_command
        if cmd:
            log.info("running warmup command", cmd=cmd)
            subprocess.run(cmd, shell=True, check=False)
        else:
            log.info("no warmup command configured, skipping")