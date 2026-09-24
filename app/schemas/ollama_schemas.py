from typing import List, get_args, get_origin
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
    # Defaults (not required): small models often omit fields or return
    # partial objects — a partial analysis beats a FAILED run.
    name: str = ""
    description: str = ""
    advantage_over_idea: str = ""


class CompetitorsOutput(BaseModel):
    direct_competitors: List[Competitor] = Field(default_factory=list)
    indirect_competitors: List[str] = Field(default_factory=list)
    differentiator: str = ""
    barriers_to_entry: List[str] = Field(default_factory=list)


class FeasibilityScore(BaseModel):
    score: int = Field(..., ge=1, le=10)
    reasoning: str


class FeasibilityOutput(BaseModel):
    overall_score: float = Field(..., ge=1.0, le=10.0)
    scores: dict[str, FeasibilityScore]
    verdict: Verdict


class FiveForcesOutput(BaseModel):
    """Porter's Five Forces — flat strings/lists only: nested objects
    garble on small models (see: COMPETITORS validation failures)."""
    competitive_rivalry: str = Field(..., min_length=20)
    threat_of_substitutes: str = Field(..., min_length=20)
    threat_of_new_entrants: str = Field(..., min_length=20)
    bargaining_power_of_buyers: str = Field(..., min_length=20)
    bargaining_power_of_suppliers: str = Field(..., min_length=20)
    market_attractiveness: str = Field(..., min_length=10)
    primary_risks: List[str]
    recommendations: List[str]


class PestelOutput(BaseModel):
    """PESTEL analysis — same flat-shape rule as FiveForcesOutput."""
    political: str = Field(..., min_length=20)
    economic: str = Field(..., min_length=20)
    social: str = Field(..., min_length=20)
    technological: str = Field(..., min_length=20)
    environmental: str = Field(..., min_length=20)
    legal: str = Field(..., min_length=20)
    opportunities: List[str]
    threats: List[str]
    recommendations: List[str]


class PrdOutput(BaseModel):
    """PRD document — flat sections plus capped open-questions list."""
    executive_summary: str = Field(..., min_length=20)
    user_personas: str = Field(..., min_length=20)
    product_scope: str = Field(..., min_length=20)
    functional_requirements: str = Field(..., min_length=20)
    non_functional_requirements: str = Field(..., min_length=20)
    ux_guidelines: str = Field(..., min_length=20)
    assumptions_risks: str = Field(..., min_length=20)
    open_questions: List[str] = Field(default_factory=list, max_length=5)


class VrioOutput(BaseModel):
    """VRIO Framework — 4 criteria + 5-tier classification + recommendations."""
    value: str = Field(..., min_length=20)
    rarity: str = Field(..., min_length=20)
    imitability: str = Field(..., min_length=20)
    organization: str = Field(..., min_length=20)
    competitive_implication: str = Field(..., min_length=10)
    recommendations: List[str]


class ThreeCsOutput(BaseModel):
    """3Cs Strategic Analysis — Customer, Competitor, Company + alignment + recommendations."""
    customer: str = Field(..., min_length=20)
    competitor: str = Field(..., min_length=20)
    company: str = Field(..., min_length=20)
    alignment_summary: str = Field(..., min_length=20)
    recommendations: List[str]


class MarketSizingOutput(BaseModel):
    """Market Sizing — TAM/SAM/SOM with formulas and assumptions."""
    tam: str = Field(..., min_length=20)
    sam: str = Field(..., min_length=20)
    som: str = Field(..., min_length=20)
    summary_table: str = Field(..., min_length=20)
    key_assumptions: List[str]


class BusinessModelCanvasOutput(BaseModel):
    """Business Model Canvas — 9 blocks + vulnerabilities + validation experiments."""
    value_propositions: str = Field(..., min_length=20)
    customer_segments: str = Field(..., min_length=20)
    channels: str = Field(..., min_length=20)
    customer_relationships: str = Field(..., min_length=20)
    revenue_streams: str = Field(..., min_length=20)
    key_resources: str = Field(..., min_length=20)
    key_activities: str = Field(..., min_length=20)
    key_partnerships: str = Field(..., min_length=20)
    cost_structure: str = Field(..., min_length=20)
    strategic_vulnerabilities: List[str]
    validation_experiments: List[str]


class HypothesisTestOutput(BaseModel):
    """Hypothesis Test — Assumptions matrix + hypotheses + experiments + roadmap."""
    assumptions_matrix: str = Field(..., min_length=20)
    hypotheses: List[str]
    experiments: List[str]
    roadmap_phases: List[str]


class GtmStrategyOutput(BaseModel):
    """GTM Execution Strategy — 6 pillars + AARRR metrics + launch roadmap."""
    market_segmentation: str = Field(..., min_length=20)
    value_proposition: str = Field(..., min_length=20)
    pricing_packaging: str = Field(..., min_length=20)
    acquisition_channels: str = Field(..., min_length=20)
    marketing_launch_plan: str = Field(..., min_length=20)
    success_metrics: str = Field(..., min_length=20)
    launch_roadmap: List[str]


# Action type to schema mapping
_ACTION_SCHEMAS = {
    "REFINE": RefineOutput,
    "COMPETITORS": CompetitorsOutput,
    "FEASIBILITY_SCORE": FeasibilityOutput,
    "FIVE_FORCES": FiveForcesOutput,
    "PESTEL": PestelOutput,
    "PRD_DOC": PrdOutput,
    "VRIO": VrioOutput,
    "THREE_CS": ThreeCsOutput,
    "MARKET_SIZING": MarketSizingOutput,
    "BUSINESS_MODEL_CANVAS": BusinessModelCanvasOutput,
    "HYPOTHESIS_TEST": HypothesisTestOutput,
    "GTM_STRATEGY": GtmStrategyOutput,
}


def _coerce_scalar_lists(obj, schema):
    """Join list-shaped values into strings where the schema expects str.

    Small models frequently emit arrays (sometimes of junk objects) for
    text fields — e.g. PESTEL `political: [{'_id': ...}]`, Refine
    `elevator_pitch: ['Ollam...']`. Join usable string items; leave the
    value untouched when nothing usable remains so validation still fails
    honestly and the strict-retry path engages.
    """
    if not isinstance(obj, dict):
        return obj
    try:
        fields = schema.model_fields
    except Exception:
        return obj
    for name, field in fields.items():
        if name not in obj:
            continue
        val = obj[name]
        ann = field.annotation
        if ann is str and isinstance(val, list):
            texts = [str(v).strip() for v in val
                     if isinstance(v, (str, int, float)) and str(v).strip()]
            if texts:
                obj[name] = " ".join(texts)
        elif get_origin(ann) is list and get_args(ann) == (str,) and isinstance(val, list):
            strs = [str(v).strip() for v in val
                    if isinstance(v, (str, int, float)) and str(v).strip()]
            if strs != val:
                obj[name] = strs
    return obj


def validate_ollama_output(action_type: str, raw_json: str):
    """Validate Ollama JSON output against the appropriate Pydantic schema."""
    schema = _ACTION_SCHEMAS.get(action_type)
    if not schema:
        raise ValueError(
            f"Unknown action type: {action_type}. "
            f"Known: {sorted(_ACTION_SCHEMAS)}")
    try:
        return schema.model_validate_json(raw_json)
    except JSONDecodeError:
        # Re-raise as JSONDecodeError so Celery retry logic works
        raise
    except ValidationError as first:
        # One coercion attempt for list-shaped scalars before giving up.
        try:
            coerced = _coerce_scalar_lists(json.loads(raw_json), schema)
            return schema.model_validate(coerced)
        except (ValueError, ValidationError):
            raise first
        except Exception as e:
            # For any other exception, re-raise as JSONDecodeError
            raise JSONDecodeError(str(e), raw_json, 0)
    except Exception as e:
        # For any other exception, re-raise as JSONDecodeError
        raise JSONDecodeError(str(e), raw_json, 0)
