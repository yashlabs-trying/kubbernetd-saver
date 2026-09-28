import os
import time
import typer
from datetime import datetime
from kubernetes import client, config
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text


def _try_load_kube():
    try:
        config.load_incluster_client()
    except Exception:
        config.load_kube_config()


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def _estimate_savings(idle_seconds: float, hourly_cost: float = 0.50) -> float:
    return round((idle_seconds / 3600) * hourly_cost, 4)


def _fetch_data(core_api, apps_api, custom_api) -> list[dict]:
    rows = []
    try:
        replicagroups = custom_api.list_cluster_custom_object(
            group="kubbernetd.io", version="v1", plural="replicagroups",
        )
    except client.exceptions.ApiException:
        try:
            replicagroups = custom_api.list_namespaced_custom_object(
                group="kubbernetd.io", version="v1", namespace="default", plural="replicagroups",
            )
            replicagroups = {"items": replicagroups}
        except Exception:
            return [{"error": "No ReplicaGroup resources found. Run 'kubbernetd watch <deployment>' first."}]

    for item in replicagroups.get("items", []):
        spec = item.get("spec", {})
        target = spec.get("target", {})
        name = target.get("name", "unknown")
        ns = item.get("metadata", {}).get("namespace", "default")
        timeout = spec.get("idleTimeout", 300)
        min_r = spec.get("minReplicas", 0)

        try:
            dep = apps_api.read_namespaced_deployment(name=name, namespace=ns)
            current = dep.spec.replicas or 0
            status_emoji = "🔴" if current == 0 else "🟢"
            status = "stopped" if current == 0 else "running"

            pods = core_api.list_namespaced_pod(namespace=ns, label_selector=f"app={name}")
            running_pods = [p for p in pods.items if p.status.phase == "Running"]

            idle_time = 0
            savings = 0
            if current == 0:
                for pod in running_pods:
                    annotations = pod.metadata.annotations or {}
                    last_req = annotations.get("kubbernetd.io/last-request")
                    if last_req:
                        try:
                            idle_time = time.time() - float(last_req)
                        except ValueError:
                            pass
                if idle_time <= 0:
                    idle_time = timeout + 1
                savings = _estimate_savings(idle_time)

            rows.append({
                "name": name,
                "namespace": ns,
                "status": f"{status_emoji} {status}",
                "replicas": str(current),
                "min": str(min_r),
                "timeout": _format_duration(timeout),
                "idle": _format_duration(idle_time) if current == 0 else "—",
                "saved": f"${savings:.2f}" if savings > 0 else "$0.00",
            })

        except client.exceptions.ApiException:
            rows.append({
                "name": name,
                "namespace": ns,
                "status": "⚠️ error",
                "replicas": "?",
                "min": str(min_r),
                "timeout": _format_duration(timeout),
                "idle": "—",
                "saved": "—",
            })

    return rows


def dashboard(
    watch_mode: bool = typer.Option(False, "--watch", "-w", help="Refresh every 5 seconds"),
):
    _try_load_kube()
    core_api = client.CoreV1Api()
    apps_api = client.AppsV1Api()
    custom_api = client.CustomObjectsApi()
    console = Console()

    while True:
        rows = _fetch_data(core_api, apps_api, custom_api)

        if not rows:
            console.print("[yellow]No deployments are being watched yet.[/yellow]")
            console.print("Run: [bold]kubbernetd watch deployment/<name>[/bold]")
            return

        if "error" in rows[0]:
            console.print(f"[yellow]{rows[0]['error']}[/yellow]")
            return

        total_saved = sum(float(r["saved"].replace("$", "")) for r in rows)
        stopped_count = sum(1 for r in rows if "stopped" in r["status"])

        table = Table(title="kubbernetd Savings Dashboard", title_style="bold cyan")
        table.add_column("Deployment", style="cyan")
        table.add_column("Namespace", style="magenta")
        table.add_column("Status", style="bold")
        table.add_column("Replicas", style="blue", justify="center")
        table.add_column("Idle Timeout", style="yellow", justify="center")
        table.add_column("Idle", style="yellow", justify="center")
        table.add_column("Saved", style="bold green", justify="right")

        for r in rows:
            table.add_row(
                r["name"], r["namespace"], r["status"],
                r["replicas"], r["timeout"], r["idle"], r["saved"],
            )

        console.clear()
        console.print(Panel(
            f"[bold green]Total Saved: ${total_saved:.2f}[/bold green]    "
            f"[bold]Deployments:[/bold] {len(rows)}    "
            f"[bold]Stopped:[/bold] {stopped_count}    "
            f"[bold]Running:[/bold] {len(rows) - stopped_count}",
            title="Summary",
        ))
        console.print("")
        console.print(table)

        if not watch_mode:
            break

        time.sleep(5)