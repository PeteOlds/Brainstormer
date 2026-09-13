from typing import List
from pydantic import BaseModel, Field, ValidationError
from enum import Enum
import json
from json import JSONDecodeError


class Verdict(str, Enum):
    RECOMMENDED = "RECOMMENDED"
    PROCEED_WITH_CAUTION = "PROCEED WITH Caution"
    HIGH_RISK = "HIGH RISK"


class RefineOutput(BaseModel):
    elevator_pitch: str = Field(..., min_length=10, max_length=500)
    target_audience: str = Field(..., min_length=5, max_length=300)
    core_value_proposition: str = Field(..., min_length=10, max_length=500)
    monetization_strategy: str = Field(..., min_length=5, max_length=300)


class Competitor(BaseModel):
    name: str
    description: str
    advantage_over_idea: str


class CompetitorsOutput(BaseModel):
    direct_competitors: List[Competitor]
    indirect_competitors: List[str]
    differentiator: str
    barriers_to_entry: List[str]


class FeasibilityScore(BaseModel):
    score: int = Field(..., ge=1, le=10)
    reasoning: str


class FeasibilityOutput(BaseModel):
    overall_score: float = Field(..., ge=1.0, le=10.0)
    scores: dict[str, FeasibilityScore]
    verdict: Verdict


# Action type to schema mapping
_ACTION_SCHEMAS = {
    "REFINE": RefineOutput,
    "COMPETITORS": CompetitorsOutput,
    "FEASIBILITY_SCORE": FeasibilityOutput,
}


def validate_ollama_output(action_type: str, raw_json: str):
    """Validate Ollama JSON output against the appropriate Pydantic schema."""
    schema = _ACTION_SCHEMAS.get(action_type)
    if not schema:
        raise ValueError(f"Unknown action type: {action_type}")
    try:
        return schema.model_validate_json(raw_json)
    except JSONDecodeError:
        # Re-raise as JSONDecodeError so Celery retry logic works
        raise
    except ValidationError:
        # Pydantic validation error - re-raise as ValidationError, not JSONDecodeError
        # so the task doesn't incorrectly retry on validation errors
        raise
    except Exception as e:
        # For any other exception, re-raise as JSONDecodeError
        raise JSONDecodeError(str(e), raw_json, 0)
