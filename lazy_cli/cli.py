"""The lazy command-line interface."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from lazy_cli.config import UserConfig, load_config, save_config
from lazy_cli.core.generator import GenerationError, create_generator
from lazy_cli.core.inspector import scan_local_context
from lazy_cli.settings import ContextSharingLevel, LazySettings, ProviderName

app = typer.Typer(no_args_is_help=True)
config_app = typer.Typer(no_args_is_help=True)
app.add_typer(config_app, name="config")


@app.command("ask")
def ask(request: Annotated[str, typer.Argument(help="Describe the command you need.")]) -> None:
    """Generate a command proposal; this command never executes it."""
    try:
        context = scan_local_context(Path.cwd())
        proposal = asyncio.run(create_generator(LazySettings(), load_config()).generate(request, context))
    except GenerationError as error:
        typer.echo(f"Generation failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(proposal.model_dump_json(indent=2))


@config_app.command("show")
def show() -> None:
    """Show non-secret provider preferences."""
    typer.echo(load_config().model_dump_json(indent=2))


@config_app.command("set")
def set_preference(
    provider: Annotated[ProviderName | None, typer.Option()] = None,
    model: Annotated[str | None, typer.Option()] = None,
    context_sharing: Annotated[ContextSharingLevel | None, typer.Option()] = None,
) -> None:
    """Select the LLM provider, model, or context sharing level."""
    if provider is None and model is None and context_sharing is None:
        raise typer.BadParameter("Specify at least one preference.")
    config = load_config()
    updated = config.model_copy(update={
        key: value
        for key, value in {"provider": provider, "model": model, "context_sharing": context_sharing}.items()
        if value is not None
    })
    save_config(updated)
    typer.echo("Configuration saved.")


@config_app.command("consent-cloud")
def consent_cloud(
    yes: Annotated[bool, typer.Option("--yes", help="Confirm cloud context sharing.")] = False,
) -> None:
    """Record explicit consent before sending sanitized context to cloud providers."""
    if not yes:
        raise typer.BadParameter("Re-run with --yes to confirm cloud context sharing.")
    config = load_config()
    save_config(config.model_copy(update={"cloud_context_consent": True}))
    typer.echo("Cloud context sharing consent recorded.")


if __name__ == "__main__":
    app()
