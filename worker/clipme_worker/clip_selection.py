"""Turn a full transcript into 3-5 candidate short-form clips.

Two modes:
- AI mode (default when LLM_API_KEY is set): sends the transcript, with stable
  per-segment IDs, to a configurable OpenAI-compatible chat completions endpoint
  and asks for candidate clips referencing those IDs.
- Manual mode (LLM_API_KEY unset): skips the LLM entirely and returns a single
  clearly-labelled clip spanning a sane default window, so the rendering
  pipeline (crop + captions + export) can be exercised locally without any
  external API key. Intended for local development/testing only.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import httpx

from .config import settings

logger = logging.getLogger(__name__)


@dataclass
class ClipCandidate:
    title: str
    reason: str
    start_segment_id: int
    end_segment_id: int
    start_seconds: float
    end_seconds: float
    selection_mode: str  # "ai" | "manual"


_SYSTEM_PROMPT = """You are a short-form video editor. You will be given a timestamped \
transcript of a single-speaker talking-head video, as numbered segments like \
"SEG_0003 [12.34-15.67]: some text". Your job is to pick the 3 to 5 best \
self-contained moments to turn into standalone vertical short clips (30-60 seconds \
each, never under 20s or over 90s).

For each candidate clip, choose a start and end SEGMENT ID (inclusive) from the \
transcript provided - do not invent IDs. Prioritize:
1. A strong, attention-grabbing opening line for the clip.
2. Enough surrounding context that someone who never saw the full video can follow it.
3. A complete thought - the clip should not cut off mid-sentence or mid-idea at the end.
Avoid overlapping or near-duplicate clips. If the transcript has fewer than 3 strong \
standalone moments, return fewer clips rather than padding with weak ones.

Respond with ONLY a JSON array (no prose, no markdown fences), where each item is:
{"title": "short catchy title", "start_segment_id": <int>, "end_segment_id": <int>, \
"reason": "one sentence on why this moment works"}
"""


def _format_transcript_prompt(segments: list[dict]) -> str:
    lines = [
        f"SEG_{seg['id']:04d} [{seg['start']:.2f}-{seg['end']:.2f}]: {seg['text']}"
        for seg in segments
    ]
    return "\n".join(lines)


def _call_llm(segments: list[dict]) -> list[dict]:
    transcript_text = _format_transcript_prompt(segments)
    url = f"{settings.llm_api_base.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    body = {
        "model": settings.llm_model,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": transcript_text},
        ],
    }

    with httpx.Client(timeout=120) as client:
        resp = client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

    content = data["choices"][0]["message"]["content"].strip()
    content = _strip_code_fences(content)
    parsed = json.loads(content)
    if not isinstance(parsed, list):
        raise ValueError("LLM response was not a JSON array")
    return parsed


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def _resolve_and_validate(
    raw_candidates: list[dict],
    segments_by_id: dict[int, dict],
    total_duration: float,
) -> list[ClipCandidate]:
    candidates: list[ClipCandidate] = []
    for item in raw_candidates:
        try:
            start_id = int(item["start_segment_id"])
            end_id = int(item["end_segment_id"])
            title = str(item.get("title") or "Untitled clip").strip()
            reason = str(item.get("reason") or "").strip()
        except (KeyError, TypeError, ValueError):
            logger.warning("Skipping malformed clip candidate: %r", item)
            continue

        if start_id not in segments_by_id or end_id not in segments_by_id:
            logger.warning("Skipping candidate with unknown segment id(s): %s-%s", start_id, end_id)
            continue
        if end_id < start_id:
            start_id, end_id = end_id, start_id

        start_seconds = float(segments_by_id[start_id]["start"])
        end_seconds = float(segments_by_id[end_id]["end"])
        duration = end_seconds - start_seconds

        if duration < settings.min_clip_seconds or duration > settings.max_clip_seconds:
            logger.info(
                "Dropping candidate '%s': duration %.1fs outside [%.0f, %.0f]",
                title, duration, settings.min_clip_seconds, settings.max_clip_seconds,
            )
            continue
        if start_seconds < 0 or end_seconds > total_duration:
            logger.warning("Dropping candidate '%s': out of range for source video", title)
            continue

        candidates.append(
            ClipCandidate(
                title=title,
                reason=reason,
                start_segment_id=start_id,
                end_segment_id=end_id,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                selection_mode="ai",
            )
        )
    return candidates


def _overlap_ratio(a: ClipCandidate, b: ClipCandidate) -> float:
    inter_start = max(a.start_seconds, b.start_seconds)
    inter_end = min(a.end_seconds, b.end_seconds)
    inter = max(0.0, inter_end - inter_start)
    shorter = min(a.end_seconds - a.start_seconds, b.end_seconds - b.start_seconds)
    if shorter <= 0:
        return 0.0
    return inter / shorter


def _dedupe_near_duplicates(candidates: list[ClipCandidate], threshold: float = 0.6) -> list[ClipCandidate]:
    kept: list[ClipCandidate] = []
    for cand in candidates:
        if any(_overlap_ratio(cand, k) >= threshold for k in kept):
            continue
        kept.append(cand)
    return kept


def _score_for_target_length(c: ClipCandidate) -> float:
    duration = c.end_seconds - c.start_seconds
    mid_target = (settings.target_min_clip_seconds + settings.target_max_clip_seconds) / 2
    return abs(duration - mid_target)


def select_clips_with_ai(segments: list[dict], total_duration: float) -> list[ClipCandidate]:
    segments_by_id = {seg["id"]: seg for seg in segments}
    raw = _call_llm(segments)
    candidates = _resolve_and_validate(raw, segments_by_id, total_duration)
    candidates = _dedupe_near_duplicates(candidates)
    candidates.sort(key=_score_for_target_length)
    return candidates[: settings.max_clips]


def select_clips_manual(segments: list[dict], total_duration: float) -> list[ClipCandidate]:
    """Local test fallback used when no LLM_API_KEY is configured. Produces a single,
    clearly-labelled clip so the render pipeline can be exercised end-to-end without
    any external API. Intended to be adjusted via the review screen's trim controls."""
    target = min(settings.target_max_clip_seconds, total_duration)
    start = 0.0
    end = min(total_duration, max(settings.target_min_clip_seconds, target))

    start_id = segments[0]["id"] if segments else 0
    end_id = segments[-1]["id"] if segments else 0
    for seg in segments:
        if seg["start"] <= end:
            end_id = seg["id"]

    return [
        ClipCandidate(
            title="Manual mode clip (adjust me)",
            reason=(
                "No LLM_API_KEY configured, so this placeholder clip was generated "
                "with fixed timestamps for local pipeline testing. Set LLM_API_KEY "
                "and reprocess for AI-selected clips, or trim this one manually."
            ),
            start_segment_id=start_id,
            end_segment_id=end_id,
            start_seconds=start,
            end_seconds=end,
            selection_mode="manual",
        )
    ]


def select_clips(segments: list[dict], total_duration: float) -> list[ClipCandidate]:
    if not segments:
        return []
    if settings.llm_enabled:
        try:
            clips = select_clips_with_ai(segments, total_duration)
            if clips:
                return clips
            logger.warning("AI selection returned no valid clips, falling back to manual mode")
        except Exception:
            logger.exception("AI clip selection failed, falling back to manual mode")
    return select_clips_manual(segments, total_duration)
