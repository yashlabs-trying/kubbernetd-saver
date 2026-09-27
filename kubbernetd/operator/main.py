import kopf
import structlog
from kubernetes import client, config

from kubbernetd.operator.controller import Controller
from kubbernetd.common.config import OperatorConfig

log = structlog.get_logger()
cfg = OperatorConfig()
controller = Controller(cfg)


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


def main():
    config.load_incluster_client()
    kopf.run()


if __name__ == "__main__":
    main()