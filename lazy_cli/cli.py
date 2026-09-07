"""The lazy command-line interface."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from lazy_cli.config import UserConfig, load_config, save_config
from lazy_cli.core.archiver import WikiArchiver
from lazy_cli.core.executor import ExecutionRefused, SafeExecutor
from lazy_cli.core.generator import GenerationError, create_generator
from lazy_cli.core.guardrail import RiskLevel
from lazy_cli.core.inspector import scan_local_context
from lazy_cli.core.risk_assessor import SemanticRiskAssessor
from lazy_cli.settings import ContextSharingLevel, LazySettings, ProviderName

app = typer.Typer(no_args_is_help=True)
config_app = typer.Typer(no_args_is_help=True)
app.add_typer(config_app, name="config")
console = Console()


@app.command("ask")
def ask(
    request: Annotated[str, typer.Argument(help="Describe the command you need.")],
    run: Annotated[bool, typer.Option("--run", help="Offer to run the proposal after safety checks.")] = False,
) -> None:
    """Generate a command proposal and optionally run it after explicit confirmation."""
    settings = LazySettings()
    config = load_config()
    try:
        context = scan_local_context(Path.cwd())
        proposal = asyncio.run(create_generator(settings, config).generate(request, context))
    except GenerationError as error:
        typer.echo(f"Generation failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    _show_proposal(proposal.command, proposal.explanation, proposal.assumptions)
    executor = SafeExecutor()
    l1 = executor.preview(proposal.command)
    _show_risk("L1 deterministic check", l1.level, l1.reason)
    if l1.blocked:
        raise typer.Exit(code=1)
    if not run:
        return
    try:
        l2 = asyncio.run(SemanticRiskAssessor(settings, config).assess(proposal.command))
    except GenerationError as error:
        typer.echo(f"Execution refused: L2 risk assessment failed ({error}).", err=True)
        raise typer.Exit(code=1) from error
    _show_risk("L2 semantic check", l2.level, l2.reason)
    if l2.level == RiskLevel.CRITICAL:
        typer.echo("Execution refused: L2 marked this command critical.", err=True)
        raise typer.Exit(code=1)
    if not typer.confirm("Run this command in the current directory?", default=False):
        typer.echo("Cancelled.")
        return
    try:
        result = executor.execute(proposal.command, Path.cwd(), console.print)
    except ExecutionRefused as error:
        typer.echo(f"Execution refused: {error}", err=True)
        raise typer.Exit(code=1) from error
    WikiArchiver().archive(request, result)
    if result.timed_out:
        typer.echo("Command timed out.", err=True)
        raise typer.Exit(code=124)
    if result.exit_code != 0:
        raise typer.Exit(code=result.exit_code)


@app.command("doctor")
def doctor() -> None:
    """Show provider readiness without ever revealing credential values."""
    settings = LazySettings()
    config = load_config()
    table = Table(title="lazy-cli diagnostics")
    table.add_column("Setting")
    table.add_column("Status")
    table.add_row("Provider", config.provider)
    table.add_row("Model", config.model or settings.ollama_model)
    table.add_row("Context sharing", config.context_sharing)
    table.add_row("Cloud consent", str(config.cloud_context_consent))
    key = {"openai": settings.openai_api_key, "anthropic": settings.anthropic_api_key, "xai": settings.xai_api_key}.get(config.provider)
    if key is not None:
        table.add_row("Provider API key", "configured" if key.get_secret_value() else "missing")
    console.print(table)


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


@config_app.command("revoke-cloud-consent")
def revoke_cloud_consent() -> None:
    """Stop future cloud context sharing until consent is granted again."""
    config = load_config()
    save_config(config.model_copy(update={"cloud_context_consent": False}))
    typer.echo("Cloud context sharing consent revoked.")


@config_app.command("reset")
def reset() -> None:
    """Restore non-secret preferences to secure defaults."""
    save_config(UserConfig())
    typer.echo("Configuration reset to local-first defaults.")


def _show_proposal(command: str, explanation: str, assumptions: list[str]) -> None:
    content = Syntax(command, "bash", word_wrap=True)
    console.print(Panel(content, title="Command proposal"))
    console.print(f"[bold]Why:[/bold] {explanation}")
    if assumptions:
        console.print("[bold]Assumptions:[/bold] " + "; ".join(assumptions))


def _show_risk(source: str, level: RiskLevel, reason: str) -> None:
    style = {RiskLevel.SAFE: "green", RiskLevel.WARNING: "yellow", RiskLevel.CRITICAL: "red"}[level]
    console.print(f"[{style}]{source}: {level.upper()}[/{style}] - {reason}")


if __name__ == "__main__":
    app()
