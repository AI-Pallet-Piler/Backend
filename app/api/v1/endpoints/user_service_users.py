from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from pydantic import BaseModel, EmailStr

from app.db import get_db
from app.models.models import User


router = APIRouter(prefix="/users", tags=["user-service"])


class UserServiceResponse(BaseModel):
    id: str
    email: str
    role: str
    badge_number: Optional[str] = None
    hashed_password: Optional[str] = None


def _role_value(role: object) -> str:
    return getattr(role, "value", str(role))


@router.get("/{user_id}", response_model=UserServiceResponse)
async def get_user_by_id(
    user_id: int,
    db: AsyncSession = Depends(get_db),
) -> UserServiceResponse:
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserServiceResponse(
        id=str(user.user_id),
        email=user.email,
        role=_role_value(user.role),
        badge_number=user.badge_number,
    )


@router.get("/by-email", response_model=UserServiceResponse)
async def get_user_by_email(
    email: EmailStr = Query(...),
    db: AsyncSession = Depends(get_db),
) -> UserServiceResponse:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserServiceResponse(
        id=str(user.user_id),
        email=user.email,
        role=_role_value(user.role),
        badge_number=user.badge_number,
    )
