from fastapi import FastAPI, Depends
from app.db import get_db
from sqlalchemy.ext.asyncio.session import AsyncSession
from sqlalchemy import text

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "hello world"}

# Simple db connection test endpoint
@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "connected"}