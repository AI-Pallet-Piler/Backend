import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.db import get_db
from app.models.models import User
from app.core.security import hash_password

async def add_initial_users():
    async for db in get_db():
        from datetime import datetime
        now = datetime.utcnow()
        users = [
            User(
                user_id=1,
                email="admin@example.com",
                hashed_password=hash_password("admin123"),
                role="admin",
                created_at=now,
                updated_at=now,
                last_login=None
            ),
            User(
                user_id=2,
                email="manager@example.com",
                hashed_password=hash_password("manager123"),
                role="manager",
                created_at=now,
                updated_at=now,
                last_login=None
            ),
            User(
                user_id=3,
                email="picker@example.com",
                hashed_password=hash_password("picker123"),
                role="picker",
                created_at=now,
                updated_at=now,
                last_login=None
            ),
        ]
        for user in users:
            result = await db.execute(select(User).where(User.email == user.email))
            if not result.scalar_one_or_none():
                db.add(user)
        await db.commit()
        print("Initial users added.")
        break

if __name__ == "__main__":
    asyncio.run(add_initial_users())
