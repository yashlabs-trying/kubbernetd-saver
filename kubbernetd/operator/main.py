import asyncio
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


def _resolve_target(spec, fallback_name):
    target = spec.get("target", {})
    return target.get("name", fallback_name)


@kopf.on.create("kubbernetd.io", "v1", "costsavers")
def on_create(spec, namespace, name, **kwargs):
    deployment_name = _resolve_target(spec, name)
    log.info("costsaver created", crd_name=name, deployment=deployment_name, namespace=namespace)
    controller.register_service(deployment_name, namespace, spec)


@kopf.on.update("kubbernetd.io", "v1", "costsavers")
def on_update(spec, namespace, name, **kwargs):
    deployment_name = _resolve_target(spec, name)
    log.info("costsaver updated", crd_name=name, deployment=deployment_name, namespace=namespace)
    controller.update_service(deployment_name, namespace, spec)


@kopf.on.delete("kubbernetd.io", "v1", "costsavers")
def on_delete(namespace, name, **kwargs):
    controller.remove_service_by_crd(namespace, name)


@kopf.on.resume("kubbernetd.io", "v1", "costsavers")
def on_resume(spec, namespace, name, **kwargs):
    deployment_name = _resolve_target(spec, name)
    log.info("costsaver resumed (operator restart)", crd_name=name, deployment=deployment_name, namespace=namespace)
    controller.register_service(deployment_name, namespace, spec)


def main():
    import threading
    try:
        config.load_incluster_client()
    except Exception:
        log.warning("not in cluster — loading kubeconfig for local dev")
        config.load_kube_config()
    kopf.run()


if __name__ == "__main__":
    main()