import typer

from kubbernetd.cli.dashboard import dashboard
from kubbernetd.cli.install import install
from kubbernetd.cli.status import status
from kubbernetd.cli.unwatch import unwatch
from kubbernetd.cli.watch import watch

app = typer.Typer(name="kubbernetd", help="Scale K8s pods to zero when idle. Save costs.")
app.command()(install)
app.command()(watch)
app.command()(unwatch)
app.command()(dashboard)
app.command()(status)


if __name__ == "__main__":
    app()