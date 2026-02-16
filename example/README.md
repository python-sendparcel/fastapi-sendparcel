# fastapi-sendparcel — example application

Demonstration of using `fastapi-sendparcel` with Tabler UI, HTMX, and SQLAlchemy.

## Running

```bash
cd example
uv sync
uv run uvicorn app:app --reload
```

Open http://localhost:8000 in your browser.

## Structure

- `app.py` — main FastAPI application with HTML views
- `models.py` — order model (SQLAlchemy) implementing the `Order` protocol
- `delivery_sim.py` — shipment delivery provider simulator with HTTP endpoints
- `templates/` — Jinja2 templates with Tabler CSS and HTMX
