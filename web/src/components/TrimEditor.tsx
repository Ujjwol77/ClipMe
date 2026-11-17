"use client";

import { useRef, useState } from "react";

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(1);
  return `${m}:${s.padStart(4, "0")}`;
}

export function TrimEditor({
  sourceUrl,
  sourceDuration,
  initialStart,
  initialEnd,
  minClipSeconds,
  maxClipSeconds,
  busy,
  onSave,
}: {
  sourceUrl: string;
  sourceDuration: number;
  initialStart: number;
  initialEnd: number;
  minClipSeconds: number;
  maxClipSeconds: number;
  busy: boolean;
  onSave: (start: number, end: number) => void;
}) {
  const [start, setStart] = useState(initialStart);
  const [end, setEnd] = useState(initialEnd);
  const videoRef = useRef<HTMLVideoElement>(null);

  const duration = end - start;
  const durationValid = duration >= minClipSeconds && duration <= maxClipSeconds && start < end;
  const changed = start !== initialStart || end !== initialEnd;

  function clamp(value: number) {
    return Math.max(0, Math.min(sourceDuration, value));
  }

  function setStartFromCurrentTime() {
    if (videoRef.current) setStart(clamp(videoRef.current.currentTime));
  }
  function setEndFromCurrentTime() {
    if (videoRef.current) setEnd(clamp(videoRef.current.currentTime));
  }
  function previewClip() {
    if (videoRef.current) {
      videoRef.current.currentTime = start;
      videoRef.current.play();
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-md border border-neutral-800 p-3">
      <video ref={videoRef} src={sourceUrl} controls className="w-full rounded-md bg-black" />

      <div className="relative h-6">
        <div className="absolute inset-y-2 left-0 right-0 rounded-full bg-neutral-800" />
        <div
          className="absolute inset-y-2 rounded-full bg-white/70"
          style={{
            left: `${(start / sourceDuration) * 100}%`,
            right: `${100 - (end / sourceDuration) * 100}%`,
          }}
        />
        <input
          type="range"
          min={0}
          max={sourceDuration}
          step={0.1}
          value={start}
          onChange={(e) => setStart(Math.min(Number(e.target.value), end - 0.1))}
          className="pointer-events-none absolute inset-0 h-6 w-full appearance-none bg-transparent [&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:w-2 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-sm [&::-webkit-slider-thumb]:bg-white"
        />
        <input
          type="range"
          min={0}
          max={sourceDuration}
          step={0.1}
          value={end}
          onChange={(e) => setEnd(Math.max(Number(e.target.value), start + 0.1))}
          className="pointer-events-none absolute inset-0 h-6 w-full appearance-none bg-transparent [&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:w-2 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-sm [&::-webkit-slider-thumb]:bg-white"
        />
      </div>

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-1 text-neutral-400">
          Start
          <input
            type="number"
            step={0.1}
            value={start.toFixed(1)}
            onChange={(e) => setStart(clamp(Number(e.target.value)))}
            className="w-20 rounded border border-neutral-700 bg-neutral-900 px-1.5 py-0.5"
          />
          <button onClick={setStartFromCurrentTime} className="text-xs underline underline-offset-2">
            use current
          </button>
        </label>
        <label className="flex items-center gap-1 text-neutral-400">
          End
          <input
            type="number"
            step={0.1}
            value={end.toFixed(1)}
            onChange={(e) => setEnd(clamp(Number(e.target.value)))}
            className="w-20 rounded border border-neutral-700 bg-neutral-900 px-1.5 py-0.5"
          />
          <button onClick={setEndFromCurrentTime} className="text-xs underline underline-offset-2">
            use current
          </button>
        </label>
        <span className="text-neutral-500">
          {formatTime(start)} - {formatTime(end)} ({duration.toFixed(1)}s)
        </span>
      </div>

      {!durationValid && (
        <p className="text-xs text-amber-400">
          Clip length must be between {minClipSeconds}s and {maxClipSeconds}s.
        </p>
      )}

      <div className="flex gap-2">
        <button
          onClick={previewClip}
          className="rounded-md border border-neutral-700 px-3 py-1.5 text-sm hover:border-neutral-500"
        >
          Preview from start
        </button>
        <button
          disabled={!durationValid || !changed || busy}
          onClick={() => onSave(start, end)}
          className="rounded-md bg-white px-3 py-1.5 text-sm font-medium text-black disabled:opacity-40"
        >
          {busy ? "Regenerating..." : "Save & regenerate"}
        </button>
      </div>
    </div>
  );
}
