"""Private, sanitized local archive of successful command executions."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from lazy_cli.core.executor import ExecutionResult

_DEFAULT_ARCHIVE_PATH = Path.home() / ".lazy_wiki.md"
_SECRET_VALUE = re.compile(
    r"(?i)\b((?:[A-Z][A-Z0-9_]*_)?(?:KEY|SECRET|TOKEN|PASSWORD))=([^\s]+)"
)
_BEARER_TOKEN = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._-]+")


class WikiArchiver:
    """Append successful actions to a user-private Markdown file."""

    def __init__(self, archive_path: Path = _DEFAULT_ARCHIVE_PATH) -> None:
        self.archive_path = archive_path

    def archive(self, request: str, result: ExecutionResult) -> None:
        """Persist a sanitized record only for successful, non-timed-out commands."""
        if result.exit_code != 0 or result.timed_out:
            return
        self.archive_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        record = (
            f"\n## {datetime.now(UTC).isoformat()}\n\n"
            f"**Request:** {_sanitize(request)}\n\n"
            f"**Command:** `{_sanitize(result.command)}`\n\n"
            f"**Output:**\n```text\n{_sanitize(result.output)[:4000]}\n```\n"
        )
        self.archive_path.write_text(
            (self.archive_path.read_text(encoding="utf-8") if self.archive_path.exists() else "# lazy-cli history\n") + record,
            encoding="utf-8",
        )
        self.archive_path.chmod(0o600)


def _sanitize(value: str) -> str:
    value = _SECRET_VALUE.sub(r"\1=[REDACTED]", value)
    return _BEARER_TOKEN.sub(r"\1[REDACTED]", value)
