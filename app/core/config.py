from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    database_url: str = Field(alias="DATABASE_URL", default="")
    secret_key: str = Field(alias="SECRET_KEY", default="change-me-in-production")
    algorithm: str = Field(alias="JWT_ALGORITHM", default="HS256")
    access_token_expire_minutes: int = Field(alias="ACCESS_TOKEN_EXPIRE_MINUTES", default=60 * 24 * 7)  # 1 week

    class Config:
        env_file = ".env"
        populate_by_name = True


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
