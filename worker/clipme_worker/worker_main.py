"""Entry point: `python -m clipme_worker.worker_main`. Polls the jobs table and
processes one job at a time per worker process (run multiple processes to scale out;
SELECT ... FOR UPDATE SKIP LOCKED in db.claim_next_job keeps them from colliding)."""
from __future__ import annotations

import logging
import time

from . import db
from .config import settings
from .pipeline import handle_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("clipme_worker")


def run_forever() -> None:
    logger.info("ClipMe worker starting as %s (poll every %.1fs)", settings.worker_id, settings.poll_interval_seconds)
    while True:
        processed = run_once()
        if not processed:
            time.sleep(settings.poll_interval_seconds)


def run_once() -> bool:
    with db.connect() as conn:
        job = db.claim_next_job(conn, settings.worker_id)
        if job is None:
            return False

        logger.info("Processing job %s (%s) for project %s", job["id"], job["job_type"], job["project_id"])
        try:
            handle_job(conn, job)
            db.mark_job_done(conn, str(job["id"]))
            logger.info("Job %s done", job["id"])
        except Exception as exc:  # noqa: BLE001
            logger.exception("Job %s failed", job["id"])
            db.mark_job_failed(conn, str(job["id"]), str(exc))
        return True


if __name__ == "__main__":
    run_forever()
