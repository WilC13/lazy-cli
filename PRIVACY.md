# Privacy Policy

`lazy-cli` is local-first and defaults to Ollama. The local inspector never sends environment-variable values. It records only names, marking sensitive names such as `TOKEN`, `SECRET`, `PASSWORD`, and `KEY`.

Cloud providers require explicit consent through `lazy config consent-cloud --yes`. The default sharing level is `sanitized`; `minimal` excludes CLI arguments and environment-variable names. The local config stores provider preferences only, never API keys. API keys are read from environment variables or `.env`, which is ignored by Git.

Successful executions can be archived locally at `~/.lazy_wiki.md`. Archive entries redact common `KEY=value` and bearer-token forms.
