"""Privacy-preserving local CLI and project context inspection."""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, Field

_SENSITIVE_NAME = re.compile(r"(?:api_?)?(?:key|secret|password|token)", re.IGNORECASE)
_CONTEXT_FILES = ("package.json", "requirements.txt", "pyproject.toml", "Dockerfile")


class CLIArgument(BaseModel):
    """A statically discovered argparse option."""

    flags: list[str]
    destination: str | None = None
    action: str | None = None
    required: bool = False
    default: str | int | float | bool | None = None
    help_text: str | None = None


class EnvironmentVariable(BaseModel):
    """An environment variable descriptor with no value by design."""

    name: str
    is_sensitive: bool


class LocalContext(BaseModel):
    """Structured, LLM-ready context that never contains environment values."""

    working_directory: str
    files_present: list[str] = Field(default_factory=list)
    git_status: str | None = None
    cli_arguments: list[CLIArgument] = Field(default_factory=list)
    environment_variables: list[EnvironmentVariable] = Field(default_factory=list)


class ArgparseInspector(ast.NodeVisitor):
    """Extract literal ``ArgumentParser.add_argument`` calls from Python source."""

    def __init__(self) -> None:
        self._parser_names: set[str] = set()
        self.arguments: list[CLIArgument] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._is_argument_parser(node.value):
            self._parser_names.update(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self._is_argument_parser(node.value) and isinstance(node.target, ast.Name):
            self._parser_names.add(node.target.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if self._is_add_argument_call(node):
            argument = self._parse_argument(node)
            if argument is not None:
                self.arguments.append(argument)
        self.generic_visit(node)

    def _is_argument_parser(self, node: ast.AST | None) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "ArgumentParser"
        )

    def _is_add_argument_call(self, node: ast.Call) -> bool:
        return (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in self._parser_names
        )

    def _parse_argument(self, node: ast.Call) -> CLIArgument | None:
        flags = [value.value for value in node.args if isinstance(value, ast.Constant) and isinstance(value.value, str)]
        if not flags:
            return None
        values = {keyword.arg: _literal(keyword.value) for keyword in node.keywords if keyword.arg}
        destination = values.get("dest")
        if not isinstance(destination, str):
            destination = next((flag.lstrip("-").replace("-", "_") for flag in flags if flag.startswith("--")), None)
        default = values.get("default")
        if _is_sensitive_argument(flags, destination):
            default = None
        return CLIArgument(
            flags=flags,
            destination=destination,
            action=values.get("action") if isinstance(values.get("action"), str) else None,
            required=values.get("required") is True,
            default=default if isinstance(default, (str, int, float, bool)) or default is None else None,
            help_text=values.get("help") if isinstance(values.get("help"), str) else None,
        )


def inspect_argparse(source_path: Path) -> list[CLIArgument]:
    """Return statically resolvable argparse parameters without executing source."""
    try:
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(source_path))
    except (OSError, SyntaxError):
        return []
    visitor = ArgparseInspector()
    visitor.visit(tree)
    return visitor.arguments


def scan_local_context(working_directory: Path) -> LocalContext:
    """Build local context while intentionally excluding every environment value."""
    root = working_directory.resolve()
    files_present = [name for name in _CONTEXT_FILES if (root / name).is_file()]
    main_path = root / "main.py"
    cli_arguments = inspect_argparse(main_path) if main_path.is_file() else []
    environment_variables = _environment_names(root)
    return LocalContext(
        working_directory=str(root),
        files_present=files_present,
        cli_arguments=cli_arguments,
        environment_variables=environment_variables,
    )


def _environment_names(root: Path) -> list[EnvironmentVariable]:
    names = set(os.environ)
    env_path = root / ".env"
    if env_path.is_file():
        try:
            names.update(_read_env_names(env_path.read_text(encoding="utf-8")))
        except OSError:
            pass
    return [
        EnvironmentVariable(name=name, is_sensitive=bool(_SENSITIVE_NAME.search(name)))
        for name in sorted(names)
    ]


def _read_env_names(content: str) -> Iterable[str]:
    for line in content.splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        name, separator, _ = candidate.removeprefix("export ").partition("=")
        if separator and name.strip():
            yield name.strip()


def _literal(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def _is_sensitive_argument(flags: list[str], destination: str | None) -> bool:
    return any(_SENSITIVE_NAME.search(value) for value in [*flags, destination or ""])
