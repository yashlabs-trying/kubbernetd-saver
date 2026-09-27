import typer

from kubbernetd.cli.install import install
from kubbernetd.cli.watch import watch
from kubbernetd.cli.dashboard import dashboard

app = typer.Typer(name="kubbernetd", help="Scale K8s pods to zero when idle. Save costs.")
app.command()(install)
app.command()(watch)
app.command()(dashboard)


if __name__ == "__main__":
    app()