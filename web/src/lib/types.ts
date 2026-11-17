export type ProjectStatus =
  | "uploaded"
  | "queued"
  | "transcribing"
  | "selecting_clips"
  | "rendering"
  | "ready"
  | "failed";

export type ClipStatus = "pending" | "rendering" | "ready" | "failed";

export interface Clip {
  id: string;
  clip_index: number;
  title: string;
  reason: string | null;
  start_seconds: number;
  end_seconds: number;
  status: ClipStatus;
  selection_mode: "ai" | "manual";
  duration_seconds: number | null;
  error_message: string | null;
  render_version: number;
  download_url: string | null;
}

export interface Project {
  id: string;
  title: string;
  status: ProjectStatus;
  error_message: string | null;
  source_filename: string | null;
  source_duration_seconds: number | null;
  source_width: number | null;
  source_height: number | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectDetail extends Project {
  clips: Clip[];
  has_transcript: boolean;
}

export const PROCESSING_STAGES: ProjectStatus[] = [
  "uploaded",
  "queued",
  "transcribing",
  "selecting_clips",
  "rendering",
  "ready",
];

export const STAGE_LABELS: Record<ProjectStatus, string> = {
  uploaded: "Uploaded",
  queued: "Queued",
  transcribing: "Transcribing audio",
  selecting_clips: "Selecting clips",
  rendering: "Rendering clips",
  ready: "Ready",
  failed: "Failed",
};
