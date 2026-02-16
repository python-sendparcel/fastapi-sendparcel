# fastapi-sendparcel — przykładowa aplikacja

Demonstracja użycia `fastapi-sendparcel` z Tabler UI, HTMX i SQLAlchemy.

## Uruchomienie

```bash
cd example
uv sync
uv run uvicorn app:app --reload
```

Otwórz http://localhost:8000 w przeglądarce.

## Struktura

- `app.py` — główna aplikacja FastAPI z widokami HTML
- `models.py` — model zamówienia (SQLAlchemy) implementujący protokół `Order`
- `delivery_sim.py` — symulator dostawcy przesyłek z endpointami HTTP
- `templates/` — szablony Jinja2 z Tabler CSS i HTMX
