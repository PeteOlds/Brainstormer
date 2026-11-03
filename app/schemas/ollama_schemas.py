from typing import List, get_args, get_origin
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
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


class DesignDocOutput(BaseModel):
    """Design document — build-ready blueprint derived from the PRD:
    architecture, screens/components, data model, API contracts."""
    architecture: str = Field(..., min_length=20)
    screens: str = Field(..., min_length=20)
    data_model: str = Field(..., min_length=20)
    api_contracts: str = Field(..., min_length=20)
    build_notes: str = Field(..., min_length=20)
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


BUILD_MAX_FILES = 25
BUILD_MAX_FILE_CHARS = 15000
BUILD_MAX_TOTAL_CHARS = 60000
BUILD_MAX_TESTS = 12

# Mirrors app.models.idea_test.TestType without importing models into the
# schema layer.
BUILD_TEST_TYPES = ("unit", "integration", "e2e", "manual", "performance")


class BuildTest(BaseModel):
    """One verification check a reviewer should perform on the build.

    These become Test-tab rows on a successful write. They are checks, not
    executed tests: the tab records what was verified and the outcome.
    """

    name: str = Field(..., min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    test_type: str = "e2e"

    @field_validator("test_type", mode="before")
    @classmethod
    def _known_type(cls, value) -> str:
        v = str(value or "e2e").strip().lower()
        return v if v in BUILD_TEST_TYPES else "e2e"


class BuildFile(BaseModel):
    """One generated source file: repo-relative path + full content."""

    path: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=BUILD_MAX_FILE_CHARS)

    @field_validator("path")
    @classmethod
    def _safe_relative_path(cls, value: str) -> str:
        # Absolute paths, home/drive prefixes and escapes are rejected
        # outright (never silently rewritten); "./" and "\" separators
        # are normalized.
        raw = str(value)
        if (
            not raw.strip()
            or raw.strip().startswith("/")
            or raw.strip().startswith("~")
            or (len(raw.strip()) >= 2 and raw.strip()[1] == ":")
        ):
            raise ValueError(f"unsafe file path: {value!r}")
        cleaned = raw.replace("\\", "/").strip()
        while cleaned.startswith("./"):
            cleaned = cleaned[2:]
        parts = [p for p in cleaned.split("/") if p not in ("", ".")]
        if not parts or any(p == ".." for p in parts):
            raise ValueError(f"unsafe file path: {value!r}")
        return "/".join(parts)


class BuildCodeOutput(BaseModel):
    """Code build manifest: files to write, plus write-state tracking.

    The first (preview) version carries ``written=False``; the confirm run
    writes the stored manifest and appends a version with ``written=True``.
    """

    summary: str = Field(..., min_length=20)
    files: List[BuildFile] = Field(..., min_length=1, max_length=BUILD_MAX_FILES)
    # Checks a reviewer should perform once the build is written. The task
    # keeps these (and adds deterministic ones) as Test-tab rows; older
    # manifests without the key still validate.
    tests: List[BuildTest] = Field(default_factory=list, max_length=BUILD_MAX_TESTS)
    written: bool = False
    target_name: str | None = None
    # Absolute server-side target root, set by the task (not the model) so
    # run instructions can ship copy/pasteable `cd "<path>" && ...` commands.
    target_path: str | None = None
    # Host-side twin of target_path (same machine users paste into), for
    # the same commands. Falls back to target_path when unmapped.
    target_host_path: str | None = None
    # Server-derived, verified runbook ({setup, run, workdir}): fully
    # rendered paste-and-run commands (host paths, venv setup, resolved
    # working directory). The UI prefers these over the raw model fields.
    runbook: dict | None = None
    write_report: List[str] = Field(default_factory=list)

    # --- Runtime / deployment info (populated by the task from generated code) ---
    # How to start the application
    start_command: str | None = None
    # URL where the application will be accessible (e.g., "http://localhost:3000")
    app_url: str | None = None
    # Port the application listens on (host side: what the user opens)
    port: int | None = None
    # Port the manifest originally asked for, when allocation moved it.
    port_requested: int | None = None
    # True when the requested port was busy and a free one was allocated.
    port_changed: bool = False
    # Human UI URL when the build ships a separate frontend/dashboard
    # (e.g. a compose `frontend` service): Open points here, not at the
    # API above (which stays the health-check target). None for
    # single-service builds.
    frontend_url: str | None = None
    # Frontend host port (what the user opens), when one was detected.
    frontend_port: int | None = None
    # Credentials for initial login (if applicable)
    credentials: dict | None = None
    # Docker image name if containerized
    docker_image: str | None = None
    # Docker Compose file path (relative to target root)
    docker_compose_file: str | None = None
    # Additional notes for the user (how to access, default credentials, etc.)
    run_notes: str | None = None

    @model_validator(mode="after")
    def _cap_total_size(self):
        total = sum(len(f.content) for f in self.files)
        if total > BUILD_MAX_TOTAL_CHARS:
            raise ValueError(
                f"manifest too large: {total} chars (max {BUILD_MAX_TOTAL_CHARS})"
            )
        return self


# Action type to schema mapping
_ACTION_SCHEMAS = {
    "REFINE": RefineOutput,
    "COMPETITORS": CompetitorsOutput,
    "FEASIBILITY_SCORE": FeasibilityOutput,
    "FIVE_FORCES": FiveForcesOutput,
    "PESTEL": PestelOutput,
    "PRD_DOC": PrdOutput,
    "DESIGN_DOC": DesignDocOutput,
    "VRIO": VrioOutput,
    "THREE_CS": ThreeCsOutput,
    "MARKET_SIZING": MarketSizingOutput,
    "BUSINESS_MODEL_CANVAS": BusinessModelCanvasOutput,
    "HYPOTHESIS_TEST": HypothesisTestOutput,
    "GTM_STRATEGY": GtmStrategyOutput,
    "BUILD_CODE": BuildCodeOutput,
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
        elif ann is str and isinstance(val, dict):
            # Model emitted an object where text belongs (recorded prod
            # shape: MarketSizing `tam: {'$1.4B ...': '...ue per user...'}`).
            # Join all string leaves; leave untouched if none.
            leaves = []

            def _walk(node):
                if isinstance(node, str) and node.strip():
                    leaves.append(node.strip())
                elif isinstance(node, (int, float)):
                    leaves.append(str(node))
                elif isinstance(node, dict):
                    for k, v in node.items():
                        _walk(k)
                        _walk(v)
                elif isinstance(node, list):
                    for v in node:
                        _walk(v)

            _walk(val)
            if leaves:
                obj[name] = " ".join(leaves)
        elif get_origin(ann) is list and get_args(ann) == (str,) and isinstance(val, list):
            strs = [str(v).strip() for v in val
                    if isinstance(v, (str, int, float)) and str(v).strip()]
            if strs != val:
                obj[name] = strs
    return obj


def get_action_schema(action_type: str):
    """Pydantic schema for an action type, or None if unknown."""
    return _ACTION_SCHEMAS.get(action_type)


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
