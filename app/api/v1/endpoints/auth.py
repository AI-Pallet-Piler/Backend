from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from pydantic import BaseModel, EmailStr

from app.core.security import verify_password
from app.db import get_db
from app.models import User


router = APIRouter(prefix="/auth", tags=["auth"])


class ValidateRequest(BaseModel):
    email: EmailStr
    password: str


class UserServiceResponse(BaseModel):
    id: str
    email: str
    role: str
    hashed_password: Optional[str] = None


def _role_value(role: object) -> str:
    return getattr(role, "value", str(role))


@router.post("/validate", response_model=UserServiceResponse)
async def validate_credentials(
    body: ValidateRequest,
    db: AsyncSession = Depends(get_db),
) -> UserServiceResponse:
    stmt = select(User).where(User.email == body.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return UserServiceResponse(
        id=str(user.user_id),
        email=user.email,
        role=_role_value(user.role),
        hashed_password=user.hashed_password,
    )
