"""Request contracts for the two highest-traffic API boundaries.

These schemas sit in front of the existing route logic: they reject wrong
shapes early while leaving the route's detailed business validation and
error messages intact. Unknown keys are ignored so older clients keep
working.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IdeaCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt_title: str = Field(min_length=1, max_length=200)
    raw_content: str = Field(min_length=1)
    parent_id: str | None = None
    child_kind: Literal["enhancement", "bugfix"] | None = None
    structured_content: dict[str, str] | None = None


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action_type: str = Field(min_length=1)
    target_id: str | None = None
    model_override: str | None = None
    provider_override: str | None = None
    build_stage: int = Field(default=1, ge=1, le=3)
    confirm: bool = False
    skills: list[str] = Field(default_factory=list)
    guidelines: list[str] = Field(default_factory=list)
    answers: list[str] = Field(default_factory=list)
