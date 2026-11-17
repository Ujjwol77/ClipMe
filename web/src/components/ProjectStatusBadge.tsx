import { STAGE_LABELS, type ProjectStatus } from "@/lib/types";

const COLORS: Record<ProjectStatus, string> = {
  uploaded: "bg-neutral-700 text-neutral-200",
  queued: "bg-neutral-700 text-neutral-200",
  transcribing: "bg-amber-900 text-amber-200",
  selecting_clips: "bg-amber-900 text-amber-200",
  rendering: "bg-amber-900 text-amber-200",
  ready: "bg-emerald-900 text-emerald-200",
  failed: "bg-red-900 text-red-200",
};

export function ProjectStatusBadge({ status }: { status: ProjectStatus }) {
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${COLORS[status]}`}>
      {STAGE_LABELS[status]}
    </span>
  );
}
