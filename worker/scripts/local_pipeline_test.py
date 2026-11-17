"""Local, DB-free smoke test for the core pipeline: given an input video and an
optional start/end, transcribe it, pick (or use given) a clip range, burn captions,
and export a vertical MP4 - then verify the output with ffprobe.

Usage:
    python scripts/local_pipeline_test.py <input.mp4> [--start 0] [--end 30] [--out out.mp4]

If --start/--end are omitted, the manual clip-selection fallback is used to pick a
default range (same code path the worker uses when no LLM_API_KEY is configured).
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clipme_worker.captions import build_cues_for_clip, write_ass_file  # noqa: E402
from clipme_worker.clip_selection import select_clips_manual  # noqa: E402
from clipme_worker.config import settings  # noqa: E402
from clipme_worker.media import extract_audio_wav, render_vertical_clip, run_ffprobe, validate_source_video  # noqa: E402
from clipme_worker.transcribe import transcribe_audio  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Path to source MP4")
    parser.add_argument("--start", type=float, default=None)
    parser.add_argument("--end", type=float, default=None)
    parser.add_argument("--out", default="clip_out.mp4")
    parser.add_argument("--work-dir", default="tmp_local_test")
    args = parser.parse_args()

    os.makedirs(args.work_dir, exist_ok=True)
    wav_path = os.path.join(args.work_dir, "audio.wav")
    ass_path = os.path.join(args.work_dir, "captions.ass")

    print(f"[1/5] Validating source video: {args.input}")
    probe = validate_source_video(args.input, settings.max_source_duration_seconds)
    print(f"      duration={probe.duration_seconds:.2f}s size={probe.width}x{probe.height}")

    print("[2/5] Extracting audio...")
    extract_audio_wav(args.input, wav_path)

    print(f"[3/5] Transcribing with faster-whisper ({settings.whisper_model_size}, {settings.whisper_device})...")
    transcript = transcribe_audio(wav_path)
    segments = [s.to_dict() for s in transcript.segments]
    print(f"      language={transcript.language} segments={len(segments)}")
    for seg in segments[:5]:
        print(f"      SEG_{seg['id']:04d} [{seg['start']:.2f}-{seg['end']:.2f}]: {seg['text']}")

    if args.start is not None and args.end is not None:
        start, end = args.start, args.end
        print(f"[4/5] Using explicit clip range: {start:.2f}s - {end:.2f}s")
    else:
        candidates = select_clips_manual(segments, probe.duration_seconds)
        start, end = candidates[0].start_seconds, candidates[0].end_seconds
        print(f"[4/5] Manual-mode fallback picked: {start:.2f}s - {end:.2f}s ({candidates[0].title})")

    cues = build_cues_for_clip(segments, start, end)
    write_ass_file(cues, ass_path, settings.output_width, settings.output_height)
    print(f"      wrote {len(cues)} caption cues to {ass_path}")

    print(f"[5/5] Rendering vertical clip to {args.out}...")
    render_vertical_clip(
        input_path=args.input,
        output_path=args.out,
        start_seconds=start,
        end_seconds=end,
        subtitles_ass_path=ass_path,
        output_width=settings.output_width,
        output_height=settings.output_height,
    )

    out_probe = run_ffprobe(args.out)
    print("\n=== ffprobe verification ===")
    print(f"duration: {out_probe.duration_seconds:.2f}s (expected ~{end - start:.2f}s)")
    print(f"resolution: {out_probe.width}x{out_probe.height} (expected {settings.output_width}x{settings.output_height})")
    print(f"has_video: {out_probe.has_video}  has_audio: {out_probe.has_audio}")

    assert out_probe.has_video and out_probe.has_audio, "Output is missing a stream"
    assert out_probe.width == settings.output_width and out_probe.height == settings.output_height, "Wrong resolution"
    print("\nOK - output looks correct.")


if __name__ == "__main__":
    main()
