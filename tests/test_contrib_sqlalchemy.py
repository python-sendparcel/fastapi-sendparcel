"""Optional sqlalchemy contrib import tests."""

import pytest


def test_sqlalchemy_contrib_importable_when_dependency_available() -> None:
    pytest.importorskip("sqlalchemy")

    from fastapi_sendparcel.contrib.sqlalchemy import (
        models,  # noqa: F401
        repository,  # noqa: F401
        retry_store,  # noqa: F401
    )
