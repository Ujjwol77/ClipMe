from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from .config import settings


@lru_cache(maxsize=1)
def get_client() -> Client:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not configured")
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def create_signed_upload_url(storage_path: str) -> dict:
    """Returns {signed_url, token, path} for the client to PUT its file directly to
    Supabase Storage, without the frontend ever seeing the service role key."""
    client = get_client()
    bucket = client.storage.from_(settings.storage_bucket)
    res = bucket.create_signed_upload_url(storage_path)
    return {
        "signed_url": res.get("signed_url") or res.get("signedURL") or res.get("url"),
        "token": res.get("token"),
        "path": storage_path,
    }


def create_signed_download_url(storage_path: str, expires_in_seconds: int = 3600) -> str:
    client = get_client()
    res = client.storage.from_(settings.storage_bucket).create_signed_url(storage_path, expires_in_seconds)
    return res.get("signedURL") or res.get("signed_url") or res.get("signedUrl")
