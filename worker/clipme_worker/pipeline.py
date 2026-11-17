"""Job handlers: process_video (transcribe -> select clips -> render all) and
render_clip (re-render a single clip, used for initial renders and regenerate-after-trim)."""
from __future__ import annotations

import logging
import os
import shutil
import tempfile

import psycopg

from . import db, storage
from .captions import build_cues_for_clip, write_ass_file
from .clip_selection import select_clips
from .config import settings
from .media import MediaError, render_vertical_clip, validate_source_video, extract_audio_wav
from .transcribe import transcribe_audio

logger = logging.getLogger(__name__)


def _project_work_dir(project_id: str) -> str:
    path = os.path.join(settings.work_dir, project_id)
    os.makedirs(path, exist_ok=True)
    return path


def _clip_storage_path(user_id: str, project_id: str, clip_id: str, version: int) -> str:
    return f"{user_id}/{project_id}/clips/{clip_id}_v{version}.mp4"


def render_single_clip(
    conn: psycopg.Connection,
    user_id: str,
    project_id: str,
    source_local_path: str,
    clip: dict,
    segments: list[dict],
) -> None:
    clip_id = str(clip["id"])
    work_dir = _project_work_dir(project_id)
    ass_path = os.path.join(work_dir, f"{clip_id}.ass")
    output_path = os.path.join(work_dir, f"{clip_id}_out.mp4")

    db.update_clip_status(conn, clip_id, status="rendering")
    try:
        cues = build_cues_for_clip(segments, float(clip["start_seconds"]), float(clip["end_seconds"]))
        write_ass_file(cues, ass_path, settings.output_width, settings.output_height)

        render_vertical_clip(
            input_path=source_local_path,
            output_path=output_path,
            start_seconds=float(clip["start_seconds"]),
            end_seconds=float(clip["end_seconds"]),
            subtitles_ass_path=ass_path,
            output_width=settings.output_width,
            output_height=settings.output_height,
        )

        next_version = int(clip["render_version"]) + 1 if clip.get("storage_path") else int(clip["render_version"])
        storage_path = _clip_storage_path(user_id, project_id, clip_id, next_version)
        storage.upload_file(storage_path, output_path)

        duration = float(clip["end_seconds"]) - float(clip["start_seconds"])
        db.update_clip_status(
            conn, clip_id, status="ready", storage_path=storage_path,
            duration_seconds=duration, bump_render_version=clip.get("storage_path") is not None,
        )
    except MediaError as exc:
        logger.exception("Render failed for clip %s", clip_id)
        db.update_clip_status(conn, clip_id, status="failed", error_message=str(exc))
    finally:
        for p in (ass_path, output_path):
            if os.path.exists(p):
                os.remove(p)


def process_video_job(conn: psycopg.Connection, job: dict) -> None:
    project_id = str(job["project_id"])
    project = db.get_project(conn, project_id)
    user_id = str(project["user_id"])

    work_dir = _project_work_dir(project_id)
    source_path = os.path.join(work_dir, "source.mp4")
    wav_path = os.path.join(work_dir, "audio.wav")

    try:
        db.update_project_status(conn, project_id, "transcribing")
        storage.download_to_file(project["source_storage_path"], source_path)

        probe = validate_source_video(source_path, settings.max_source_duration_seconds)
        db.set_project_probe_info(conn, project_id, probe.duration_seconds, probe.width, probe.height)

        extract_audio_wav(source_path, wav_path)
        transcript = transcribe_audio(wav_path)
        segments = [s.to_dict() for s in transcript.segments]
        db.upsert_transcript(conn, project_id, transcript.language, segments)

        db.update_project_status(conn, project_id, "selecting_clips")
        candidates = select_clips(segments, probe.duration_seconds)
        if not candidates:
            db.update_project_status(
                conn, project_id, "failed",
                "No suitable clips were found in this video. Try a longer or more "
                "conversational source video.",
            )
            return

        clip_rows = db.replace_clips(
            conn, project_id,
            [
                {
                    "title": c.title,
                    "reason": c.reason,
                    "start_seconds": c.start_seconds,
                    "end_seconds": c.end_seconds,
                    "source_segment_start_id": c.start_segment_id,
                    "source_segment_end_id": c.end_segment_id,
                    "selection_mode": c.selection_mode,
                }
                for c in candidates
            ],
        )

        db.update_project_status(conn, project_id, "rendering")
        any_ready = False
        for clip_row in clip_rows:
            render_single_clip(conn, user_id, project_id, source_path, clip_row, segments)
            refreshed = db.get_clip(conn, str(clip_row["id"]))
            any_ready = any_ready or refreshed["status"] == "ready"

        if any_ready:
            db.update_project_status(conn, project_id, "ready")
        else:
            db.update_project_status(conn, project_id, "failed", "All clip renders failed.")

    except MediaError as exc:
        logger.exception("process_video failed for project %s", project_id)
        db.update_project_status(conn, project_id, "failed", str(exc))
        raise
    except Exception as exc:  # noqa: BLE001 - surfaced to the user via project.error_message
        logger.exception("process_video failed for project %s", project_id)
        db.update_project_status(conn, project_id, "failed", f"Unexpected error: {exc}")
        raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def render_clip_job(conn: psycopg.Connection, job: dict) -> None:
    project_id = str(job["project_id"])
    clip_id = str(job["clip_id"])
    project = db.get_project(conn, project_id)
    clip = db.get_clip(conn, clip_id)
    segments = db.get_transcript_segments(conn, project_id)

    work_dir = _project_work_dir(project_id)
    source_path = os.path.join(work_dir, "source.mp4")
    try:
        storage.download_to_file(project["source_storage_path"], source_path)
        render_single_clip(conn, str(project["user_id"]), project_id, source_path, clip, segments)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def handle_job(conn: psycopg.Connection, job: dict) -> None:
    if job["job_type"] == "process_video":
        process_video_job(conn, job)
    elif job["job_type"] == "render_clip":
        render_clip_job(conn, job)
    else:
        raise ValueError(f"Unknown job_type: {job['job_type']}")
