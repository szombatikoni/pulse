"""Alkalmazásbeállítások környezeti változókból (és helyben opcionálisan .env fájlból)."""

from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Helyi fejlesztéskor a docker-compose adatbázisára mutat. Szándékosan
    # 127.0.0.1 és nem localhost: a compose csak IPv4-en, a saját gépen teszi
    # elérhetővé a portot, a localhost viszont előbb IPv6-on (::1) próbálkozna,
    # és időtúllépésig várna.
    database_url: str = "postgresql+psycopg://pulse:pulse@127.0.0.1:5432/pulse"

    # A tokenek aláírókulcsa. Az alapérték CSAK helyi fejlesztésre való; a
    # demókörnyezetben a JWT_SECRET_KEY környezeti változóval kell felülírni.
    jwt_secret_key: str = "dev-only-insecure-secret-change-me-0123456789"
    # A bejelentkezés (access token) érvényessége percben.
    access_token_expire_minutes: int = 60

    # Előírás nélkül meddig számít frissnek a beteg legutóbbi adata (napban);
    # utána a státusz Adathiány (07_mukodesi_szabalyok.md, 1. rész).
    # Rendszerszintű beállítás, nem betegenkénti érték.
    data_freshness_days: int = 7

    # A rendszer időzónája (a hallgató döntése, 2026-10-12): minden beteg helyi
    # ideje ebből számítódik — a mérés helyi napja (M3: alkalmak) és a FHIR-export
    # időeltolása. Az adatbázis az időpontokat időzónával (UTC-ben) tárolja.
    timezone: str = "Europe/Budapest"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


settings = Settings()
