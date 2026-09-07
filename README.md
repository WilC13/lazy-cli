# lazy-cli

A privacy-aware natural-language CLI assistant. `lazy` statically inspects local `argparse` projects and generates a structured command proposal. It does not execute the proposal.

## Providers

Ollama is the default local provider. OpenAI, Anthropic, and xAI are also supported through a unified generator interface.

```sh
# Local-first default
lazy config set --provider ollama --model qwen2.5:7b

# Configure a cloud provider and model. API keys stay in environment variables.
lazy config set --provider openai --model gpt-4o-mini
lazy config consent-cloud --yes
lazy ask "show uncommitted Git changes"
```

Set `LAZY_OPENAI_API_KEY`, `LAZY_ANTHROPIC_API_KEY`, or `LAZY_XAI_API_KEY` in your environment for cloud providers. The user config at `~/.config/lazy-cli/config.json` stores no credentials.

Cloud providers require explicit `lazy config consent-cloud --yes` before any sanitized local context is sent. Context sharing defaults to `sanitized`; use `lazy config set --context-sharing minimal` to omit CLI arguments and environment-variable names. Environment values are never included.

## Development

```sh
uv run python -m unittest discover -s tests -v
```
