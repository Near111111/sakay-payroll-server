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
    # Full connection string, e.g.:
    # postgresql://postgres:Sakay-Ph123@<host>:<port>/<db>
    DATABASE_URL: str

    # ── MinIO (Railway) ───────────────────────────────────────
    # Internal endpoint used by your server to talk to MinIO
    # e.g. http://bucket.railway.internal:9000
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    # Public-facing base URL for generating presigned URLs
    # e.g. https://bucket-production-1bff.up.railway.app
    MINIO_PUBLIC_URL: str

    # ── SMS OTP ───────────────────────────────────────────────
    TXTBOX_API_KEY: str
    TXTBOX_SENDER: str


settings = Settings()