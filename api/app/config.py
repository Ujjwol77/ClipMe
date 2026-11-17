from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = ""
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    storage_bucket: str = "clipme-media"

    max_source_duration_seconds: float = 30 * 60
    max_upload_size_bytes: int = 2 * 1024 * 1024 * 1024
    min_clip_seconds: float = 25
    max_clip_seconds: float = 75

    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
