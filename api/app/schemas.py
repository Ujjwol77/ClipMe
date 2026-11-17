from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CreateProjectRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = "video/mp4"
    title: Optional[str] = None


class CreateProjectResponse(BaseModel):
    project_id: str
    upload: dict  # {signed_url, token, path}


class ProjectOut(BaseModel):
    id: str
    title: str
    status: str
    error_message: Optional[str] = None
    source_filename: Optional[str] = None
    source_duration_seconds: Optional[float] = None
    source_width: Optional[int] = None
    source_height: Optional[int] = None
    created_at: str
    updated_at: str


class ClipOut(BaseModel):
    id: str
    clip_index: int
    title: str
    reason: Optional[str] = None
    start_seconds: float
    end_seconds: float
    status: str
    selection_mode: str
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    render_version: int
    download_url: Optional[str] = None


class ProjectDetailOut(ProjectOut):
    clips: list[ClipOut] = []
    has_transcript: bool = False


class UpdateClipTrimRequest(BaseModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
