# Contributing to fastapi-sendparcel

Thank you for considering a contribution to `fastapi-sendparcel` — the FastAPI
adapter for the sendparcel ecosystem.

## Prerequisites

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/) package manager

## Development setup

1. Clone the repository and navigate to the `fastapi-sendparcel` directory.
2. Install the project with dev dependencies:

```bash
uv sync --extra dev
```

## Running tests

Tests use **pytest** with **pytest-asyncio** (`asyncio_mode = "auto"`).

```bash
uv run --extra dev pytest tests/ -q
```

Always run tests through `uv run` so the correct virtualenv is used.

## Linting and formatting

The project uses **ruff** for both linting and formatting:

```bash
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
```

## Code style

- All code, comments, docstrings, and messages **must be in English**.
- Keep APIs **async-first**.
- Use `anyio` for async primitives and async/sync bridging points.
- Imports belong at the **top of the file** (PEP 8). Inline imports are
  only acceptable to break a verified circular import, with a comment
  explaining the reason.
- Follow the ruff rule set configured in `pyproject.toml`
  (`E`, `W`, `F`, `I`, `N`, `UP`, `B`, `A`, `SIM`, `RUF`).

## Pull request process

1. Fork the repository and create a feature branch from `main`.
2. Make your changes in small, focused commits.
3. Ensure all quality checks pass (tests, linting, formatting).
4. Open a pull request against `main` with a clear description of your
   changes.

## Commit messages

- Use the **imperative mood** ("Add feature", not "Added feature").
- Keep the subject line concise (72 characters or fewer).
- Reference related issues when applicable (e.g., `Fix #42`).

## Ecosystem rules

- Keep APIs async-first.
- Use `anyio` for async primitives and async/sync bridging points.
- Preserve plugin compatibility with `python-sendparcel` core contracts —
  this adapter must conform to the interfaces defined in the core package.
- Test against the editable local core (`python-sendparcel`) to catch
  breaking changes early.
