"""Timestamped transcription using faster-whisper, run on CPU."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from faster_whisper import WhisperModel

from .config import settings


@dataclass
class Segment:
    id: int
    start: float
    end: float
    text: str

    def to_dict(self) -> dict:
        return {"id": self.id, "start": self.start, "end": self.end, "text": self.text}


@dataclass
class TranscriptResult:
    language: str
    segments: list[Segment]


@lru_cache(maxsize=1)
def _get_model() -> WhisperModel:
    return WhisperModel(
        settings.whisper_model_size,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )


def transcribe_audio(wav_path: str) -> TranscriptResult:
    model = _get_model()
    segments_iter, info = model.transcribe(
        wav_path,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )

    segments: list[Segment] = []
    for idx, seg in enumerate(segments_iter):
        text = seg.text.strip()
        if not text:
            continue
        segments.append(Segment(id=idx, start=float(seg.start), end=float(seg.end), text=text))

    # Re-number ids contiguously after dropping empty segments, so "stable IDs" given
    # to the LLM always line up with what we stored.
    for new_id, seg in enumerate(segments):
        seg.id = new_id

    return TranscriptResult(language=info.language or "en", segments=segments)
