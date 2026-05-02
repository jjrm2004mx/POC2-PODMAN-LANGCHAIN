import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

_user = os.getenv("POSTGRES_USER", "admin")
_password = os.getenv("POSTGRES_PASSWORD", "admin")
_host = os.getenv("POSTGRES_HOST", "postgres")
_port = os.getenv("POSTGRES_PORT", "5432")
_db = os.getenv("POSTGRES_DB", "classifier_db")

DATABASE_URL = f"postgresql+asyncpg://{_user}:{_password}@{_host}:{_port}/{_db}"

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
