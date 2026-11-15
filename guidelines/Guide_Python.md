# Python Development Best Practice Guide

> **Status: Adopted (with BS deltas).** Applies to Brainstormer today. Canonical tooling per root `AGENTS.md`: virtual environment `venv/`, `black` + `isort` + `mypy`, `pytest`. On any conflict with `AGENTS.md`, `AGENTS.md` wins.

## Core Principles

Write self-documenting, concise Python code that prioritizes readability, strict type safety, and standardized structure.

* **Type Hinting**: Always use static typing via `typing` or modern Python 3.10+ native pipe syntax (`str | None`).
* **Dataclasses & Pydantic**: Prefer `@dataclass` or `pydantic.BaseModel` over raw dictionaries for structured data transfer.
* **Pure Functions**: Favor stateless, side-effect-free functions that are easy for LLMs to analyze, mock, and test.
* **DRY & Expressive**: Avoid redundant boilerplate by leveraging built-ins (`zip`, `enumerate`, list/dict comprehensions).

---

## Environment & Dependency Management

Always isolate project dependencies using the project's virtual environment (`venv/`). Never install project dependencies directly into the global system Python environment.

* **Creating a Virtual Environment**:
  ```bash
  python3 -m venv venv

```

* **Activating the Environment**:
* **macOS/Linux**: `source venv/bin/activate`
* **Windows**: `venv\Scripts\activate`


* **Dependency Locking**: Maintain deterministic builds using a pinned dependency file (`requirements.txt`, `pyproject.toml`, or `uv.lock`). Exclude the `venv/` directory from source control via `.gitignore`.

---

## Code Style & Formatting Guidelines

Maintain strict consistency across codebases using the project's standard tooling: `black` (line length 88), `isort` (profile `black`), and `mypy` — see `pyproject.toml` and root `AGENTS.md`. (`ruff` is an acceptable alternative only where a project has explicitly adopted it.)

| Aspect | Standard Practice | Example |
| --- | --- | --- |
| **Formatting** | Standard 4-space indentation, max 88 characters per line. | Use automated formatters (`black .`). |
| **Imports** | Grouped: Stdlib first, 3rd party second, local modules third. | Absolute imports over relative imports (`isort`). |
| **Naming Conventions** | `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE` for constants. | `def calculate_total(item_list: list[float]) -> float:` |
| **Docstrings** | Google Style docstrings for complex logic; omit for trivial self-explanatory functions. | Keep concise and focus on invariants or non-obvious side effects. |
| **Type checking** | `mypy` per `pyproject.toml`. | `mypy app` must pass before committing. |

---

## Design Patterns & Maintainability

### Data Containers

Use `pydantic.BaseModel` for validation at input boundaries (APIs, config files) and standard `@dataclass(slots=True)` for internal low-overhead data transfer object (DTO) patterns.

```python
from dataclasses import dataclass
from pydantic import BaseModel, EmailStr

# Internal DTO
@dataclass(slots=True, frozen=True)
class UserDTO:
    id: int
    username: str

# API Input Boundary Validation
class UserCreateSchema(BaseModel):
    username: str
    email: EmailStr  # requires the `email-validator` package

```

> **BS delta:** model IDs are `GUID` (UUID), not `int` — see `app/models/types.py`.

### Error Handling

Catch specific exceptions, avoid bare `except:`, and wrap domain-specific errors in custom exception hierarchies.

```python
class DomainError(Exception):
    """Base exception for application domain errors."""

class UserNotFoundError(DomainError):
    def __init__(self, user_id: int):
        super().__init__(f"User with ID {user_id} was not found.")

```

### Context Managers

Wrap external resource allocation (files, HTTP sessions, database transactions) in context managers to guarantee deterministic cleanup.

```python
from contextlib import contextmanager
from typing import Generator

@contextmanager
def db_session() -> Generator[None, None, None]:
    session = create_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

```

---

## Architectural Considerations & Integration

* **Separation of Concerns**: Decouple business logic from framework code (e.g., Flask handlers, CLI parsers).
* **Front-End Interoperability**: When integrating backend Python services with client applications, treat Python as the API/backend layer (front-end interfaces are typically built using frameworks like Flutter). Ensure API payloads serialize cleanly to JSON for easy consumption.
* **Testing Strategy**: Use `pytest` with `pytest-mock`. Keep unit tests fast, deterministic, and closely collocated or aligned with the module structure. See root `AGENTS.md` "Test Patterns" and `tests/conftest.py` for fixture conventions.

---

## BS Deltas (Brainstormer-specific, mandatory here)

These rules override or extend the generic guidance above within Brainstormer:

* **Primary keys:** use the `GUID` TypeDecorator (`app/models/types.py`), not integer IDs — required for SQLite/Postgres portability and offline-first sync.
* **Datetimes:** SQLite returns naive datetimes for `DateTime(timezone=True)`. Always compare via `ensure_aware()` (`app/models/types.py`) or comparisons raise `TypeError`.
* **JSON columns:** plain `db.JSON` with no in-place mutation — build a fresh dict and assign, or SQLAlchemy skips the UPDATE.
* **Logging:** structured logging via `structlog` (JSON in production). Never log prompt bodies, idea content, or PII — log IDs and hashes only.
* **LLM output:** always request JSON mode and validate with the Pydantic schemas in `app/schemas/ollama_schemas.py`; preserve raw decode errors for Celery retry.
* **Sessions/transactions:** use the Flask-SQLAlchemy scoped session (`db.session`), not a hand-rolled `db_session` context manager; tests get a fresh in-memory DB per test via function-scoped fixtures.

