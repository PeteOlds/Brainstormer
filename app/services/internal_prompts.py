"""Central catalogue for internal AI prompts.

Every shared prompt has a stable key and a template file under
``app/prompt_templates``. Site-admin overrides are resolved here (slice 2);
this module keeps call sites independent of storage details.
"""

import re
from pathlib import Path
from string import Template

import structlog

from app.config import Config

logger = structlog.get_logger()

MAX_PROMPT_CHARS = 20000
SECRET_RE = re.compile(
    r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
)

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


def override_body(key: str) -> str | None:
    """Return a saved site override, or None (including before migration)."""
    from flask import has_app_context

    if not has_app_context():
        return None
    try:
        from app.models import SitePrompt

        row = SitePrompt.query.filter_by(key=key).first()
        return row.body if row is not None else None
    except Exception:
        logger.exception("site_prompt_override_unavailable", key=key)
        return None


def get_internal_prompt(key: str) -> InternalPrompt:
    """Return the effective prompt: site override first, shipped file second."""
    body = override_body(key)
    if body is None:
        body = default_body(key)
    return InternalPrompt(key, body)


def validate_prompt_body(key: str, body: object) -> str:
    """Validate an override and return the normalised body, or raise ValueError."""
    if key not in PROMPT_CATALOGUE:
        raise ValueError(f"Unknown internal prompt: {key}")
    if not isinstance(body, str):
        raise ValueError("body must be a string")
    text = body.strip()
    if not text:
        raise ValueError("body must not be empty")
    if len(text) > MAX_PROMPT_CHARS:
        raise ValueError(f"body must be at most {MAX_PROMPT_CHARS} characters")
    default = default_body(key)
    required = InternalPrompt(key, default).required_placeholders
    missing = [name for name in required if "${" + name + "}" not in text]
    if missing:
        raise ValueError("missing placeholders: " + ", ".join(missing))
    if "OUTPUT JSON SCHEMA" in default and "OUTPUT JSON SCHEMA" not in text:
        raise ValueError("JSON prompts must retain the OUTPUT JSON SCHEMA section")
    if SECRET_RE.search(text):
        raise ValueError("body contains a token or private key pattern")
    return text


def list_internal_prompts() -> list[dict[str, object]]:
    """Catalogue with effective bodies and source, for the admin API."""
    rows: list[dict[str, object]] = []
    for key, (_, label) in PROMPT_CATALOGUE.items():
        default = default_body(key)
        override = override_body(key)
        prompt = InternalPrompt(key, override if override is not None else default)
        rows.append(
            {
                "key": key,
                "label": label,
                "source": "override" if override is not None else "default",
                "body": prompt.body,
                "default_body": default,
                "required_placeholders": prompt.required_placeholders,
                "updated_at": None,
            }
        )
    return rows
