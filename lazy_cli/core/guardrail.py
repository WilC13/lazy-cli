"""Deterministic first-line command safety checks."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel


class RiskLevel(StrEnum):
    SAFE = "safe"
    WARNING = "warning"
    CRITICAL = "critical"


class GuardrailVerdict(BaseModel):
    """The L1 decision. Critical commands must never reach execution."""

    level: RiskLevel
    reason: str
    blocked: bool


class L1Guardrail:
    """Block known destructive shell patterns without calling an LLM."""

    _CRITICAL_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"\brm\s+(?:-[A-Za-z]*[rR][fF][A-Za-z]*\s+|--recursive\s+--force\s+)(?:/|~|\$HOME)(?:\s|$)"), "Recursive forced deletion of a system or home directory."),
        (re.compile(r"\b(?:sudo\s+)?(?:tee|cat\s+>)\s*/etc/(?:passwd|shadow|sudoers)(?:\s|$)"), "Modification of a critical system account file."),
        (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*}\s*;\s*:"), "Fork bomb pattern."),
        (re.compile(r"\b(?:mkfs(?:\.[\w-]+)?|dd)\b[^\n]*(?:/dev/(?:sd|disk|nvme|rdisk))"), "Potential destructive disk operation."),
        (re.compile(r"\bchmod\s+(?:-R\s+)?(?:777|666)\s+/(?:\s|$)"), "Unsafe permissions change on the root filesystem."),
        (re.compile(r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:ba)?sh\b"), "Remote content piped directly into a shell."),
        (re.compile(r"\b(?:base64\s+-d|openssl\s+enc\s+-d)[^\n|]*\|\s*(?:ba)?sh\b"), "Decoded content piped directly into a shell."),
    )

    _WARNING_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"\bgit\s+push\s+.*--force(?:-with-lease)?\b"), "Force push can overwrite remote history."),
        (re.compile(r"\brm\s+.*(?:^|\s)-[A-Za-z]*[rR]"), "Recursive deletion requires careful review."),
        (re.compile(r"\b(?:sudo|doas)\b"), "Elevated privileges requested."),
        (re.compile(r"\bgit\s+reset\s+--hard\b"), "Hard reset discards uncommitted changes."),
    )

    def assess(self, command: str) -> GuardrailVerdict:
        """Return the highest deterministic risk found in a non-empty command."""
        normalized = command.strip()
        if not normalized:
            return GuardrailVerdict(level=RiskLevel.CRITICAL, reason="Command is empty.", blocked=True)
        for pattern, reason in self._CRITICAL_RULES:
            if pattern.search(normalized):
                return GuardrailVerdict(level=RiskLevel.CRITICAL, reason=reason, blocked=True)
        for pattern, reason in self._WARNING_RULES:
            if pattern.search(normalized):
                return GuardrailVerdict(level=RiskLevel.WARNING, reason=reason, blocked=False)
        return GuardrailVerdict(level=RiskLevel.SAFE, reason="No deterministic high-risk pattern found.", blocked=False)
