"""Supabase Storage access for the worker, using the service role key (server-side only)."""
from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from .config import settings


@lru_cache(maxsize=1)
def get_client() -> Client:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not configured")
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def download_to_file(storage_path: str, local_path: str) -> None:
    client = get_client()
    data = client.storage.from_(settings.storage_bucket).download(storage_path)
    with open(local_path, "wb") as f:
        f.write(data)


def upload_file(storage_path: str, local_path: str, content_type: str = "video/mp4") -> None:
    client = get_client()
    with open(local_path, "rb") as f:
        client.storage.from_(settings.storage_bucket).upload(
            storage_path,
            f,
            file_options={"content-type": content_type, "upsert": "true"},
        )


def create_signed_url(storage_path: str, expires_in_seconds: int = 3600) -> str:
    client = get_client()
    res = client.storage.from_(settings.storage_bucket).create_signed_url(storage_path, expires_in_seconds)
    return res["signedURL"] if "signedURL" in res else res["signed_url"]
