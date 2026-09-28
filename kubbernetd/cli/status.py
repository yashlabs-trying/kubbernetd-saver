import typer
from kubernetes import client, config
from rich.console import Console
from rich.table import Table
from rich.panel import Panel


def _try_load_kube():
    try:
        config.load_incluster_client()
    except Exception:
        config.load_kube_config()


def status():
    _try_load_kube()
    core_api = client.CoreV1Api()
    custom_api = client.CustomObjectsApi()
    console = Console()

    operator_pods = []
    try:
        pods = core_api.list_namespaced_pod(namespace="kubbernetd")
        operator_pods = [p for p in pods.items if "kubbernetd" in p.metadata.name]
    except client.exceptions.ApiException:
        try:
            pods = core_api.list_pod_for_all_namespaces(watch=False)
            operator_pods = [p for p in pods.items if "kubbernetd" in p.metadata.name]
        except Exception:
            pass

    watched_count = 0
    try:
        crds = custom_api.list_cluster_custom_object(
            group="kubbernetd.io", version="v1", plural="replicagroups",
        )
        watched_count = len(crds.get("items", []))
    except Exception:
        pass

    table = Table(title="kubbernetd System Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details")

    if operator_pods:
        for pod in operator_pods:
            phase = pod.status.phase
            emoji = "🟢" if phase == "Running" else "🟡" if phase == "Pending" else "🔴"
            table.add_row("Operator", f"{emoji} {phase}", pod.metadata.name)
    else:
        table.add_row("Operator", "⚠️ not found", "Run 'kubbernetd install' first")

    table.add_row("ReplicaGroups", f"{watched_count} watched", f"{watched_count} model replica group(s) being monitored")
    table.add_row("Version", "0.1.0", "github.com/yashlabs-trying/kubbernetd-saver")

    is_healthy = len(operator_pods) > 0
    console.print(Panel(
        "[bold green]kubbernetd is running[/bold green]" if is_healthy
        else "[bold yellow]kubbernetd is not fully installed[/bold yellow]",
        title="System Health",
    ))
    console.print("")
    console.print(table)