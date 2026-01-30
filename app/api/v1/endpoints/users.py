
from sqlalchemy.exc import NoResultFound
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from typing import List, Optional

from app.db import get_db
from app.models.models import User

router = APIRouter(prefix="/users", tags=["users"])

@router.get("", response_model=List[User])
@router.get("/", response_model=List[User])
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    users = result.scalars().all()
    return users

# DELETE /users/{user_id}
@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()
    return None

# PUT /users/{user_id}
from fastapi import Body
from sqlmodel import SQLModel

class UserUpdate(SQLModel):
    email: Optional[str] = None
    role: Optional[str] = None
    # Add other updatable fields as needed

@router.put("/{user_id}", response_model=User)
async def update_user(user_id: int, user_update: UserUpdate = Body(...), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    update_data = user_update.dict(exclude_unset=True)
    if "role" in update_data and update_data["role"] is not None:
        update_data["role"] = update_data["role"].lower()
    for key, value in update_data.items():
        setattr(user, key, value)
    await db.commit()
    await db.refresh(user)
    return user