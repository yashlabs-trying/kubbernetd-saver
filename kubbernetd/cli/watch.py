import typer
import structlog
from kubernetes import client, config

log = structlog.get_logger()


def _try_load_kube():
    try:
        config.load_incluster_client()
    except Exception:
        config.load_kube_config()


def watch(
    deployment: str = typer.Argument(..., help="Deployment name to form a ReplicaGroup for"),
    namespace: str = typer.Option("default", "--namespace", "-n"),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of worker replicas"),
    idle_timeout: int = typer.Option(300, "--idle-timeout", "-t", help="Idle timeout in seconds"),
    wake_slo: int = typer.Option(30, "--wake-slo", help="Target wake SLO in seconds"),
):
    _try_load_kube()
    custom_api = client.CustomObjectsApi()

    body = {
        "apiVersion": "kubbernetd.io/v1",
        "kind": "ReplicaGroup",
        "metadata": {
            "name": f"{deployment}-rg",
            "namespace": namespace,
        },
        "spec": {
            "model": {
                "name": deployment,
                "engine": "vLLM",
                "tensorParallel": min(workers, 8),
                "workers": workers,
                "weightShards": workers,
            },
            "targetRef": {
                "kind": "Deployment",
                "name": deployment,
            },
            "wakeSLO": wake_slo,
            "sleepPolicy": {
                "sleepDepth": "full",
                "idleTimeout": idle_timeout,
                "activeSequenceThreshold": 0,
            },
        },
    }

    name = f"{deployment}-rg"
    try:
        existing = custom_api.get_namespaced_custom_object(
            group="kubbernetd.io", version="v1", namespace=namespace,
            plural="replicagroups", name=name,
        )
        custom_api.patch_namespaced_custom_object(
            group="kubbernetd.io", version="v1", namespace=namespace,
            plural="replicagroups", name=name, body=body,
        )
        typer.echo(f"Updated ReplicaGroup for '{deployment}' ({workers} workers)")
    except client.exceptions.ApiException as e:
        if e.status == 404:
            custom_api.create_namespaced_custom_object(
                group="kubbernetd.io", version="v1", namespace=namespace,
                plural="replicagroups", body=body,
            )
            typer.echo(f"Created ReplicaGroup for '{deployment}'")
            typer.echo(f"  workers: {workers}, idle timeout: {idle_timeout}s, wake SLO: {wake_slo}s")
            typer.echo("Run 'kubbernetd dashboard' to see status")
        else:
            typer.echo(f"API error: {e}", err=True)
            raise typer.Exit(1)