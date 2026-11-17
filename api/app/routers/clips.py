from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import repo, storage
from ..auth import CurrentUser, get_current_user
from ..config import settings
from ..db import get_conn
from ..schemas import UpdateClipTrimRequest

router = APIRouter(prefix="/api/clips", tags=["clips"])


@router.patch("/{clip_id}")
def update_clip_trim(clip_id: str, body: UpdateClipTrimRequest, user: CurrentUser = Depends(get_current_user)):
    """Adjusts a clip's start/end against the source video and queues a re-render.
    Idempotent: if a render job for this clip is already queued/processing, we don't
    queue a second one."""
    with get_conn() as conn:
        clip = repo.get_clip_for_user(conn, clip_id, user.id)
        if clip is None:
            raise HTTPException(404, "Clip not found")

        project = repo.get_project_for_user(conn, str(clip["project_id"]), user.id)
        if project is None:
            raise HTTPException(404, "Project not found")

        duration = body.end_seconds - body.start_seconds
        if duration < settings.min_clip_seconds or duration > settings.max_clip_seconds:
            raise HTTPException(
                400,
                f"Clip duration must be between {settings.min_clip_seconds:.0f}s and "
                f"{settings.max_clip_seconds:.0f}s (got {duration:.1f}s)",
            )
        source_duration = project.get("source_duration_seconds")
        if source_duration is not None and body.end_seconds > float(source_duration):
            raise HTTPException(400, "End time is past the end of the source video")
        if body.start_seconds >= body.end_seconds:
            raise HTTPException(400, "start_seconds must be before end_seconds")

        updated = repo.update_clip_trim(conn, clip_id, body.start_seconds, body.end_seconds)

        if not repo.has_active_job(conn, str(clip["project_id"]), "render_clip", clip_id=clip_id):
            repo.enqueue_job(conn, str(clip["project_id"]), "render_clip", {}, clip_id=clip_id)

    return {
        "id": str(updated["id"]),
        "start_seconds": float(updated["start_seconds"]),
        "end_seconds": float(updated["end_seconds"]),
        "status": updated["status"],
    }


@router.post("/{clip_id}/regenerate")
def regenerate_clip(clip_id: str, user: CurrentUser = Depends(get_current_user)):
    with get_conn() as conn:
        clip = repo.get_clip_for_user(conn, clip_id, user.id)
        if clip is None:
            raise HTTPException(404, "Clip not found")
        if not repo.has_active_job(conn, str(clip["project_id"]), "render_clip", clip_id=clip_id):
            repo.enqueue_job(conn, str(clip["project_id"]), "render_clip", {}, clip_id=clip_id)
    return {"queued": True}


@router.get("/{clip_id}/download")
def download_clip(clip_id: str, user: CurrentUser = Depends(get_current_user)):
    with get_conn() as conn:
        clip = repo.get_clip_for_user(conn, clip_id, user.id)
        if clip is None:
            raise HTTPException(404, "Clip not found")
        if clip["status"] != "ready" or not clip.get("storage_path"):
            raise HTTPException(409, "Clip is not ready yet")

    url = storage.create_signed_download_url(clip["storage_path"])
    return {"url": url}
