import typer
from rich.console import Console
from rich.table import Table


def dashboard():
    console = Console()
    table = Table(title="kubbernetd Savings Dashboard")
    table.add_column("Deployment", style="cyan")
    table.add_column("Namespace", style="magenta")
    table.add_column("Status", style="green")
    table.add_column("Idle Time", style="yellow")
    table.add_column("Saved (est.)", style="bold green")

    table.add_row("my-model", "default", "stopped", "12m 30s", "$0.42")

    console.print(table)