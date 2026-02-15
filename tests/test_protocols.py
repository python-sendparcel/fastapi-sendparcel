"""Protocol conformance tests."""

from fastapi_sendparcel.protocols import CallbackRetryStore


class _FullRetryStore:
    """Minimal implementation to verify protocol shape."""

    async def store_failed_callback(
        self, shipment_id: str, payload: dict, headers: dict
    ) -> str:
        return "retry-1"

    async def get_due_retries(self, limit: int = 10) -> list[dict]:
        return []

    async def mark_succeeded(self, retry_id: str) -> None:
        pass

    async def mark_failed(self, retry_id: str, error: str) -> None:
        pass

    async def mark_exhausted(self, retry_id: str) -> None:
        pass


class _IncompleteRetryStore:
    """Missing methods — should NOT satisfy protocol."""

    async def store_failed_callback(
        self, shipment_id: str, payload: dict, headers: dict
    ) -> str:
        return "retry-1"


def test_full_store_satisfies_protocol() -> None:
    assert isinstance(_FullRetryStore(), CallbackRetryStore)


def test_incomplete_store_does_not_satisfy_protocol() -> None:
    assert not isinstance(_IncompleteRetryStore(), CallbackRetryStore)


def test_protocol_has_five_methods() -> None:
    expected_methods = {
        "store_failed_callback",
        "get_due_retries",
        "mark_succeeded",
        "mark_failed",
        "mark_exhausted",
    }
    for method_name in expected_methods:
        assert hasattr(CallbackRetryStore, method_name), (
            f"CallbackRetryStore missing method {method_name}"
        )
