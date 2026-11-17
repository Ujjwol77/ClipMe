"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/apiClient";
import { STORAGE_BUCKET, supabase } from "@/lib/supabaseClient";

const ALLOWED_TYPES = ["video/mp4", "video/quicktime", "video/x-m4v"];
const MAX_UPLOAD_SIZE_BYTES = Number(
  process.env.NEXT_PUBLIC_MAX_UPLOAD_SIZE_BYTES ?? 2 * 1024 * 1024 * 1024
);

export function UploadForm() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [progressLabel, setProgressLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File | null) {
    if (!file) return;
    setError(null);

    if (!ALLOWED_TYPES.includes(file.type) && !/\.(mp4|mov|m4v)$/i.test(file.name)) {
      setError("Please choose an MP4 or MOV video file.");
      return;
    }
    if (file.size > MAX_UPLOAD_SIZE_BYTES) {
      const limitGb = (MAX_UPLOAD_SIZE_BYTES / (1024 * 1024 * 1024)).toFixed(1);
      setError(`File is too large. The limit is ${limitGb} GB.`);
      return;
    }

    setBusy(true);
    try {
      setProgressLabel("Preparing upload...");
      const { project_id, upload } = await api.createProject(file.name, file.type || "video/mp4");

      setProgressLabel("Uploading video...");
      const { error: uploadError } = await supabase.storage
        .from(STORAGE_BUCKET)
        .uploadToSignedUrl(upload.path, upload.token, file, {
          contentType: file.type || "video/mp4",
        });
      if (uploadError) throw uploadError;

      setProgressLabel("Queuing processing...");
      await api.processProject(project_id);

      router.push(`/projects/${project_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setBusy(false);
      setProgressLabel(null);
    }
  }

  return (
    <div className="rounded-lg border border-dashed border-neutral-700 p-8 text-center">
      <label className="cursor-pointer">
        <input
          type="file"
          accept="video/mp4,video/quicktime,.mp4,.mov,.m4v"
          className="hidden"
          disabled={busy}
          onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
        />
        <span className="rounded-md bg-white px-4 py-2 text-sm font-medium text-black">
          {busy ? progressLabel ?? "Working..." : "Choose a video to upload"}
        </span>
      </label>
      <p className="mt-3 text-xs text-neutral-500">
        MP4 or MOV, single speaker, up to 30 minutes.
      </p>
      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
    </div>
  );
}
