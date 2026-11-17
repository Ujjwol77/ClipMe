"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ClipCard } from "@/components/ClipCard";
import { ProjectStatusBadge } from "@/components/ProjectStatusBadge";
import { useAuth } from "@/lib/AuthProvider";
import { api } from "@/lib/apiClient";
import { PROCESSING_STAGES, STAGE_LABELS, type ProjectDetail } from "@/lib/types";

const MIN_CLIP_SECONDS = Number(process.env.NEXT_PUBLIC_MIN_CLIP_SECONDS ?? 25);
const MAX_CLIP_SECONDS = Number(process.env.NEXT_PUBLIC_MAX_CLIP_SECONDS ?? 75);

const ACTIVE_STATUSES = ["uploaded", "queued", "transcribing", "selecting_clips", "rendering"];
const POLL_INTERVAL_MS = 3000;

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [sourceUrl, setSourceUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [trimBusyClipId, setTrimBusyClipId] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [authLoading, user, router]);

  const refresh = useCallback(async () => {
    try {
      const data = await api.getProject(id);
      setProject(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [id]);

  useEffect(() => {
    if (!user) return;
    refresh();
  }, [user, refresh]);

  useEffect(() => {
    if (!project) return;
    const stillActive = ACTIVE_STATUSES.includes(project.status);
    const anyClipPending = project.clips.some((c) => c.status === "pending" || c.status === "rendering");
    if (!stillActive && !anyClipPending) return;

    pollRef.current = setInterval(refresh, POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [project, refresh]);

  useEffect(() => {
    if (!project || project.status !== "ready") return;
    if (sourceUrl) return;
    api
      .getSourceUrl(project.id)
      .then((r) => setSourceUrl(r.url))
      .catch(() => setSourceUrl(null));
  }, [project, sourceUrl]);

  async function handleRetry() {
    setRetrying(true);
    try {
      await api.retryProject(id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRetrying(false);
    }
  }

  async function handleTrimSave(clipId: string, start: number, end: number) {
    setTrimBusyClipId(clipId);
    try {
      await api.updateClipTrim(clipId, start, end);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setTrimBusyClipId(null);
    }
  }

  if (authLoading || !user || !project) {
    return <main className="flex min-h-screen items-center justify-center text-neutral-500">Loading...</main>;
  }

  const stageIndex = PROCESSING_STAGES.indexOf(project.status);

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">{project.title}</h1>
          {project.source_duration_seconds && (
            <p className="text-xs text-neutral-500">
              Source: {Math.round(project.source_duration_seconds)}s
            </p>
          )}
        </div>
        <ProjectStatusBadge status={project.status} />
      </div>

      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

      {project.status !== "ready" && project.status !== "failed" && (
        <div className="mb-8 flex flex-col gap-2">
          {PROCESSING_STAGES.slice(1).map((stage, i) => {
            const stageN = i + 1;
            const state = stageN < stageIndex ? "done" : stageN === stageIndex ? "active" : "pending";
            return (
              <div key={stage} className="flex items-center gap-3 text-sm">
                <span
                  className={`h-2 w-2 rounded-full ${
                    state === "done"
                      ? "bg-emerald-500"
                      : state === "active"
                      ? "animate-pulse bg-amber-400"
                      : "bg-neutral-700"
                  }`}
                />
                <span className={state === "pending" ? "text-neutral-600" : "text-neutral-200"}>
                  {STAGE_LABELS[stage]}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {project.status === "failed" && (
        <div className="mb-8 rounded-md border border-red-900 bg-red-950/40 p-4">
          <p className="text-sm text-red-300">{project.error_message ?? "Processing failed."}</p>
          <button
            onClick={handleRetry}
            disabled={retrying}
            className="mt-3 rounded-md bg-white px-3 py-1.5 text-sm font-medium text-black disabled:opacity-50"
          >
            {retrying ? "Retrying..." : "Retry processing"}
          </button>
        </div>
      )}

      {project.clips.length > 0 && (
        <div className="flex flex-col gap-6">
          {project.clips.map((clip) => (
            <ClipCard
              key={clip.id}
              clip={clip}
              sourceUrl={sourceUrl}
              sourceDuration={project.source_duration_seconds}
              minClipSeconds={MIN_CLIP_SECONDS}
              maxClipSeconds={MAX_CLIP_SECONDS}
              trimBusy={trimBusyClipId === clip.id}
              onTrimSave={handleTrimSave}
            />
          ))}
        </div>
      )}

      {project.status === "ready" && project.clips.length === 0 && (
        <p className="text-sm text-neutral-500">
          No strong clips were found in this video. Try a longer or more conversational source video.
        </p>
      )}
    </main>
  );
}
