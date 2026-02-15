# Contributing to fastapi-sendparcel

## Development setup

```bash
uv sync --extra dev
```

## Quality checks

```bash
uv run --extra dev ruff check src tests
uv run --extra dev pytest -q
```

## Ecosystem rules

- Keep APIs async-first.
- Use `anyio` for async primitives and async/sync bridging points.
- Preserve plugin compatibility with `python-sendparcel` core contracts.
