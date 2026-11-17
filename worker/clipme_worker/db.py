"""Direct Postgres access for the worker (connects straight to the Supabase project's
Postgres instance using the service role's connection string, bypassing RLS -
authorization is enforced by the API layer, not here)."""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator, Optional

import psycopg
from psycopg.rows import dict_row

from .config import settings


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(settings.database_url, row_factory=dict_row, autocommit=False)
    try:
        yield conn
    finally:
        conn.close()


def claim_next_job(conn: psycopg.Connection, worker_id: str) -> Optional[dict]:
    """Atomically claim the oldest queued job using SELECT ... FOR UPDATE SKIP LOCKED,
    so multiple worker processes never process the same job twice."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select * from public.jobs
            where status = 'queued'
            order by created_at asc
            for update skip locked
            limit 1
            """
        )
        job = cur.fetchone()
        if job is None:
            conn.rollback()
            return None

        cur.execute(
            """
            update public.jobs
            set status = 'processing', attempts = attempts + 1,
                locked_at = now(), locked_by = %s
            where id = %s
            """,
            (worker_id, job["id"]),
        )
        conn.commit()
        job["status"] = "processing"
        return job


def mark_job_done(conn: psycopg.Connection, job_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute("update public.jobs set status = 'done' where id = %s", (job_id,))
    conn.commit()


def mark_job_failed(conn: psycopg.Connection, job_id: str, error_message: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "update public.jobs set status = 'failed', error_message = %s where id = %s",
            (error_message[:4000], job_id),
        )
    conn.commit()


def update_project_status(
    conn: psycopg.Connection, project_id: str, status: str, error_message: str | None = None
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "update public.projects set status = %s, error_message = %s where id = %s",
            (status, error_message, project_id),
        )
    conn.commit()


def set_project_probe_info(
    conn: psycopg.Connection, project_id: str, duration: float, width: int | None, height: int | None
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            update public.projects
            set source_duration_seconds = %s, source_width = %s, source_height = %s
            where id = %s
            """,
            (duration, width, height, project_id),
        )
    conn.commit()


def get_project(conn: psycopg.Connection, project_id: str) -> dict:
    with conn.cursor() as cur:
        cur.execute("select * from public.projects where id = %s", (project_id,))
        row = cur.fetchone()
    if row is None:
        raise LookupError(f"project {project_id} not found")
    return row


def upsert_transcript(conn: psycopg.Connection, project_id: str, language: str, segments: list[dict]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into public.transcripts (project_id, language, segments)
            values (%s, %s, %s)
            on conflict (project_id) do update
              set language = excluded.language, segments = excluded.segments
            """,
            (project_id, language, json.dumps(segments)),
        )
    conn.commit()


def get_transcript_segments(conn: psycopg.Connection, project_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("select segments from public.transcripts where project_id = %s", (project_id,))
        row = cur.fetchone()
    if row is None:
        return []
    return row["segments"]


def replace_clips(conn: psycopg.Connection, project_id: str, clips: list[dict]) -> list[dict]:
    """Idempotent on retry: deletes any existing candidate rows for this project
    before inserting the freshly-selected set, inside one transaction."""
    with conn.cursor() as cur:
        cur.execute("delete from public.clips where project_id = %s", (project_id,))
        inserted = []
        for idx, clip in enumerate(clips):
            cur.execute(
                """
                insert into public.clips
                  (project_id, clip_index, title, reason, start_seconds, end_seconds,
                   source_segment_start_id, source_segment_end_id, selection_mode, status)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                returning *
                """,
                (
                    project_id, idx, clip["title"], clip.get("reason", ""),
                    clip["start_seconds"], clip["end_seconds"],
                    clip.get("source_segment_start_id"), clip.get("source_segment_end_id"),
                    clip["selection_mode"],
                ),
            )
            inserted.append(cur.fetchone())
    conn.commit()
    return inserted


def list_clips(conn: psycopg.Connection, project_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "select * from public.clips where project_id = %s order by clip_index asc", (project_id,)
        )
        return cur.fetchall()


def get_clip(conn: psycopg.Connection, clip_id: str) -> dict:
    with conn.cursor() as cur:
        cur.execute("select * from public.clips where id = %s", (clip_id,))
        row = cur.fetchone()
    if row is None:
        raise LookupError(f"clip {clip_id} not found")
    return row


def update_clip_status(
    conn: psycopg.Connection,
    clip_id: str,
    status: str,
    storage_path: str | None = None,
    duration_seconds: float | None = None,
    error_message: str | None = None,
    bump_render_version: bool = False,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            update public.clips
            set status = %s,
                storage_path = coalesce(%s, storage_path),
                duration_seconds = coalesce(%s, duration_seconds),
                error_message = %s,
                render_version = render_version + (case when %s then 1 else 0 end)
            where id = %s
            """,
            (status, storage_path, duration_seconds, error_message, bump_render_version, clip_id),
        )
    conn.commit()


def update_clip_trim(conn: psycopg.Connection, clip_id: str, start_seconds: float, end_seconds: float) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            update public.clips
            set start_seconds = %s, end_seconds = %s, status = 'pending', selection_mode = 'manual'
            where id = %s
            """,
            (start_seconds, end_seconds, clip_id),
        )
    conn.commit()


def enqueue_job(conn: psycopg.Connection, project_id: str, job_type: str, payload: dict, clip_id: str | None = None) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into public.jobs (project_id, clip_id, job_type, payload)
            values (%s, %s, %s, %s)
            returning id
            """,
            (project_id, clip_id, job_type, json.dumps(payload)),
        )
        job_id = cur.fetchone()["id"]
    conn.commit()
    return str(job_id)
