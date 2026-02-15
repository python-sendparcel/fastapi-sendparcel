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
