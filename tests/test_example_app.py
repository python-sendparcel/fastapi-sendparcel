"""FastAPI example app tests."""

from __future__ import annotations

import importlib.util
import re
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
        page = client.get("/")
        assert page.status_code == 200
        assert "tabler.min.css" in page.text
        assert 'name="provider"' in page.text
        assert 'name="recipient_email"' in page.text
        assert 'name="sender_email"' in page.text
        assert 'name="package_size"' in page.text
        assert "dummy" in page.text

        checkout = client.post(
            "/checkout",
            data={
                "provider": "dummy",
                "recipient_email": "alice@example.com",
                "recipient_phone": "+48123456789",
                "recipient_address": "Main Street 1",
                "recipient_locker": "",
                "sender_email": "shop@example.com",
                "package_size": "M",
                "insurance": "1",
                "insurance_amount": "120",
            },
        )
        assert checkout.status_code == 200
        assert "DummyPay simulator" in checkout.text

        pay_match = re.search(r'action="(/pay/[^"]+)"', checkout.text)
        assert pay_match is not None
        payment = client.post(pay_match.group(1))
        assert payment.status_code == 200
        assert "Download label PDF" in payment.text

        label_match = re.search(r'href="(/label/[^"]+\.pdf)"', payment.text)
        assert label_match is not None
        label = client.get(label_match.group(1))
        assert label.status_code == 200
        assert label.headers["content-type"].startswith("application/pdf")
        assert label.content.startswith(b"%PDF-")
