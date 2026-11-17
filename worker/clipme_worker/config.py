"""Environment-driven configuration for the ClipMe worker."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    # Database (direct Postgres connection to the Supabase project)
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))

    # Supabase Storage
    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    supabase_service_role_key: str = field(
        default_factory=lambda: os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    )
    storage_bucket: str = field(default_factory=lambda: os.getenv("STORAGE_BUCKET", "clipme-media"))

    # Transcription
    whisper_model_size: str = field(default_factory=lambda: os.getenv("WHISPER_MODEL_SIZE", "small"))
    whisper_device: str = field(default_factory=lambda: os.getenv("WHISPER_DEVICE", "cpu"))
    whisper_compute_type: str = field(
        default_factory=lambda: os.getenv("WHISPER_COMPUTE_TYPE", "int8")
    )

    # LLM clip selection (OpenAI-compatible chat completions API). Leave LLM_API_KEY
    # unset to fall back to manual timestamp mode.
    llm_api_base: str = field(
        default_factory=lambda: os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
    )
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))

    # Clip constraints
    min_clip_seconds: float = field(default_factory=lambda: float(os.getenv("MIN_CLIP_SECONDS", "25")))
    max_clip_seconds: float = field(default_factory=lambda: float(os.getenv("MAX_CLIP_SECONDS", "75")))
    target_min_clip_seconds: float = field(
        default_factory=lambda: float(os.getenv("TARGET_MIN_CLIP_SECONDS", "30"))
    )
    target_max_clip_seconds: float = field(
        default_factory=lambda: float(os.getenv("TARGET_MAX_CLIP_SECONDS", "60"))
    )
    max_clips: int = field(default_factory=lambda: int(os.getenv("MAX_CLIPS", "5")))

    # Upload / source video limits
    max_source_duration_seconds: float = field(
        default_factory=lambda: float(os.getenv("MAX_SOURCE_DURATION_SECONDS", str(30 * 60)))
    )
    max_upload_size_bytes: int = field(
        default_factory=lambda: int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(2 * 1024 * 1024 * 1024)))
    )

    # Worker loop
    poll_interval_seconds: float = field(default_factory=lambda: float(os.getenv("POLL_INTERVAL_SECONDS", "3")))
    worker_id: str = field(default_factory=lambda: os.getenv("WORKER_ID", f"worker-{os.getpid()}"))
    work_dir: str = field(default_factory=lambda: os.getenv("WORK_DIR", os.path.join(os.getcwd(), "tmp")))

    # Output video
    output_width: int = field(default_factory=lambda: int(os.getenv("OUTPUT_WIDTH", "1080")))
    output_height: int = field(default_factory=lambda: int(os.getenv("OUTPUT_HEIGHT", "1920")))

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key.strip())


settings = Settings()
