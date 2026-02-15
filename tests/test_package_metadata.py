"""Package metadata tests."""

from pathlib import Path


def test_version_is_available() -> None:
    from fastapi_sendparcel import __version__

    assert __version__ == "0.1.0"


def test_py_typed_marker_exists() -> None:
    marker = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "fastapi_sendparcel"
        / "py.typed"
    )
    assert marker.exists(), "py.typed marker file must exist"


def test_all_exports_importable() -> None:
    import fastapi_sendparcel

    expected = {
        "CallbackRetryStore",
        "FastAPIPluginRegistry",
        "OrderResolver",
        "SendparcelConfig",
        "ShipmentNotFoundError",
        "__version__",
        "create_shipping_router",
        "register_exception_handlers",
    }
    assert set(fastapi_sendparcel.__all__) == expected

    for name in expected:
        obj = getattr(fastapi_sendparcel, name)
        assert obj is not None, f"{name} resolved to None"


def test_getattr_raises_for_unknown_attribute() -> None:
    import pytest

    import fastapi_sendparcel

    with pytest.raises(AttributeError, match="no_such_thing"):
        fastapi_sendparcel.no_such_thing  # noqa: B018
