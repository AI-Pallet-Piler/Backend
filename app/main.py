from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio.session import AsyncSession

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.inventory import router as inventory_router
from app.api.v1.endpoints.products import router as products_router
from app.api.v1.endpoints.users import router as users_router
from app.api.v1.endpoints.user_service_users import router as user_service_users_router
from app.db import create_tables, get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    await create_tables()
    print("Database tables created successfully!")

    yield  # Application runs while inside this block

    print("Application is shutting down...")


app = FastAPI(lifespan=lifespan, redirect_slashes=False)

# Register API routers
app.include_router(inventory_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api")
app.include_router(user_service_users_router, prefix="/api")


@app.get("/")
async def root():
    return {"message": "hello world"}

# Simple db connection test endpoint
@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "connected"}