from sqlmodel import SQLModel
from sqlalchemy.exc import NoResultFound
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from typing import List, Optional
from pydantic import field_validator

from app.db import get_db
from app.models.models import User, UserRole

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

# --- UPDATED MODEL HERE ---
class UserUpdate(SQLModel):
    name: Optional[str] = None         # Added
    email: Optional[str] = None
    badge_number: Optional[str] = None # Added
    role: Optional[UserRole] = None

    @field_validator("role", mode="before")
    def normalize_role(cls, value):
        if value is None or isinstance(value, UserRole):
            return value
        if isinstance(value, str):
            value = value.strip().lower()
        try:
            return UserRole(value)
        except ValueError as exc:
            raise ValueError("Invalid role. Must be one of: admin, manager, picker.") from exc

@router.put("/{user_id}", response_model=User)
async def update_user(user_id: int, user_update: UserUpdate = Body(...), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    update_data = user_update.model_dump(exclude_unset=True)
    
    for key, value in update_data.items():
        setattr(user, key, value)
        
    await db.commit()
    await db.refresh(user)
    return user

class UserCreate(SQLModel):
    name: str
    email: str
    badge_number: str
    hashed_password: str
    role: UserRole

    @field_validator("role", mode="before")
    def normalize_role(cls, value):
        if isinstance(value, UserRole):
            return value
        if isinstance(value, str):
            value = value.strip().lower()
        try:
            return UserRole(value)
        except ValueError as exc:
            raise ValueError("Invalid role. Must be one of: admin, manager, picker.") from exc

@router.post("/create", response_model=User, status_code=201)
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check for existing email or badge_number
    result = await db.execute(select(User).where((User.email == user.email) | (User.badge_number == user.badge_number)))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="User with this email or badge number already exists")
    new_user = User(
        name=user.name,
        email=user.email,
        badge_number=user.badge_number,
        hashed_password=user.hashed_password,
        role=user.role
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user