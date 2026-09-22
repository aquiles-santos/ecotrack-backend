from collections.abc import AsyncGenerator

import pytest
from app.core.config import get_settings
from app.core.database import Base, get_session
from app.main import app
from app.models.alert import Alert, ReadingCache
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    settings = get_settings()
    test_engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
    )

    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    connection = await test_engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_session] = override_get_session

    await session.execute(delete(ReadingCache))
    await session.execute(delete(Alert))
    await session.flush()

    try:
        yield session
    finally:
        app.dependency_overrides.clear()
        await session.close()
        await transaction.rollback()
        await connection.close()
        await test_engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
