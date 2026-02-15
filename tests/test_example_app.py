"""FastAPI example app tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sendparcel.providers.dummy import DummyProvider
from sendparcel.registry import registry


def _load_example_module():
    path = Path(__file__).resolve().parents[1] / "examples" / "app.py"
    spec = importlib.util.spec_from_file_location(
        "fastapi_sendparcel_example",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load FastAPI example app module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_example_app_uses_builtin_dummy_provider() -> None:
    module = _load_example_module()

    assert DummyProvider.slug == module.DEFAULT_PROVIDER
    assert registry.get_by_slug("dummy") is DummyProvider

    with TestClient(module.app) as client:
        response = client.post("/shipments", json={"order_id": "o-1"})

    assert response.status_code == 200
    assert response.json()["provider"] == "dummy"
