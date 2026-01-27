from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.ext.asyncio.session import AsyncSession 
from sqlalchemy.orm import declarative_base
from sqlmodel import SQLModel
import os
from dotenv import load_dotenv

# Import all models to register them with SQLModel.metadata
from app.models import (
    Product,
    Location,
    Inventory,
    Order,
    OrderLine,
    Pallet,
    PalletLayer,
    PalletItem,
    StackingRule,
    PickTask,
)

load_dotenv()

# Database URL from environment variable
DATABASE_URL = os.getenv("DATABASE_URL")

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # Set to False in production
    future=True
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Base class for models (keeping for compatibility if needed)
Base = declarative_base()

# Dependency to get database session
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Function to create all tables
async def create_tables():
    """Create all database tables from SQLModel models."""
    async with engine.begin() as conn:
        # Run the sync create_all in the async context
        await conn.run_sync(lambda sync_conn: SQLModel.metadata.create_all(bind=sync_conn))
