import subprocess
import sys

import click

from service_framework.sdk import ServiceContext


@click.group()
def main():
    """Service Framework CLI Tool."""
    pass


@main.command(context_settings=dict(ignore_unknown_options=True, allow_extra_args=True))
@click.option("--service-name", required=True, help="Name of the service")
@click.pass_context
def run(ctx: click.Context, service_name: str):
    """Executes an arbitrary binary/script within the service framework context."""
    if not ctx.args:
        click.echo("Error: No command or script specified to execute.", err=True)
        sys.exit(1)

    cmd = ctx.args
    sfw_ctx = ServiceContext(service_name=service_name)
    sfw_ctx.log("INFO", f"Starting command execution: {' '.join(cmd)}")

    try:
        res = subprocess.run(cmd)
        if res.returncode == 0:
            sfw_ctx.update_status("SUCCESS", exit_code=0)
            sfw_ctx.log("INFO", "Command completed successfully")
        else:
            sfw_ctx.update_status(
                "FAILED",
                error=f"Process exited with status code {res.returncode}",
                exit_code=res.returncode,
            )
            sfw_ctx.log("ERROR", f"Command failed with exit code {res.returncode}")
        sys.exit(res.returncode)
    except Exception as e:
        sfw_ctx.update_status("FAILED", error=str(e), exit_code=1)
        sfw_ctx.log("ERROR", f"Execution error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
