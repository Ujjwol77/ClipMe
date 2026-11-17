from __future__ import annotations

import os
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException

from .. import repo, storage
from ..auth import CurrentUser, get_current_user
from ..config import settings
from ..db import get_conn
from ..schemas import ClipOut, CreateProjectRequest, CreateProjectResponse, ProjectDetailOut, ProjectOut

router = APIRouter(prefix="/api/projects", tags=["projects"])

_ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v"}


def _safe_extension(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    ext = re.sub(r"[^a-z0-9.]", "", ext)
    return ext if ext in _ALLOWED_EXTENSIONS else ".mp4"


def _serialize_project(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "status": row["status"],
        "error_message": row.get("error_message"),
        "source_filename": row.get("source_filename"),
        "source_duration_seconds": row.get("source_duration_seconds"),
        "source_width": row.get("source_width"),
        "source_height": row.get("source_height"),
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


def _serialize_clip(row: dict) -> dict:
    download_url = None
    if row["status"] == "ready" and row.get("storage_path"):
        try:
            download_url = storage.create_signed_download_url(row["storage_path"])
        except Exception:
            download_url = None
    return {
        "id": str(row["id"]),
        "clip_index": row["clip_index"],
        "title": row["title"],
        "reason": row.get("reason"),
        "start_seconds": float(row["start_seconds"]),
        "end_seconds": float(row["end_seconds"]),
        "status": row["status"],
        "selection_mode": row["selection_mode"],
        "duration_seconds": float(row["duration_seconds"]) if row.get("duration_seconds") is not None else None,
        "error_message": row.get("error_message"),
        "render_version": row["render_version"],
        "download_url": download_url,
    }


@router.post("", response_model=CreateProjectResponse)
def create_project(body: CreateProjectRequest, user: CurrentUser = Depends(get_current_user)):
    ext = _safe_extension(body.filename)
    project_id = str(uuid.uuid4())
    storage_path = f"{user.id}/{project_id}/source{ext}"

    with get_conn() as conn:
        row = repo.create_project(
            conn, user.id, body.title or body.filename, body.filename, storage_path
        )

    try:
        upload = storage.create_signed_upload_url(storage_path)
    except Exception as exc:
        raise HTTPException(500, f"Failed to create upload URL: {exc}") from exc

    return {"project_id": str(row["id"]), "upload": upload}


@router.get("", response_model=list[ProjectOut])
def list_projects(user: CurrentUser = Depends(get_current_user)):
    with get_conn() as conn:
        rows = repo.list_projects_for_user(conn, user.id)
    return [_serialize_project(r) for r in rows]


@router.get("/{project_id}", response_model=ProjectDetailOut)
def get_project(project_id: str, user: CurrentUser = Depends(get_current_user)):
    with get_conn() as conn:
        row = repo.get_project_for_user(conn, project_id, user.id)
        if row is None:
            raise HTTPException(404, "Project not found")
        clips = repo.list_clips_for_project(conn, project_id)
        transcript_available = repo.has_transcript(conn, project_id)

    out = _serialize_project(row)
    out["clips"] = [_serialize_clip(c) for c in clips]
    out["has_transcript"] = transcript_available
    return out


@router.post("/{project_id}/process")
def process_project(project_id: str, user: CurrentUser = Depends(get_current_user)):
    """Enqueues the process_video job (transcribe -> select clips -> render).
    Safe to call again after a failure: skipped if a job is already in flight,
    which keeps retries from creating duplicate clip/job rows."""
    with get_conn() as conn:
        row = repo.get_project_for_user(conn, project_id, user.id)
        if row is None:
            raise HTTPException(404, "Project not found")
        if row["status"] in ("queued", "transcribing", "selecting_clips", "rendering"):
            return {"status": row["status"], "already_processing": True}
        if repo.has_active_job(conn, project_id, "process_video"):
            return {"status": row["status"], "already_processing": True}

        repo.set_project_status(conn, project_id, "queued")
        repo.enqueue_job(conn, project_id, "process_video", {})
    return {"status": "queued", "already_processing": False}


@router.get("/{project_id}/source-url")
def get_source_url(project_id: str, user: CurrentUser = Depends(get_current_user)):
    with get_conn() as conn:
        row = repo.get_project_for_user(conn, project_id, user.id)
        if row is None:
            raise HTTPException(404, "Project not found")
        if not row.get("source_storage_path"):
            raise HTTPException(409, "Source video not uploaded yet")
    url = storage.create_signed_download_url(row["source_storage_path"])
    return {"url": url}


@router.post("/{project_id}/retry")
def retry_project(project_id: str, user: CurrentUser = Depends(get_current_user)):
    return process_project(project_id, user)


@router.delete("/{project_id}")
def delete_project(project_id: str, user: CurrentUser = Depends(get_current_user)):
    with get_conn() as conn:
        deleted = repo.delete_project(conn, project_id, user.id)
    if not deleted:
        raise HTTPException(404, "Project not found")
    return {"deleted": True}
