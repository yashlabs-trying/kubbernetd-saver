import os
import sys
import tempfile
import typer
import structlog
from pathlib import Path

log = structlog.get_logger()


def _find_config_file(name: str) -> str:
    script_dir = Path(__file__).resolve().parent.parent.parent
    candidates = [
        script_dir / "config" / name,
        Path.cwd() / "config" / name,
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return f"config/{name}"


def install(
    namespace: str = typer.Option("kubbernetd", "--namespace", "-n", help="Namespace to install into"),
    set_default: bool = typer.Option(False, "--set-default", help="Set kubectl default namespace"),
):
    import subprocess

    typer.echo(f"Installing kubbernetd operator into namespace '{namespace}'...")

    crd = _find_config_file("crd.yaml")
    rbac = _find_config_file("operator-rbac.yaml")
    deploy = _find_config_file("operator-deployment.yaml")

    result = subprocess.run(
        ["kubectl", "apply", "-f", crd],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        typer.echo(f"Failed to apply CRD: {result.stderr}", err=True)
        raise typer.Exit(1)
    typer.echo(f"  CRD applied: {result.stdout.strip()}")

    result = subprocess.run(
        ["kubectl", "create", "namespace", namespace, "--dry-run=client", "-o", "yaml"],
        capture_output=True, text=True,
    )
    subprocess.run(["kubectl", "apply", "-f", "-"], input=result.stdout, capture_output=True)

    result = subprocess.run(
        ["kubectl", "apply", "-f", rbac, "-n", namespace],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        typer.echo(f"Failed to apply RBAC: {result.stderr}", err=True)
        raise typer.Exit(1)
    typer.echo(f"  RBAC applied: {result.stdout.strip()}")

    result = subprocess.run(
        ["kubectl", "apply", "-f", deploy, "-n", namespace],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        typer.echo(f"Failed to apply operator deployment: {result.stderr}", err=True)
        raise typer.Exit(1)
    typer.echo(f"  Operator applied: {result.stdout.strip()}")

    if set_default:
        subprocess.run(
            ["kubectl", "config", "set-context", "--current", f"--namespace={namespace}"],
            capture_output=True,
        )

    typer.echo("")
    typer.echo("kubbernetd installed successfully!")
    typer.echo(f"  Operator running in namespace: {namespace}")
    typer.echo("  Run 'kubbernetd watch deployment/<name>' to start saving")