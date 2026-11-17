"use client";

import { useState } from "react";
import { TrimEditor } from "./TrimEditor";
import type { Clip } from "@/lib/types";

const STATUS_LABEL: Record<Clip["status"], string> = {
  pending: "Queued for render",
  rendering: "Rendering...",
  ready: "Ready",
  failed: "Render failed",
};

export function ClipCard({
  clip,
  sourceUrl,
  sourceDuration,
  minClipSeconds,
  maxClipSeconds,
  onTrimSave,
  trimBusy,
}: {
  clip: Clip;
  sourceUrl: string | null;
  sourceDuration: number | null;
  minClipSeconds: number;
  maxClipSeconds: number;
  onTrimSave: (clipId: string, start: number, end: number) => void;
  trimBusy: boolean;
}) {
  const [editing, setEditing] = useState(false);

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-neutral-800 p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-medium">{clip.title}</h3>
          {clip.reason && <p className="mt-1 text-sm text-neutral-400">{clip.reason}</p>}
          <p className="mt-1 text-xs text-neutral-500">
            {clip.duration_seconds?.toFixed(1) ?? (clip.end_seconds - clip.start_seconds).toFixed(1)}s
            {" - "}
            {clip.selection_mode === "manual" ? "manual timestamps" : "AI selected"}
          </p>
        </div>
        <span className="shrink-0 text-xs text-neutral-500">{STATUS_LABEL[clip.status]}</span>
      </div>

      {clip.status === "ready" && clip.download_url && (
        <video src={clip.download_url} controls className="mx-auto max-h-96 rounded-md bg-black" />
      )}

      {clip.status === "failed" && clip.error_message && (
        <p className="text-sm text-red-400">{clip.error_message}</p>
      )}

      <div className="flex gap-2">
        {clip.status === "ready" && clip.download_url && (
          <a
            href={clip.download_url}
            download
            className="rounded-md bg-white px-3 py-1.5 text-sm font-medium text-black"
          >
            Download
          </a>
        )}
        <button
          onClick={() => setEditing((v) => !v)}
          className="rounded-md border border-neutral-700 px-3 py-1.5 text-sm hover:border-neutral-500"
        >
          {editing ? "Close trim editor" : "Adjust trim"}
        </button>
      </div>

      {editing && sourceUrl && sourceDuration && (
        <TrimEditor
          sourceUrl={sourceUrl}
          sourceDuration={sourceDuration}
          initialStart={clip.start_seconds}
          initialEnd={clip.end_seconds}
          minClipSeconds={minClipSeconds}
          maxClipSeconds={maxClipSeconds}
          busy={trimBusy}
          onSave={(start, end) => onTrimSave(clip.id, start, end)}
        />
      )}
    </div>
  );
}
