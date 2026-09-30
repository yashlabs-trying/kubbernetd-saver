import asyncio
import threading

import kopf
import structlog
from kubernetes import client, config

from kubbernetd.operator.rg_controller import ReplicaGroupController
from kubbernetd.operator.metrics import MetricsExporter
from kubbernetd.common.types import OperatorConfig

log = structlog.get_logger()
cfg = OperatorConfig()

controller: ReplicaGroupController = None
metrics: MetricsExporter = None


def _tick_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while True:
        try:
            controller.tick()
            metrics.set_watched_count(len(controller._groups))
        except Exception:
            log.exception("tick loop crashed - continuing")
        loop.run_until_complete(asyncio.sleep(cfg.check_interval_seconds))


@kopf.on.startup()
def on_startup(**kwargs):
    global controller, metrics
    metrics = MetricsExporter(cfg, skip_server=False)
    controller = ReplicaGroupController(cfg, metrics)
    controller._tick_count = 0
    thread = threading.Thread(target=_tick_loop, daemon=True, name="tick-loop")
    thread.start()
    log.info("operator started", check_interval=cfg.check_interval_seconds)


@kopf.on.create("kubbernetd.io", "v1", "replicagroups")
def on_create(spec, namespace, name, **kwargs):
    log.info("replicagroup created", name=name, namespace=namespace)
    controller.register_group(name, namespace, spec)


@kopf.on.update("kubbernetd.io", "v1", "replicagroups")
def on_update(spec, namespace, name, **kwargs):
    log.info("replicagroup updated", name=name, namespace=namespace)
    controller.update_group(name, namespace, spec)


@kopf.on.delete("kubbernetd.io", "v1", "replicagroups")
def on_delete(namespace, name, **kwargs):
    log.info("replicagroup deleted", name=name, namespace=namespace)
    controller.remove_group(name, namespace)


@kopf.on.resume("kubbernetd.io", "v1", "replicagroups")
def on_resume(spec, namespace, name, **kwargs):
    log.info("replicagroup resumed (operator restart)", name=name, namespace=namespace)
    controller.register_group(name, namespace, spec)


def main():
    try:
        config.load_incluster_config()
    except Exception:
        log.warning("not in cluster - loading kubeconfig for local dev")
        config.load_kube_config()
    kopf.run()


if __name__ == "__main__":
    main()
