from fastapi import FastAPI, Depends
from app.db import get_db, create_tables
from sqlalchemy.ext.asyncio.session import AsyncSession
from contextlib import asynccontextmanager
from sqlalchemy import text

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    await create_tables()
    print("Database tables created successfully!")

    yield  # Application runs while inside this block

    print("Application is shutting down...")

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"message": "hello world"}

# Simple db connection test endpoint
@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "connected"}