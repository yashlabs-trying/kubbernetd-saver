import subprocess
import typer
import structlog

log = structlog.get_logger()


def install(
    namespace: str = typer.Option("kubbernetd", "--namespace", "-n", help="Namespace to install into"),
):
    typer.echo(f"Installing kubbernetd operator into namespace '{namespace}'...")
    subprocess.run(
        ["kubectl", "apply", "-f", "config/crd.yaml"], check=True
    )
    subprocess.run(
        ["kubectl", "apply", "-f", "config/operator-rbac.yaml", "-n", namespace], check=True
    )
    typer.echo("kubbernetd installed successfully!")