# ClipMe

Upload a long talking-head video, get 3-5 AI-selected short vertical clips with
burned-in captions, review and re-trim them, and download the result.

## Architecture

- `web/` - Next.js + TypeScript frontend (upload, progress, review, download)
- `api/` - FastAPI backend (auth, project/clip CRUD, job queue, signed storage URLs)
- `worker/` - Python worker: faster-whisper transcription, LLM clip selection,
  ffmpeg rendering (vertical crop + burned-in captions)
- `supabase/migrations/` - Postgres schema, RLS policies, storage bucket/policies

The API and worker both connect directly to the Supabase project's Postgres
database and to Supabase Storage using the **service role key** (server-side
only). The frontend only ever sees the public anon key and short-lived signed
URLs; the API enforces that every project/clip belongs to the authenticated
user (`user_id = auth.uid()`-style checks, done manually in `api/app/repo.py`
since the service-role connection bypasses RLS).

Jobs (`process_video`, `render_clip`) are rows in a Postgres `jobs` table.
The worker polls it with `SELECT ... FOR UPDATE SKIP LOCKED`, so you can run
multiple worker processes safely. Retrying a failed project re-enqueues the
job only if nothing is already queued/processing for it, and `process_video`
deletes-then-reinserts a project's clip rows in one transaction - so retries
never create duplicate clips.

## 1. Create a Supabase project

1. Create a free project at https://supabase.com/dashboard.
2. Project Settings -> API: copy the **Project URL**, **anon public key**,
   **service_role key**, and **JWT Secret**.
3. Project Settings -> Database: copy the **connection string** (URI) - this
   is `DATABASE_URL`.
4. Apply the schema in `supabase/migrations/0001_init.sql`: open the SQL
   Editor in the Supabase dashboard, paste the file's contents, and run it.
   (Equivalently, if you have `psql` installed: `psql "$DATABASE_URL" -f supabase/migrations/0001_init.sql`.)
   This also creates the private `clipme-media` storage bucket and its RLS
   policies.
5. By default new Supabase projects require email confirmation for sign-up.
   For local testing you can disable that under Authentication -> Providers ->
   Email -> "Confirm email", or just confirm the test account's email via the
   link Supabase sends.

## 2. Install FFmpeg

The worker shells out to `ffmpeg`/`ffprobe`. On Windows:

```bash
winget install --id Gyan.FFmpeg -e
```

(macOS: `brew install ffmpeg`. Linux: your package manager.) Make sure a new
terminal has `ffmpeg` and `ffprobe` on `PATH` before running the worker.

## 3. Worker setup

```bash
cd worker
python -m venv .venv
.venv\Scripts\activate          # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
copy .env.example .env          # then fill in DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
python -m clipme_worker.worker_main
```

Leave `LLM_API_KEY` empty in `.env` to use the **manual timestamp mode**: the
worker will create one clearly-labelled placeholder clip per video (instead of
calling an LLM) so you can exercise the whole render pipeline - including
captions and the vertical export - without any external API key. Set
`LLM_API_KEY` (and optionally `LLM_API_BASE`/`LLM_MODEL` for a non-OpenAI,
OpenAI-compatible endpoint) to turn on AI clip selection.

### Local, DB-free smoke test

Before wiring up Supabase at all, you can test transcription + captioning +
vertical rendering directly against a video file on disk:

```bash
cd worker
python scripts/local_pipeline_test.py path\to\video.mp4 --out clip_out.mp4
# or with an explicit range instead of the manual-mode default:
python scripts/local_pipeline_test.py path\to\video.mp4 --start 10 --end 45 --out clip_out.mp4
```

This prints the transcript, the chosen clip range, and verifies the output
with `ffprobe` (duration, 1080x1920 resolution, audio+video streams present).

## 4. API setup

```bash
cd api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # fill in DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWT_SECRET
uvicorn app.main:app --reload --port 8000
```

Check it's up: `curl http://localhost:8000/health` -> `{"status":"ok"}`.

## 5. Frontend setup

```bash
cd web
npm install
copy .env.local.example .env.local   # fill in NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY
npm run dev
```

Open http://localhost:3000, sign up with an email/password, upload an MP4,
and watch it move through queued -> transcribing -> selecting clips ->
rendering -> ready.

## Notes on scope

- English, single-speaker videos up to 30 minutes (`MAX_SOURCE_DURATION_SECONDS`).
- Clips target 30-60s (`TARGET_MIN/MAX_CLIP_SECONDS`), hard bounds 25-75s
  (`MIN/MAX_CLIP_SECONDS`), up to 5 per video (`MAX_CLIPS`). Fewer clips are
  returned when the LLM finds fewer strong moments, or none at all if the
  video has no suitable material (the project is marked `failed` with a
  clear message in that case).
- First version uses a fixed center crop to 9:16, not active-speaker tracking.
- Re-trimming a clip always re-renders captions from the full transcript, so
  captions stay in sync with the new cut.
