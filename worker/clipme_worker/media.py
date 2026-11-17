"""ffmpeg / ffprobe helpers. All subprocess calls use argument lists (no shell=True)
so paths and values are never interpreted by a shell."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass


class MediaError(RuntimeError):
    pass


@dataclass
class ProbeResult:
    duration_seconds: float
    width: int | None
    height: int | None
    has_audio: bool
    has_video: bool
    format_name: str


def run_ffprobe(path: str) -> ProbeResult:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError as exc:
        raise MediaError("ffprobe is not installed or not on PATH") from exc
    if proc.returncode != 0:
        raise MediaError(f"ffprobe failed for {path}: {proc.stderr.strip()}")

    data = json.loads(proc.stdout)
    fmt = data.get("format", {})
    streams = data.get("streams", [])

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration = fmt.get("duration")
    if duration is None and video_stream is not None:
        duration = video_stream.get("duration")
    if duration is None:
        raise MediaError(f"Could not determine duration for {path}")

    return ProbeResult(
        duration_seconds=float(duration),
        width=int(video_stream["width"]) if video_stream and video_stream.get("width") else None,
        height=int(video_stream["height"]) if video_stream and video_stream.get("height") else None,
        has_audio=audio_stream is not None,
        has_video=video_stream is not None,
        format_name=fmt.get("format_name", ""),
    )


def validate_source_video(path: str, max_duration_seconds: float) -> ProbeResult:
    probe = run_ffprobe(path)
    if not probe.has_video:
        raise MediaError("File has no video stream")
    if not probe.has_audio:
        raise MediaError("File has no audio stream; transcription requires audio")
    if probe.duration_seconds > max_duration_seconds:
        raise MediaError(
            f"Video is {probe.duration_seconds:.0f}s, which exceeds the "
            f"{max_duration_seconds:.0f}s limit"
        )
    return probe


def extract_audio_wav(input_path: str, output_wav_path: str, sample_rate: int = 16000) -> None:
    """Extract mono 16kHz PCM WAV audio, the format faster-whisper expects."""
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vn",
        "-ac", "1",
        "-ar", str(sample_rate),
        "-f", "wav",
        output_wav_path,
    ]
    _run_ffmpeg(cmd)


def render_vertical_clip(
    input_path: str,
    output_path: str,
    start_seconds: float,
    end_seconds: float,
    subtitles_ass_path: str | None,
    output_width: int,
    output_height: int,
) -> None:
    """Cut [start, end] from input_path, center-crop to output_width x output_height,
    and (optionally) burn in subtitles from an ASS file. Re-encodes for frame-accurate cuts."""
    duration = max(0.1, end_seconds - start_seconds)

    # Center-crop to the target aspect ratio: scale so the shorter dimension covers the
    # target, then crop the overflow symmetrically from the center.
    vf_parts = [
        f"scale=w={output_width}:h={output_height}:force_original_aspect_ratio=increase",
        f"crop={output_width}:{output_height}",
    ]

    # The ffmpeg filtergraph parser's escaping rules for '\' and ':' in the ass/subtitles
    # filter are notoriously unreliable with Windows drive-letter paths (e.g. "E:\...").
    # Sidestepping the problem entirely: run ffmpeg with its cwd set to the subtitle
    # file's directory and reference it by bare filename, so the filter string never
    # contains a drive letter or a backslash.
    cwd = None
    if subtitles_ass_path:
        abs_ass_path = os.path.abspath(subtitles_ass_path)
        cwd = os.path.dirname(abs_ass_path)
        vf_parts.append(f"ass={_escape_ffmpeg_filter_path(os.path.basename(abs_ass_path))}")

    vf = ",".join(vf_parts)

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start_seconds:.3f}",
        "-i", os.path.abspath(input_path),
        "-t", f"{duration:.3f}",
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        os.path.abspath(output_path),
    ]
    _run_ffmpeg(cmd, cwd=cwd)


def _escape_ffmpeg_filter_path(path: str) -> str:
    # The ffmpeg filtergraph parser treats '\', ':' and ',' specially; this is only
    # applied to the bare filename (see render_vertical_clip), so in practice there's
    # nothing left to escape, but kept for correctness/clarity.
    posix_path = path.replace("\\", "/")
    return posix_path.replace(":", "\\:")


def _run_ffmpeg(cmd: list[str], cwd: str | None = None) -> None:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=cwd)
    except FileNotFoundError as exc:
        raise MediaError("ffmpeg is not installed or not on PATH") from exc
    if proc.returncode != 0:
        raise MediaError(f"ffmpeg command failed: {' '.join(cmd)}\n{proc.stderr[-4000:]}")
