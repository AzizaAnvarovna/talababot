from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str
    user_hash_salt: str
    bot_api_token: str
    admin_password: str

    database_url: str = "sqlite:///./talababot.db"
    cookie_secure: bool = False
    test_mode: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
