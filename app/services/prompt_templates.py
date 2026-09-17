from pathlib import Path
from string import Template

from app.config import Config


class PromptTemplate:
    """Loads and renders prompt templates from files."""

    def __init__(self, name: str):
        self.name = name
        self.template_path = Path(Config.PROMPT_TEMPLATES_DIR) / f"{name}.txt"
        if not self.template_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {self.template_path}")
        self.template = Template(self.template_path.read_text())

    def render(self, **kwargs) -> str:
        """Render template with safe substitution (missing keys left as {{KEY}})."""
        return self.template.safe_substitute(kwargs)


# Pre-load templates
def get_base_prompt() -> str:
    """Get the base system prompt."""
    path = Path(Config.PROMPT_TEMPLATES_DIR) / "base.txt"
    return path.read_text()


def get_refine_prompt() -> PromptTemplate:
    return PromptTemplate("refine")


def get_competitors_prompt() -> PromptTemplate:
    return PromptTemplate("competitors")


def get_feasibility_prompt() -> PromptTemplate:
    return PromptTemplate("feasibility")


def get_prompt_template(action_type: str) -> PromptTemplate:
    """Get prompt template for action type."""
    mapping = {
        "REFINE": "refine",
        "COMPETITORS": "competitors",
        "FEASIBILITY_SCORE": "feasibility",
        "FIVE_FORCES": "forces",
        "PESTEL": "pestel",
        "PRD_DOC": "prd_doc",
    }
    template_name = mapping.get(action_type)
    if not template_name:
        raise ValueError(f"Unknown action type: {action_type}")
    return PromptTemplate(template_name)