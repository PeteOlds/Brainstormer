"""Turn a written build into Test-tab entries.

The Test tab is a record of what should be (and has been) verified next to
an idea. A build used to say nothing about that, so a freshly built app
opened on an empty tab. This module derives a short, honest checklist from
the manifest the model actually wrote:

- a UI check first, naming the URL and screen (the browser path is the one
  reviewers miss, so every build with an entry point gets one);
- the model's own design-specific checks when it supplied them;
- deterministic endpoint / dependency / container checks inferred from the
  generated files, so older manifests and weaker models still get coverage.

Writes are idempotent: ``seed_idea_tests`` matches ``source="build"`` rows
by name, updates them in place (keeping their recorded status), inserts new
ones and prunes checks the latest build no longer produces. Manual rows are
never touched.
"""

from __future__ import annotations

import re

BUILD_SOURCE = "build"
MANUAL_SOURCE = "manual"
MAX_TESTS = 12
MAX_DESCRIPTION = 1000


def _normalise_name(name) -> str:
    return re.sub(r"\s+", " ", str(name or "")).strip()


def _test_type(value) -> str:
    from app.models.idea_test import TestType

    try:
        return TestType(str(value or "e2e").strip().lower()).value
    except ValueError:
        return TestType.E2E.value


def _normalise(spec) -> dict | None:
    """One stored test spec ({name, description, test_type}), or None."""
    if not isinstance(spec, dict):
        return None
    name = _normalise_name(spec.get("name"))
    if len(name) < 3:
        return None
    description = _normalise_name(spec.get("description")) or None
    if description and len(description) > MAX_DESCRIPTION:
        description = description[: MAX_DESCRIPTION - 1].rstrip() + "…"
    return {
        "name": name[:200],
        "description": description,
        "test_type": _test_type(spec.get("test_type")),
    }


def _has_ui(files: list, runtime: dict) -> bool:
    if runtime.get("frontend_url"):
        return True
    for f in files:
        path = str(f.get("path") or "").lower()
        content = str(f.get("content") or "")
        if path.endswith((".html", ".jsx", ".tsx", ".vue", ".svelte")):
            return True
        lowered = content.lower()
        if "render_template(" in content or "<!doctype html" in lowered:
            return True
        if "<html" in lowered:
            return True
    return False


def _has_test_suite(files: list) -> bool:
    for f in files:
        path = str(f.get("path") or "").lower()
        name = path.rsplit("/", 1)[-1]
        if path.startswith(("tests/", "test/", "spec/")):
            return True
        if name.startswith("test_") and name.endswith(".py"):
            return True
        if name.endswith(("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts")):
            return True
    return False


def _routes(files: list) -> list[tuple[str, str]]:
    """(method, path) pairs found in Flask/FastAPI/Express sources."""
    routes: list[tuple[str, str]] = []
    flask_re = re.compile(
        r"@\w+\.route\(\s*['\"]([^'\"]+)['\"]"
        r"(?:\s*,\s*methods\s*=\s*\[([^\]]*)\])?"
    )
    fastapi_re = re.compile(
        r"@\w+\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]", re.I
    )
    express_re = re.compile(
        r"\b(?:app|router)\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]",
        re.I,
    )
    for f in files:
        content = str(f.get("content") or "")
        if not content:
            continue
        if "Flask(" in content or "Blueprint(" in content:
            for match in flask_re.finditer(content):
                path = match.group(1)
                methods = re.findall(r"[A-Z]+", (match.group(2) or "GET").upper())
                for method in methods or ["GET"]:
                    routes.append((method, path))
        for match in fastapi_re.finditer(content):
            routes.append((match.group(1).upper(), match.group(2)))
        for match in express_re.finditer(content):
            routes.append((match.group(1).upper(), match.group(2)))
    # Stable de-dupe, keep first occurrence.
    seen = set()
    unique = []
    for method, path in routes:
        key = (method, path)
        if key not in seen:
            seen.add(key)
            unique.append(key)
    return unique


def _ui_test(runtime: dict, runbook: dict | None, has_ui: bool) -> dict:
    url = runtime.get("frontend_url") or runtime.get("app_url")
    run_cmd = (runbook or {}).get("run")
    start = f"Run the app ({run_cmd})" if run_cmd else "Start the app"
    if has_ui and url:
        name = "UI: main screen loads in a browser"
        description = (
            f"{start} and open {url}. The main screen renders with its "
            "controls and data visible — no stack trace, blank page or 500."
        )
    elif url:
        name = "UI: app responds at its URL"
        description = (
            f"{start} and open {url}. Expect an HTTP 200 with the app's "
            "own output (JSON or HTML), not a connection error."
        )
    else:
        name = "App starts from the documented run command"
        description = (
            f"{start}. Expect it to stay running without a traceback; note "
            "the URL it prints, then open that URL in a browser."
        )
    return {"name": name, "description": description, "test_type": "e2e"}


def derive_build_tests(
    files: list,
    runtime: dict | None = None,
    model_tests: list | None = None,
    runbook: dict | None = None,
) -> list[dict]:
    """Build the checklist for a written manifest.

    Order: the UI check first (always), then the model's design-specific
    checks, then deterministic coverage inferred from the files.
    """
    files = [f for f in (files or []) if isinstance(f, dict)]
    runtime = runtime or {}
    runbook = runbook or {}
    started = bool(
        runtime.get("app_url")
        or runtime.get("frontend_url")
        or runtime.get("start_command")
        or runbook.get("run")
    )
    has_ui = _has_ui(files, runtime)
    url = runtime.get("frontend_url") or runtime.get("app_url")
    start_cmd = runtime.get("start_command") or runbook.get("run") or ""

    tests: list[dict] = []
    seen: set[str] = set()

    def add(spec) -> None:
        item = _normalise(spec)
        if item is None or len(tests) >= MAX_TESTS:
            return
        key = item["name"].strip().lower()
        if key in seen:
            return
        seen.add(key)
        tests.append(item)

    if started:
        add(_ui_test(runtime, runbook, has_ui))

    # Model-declared checks know the design (specific screens, payloads);
    # they go straight after the UI check.
    for spec in model_tests or []:
        if hasattr(spec, "model_dump"):
            spec = spec.model_dump()
        add(spec)

    routes = _routes(files)
    for method, path in routes[:6]:
        if method == "GET" and path in ("/", ""):
            add(
                {
                    "name": f"GET {path or '/'} returns the page",
                    "description": (
                        f"Load {url or (path or '/')} directly. Expect HTTP "
                        "200 and the page markup rendered by the app."
                    ),
                    "test_type": "e2e" if has_ui else "integration",
                }
            )
        elif method == "GET":
            add(
                {
                    "name": f"GET {path} responds",
                    "description": (
                        f"Request GET {path} with no body. Expect HTTP 200 "
                        "and the documented response shape."
                    ),
                    "test_type": "integration",
                }
            )
        elif method == "POST":
            add(
                {
                    "name": f"POST {path} returns a valid response",
                    "description": (
                        f"Send a valid request to POST {path} (use the same "
                        "fields the UI submits). Expect HTTP 200 and the "
                        "documented JSON/HTML — and a clear error for a "
                        "missing field."
                    ),
                    "test_type": "integration",
                }
            )

    has_python_deps = any(
        str(f.get("path") or "").rsplit("/", 1)[-1]
        in ("requirements.txt", "pyproject.toml")
        for f in files
    )
    if has_python_deps:
        add(
            {
                "name": "Dependencies install cleanly",
                "description": (
                    "Run the Setup step in the same folder as the app and "
                    "expect it to finish without resolver or build errors."
                ),
                "test_type": "unit",
            }
        )
    if any(
        str(f.get("path") or "").rsplit("/", 1)[-1] == "package.json"
        for f in files
    ):
        add(
            {
                "name": "npm install completes",
                "description": (
                    "Run `npm install` in the app folder. Expect no "
                    "unresolved peer dependencies or build-script failures."
                ),
                "test_type": "unit",
            }
        )

    if any(
        str(f.get("path") or "").rsplit("/", 1)[-1].lower()
        in ("dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml")
        for f in files
    ):
        add(
            {
                "name": "Container image builds",
                "description": (
                    "Run the Compose/Docker build command in the How-to-run "
                    "panel. Expect a successful image build and a container "
                    "that stays up."
                ),
                "test_type": "integration",
            }
        )

    if _has_test_suite(files):
        add(
            {
                "name": "Generated test suite passes",
                "description": (
                    "Run the project's test command (e.g. `pytest` or "
                    "`npm test`) in the build folder. Expect all generated "
                    "tests to pass."
                ),
                "test_type": "unit",
            }
        )

    # The UI path is the one reviewers skip: never hand back a checklist
    # without a browser-level check when the build runs at all.
    if started and not any(t["test_type"] == "e2e" for t in tests):
        add(_ui_test(runtime, runbook, has_ui))

    if not tests:
        add(
            {
                "name": "App starts and serves a request",
                "description": (
                    f"Run `{start_cmd}` if the runbook provides one, then "
                    "open the printed URL and confirm the app responds."
                ),
                "test_type": "manual",
            }
        )
    return tests


def seed_idea_tests(idea, tests: list[dict], source: str = BUILD_SOURCE) -> dict:
    """Upsert derived checks onto an idea's Test tab.

    Matching is by case-insensitive name within ``source``. Existing rows
    keep their recorded status/coverage/last-run: a rebuild must not erase
    evidence that a check was run. Returns counts for the write report.
    """
    from app.extensions import db
    from app.models.idea_test import IdeaTest, TestStatus, TestType

    desired: list[dict] = []
    seen: set[str] = set()
    for spec in tests or []:
        item = _normalise(spec)
        if item is None:
            continue
        key = item["name"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        desired.append(item)

    existing = IdeaTest.query.filter_by(idea_id=idea.id, source=source).all()
    by_name = {row.name.strip().lower(): row for row in existing}
    stats = {"created": 0, "updated": 0, "removed": 0}

    for item in desired:
        key = item["name"].strip().lower()
        row = by_name.get(key)
        if row is not None:
            changed = (
                row.description != item["description"]
                or row.test_type != TestType(item["test_type"])
            )
            if changed:
                row.description = item["description"]
                row.test_type = TestType(item["test_type"])
                stats["updated"] += 1
            continue
        db.session.add(
            IdeaTest(
                idea_id=idea.id,
                instance_id=getattr(idea, "instance_id", None),
                name=item["name"],
                description=item["description"],
                test_type=TestType(item["test_type"]),
                status=TestStatus.NOT_RUN,
                source=source,
            )
        )
        stats["created"] += 1

    for row in existing:
        if row.name.strip().lower() not in seen:
            db.session.delete(row)
            stats["removed"] += 1

    db.session.flush()
    return stats
