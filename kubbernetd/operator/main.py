import asyncio
import threading

import kopf
import structlog
from kubernetes import client, config

from kubbernetd.operator.controller import Controller
from kubbernetd.common.types import OperatorConfig

log = structlog.get_logger()
cfg = OperatorConfig()
controller = Controller(cfg)


def _tick_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while True:
        try:
            controller.tick()
        except Exception:
            log.exception("tick loop crashed — continuing")
        loop.run_until_complete(asyncio.sleep(cfg.check_interval_seconds))


@kopf.on.startup()
def on_startup(**kwargs):
    controller.mark_ready()
    controller.sync_from_cluster()
    thread = threading.Thread(target=_tick_loop, daemon=True, name="tick-loop")
    thread.start()
    log.info("operator started", check_interval=cfg.check_interval_seconds,
             idle_timeout=cfg.idle_timeout_seconds)


@kopf.on.create("kubbernetd.io", "v1", "costsavers")
def on_create(spec, namespace, name, **kwargs):
    log.info("costsaver created", name=name, namespace=namespace)
    controller.register_service(name, namespace, spec)


@kopf.on.update("kubbernetd.io", "v1", "costsavers")
def on_update(spec, namespace, name, **kwargs):
    log.info("costsaver updated", name=name, namespace=namespace)
    controller.update_service(name, namespace, spec)


@kopf.on.delete("kubbernetd.io", "v1", "costsavers")
def on_delete(namespace, name, **kwargs):
    log.info("costsaver deleted", name=name, namespace=namespace)
    controller.remove_service(name, namespace)


@kopf.on.resume("kubbernetd.io", "v1", "costsavers")
def on_resume(spec, namespace, name, **kwargs):
    log.info("costsaver resumed (operator restart)", name=name, namespace=namespace)
    controller.register_service(name, namespace, spec)


def main():
    try:
        config.load_incluster_client()
    except Exception:
        log.warning("not in cluster — loading kubeconfig for local dev")
        config.load_kube_config()
    kopf.run()


if __name__ == "__main__":
    main()