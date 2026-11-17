"""Database queries used by the API. All project-scoped queries filter by user_id,
since the API connects with the service role and must enforce ownership itself
(RLS is not in effect for this connection)."""
from __future__ import annotations

import json

import psycopg


def create_project(conn: psycopg.Connection, user_id: str, title: str, filename: str, storage_path: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into public.projects (user_id, title, source_filename, source_storage_path, status)
            values (%s, %s, %s, %s, 'uploaded')
            returning *
            """,
            (user_id, title, filename, storage_path),
        )
        row = cur.fetchone()
    conn.commit()
    return row


def get_project_for_user(conn: psycopg.Connection, project_id: str, user_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "select * from public.projects where id = %s and user_id = %s", (project_id, user_id)
        )
        return cur.fetchone()


def list_projects_for_user(conn: psycopg.Connection, user_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "select * from public.projects where user_id = %s order by created_at desc", (user_id,)
        )
        return cur.fetchall()


def list_clips_for_project(conn: psycopg.Connection, project_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "select * from public.clips where project_id = %s order by clip_index asc", (project_id,)
        )
        return cur.fetchall()


def get_clip_for_user(conn: psycopg.Connection, clip_id: str, user_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            select c.* from public.clips c
            join public.projects p on p.id = c.project_id
            where c.id = %s and p.user_id = %s
            """,
            (clip_id, user_id),
        )
        return cur.fetchone()


def has_transcript(conn: psycopg.Connection, project_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("select 1 from public.transcripts where project_id = %s", (project_id,))
        return cur.fetchone() is not None


def has_active_job(conn: psycopg.Connection, project_id: str, job_type: str, clip_id: str | None = None) -> bool:
    with conn.cursor() as cur:
        if clip_id:
            cur.execute(
                """
                select 1 from public.jobs
                where project_id = %s and job_type = %s and clip_id = %s
                  and status in ('queued', 'processing')
                """,
                (project_id, job_type, clip_id),
            )
        else:
            cur.execute(
                """
                select 1 from public.jobs
                where project_id = %s and job_type = %s and status in ('queued', 'processing')
                """,
                (project_id, job_type),
            )
        return cur.fetchone() is not None


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


def set_project_status(conn: psycopg.Connection, project_id: str, status: str, error_message: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "update public.projects set status = %s, error_message = %s where id = %s",
            (status, error_message, project_id),
        )
    conn.commit()


def update_clip_trim(conn: psycopg.Connection, clip_id: str, start_seconds: float, end_seconds: float) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            update public.clips
            set start_seconds = %s, end_seconds = %s, status = 'pending', selection_mode = 'manual'
            where id = %s
            returning *
            """,
            (start_seconds, end_seconds, clip_id),
        )
        row = cur.fetchone()
    conn.commit()
    return row


def delete_project(conn: psycopg.Connection, project_id: str, user_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "delete from public.projects where id = %s and user_id = %s", (project_id, user_id)
        )
        deleted = cur.rowcount > 0
    conn.commit()
    return deleted
