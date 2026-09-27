import asyncio
import time
import structlog
from kubernetes import client, config

from kubbernetd.common.config import AgentConfig
from kubbernetd.agent.warmer import ModelWarmer
from kubbernetd.agent.reporter import StatusReporter

log = structlog.get_logger()


class Sidecar:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.warmer = ModelWarmer(config)
        self.reporter = StatusReporter()

    async def run(self):
        self.warmer.warm_up()
        while True:
            self.reporter.report_online()
            await asyncio.sleep(self.config.report_interval_seconds)


def main():
    config.load_incluster_client()
    cfg = AgentConfig()
    sidecar = Sidecar(cfg)
    asyncio.run(sidecar.run())


if __name__ == "__main__":
    main()