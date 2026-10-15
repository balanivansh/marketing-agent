"""Data schemas and Pydantic models for Marketing OS."""

from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class LLMTaskType(str, Enum):
    """Task category for dynamic LLM routing."""

    TRIAGE_SCORING = "TRIAGE_SCORING"
    IDEATION = "IDEATION"
    DRAFTING = "DRAFTING"
    CRITIC = "CRITIC"
    OBSERVATION = "OBSERVATION"


class LLMEngine(str, Enum):
    """Execution engine for LLM inference."""

    LOCAL = "LOCAL"
    CLOUD = "CLOUD"


class LLMResponse(BaseModel):
    """Standardized output response from LLM inference."""

    content: str
    engine: LLMEngine
    model_name: str
    latency_ms: float
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    raw_json: Optional[dict] = None



class BrandConfig(BaseModel):
    """Pydantic model representing tenant brand configuration."""

    tenant_id: str
    brand_name: str
    pillars: List[str] = Field(default_factory=list)
    tone: List[str] = Field(default_factory=list)
    banned_words: List[str] = Field(default_factory=list)
    reel_default_mode: str = "faceless"
    custom_rules: List[str] = Field(default_factory=list)
    sources: List[Any] = Field(default_factory=list)


class ResearchItem(BaseModel):
    """Model for a research source item."""

    id: Optional[int] = None
    source_type: str
    title: str
    url: str
    raw_text: str
    relevance_score: float = 0.0
    matched_pillar: Optional[str] = None
    one_line_angle: Optional[str] = None
    processed: int = 0
    created_at: Optional[str] = None


class Draft(BaseModel):
    """Model for content draft."""

    id: Optional[int] = None
    format: str
    pillar: str
    target_mode: str
    caption: str
    payload_json: Optional[str] = None
    status: str = "pending_review"
    human_edited: int = 0
    source_url: Optional[str] = None
    created_at: Optional[str] = None


class DraftDiff(BaseModel):
    """Model for human edit tracking / diff."""

    id: Optional[int] = None
    draft_id: int
    original_caption: str
    edited_caption: str
    diff_text: str
    created_at: Optional[str] = None


class StyleObservation(BaseModel):
    """Model for continuous style learning observations."""

    id: Optional[int] = None
    observation: str
    count: int = 1
    status: str = "pending"
    created_at: Optional[str] = None
