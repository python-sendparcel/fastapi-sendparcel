"""Public API surface tests."""

import re

import fastapi_sendparcel


def test_all_exports_exact_set() -> None:
    expected = {
        "CallbackRetryStore",
        "FastAPIPluginRegistry",
        "SendparcelConfig",
        "ShipmentNotFoundError",
        "__version__",
        "create_shipping_router",
        "register_exception_handlers",
    }
    assert set(fastapi_sendparcel.__all__) == expected
    assert len(fastapi_sendparcel.__all__) == 7


def test_all_exports_importable() -> None:
    for name in fastapi_sendparcel.__all__:
        obj = getattr(fastapi_sendparcel, name)
        assert obj is not None, f"{name} resolved to None"


def test_version_semver_format() -> None:
    version = fastapi_sendparcel.__version__
    assert isinstance(version, str)
    assert len(version) > 0
    assert re.match(r"^\d+\.\d+\.\d+", version), (
        f"Version {version!r} does not match semver format"
    )
