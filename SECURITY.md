# Security Policy

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability or leaked credential. Contact the repository maintainers privately with reproduction steps and impact.

## Safety model

`lazy-cli` never executes a generated command unless the user passes `--run` and confirms interactively. L1 blocks known destructive patterns. L2 uses the selected model for semantic review; a critical L2 result or an L2 error prevents execution. The executor uses `shell=False` and rejects shell operators.

No guardrail can make arbitrary shell commands safe. Review every proposal before confirming it.
