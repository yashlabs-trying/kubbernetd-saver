import os
import subprocess
import time
import structlog
from pathlib import Path
from typing import Optional

from kubbernetd.common.config import AgentConfig

log = structlog.get_logger()


class ModelWarmer:
    def __init__(self, config: AgentConfig):
        self.config = config
        self._ready = False

    def warm_up(self) -> bool:
        cmd = self.config.warmup_command

        if cmd:
            log.info("running user warmup command", cmd=cmd)
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.returncode != 0:
                log.error("warmup command failed", stderr=result.stderr)
                return False
            log.info("user warmup command completed")
        else:
            log.info("no warmup command configured, skipping")

        self._check_model_files()

        self._ready = True
        log.info("model warmup complete")
        return True

    def _check_model_files(self):
        model_path = self.config.model_path
        if model_path and Path(model_path).exists():
            log.info("model file found at path", path=model_path)
        elif model_path:
            log.warning("model file not found at path", path=model_path)

    @property
    def is_ready(self) -> bool:
        return self._ready