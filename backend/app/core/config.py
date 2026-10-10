"""Alkalmazásbeállítások környezeti változókból (és helyben opcionálisan .env fájlból)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Helyi fejlesztéskor a docker-compose adatbázisára mutat (localhost:5432).
    database_url: str = "postgresql+psycopg://pulse:pulse@localhost:5432/pulse"

    # A tokenek aláírókulcsa. Az alapérték CSAK helyi fejlesztésre való; a
    # demókörnyezetben a JWT_SECRET_KEY környezeti változóval kell felülírni.
    jwt_secret_key: str = "dev-only-insecure-secret-change-me-0123456789"
    # A bejelentkezés (access token) érvényessége percben.
    access_token_expire_minutes: int = 60


settings = Settings()
