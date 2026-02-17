"""SQLAlchemy repository integration tests with real aiosqlite DB."""

import pytest
from sendparcel.exceptions import ShipmentNotFoundError


class TestSQLAlchemyShipmentRepository:
    async def test_create(self, sqlalchemy_repository) -> None:
        shipment = await sqlalchemy_repository.create(
            id="s-1",
            provider="dummy",
            status="new",
        )
        assert shipment.id == "s-1"
        assert shipment.provider == "dummy"
        assert shipment.status == "new"

    async def test_get_by_id(self, sqlalchemy_repository) -> None:
        created = await sqlalchemy_repository.create(
            id="s-2",
            provider="dummy",
            status="new",
        )
        fetched = await sqlalchemy_repository.get_by_id("s-2")
        assert fetched.id == created.id
        assert fetched.provider == "dummy"

    async def test_get_by_id_not_found(self, sqlalchemy_repository) -> None:
        with pytest.raises(ShipmentNotFoundError):
            await sqlalchemy_repository.get_by_id("nonexistent")

    async def test_save(self, sqlalchemy_repository) -> None:
        shipment = await sqlalchemy_repository.create(
            id="s-3",
            provider="dummy",
            status="new",
        )
        shipment.external_id = "ext-updated"
        saved = await sqlalchemy_repository.save(shipment)
        assert saved.external_id == "ext-updated"
        fetched = await sqlalchemy_repository.get_by_id("s-3")
        assert fetched.external_id == "ext-updated"

    async def test_update_status(self, sqlalchemy_repository) -> None:
        await sqlalchemy_repository.create(
            id="s-4",
            provider="dummy",
            status="new",
        )
        updated = await sqlalchemy_repository.update_status(
            "s-4",
            "created",
            external_id="ext-4",
        )
        assert updated.status == "created"
        assert updated.external_id == "ext-4"

    async def test_list_by_reference(self, sqlalchemy_repository) -> None:
        await sqlalchemy_repository.create(
            id="s-5",
            provider="dummy",
            status="new",
            reference_id="ref-A",
        )
        await sqlalchemy_repository.create(
            id="s-6",
            provider="dummy",
            status="new",
            reference_id="ref-A",
        )
        await sqlalchemy_repository.create(
            id="s-7",
            provider="dummy",
            status="new",
            reference_id="ref-B",
        )
        results = await sqlalchemy_repository.list_by_reference("ref-A")
        assert len(results) == 2
        ids = {s.id for s in results}
        assert ids == {"s-5", "s-6"}

    async def test_list_by_reference_empty(self, sqlalchemy_repository) -> None:
        results = await sqlalchemy_repository.list_by_reference("nonexistent")
        assert results == []
