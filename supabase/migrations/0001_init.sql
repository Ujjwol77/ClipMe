-- ClipMe initial schema
-- Projects: one per uploaded source video and its processing run.
create table if not exists public.projects (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null default 'Untitled project',
  source_storage_path text,
  source_filename text,
  source_duration_seconds numeric,
  source_width int,
  source_height int,
  status text not null default 'uploaded'
    check (status in ('uploaded', 'queued', 'transcribing', 'selecting_clips', 'rendering', 'ready', 'failed')),
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists projects_user_id_idx on public.projects(user_id);

-- Transcripts: one per project, stores stable-ID segments produced by faster-whisper.
create table if not exists public.transcripts (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null unique references public.projects(id) on delete cascade,
  language text,
  segments jsonb not null default '[]'::jsonb, -- [{id, start, end, text}]
  created_at timestamptz not null default now()
);

-- Clips: candidate / rendered short clips belonging to a project.
create table if not exists public.clips (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  clip_index int not null, -- stable position (0-based) within the project, used for idempotent upserts
  title text not null default 'Clip',
  reason text,
  start_seconds numeric not null,
  end_seconds numeric not null,
  source_segment_start_id int,
  source_segment_end_id int,
  selection_mode text not null default 'ai' check (selection_mode in ('ai', 'manual')),
  status text not null default 'pending'
    check (status in ('pending', 'rendering', 'ready', 'failed')),
  storage_path text,
  duration_seconds numeric,
  render_version int not null default 1,
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (project_id, clip_index)
);

create index if not exists clips_project_id_idx on public.clips(project_id);

-- Jobs: work queue processed by the Python worker. Uses SELECT ... FOR UPDATE SKIP LOCKED.
create table if not exists public.jobs (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  clip_id uuid references public.clips(id) on delete cascade,
  job_type text not null check (job_type in ('process_video', 'render_clip')),
  status text not null default 'queued' check (status in ('queued', 'processing', 'done', 'failed')),
  payload jsonb not null default '{}'::jsonb,
  attempts int not null default 0,
  error_message text,
  locked_at timestamptz,
  locked_by text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists jobs_status_idx on public.jobs(status, created_at);
create index if not exists jobs_project_id_idx on public.jobs(project_id);

-- updated_at triggers
create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists projects_set_updated_at on public.projects;
create trigger projects_set_updated_at before update on public.projects
  for each row execute function public.set_updated_at();

drop trigger if exists clips_set_updated_at on public.clips;
create trigger clips_set_updated_at before update on public.clips
  for each row execute function public.set_updated_at();

drop trigger if exists jobs_set_updated_at on public.jobs;
create trigger jobs_set_updated_at before update on public.jobs
  for each row execute function public.set_updated_at();

-- Row Level Security: users can only see/manage their own projects and derived rows.
alter table public.projects enable row level security;
alter table public.transcripts enable row level security;
alter table public.clips enable row level security;
alter table public.jobs enable row level security;

create policy "projects_select_own" on public.projects
  for select using (auth.uid() = user_id);
create policy "projects_insert_own" on public.projects
  for insert with check (auth.uid() = user_id);
create policy "projects_update_own" on public.projects
  for update using (auth.uid() = user_id);
create policy "projects_delete_own" on public.projects
  for delete using (auth.uid() = user_id);

create policy "transcripts_select_own" on public.transcripts
  for select using (exists (
    select 1 from public.projects p where p.id = transcripts.project_id and p.user_id = auth.uid()
  ));

create policy "clips_select_own" on public.clips
  for select using (exists (
    select 1 from public.projects p where p.id = clips.project_id and p.user_id = auth.uid()
  ));

create policy "jobs_select_own" on public.jobs
  for select using (exists (
    select 1 from public.projects p where p.id = jobs.project_id and p.user_id = auth.uid()
  ));

-- Note: inserts/updates to transcripts, clips and jobs are performed by the API/worker
-- using the Supabase service role key, which bypasses RLS. The FastAPI layer enforces
-- that a user can only trigger actions on projects they own.

-- Storage bucket for private video uploads and rendered clips.
insert into storage.buckets (id, name, public)
values ('clipme-media', 'clipme-media', false)
on conflict (id) do nothing;

-- Storage objects are laid out as {user_id}/{project_id}/source.mp4 and
-- {user_id}/{project_id}/clips/{clip_id}.mp4 so a simple foldername(name) check
-- restricts each user to their own prefix.
create policy "clipme_media_select_own"
  on storage.objects for select
  using (bucket_id = 'clipme-media' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "clipme_media_insert_own"
  on storage.objects for insert
  with check (bucket_id = 'clipme-media' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "clipme_media_delete_own"
  on storage.objects for delete
  using (bucket_id = 'clipme-media' and (storage.foldername(name))[1] = auth.uid()::text);
