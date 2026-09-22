from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from app.core.config import get_settings
from app.core.database import Base, get_session
from app.main import app
from app.models.alert import Alert, ReadingCache
from app.services.openweather_service import reset_circuit_breaker, set_http_client
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool


@pytest.fixture(autouse=True)
def reset_openweather_state() -> Generator[None, None, None]:
    reset_circuit_breaker()
    set_http_client(None)
    yield
    reset_circuit_breaker()
    set_http_client(None)


@pytest_asyncio.fixture
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(
    test_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )

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


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
