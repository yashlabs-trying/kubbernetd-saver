import typer


def watch(
    deployment: str = typer.Argument(..., help="Deployment name to watch"),
    namespace: str = typer.Option("default", "--namespace", "-n"),
    idle_timeout: int = typer.Option(300, "--idle-timeout", "-t", help="Idle timeout in seconds"),
):
    typer.echo(f"Watching deployment '{deployment}' in namespace '{namespace}'")
    typer.echo(f"Idle timeout: {idle_timeout}s")
    typer.echo("Run 'kubbernetd dashboard' to see your savings")