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
    deployment: str = typer.Argument(..., help="Deployment name to watch"),
    namespace: str = typer.Option("default", "--namespace", "-n"),
    idle_timeout: int = typer.Option(300, "--idle-timeout", "-t", help="Idle timeout in seconds"),
    min_replicas: int = typer.Option(0, "--min-replicas", help="Minimum replicas (0 to scale to zero)"),
    max_replicas: int = typer.Option(10, "--max-replicas", help="Maximum replicas"),
):
    _try_load_kube()

    custom_api = client.CustomObjectsApi()

    body = {
        "apiVersion": "kubbernetd.io/v1",
        "kind": "CostSaver",
        "metadata": {
            "name": f"{deployment}-saver",
            "namespace": namespace,
        },
        "spec": {
            "target": {
                "kind": "Deployment",
                "name": deployment,
            },
            "idleTimeout": idle_timeout,
            "minReplicas": min_replicas,
            "maxReplicas": max_replicas,
            "shadowPods": 1,
        },
    }

    try:
        existing = custom_api.get_namespaced_custom_object(
            group="kubbernetd.io",
            version="v1",
            namespace=namespace,
            plural="costsavers",
            name=f"{deployment}-saver",
        )
        custom_api.patch_namespaced_custom_object(
            group="kubbernetd.io",
            version="v1",
            namespace=namespace,
            plural="costsavers",
            name=f"{deployment}-saver",
            body=body,
        )
        typer.echo(f"Updated CostSaver for '{deployment}' in namespace '{namespace}'")
    except client.exceptions.ApiException as e:
        if e.status == 404:
            custom_api.create_namespaced_custom_object(
                group="kubbernetd.io",
                version="v1",
                namespace=namespace,
                plural="costsavers",
                body=body,
            )
            typer.echo(f"Now watching '{deployment}' in namespace '{namespace}'")
            typer.echo(f"  idle timeout: {idle_timeout}s")
            typer.echo(f"  min replicas: {min_replicas}")
            typer.echo(f"  max replicas: {max_replicas}")
            typer.echo("")
            typer.echo("Run 'kubbernetd dashboard' to see your savings")
        else:
            typer.echo(f"API error: {e}", err=True)
            raise typer.Exit(1)