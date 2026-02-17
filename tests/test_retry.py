"""Retry mechanism tests."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sendparcel.providers.dummy import DummyProvider
from sendparcel.registry import registry

from conftest import DemoShipment
from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.retry import compute_next_retry_at, process_due_retries


class TestComputeNextRetryAt:
    def test_attempt_1_gives_base_delay(self) -> None:
        before = datetime.now(tz=UTC)
        result = compute_next_retry_at(attempt=1, backoff_seconds=60)
        after = datetime.now(tz=UTC)

        assert (
            before + timedelta(seconds=60)
            <= result
            <= after + timedelta(seconds=60)
        )

    def test_attempt_2_gives_double_delay(self) -> None:
        before = datetime.now(tz=UTC)
        result = compute_next_retry_at(attempt=2, backoff_seconds=60)
        after = datetime.now(tz=UTC)

        assert (
            before + timedelta(seconds=120)
            <= result
            <= after + timedelta(seconds=120)
        )

    def test_attempt_3_gives_quadruple_delay(self) -> None:
        before = datetime.now(tz=UTC)
        result = compute_next_retry_at(attempt=3, backoff_seconds=60)
        after = datetime.now(tz=UTC)

        assert (
            before + timedelta(seconds=240)
            <= result
            <= after + timedelta(seconds=240)
        )

    def test_custom_backoff_seconds(self) -> None:
        before = datetime.now(tz=UTC)
        result = compute_next_retry_at(attempt=1, backoff_seconds=30)
        after = datetime.now(tz=UTC)

        assert (
            before + timedelta(seconds=30)
            <= result
            <= after + timedelta(seconds=30)
        )


class TestProcessDueRetries:
    @pytest.fixture()
    def config(self) -> SendparcelConfig:
        return SendparcelConfig(
            default_provider="dummy",
            retry_max_attempts=5,
            retry_backoff_seconds=60,
        )

    @pytest.fixture()
    def mock_retry_store(self) -> AsyncMock:
        store = AsyncMock()
        store.get_due_retries = AsyncMock(return_value=[])
        store.mark_succeeded = AsyncMock()
        store.mark_failed = AsyncMock()
        store.mark_exhausted = AsyncMock()
        return store

    @pytest.fixture()
    def mock_repository(self) -> AsyncMock:
        repo = AsyncMock()
        return repo

    async def test_no_due_retries_returns_zero(
        self, mock_retry_store, mock_repository, config
    ) -> None:
        result = await process_due_retries(
            retry_store=mock_retry_store,
            repository=mock_repository,
            config=config,
        )
        assert result == 0
        mock_retry_store.get_due_retries.assert_awaited_once_with(limit=10)

    async def test_successful_retry_marks_succeeded(
        self, mock_retry_store, mock_repository, config
    ) -> None:
        registry.register(DummyProvider)

        mock_retry_store.get_due_retries.return_value = [
            {
                "id": "retry-1",
                "shipment_id": "ship-1",
                "payload": {"event": "picked_up"},
                "headers": {"x-dummy-token": "dummy-token"},
                "attempts": 1,
            },
        ]

        shipment = DemoShipment(
            id="ship-1",
            reference_id="ref-1",
            status="label_ready",
            provider="dummy",
        )
        mock_repository.get_by_id.return_value = shipment

        result = await process_due_retries(
            retry_store=mock_retry_store,
            repository=mock_repository,
            config=config,
        )
        assert result == 1
        mock_retry_store.mark_succeeded.assert_awaited_once_with("retry-1")

    async def test_shipment_not_found_marks_exhausted(
        self, mock_retry_store, mock_repository, config
    ) -> None:
        mock_retry_store.get_due_retries.return_value = [
            {
                "id": "retry-1",
                "shipment_id": "missing-ship",
                "payload": {},
                "headers": {},
                "attempts": 0,
            },
        ]
        mock_repository.get_by_id.side_effect = KeyError("missing-ship")

        result = await process_due_retries(
            retry_store=mock_retry_store,
            repository=mock_repository,
            config=config,
        )
        assert result == 1
        mock_retry_store.mark_exhausted.assert_awaited_once_with("retry-1")

    async def test_max_attempts_exceeded_marks_exhausted(
        self, mock_retry_store, mock_repository, config
    ) -> None:
        registry.register(DummyProvider)

        mock_retry_store.get_due_retries.return_value = [
            {
                "id": "retry-1",
                "shipment_id": "ship-1",
                "payload": {"event": "x"},
                "headers": {},
                "attempts": 5,  # equals max_attempts
            },
        ]

        shipment = DemoShipment(
            id="ship-1",
            reference_id="ref-1",
            status="label_ready",
            provider="dummy",
        )
        mock_repository.get_by_id.return_value = shipment

        result = await process_due_retries(
            retry_store=mock_retry_store,
            repository=mock_repository,
            config=config,
        )
        assert result == 1
        mock_retry_store.mark_exhausted.assert_awaited_once_with("retry-1")

    async def test_failed_retry_under_limit_marks_failed(
        self, mock_retry_store, mock_repository, config
    ) -> None:
        registry.register(DummyProvider)

        mock_retry_store.get_due_retries.return_value = [
            {
                "id": "retry-1",
                "shipment_id": "ship-1",
                "payload": {"event": "x"},
                "headers": {},
                "attempts": 2,  # under max_attempts (5)
            },
        ]

        shipment = DemoShipment(
            id="ship-1",
            reference_id="ref-1",
            status="label_ready",
            provider="dummy",
        )
        mock_repository.get_by_id.return_value = shipment

        result = await process_due_retries(
            retry_store=mock_retry_store,
            repository=mock_repository,
            config=config,
        )
        assert result == 1
        mock_retry_store.mark_failed.assert_awaited_once()
        call_args = mock_retry_store.mark_failed.call_args
        assert call_args[0][0] == "retry-1"  # retry_id
        assert isinstance(call_args[1]["error"], str)  # error message
