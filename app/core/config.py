# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding='utf-8',
        extra='ignore'
    )

    # ── JWT / Auth ────────────────────────────────────────────
    SECRET_KEY: str
    REFRESH_SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── PostgreSQL (Railway) ──────────────────────────────────
    DATABASE_URL: str

    # ── Railway Object Storage ────────────────────────────────
    # Copy all five from the Railway dashboard → bucket → Credentials tab
    RAILWAY_BUCKET_NAME: str
    RAILWAY_ACCESS_KEY_ID: str
    RAILWAY_SECRET_ACCESS_KEY: str
    RAILWAY_REGION: str
    RAILWAY_ENDPOINT_URL: str

    # ── Presigned URL expiry overrides (optional) ─────────────
    # Change these in .env without touching code.
    # SENSITIVE floor is enforced at 3600 s minimum in storage_client.py.
    STANDARD_URL_EXPIRE_SECONDS: int = 86_400   # 24 h
    SENSITIVE_URL_EXPIRE_SECONDS: int = 3_600   # 1 h

    # ── SMS OTP ───────────────────────────────────────────────
    TXTBOX_API_KEY: str
    TXTBOX_SENDER: str


settings = Settings()