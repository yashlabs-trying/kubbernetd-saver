import typer
from kubernetes import client, config


def _try_load_kube():
    try:
        config.load_incluster_client()
    except Exception:
        config.load_kube_config()


def unwatch(
    deployment: str = typer.Argument(..., help="Deployment name to stop watching"),
    namespace: str = typer.Option("default", "--namespace", "-n"),
):
    _try_load_kube()
    custom_api = client.CustomObjectsApi()

    try:
        custom_api.delete_namespaced_custom_object(
            group="kubbernetd.io", version="v1", namespace=namespace,
            plural="replicagroups", name=f"{deployment}-rg",
        )
        typer.echo(f"Stopped watching '{deployment}' in namespace '{namespace}'")
    except client.exceptions.ApiException as e:
        if e.status == 404:
            typer.echo(f"No ReplicaGroup found for '{deployment}' in namespace '{namespace}'")
        else:
            typer.echo(f"API error: {e}", err=True)
            raise typer.Exit(1)