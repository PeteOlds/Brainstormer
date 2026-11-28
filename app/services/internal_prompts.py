"""Central catalogue for internal AI prompts.

Every shared prompt has a stable key and a template file under
``app/prompt_templates``. Site-admin overrides are resolved here (slice 2);
this module keeps call sites independent of storage details.
"""

from pathlib import Path
from string import Template

from app.config import Config

# Stable key -> (template filename, human label).
PROMPT_CATALOGUE: dict[str, tuple[str, str]] = {
    "base": ("base", "Base system prompt"),
    "initial": ("initial", "Idea generation"),
    "chat_system": ("chat_system", "Chat system suffix"),
    "strict_retry": ("strict_retry", "Strict JSON retry"),
    "diagnose_tests": ("diagnose_tests", "Test failure diagnosis"),
    "diagnose_app": ("diagnose_app", "App startup diagnosis"),
    "refine": ("refine", "Refine idea"),
    "competitors": ("competitors", "Competitor analysis"),
    "feasibility": ("feasibility", "Feasibility score"),
    "forces": ("forces", "Five Forces"),
    "pestel": ("pestel", "PESTEL"),
    "prd_doc": ("prd_doc", "Brief"),
    "design_doc": ("design_doc", "Design"),
    "vrio": ("vrio", "VRIO"),
    "three_cs": ("three_cs", "3Cs"),
    "market_sizing": ("market_sizing", "Market sizing"),
    "business_model_canvas": ("business_model_canvas", "Business model canvas"),
    "hypothesis_test": ("hypothesis_test", "Hypothesis test"),
    "gtm_strategy": ("gtm_strategy", "GTM strategy"),
    "build_code": ("build_code", "Build code"),
    "build_review": ("build_review", "Build review"),
}


class InternalPrompt:
    """A resolved prompt body with safe placeholder substitution."""

    def __init__(self, key: str, body: str):
        self.key = key
        self.body = body

    def render(self, **kwargs: object) -> str:
        return Template(self.body).safe_substitute(kwargs)

    @property
    def required_placeholders(self) -> list[str]:
        return sorted(
            {
                match[1] or match[2]
                for match in Template.pattern.findall(self.body)
                if match[1] or match[2]
            }
        )


def default_body(key: str) -> str:
    """Read the shipped template file for a catalogue key."""
    if key not in PROMPT_CATALOGUE:
        raise ValueError(f"Unknown internal prompt: {key}")
    filename = PROMPT_CATALOGUE[key][0]
    path = Path(Config.PROMPT_TEMPLATES_DIR) / f"{filename}.txt"
    return path.read_text(encoding="utf-8")


def get_internal_prompt(key: str) -> InternalPrompt:
    """Return the effective prompt for a key (override support lands in slice 2)."""
    return InternalPrompt(key, default_body(key))


def list_internal_prompts() -> list[dict[str, object]]:
    """Catalogue with default bodies, for the admin API."""
    return [
        {
            "key": key,
            "label": label,
            "body": default_body(key),
            "required_placeholders": InternalPrompt(
                key, default_body(key)
            ).required_placeholders,
        }
        for key, (_, label) in PROMPT_CATALOGUE.items()
    ]
