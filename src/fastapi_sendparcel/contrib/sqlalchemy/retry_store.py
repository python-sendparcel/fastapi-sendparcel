"""SQLAlchemy callback retry store."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastapi_sendparcel.contrib.sqlalchemy.models import CallbackRetryModel


class SQLAlchemyRetryStore:
    """Persist callback retries in SQLAlchemy table."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self.session_factory = session_factory

    async def enqueue(self, payload: dict) -> None:
        async with self.session_factory() as session:
            session.add(CallbackRetryModel(payload=payload))
            await session.commit()
