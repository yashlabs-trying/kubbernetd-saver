import asyncio
import signal
import structlog
from kubernetes import client, config

from kubbernetd.common.types import AgentConfig
from kubbernetd.agent.warmer import ModelWarmer
from kubbernetd.agent.reporter import StatusReporter
from kubbernetd.agent.engine_adapter import EngineAdapter

log = structlog.get_logger()


class Sidecar:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.warmer = ModelWarmer(config)
        self.reporter = StatusReporter()
        self.engine = EngineAdapter(self.reporter, upstream_port=8080)
        self._shutdown = False

    def handle_signal(self, signum, frame):
        log.info("received signal, shutting down", signal=signum)
        self._shutdown = True

    async def run(self):
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)

        warm_ok = self.warmer.warm_up()
        if not warm_ok:
            log.error("warmup failed, exiting")
            return

        asyncio.create_task(self.engine.run_progressive_checks())

        while not self._shutdown:
            await asyncio.sleep(1)

        self.reporter.mark_stopped()
        log.info("sidecar stopped cleanly")


def main():
    config.load_incluster_client()
    cfg = AgentConfig()
    sidecar = Sidecar(cfg)
    asyncio.run(sidecar.run())


if __name__ == "__main__":
    main()