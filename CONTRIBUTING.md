# Contributing

Use Python 3.11 or newer and install the project with `uv sync --all-groups`.

Before opening a pull request, run:

```sh
uv run ruff check .
uv run pyright
uv run python -m unittest discover -s tests -v
```

Never commit `.env` files, credentials, user archives, or generated logs. Add focused tests for safety and privacy behavior changes.
