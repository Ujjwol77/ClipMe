"""Generate a burned-in ASS subtitle track for a single rendered clip.

Takes the full-video transcript segments, keeps only the slice that overlaps the
clip's [start, end) window, shifts timestamps to be clip-relative, and splits each
segment into short multi-word lines (approximating word-level captions without
needing word-level timestamps from Whisper) so captions stay readable on a
vertical 1080x1920 frame.
"""
from __future__ import annotations

from dataclasses import dataclass

_MAX_WORDS_PER_LINE = 4
_MAX_CHARS_PER_LINE = 36


@dataclass
class CaptionCue:
    start: float  # seconds, relative to clip start
    end: float
    text: str


def _split_segment_into_cues(start: float, end: float, text: str) -> list[CaptionCue]:
    words = text.split()
    if not words:
        return []

    lines: list[list[str]] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join(current + [word])
        if current and (len(current) >= _MAX_WORDS_PER_LINE or len(candidate) > _MAX_CHARS_PER_LINE):
            lines.append(current)
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(current)

    total_words = sum(len(line) for line in lines)
    duration = max(0.01, end - start)
    cues: list[CaptionCue] = []
    t = start
    for line in lines:
        share = len(line) / total_words
        line_duration = duration * share
        cues.append(CaptionCue(start=t, end=t + line_duration, text=" ".join(line)))
        t += line_duration
    return cues


def _format_ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    centis = int(round((secs - int(secs)) * 100))
    if centis == 100:
        centis = 0
        secs += 1
    return f"{hours:d}:{minutes:02d}:{int(secs):02d}.{centis:02d}"


def _escape_ass_text(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").replace("\n", " ")


def build_cues_for_clip(segments: list[dict], clip_start: float, clip_end: float) -> list[CaptionCue]:
    cues: list[CaptionCue] = []
    for seg in segments:
        seg_start, seg_end = float(seg["start"]), float(seg["end"])
        if seg_end <= clip_start or seg_start >= clip_end:
            continue
        overlap_start = max(seg_start, clip_start)
        overlap_end = min(seg_end, clip_end)
        rel_start = overlap_start - clip_start
        rel_end = overlap_end - clip_start
        cues.extend(_split_segment_into_cues(rel_start, rel_end, seg["text"]))
    return cues


def write_ass_file(
    cues: list[CaptionCue],
    output_path: str,
    video_width: int,
    video_height: int,
) -> None:
    font_size = max(28, video_width // 18)
    margin_v = video_height // 6

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,4,1,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for cue in cues:
        if cue.end <= cue.start:
            continue
        text = _escape_ass_text(cue.text.upper())
        lines.append(
            f"Dialogue: 0,{_format_ass_time(cue.start)},{_format_ass_time(cue.end)},Default,,0,0,0,,{text}\n"
        )

    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
