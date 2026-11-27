"""Build runtime/runbook/port helpers extracted from ollama_tasks.

These helpers derive how to run a built app (entry point, port, runbook) and
rewrite hard-coded ports. They are pure-ish (no Celery task state) and are
re-exported from ``app.tasks.ollama_tasks`` for backwards compatibility.
"""

import os
import re

from app.services.build_file_helpers import (  # noqa: F401
    _IMPORT_TO_PACKAGE,
    _ensure_requirements,
    _inject_root_route,
    _merge_files,
)
from app.services.build_port_helpers import (  # noqa: F401
    _allocate_build_port,
    _host_network_ip,
    _rewrite_compose_host_port,
    _rewrite_source_port,
)


def _infer_entry_command(
    by_path: dict,
    known_port=None,
    preferred_paths=None,
    start_dir=None,
):
    """Guess a start command when the manifest has no Dockerfile/compose/package.json.

    Searches the whole tree rather than a fixed prefix list, so a monorepo
    entry such as ``backend/src/app.py`` is found too. When several entries
    exist, one under a changed file's directory wins, then one directly in
    ``start_dir``, then the shallowest path.

    Returns ``(start_command, port, note)`` or ``(None, None, None)``. Only
    fires on a recognisable Python entry file, so an unrelated manifest
    (README-only) stays unrunnable — and the build confirm refuses it
    rather than reporting a build nobody can start.
    """
    import re as _re

    names = ("app.py", "main.py", "server.py", "run.py", "wsgi.py", "asgi.py")

    def _norm(value) -> str:
        text = str(value or "").replace("\\", "/")
        while text.startswith("./"):
            text = text[2:]
        return text

    def _module(rel: str) -> str:
        return rel[:-3].replace("/", ".") if rel.endswith(".py") else rel

    def _dir_of(rel: str) -> str:
        return rel.rsplit("/", 1)[0] if "/" in rel else ""

    normalised = {
        _norm(path): str(content)
        for path, content in (by_path or {}).items()
        if _norm(path)
    }
    preferred = [_norm(path) for path in (preferred_paths or []) if _norm(path)]
    base = _norm(start_dir or "").strip("/")

    def _under(path: str, folder: str) -> bool:
        return bool(folder) and (path == folder or path.startswith(folder + "/"))

    def _near_preferred(rel: str) -> bool:
        folder = _dir_of(rel)
        for path in preferred:
            other = _dir_of(path)
            if rel == path or folder == other:
                return True
            if (
                folder
                and other
                and (folder.startswith(other + "/") or other.startswith(folder + "/"))
            ):
                return True
        return False

    candidates = []
    for rel in normalised:
        name = rel.rsplit("/", 1)[-1]
        if name not in names:
            continue
        candidates.append(
            (
                0 if _under(rel, base) else 1,
                0 if _near_preferred(rel) else 1,
                rel.count("/"),
                names.index(name),
                rel,
            )
        )
    candidates.sort()
    has_requirements = any(
        _re.search(r"(^|/)requirements[^/]*\.txt$", path or "") for path in normalised
    )
    for _base_rank, _pref_rank, _depth, _name_rank, rel in candidates:
        text = normalised[rel]
        mod = _module(rel)
        if "FastAPI(" in text or "fastapi import" in text:
            port = known_port or 8000
            note = f"Start command inferred from {rel} (FastAPI)."
            if not has_requirements:
                note += (
                    "\nNo requirements.txt in this build — install uvicorn "
                    "and fastapi before running."
                )
            return (
                f"python3 -m uvicorn {mod}:app --host 0.0.0.0 --port {port}",
                port,
                note,
            )
        if _re.search(r"\bFlask\s*\(", text) or "flask import" in text:
            port = known_port or 5000
            note = f"Start command inferred from {rel} (Flask)."
            if not has_requirements:
                note += (
                    "\nNo requirements.txt in this build — install flask "
                    "before running."
                )
            if _re.search(r"(?m)^\s*app\s*=\s*Flask\s*\(", text):
                return (
                    f"python3 -m flask --app {mod} run --host 0.0.0.0 --port {port}",
                    port,
                    note,
                )
            return f"python3 {rel}", port, note
        # Canonical script names run as scripts even without a
        # __main__ guard; wsgi/asgi modules only when they have one.
        if (
            rel.rsplit("/", 1)[-1] in ("app.py", "main.py", "server.py", "run.py")
            or "__main__" in text
        ):
            return f"python3 {rel}", known_port, f"Start command inferred from {rel}."
    return None, None, None


def _extract_runtime_info(files: list, preferred_paths=None) -> dict:
    """Infer how to run a built app from its manifest files.

    Inspects Dockerfile (EXPOSE/CMD), docker-compose (ports/image),
    package.json (start script) and .env.example (credentials) without
    executing anything. ``preferred_paths`` are the files this build
    changed; they decide which service in a monorepo is the primary one
    (a backend change must not run the frontend's Dockerfile). Returns
    only plain JSON-safe values so the result row can carry them straight
    to the UI instructions modal.
    """
    import json
    import re

    # Compose service names that conventionally serve the human UI
    # rather than the API. Matched case-insensitively, exact or as a
    # path segment of the build context (./frontend, ./client …).
    FRONTEND_HINTS = (
        "frontend",
        "ui",
        "client",
        "web",
        "www",
        "site",
        "dashboard",
        "portal",
        "app",
    )

    def _norm(value) -> str:
        text = str(value or "").replace("\\", "/")
        while text.startswith("./"):
            text = text[2:]
        return text

    def _dir_of(path: str) -> str:
        rel = _norm(path)
        return rel.rsplit("/", 1)[0] if "/" in rel else ""

    def _under(path: str, folder: str) -> bool:
        return bool(folder) and (path == folder or path.startswith(folder + "/"))

    def _frontend_dir(folder: str) -> bool:
        parts = [p for p in _norm(folder).lower().split("/") if p]
        return any(
            p
            in ("frontend", "ui", "client", "web", "www", "site", "dashboard", "portal")
            for p in parts
        )

    def _pub_ports(mapping):
        """Published (host, container) ports from one compose ports entry."""
        host, target = None, None
        if isinstance(mapping, int):
            target = mapping
        elif isinstance(mapping, str) and mapping.strip():
            parts = mapping.strip().strip("\"'").split(":")
            try:
                if len(parts) >= 2:
                    host = int(parts[-2])
                target = int(parts[-1])
            except ValueError:
                host = target = None
        elif isinstance(mapping, dict) and mapping.get("target") is not None:
            try:
                target = int(mapping["target"])
            except (TypeError, ValueError):
                target = None
            try:
                host = (
                    int(mapping["published"])
                    if mapping.get("published") is not None
                    else None
                )
            except (TypeError, ValueError):
                host = None
        return host, target

    def _looks_frontend(name, svc):
        low = str(name or "").lower()
        if low in FRONTEND_HINTS:
            return True
        build = svc.get("build") if isinstance(svc, dict) else None
        ctx = build.get("context") if isinstance(build, dict) else build
        if isinstance(ctx, str) and any(h in ctx.lower() for h in FRONTEND_HINTS):
            return True
        image = svc.get("image") if isinstance(svc, dict) else None
        if isinstance(image, str) and "nginx" in image.lower():
            return True
        return False

    info: dict = {
        "start_command": None,
        "start_dir": None,
        "app_url": None,
        "port": None,
        "frontend_url": None,
        "frontend_port": None,
        "credentials": None,
        "docker_image": None,
        "docker_compose_file": None,
        "run_notes": None,
    }
    by_path = {}
    for entry in files or []:
        if isinstance(entry, dict) and entry.get("path"):
            by_path[_norm(entry["path"])] = str(entry.get("content") or "")
    preferred = [_norm(path) for path in (preferred_paths or []) if _norm(path)]

    def _changed_under(folder: str) -> bool:
        if not preferred:
            return False
        if not folder:
            return False
        return any(_under(path, folder) for path in preferred)

    def _dockerfile():
        """Pick the primary Dockerfile when a monorepo has several."""
        candidates = [
            (path, content)
            for path, content in by_path.items()
            if path == "Dockerfile" or path.endswith("/Dockerfile")
        ]
        if not candidates:
            return None, None

        def _score(item):
            path, _content = item
            folder = _dir_of(path)
            changed = _changed_under(folder)
            if changed:
                base = 0 if not _frontend_dir(folder) else 1
            elif folder in backend_dirs and folder not in frontend_dirs:
                base = 2
            elif folder == "":
                base = 3
            elif folder in frontend_dirs:
                base = 4
            else:
                base = 5
            return (base, 0 if changed else 1, folder.count("/"), path)

        path, content = min(candidates, key=_score)
        return content, _dir_of(path)

    def _compose():
        for path, content in by_path.items():
            low = path.lower()
            if low.endswith("docker-compose.yml") or low.endswith(
                "docker-compose.yaml"
            ):
                return path, content
        return None, None

    compose_path, compose_content = _compose()
    compose = {}
    if compose_content:
        try:
            import yaml

            compose = yaml.safe_load(compose_content) or {}
        except Exception:
            compose = {}
    services = compose.get("services") if isinstance(compose, dict) else {}
    if not isinstance(services, dict):
        services = {}

    frontend_dirs = set()
    backend_dirs = set()
    for name, svc in services.items():
        if not isinstance(svc, dict):
            continue
        build = svc.get("build")
        ctx = build.get("context") if isinstance(build, dict) else build
        folder = _norm(ctx).strip("/") if isinstance(ctx, str) else ""
        if not folder or folder == ".":
            continue
        if _looks_frontend(name, svc):
            frontend_dirs.add(folder)
        else:
            backend_dirs.add(folder)

    port = None
    start_command = None
    start_dir = None
    dockerfile, start_dir = _dockerfile()
    if dockerfile:
        match = re.search(r"(?m)^\s*EXPOSE\s+(\d+)", dockerfile)
        if match:
            try:
                port = int(match.group(1))
            except ValueError:
                pass
        # A HEALTHCHECK also has a nested CMD line; only the last bare CMD
        # is the container's start command (Docker uses the final one).
        matches = re.findall(r"(?m)^\s*CMD\s+(.+)$", dockerfile)
        if matches:
            start_command = matches[-1].strip()
    info["start_dir"] = start_dir

    docker_image = None
    frontend_port = None
    if compose_content:
        info["docker_compose_file"] = compose_path
        compose_host_seen = False
        for _name, svc in services.items():
            if not isinstance(svc, dict):
                continue
            for mapping in svc.get("ports") or []:
                # Host side is what the user opens and what can
                # collide: "HOST:CONTAINER" binds HOST, a bare port
                # (or int) only names the container side.
                host, target = _pub_ports(mapping)
                if _looks_frontend(_name, svc):
                    if host and frontend_port is None:
                        frontend_port = host
                    continue
                if host:
                    # A compose host binding is deployment truth: it
                    # overwrites a Dockerfile EXPOSE, first one wins
                    # across services — but keep scanning, a frontend
                    # service may still follow.
                    if not compose_host_seen:
                        port = host
                        compose_host_seen = True
                    break
                if target and port is None:
                    # Expose-only form: no host binding to collide
                    # with, but still the port the app serves.
                    port = target
            if isinstance(svc.get("image"), str) and svc["image"].strip():
                docker_image = svc["image"].strip()

    package_entries = [
        (path, content)
        for path, content in by_path.items()
        if path == "package.json" or path.endswith("/package.json")
    ]
    if package_entries:

        def _pkg_score(item):
            path, _content = item
            folder = _dir_of(path)
            changed = _changed_under(folder)
            return (0 if changed else 1, folder.count("/"), path)

        _pkg_path, pkg_content = min(package_entries, key=_pkg_score)
        try:
            pkg = json.loads(pkg_content)
            scripts = pkg.get("scripts") or {}
            if isinstance(scripts, dict) and scripts.get("start"):
                start_command = start_command or str(scripts["start"])
        except (ValueError, AttributeError):
            pass

    # Detect a hard-coded listener port from source BEFORE inferring a
    # default, so a generated app that calls app.run(port=8000) reports
    # 8000 rather than the framework default (5000/8000). This keeps the
    # port-allocation rewrite honest.
    if port is None:
        for content in by_path.values():
            m = re.search(r"\.run\([^)]*?\bport\s*=\s*(\d+)", content, re.S)
            if m:
                try:
                    port = int(m.group(1))
                    break
                except ValueError:
                    pass
            m = re.search(r"\.listen\(\s*(\d+)", content)
            if m:
                try:
                    port = int(m.group(1))
                    break
                except ValueError:
                    pass
            m = re.search(r"\bPORT\s*=\s*(\d+)", content)
            if m:
                try:
                    port = int(m.group(1))
                    break
                except ValueError:
                    pass

    # No Dockerfile CMD / package.json start script: infer from the app's
    # own entry file so a plain Flask/FastAPI app still gets a runbook.
    inferred_note = None
    if not start_command:
        start_command, inferred_port, inferred_note = _infer_entry_command(
            by_path,
            port,
            preferred_paths=preferred,
            start_dir=start_dir,
        )
        if inferred_port:
            port = inferred_port

    credentials = None
    for path, content in by_path.items():
        low = path.lower()
        if low.endswith(".env.example") or low.endswith(".env.sample"):
            found = {}
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, _val = line.partition("=")
                key = key.strip()
                if key and (
                    "password" in key.lower()
                    or "secret" in key.lower()
                    or "user" in key.lower()
                    or "login" in key.lower()
                ):
                    found[key] = "<set via environment>"
            if found:
                credentials = found
                break

    # Native (non-pip) dependencies cannot be installed into the venv by
    # the supervised runner, so name them up front instead of failing at
    # first use (e.g. pytesseract needs the tesseract binary).
    system_deps = set()
    for content in by_path.values():
        low = content.lower()
        if "pytesseract" in low:
            system_deps.add("tesseract-ocr (for pytesseract)")
        if "psycopg2" in low or "psycopg[binary]" in low or "psycopg " in low:
            system_deps.add("libpq-dev (for psycopg/psycopg2)")
        if "mysqlclient" in low:
            system_deps.add("default-libmysqlclient-dev (for mysqlclient)")
        if "python-ldap" in low or "ldap3" in low:
            system_deps.add("libldap2-dev (for LDAP support)")
        if "lxml" in low or "weasyprint" in low:
            system_deps.add("libxml2-dev libxslt1-dev (for lxml/weasyprint)")
        if "cryptography" in low or "pyopenssl" in low:
            system_deps.add("libssl-dev libffi-dev (for cryptography)")
        if "pillow" in low or "pil" in low:
            system_deps.add("zlib1g-dev libjpeg-dev libpng-dev (for Pillow)")
        if "opencv" in low or "cv2" in low:
            system_deps.add("libgl1 libsm6 (for OpenCV)")

    # Detect a hard-coded listener port from source even when there is
    # no Dockerfile EXPOSE or compose mapping (common in generated apps).
    if port is None:
        for content in by_path.values():
            m = re.search(r"\.run\([^)]*?\bport\s*=\s*(\d+)", content, re.S)
            if m:
                try:
                    port = int(m.group(1))
                    break
                except ValueError:
                    pass
            m = re.search(r"\.listen\(\s*(\d+)", content)
            if m:
                try:
                    port = int(m.group(1))
                    break
                except ValueError:
                    pass
            m = re.search(r"\bPORT\s*=\s*(\d+)", content)
            if m:
                try:
                    port = int(m.group(1))
                    break
                except ValueError:
                    pass
    notes = []
    if inferred_note:
        notes.append(inferred_note)
    if system_deps:
        notes.append(
            "System packages required on the host: " + ", ".join(sorted(system_deps))
        )
    # No "Start command:" note: the How-to-run panel already shows it as a
    # copyable Run row, and models restate it here verbatim (noise).
    # Browser step goes last: open the app only after starting it.
    app_url = None
    if credentials:
        notes.append("Default credentials: " + ", ".join(sorted(credentials)))
    if docker_image:
        notes.append(f"Docker image: {docker_image}")
    if compose_path:
        notes.append(
            f"Or run everything with Docker Compose using {compose_path} (install docker-compose-v2 first if `docker compose` is missing; create /var/log/opencode and copy .env.example to .env if needed)."
        )
    if port:
        app_url = f"http://{_host_network_ip()}:{port}"
    frontend_url = None
    if frontend_port:
        frontend_url = f"http://{_host_network_ip()}:{frontend_port}"
        notes.append(f"Open {frontend_url} in your browser once it is running.")
    elif app_url:
        notes.append(f"Open {app_url} in your browser once it is running.")
    info.update(
        {
            "start_command": start_command,
            "app_url": app_url,
            "port": port,
            "frontend_url": frontend_url,
            "frontend_port": frontend_port,
            "credentials": credentials,
            "docker_image": docker_image,
            "run_notes": "\n".join(notes) if notes else None,
        }
    )
    return info


def _pretty_cmd(value) -> str:
    """Model commands into runnable host commands.

    Joins real and stringified lists ('["python", "app.py"]' →
    'python app.py') and rewrites the bare `python` interpreter to
    `python3` (host shells lack `python`; venvs provide `python3`).
    """
    import json as _json
    import re as _re

    if isinstance(value, (list, tuple)):
        text = " ".join(str(v) for v in value)
    elif isinstance(value, str) and value.strip().startswith("["):
        try:
            parsed = _json.loads(value)
            text = (
                " ".join(str(v) for v in parsed) if isinstance(parsed, list) else value
            )
        except ValueError:
            text = value
    else:
        text = value if isinstance(value, str) else ""
    return _re.sub(r"(^|&&\s*|;\s*|\|\s*|\)\s*)python(?=\s|$)", r"\1python3", text)


def _derive_runbook(
    files: list,
    start_command,
    host_root: str,
    container_root: str | None = None,
    start_dir: str | None = None,
) -> dict | None:
    """Derive verified paste-and-run commands from a build manifest.

    Resolves the entry point (``python -m pkg.mod``, ``python app.py``,
    ``uvicorn pkg.mod:app``) against the manifest's file list to find the
    directory the command must run in, and pairs it with a venv setup step
    when a pip requirements file ships (bare hosts refuse system pip via
    PEP 668). ``start_dir`` is the primary service folder (for example
    ``backend`` when the chosen Dockerfile is ``backend/Dockerfile``); it
    lets a bare ``python app.py`` resolve to ``backend/src/app.py`` and
    rewrite the command to ``python src/app.py``. Returns
    ``{"setup", "setup_fallback", "run", "workdir", "command"}`` with
    absolute host paths (the fallback installs the same packages unpinned,
    for newer Pythons the old pins no longer build on), plus
    container-native ``run_argv``/``setup_argv``/``pip_argv`` for the
    supervised runner when ``container_root`` is given (host paths do not
    exist inside worker containers). Returns None when the command cannot
    be resolved (callers fall back to the raw fields).
    """
    import os as _os
    import re as _re

    if not host_root or not start_command:
        return None
    cmd = _pretty_cmd(start_command).strip()
    if not cmd:
        return None
    paths = [
        str(e.get("path") or "").replace("\\", "/").lstrip("./")
        for e in files or []
        if isinstance(e, dict) and e.get("path")
    ]
    if not paths:
        return None
    base_dir = str(start_dir or "").replace("\\", "/")
    while base_dir.startswith("./"):
        base_dir = base_dir[2:]
    base_dir = base_dir.strip("/")

    def _resolve_script(rel: str) -> tuple[str, str] | None:
        """(appdir, command-relative script) for a Python script token.

        ``python app.py`` with a ``backend/Dockerfile`` and only
        ``backend/src/app.py`` in the tree resolves to appdir ``backend``
        and rewritten script ``src/app.py``. Running the original from the
        repo root (or from ``backend``) would fail.
        """
        script = rel.replace("\\", "/")
        while script.startswith("./"):
            script = script[2:]
        pool = paths
        if base_dir:
            pool = [
                path
                for path in paths
                if path == base_dir or path.startswith(base_dir + "/")
            ]
        hits = [path for path in pool if path == script or path.endswith("/" + script)]
        if not hits and base_dir:
            hits = [
                path for path in paths if path == script or path.endswith("/" + script)
            ]
        if not hits:
            return None
        hit = sorted(set(hits), key=lambda path: (path.count("/"), path))[0]
        if base_dir and hit.startswith(base_dir + "/"):
            return base_dir, hit[len(base_dir) + 1 :]
        if hit.endswith("/" + script):
            return hit[: -len(script)].rstrip("/"), script
        return "", script

    def _resolve_module(mod: str) -> str | None:
        mod_path = mod.replace(".", "/")
        for cand in (mod_path + ".py", mod_path + "/__init__.py"):
            hits = [path for path in paths if path == cand or path.endswith("/" + cand)]
            if base_dir:
                under = [
                    path
                    for path in hits
                    if path == base_dir or path.startswith(base_dir + "/")
                ]
                if under:
                    hits = under
            if hits:
                hit = sorted(set(hits), key=lambda path: (path.count("/"), path))[0]
                return hit[: len(hit) - len(cand)].rstrip("/")
        return None

    _RUNNERS = {"uvicorn", "gunicorn", "hypercorn", "daphne"}

    def _runner_dir(text) -> str | None:
        """Find the ``module:app`` argument after any runner flags.

        ``gunicorn --bind 0.0.0.0:8000 ... app:app`` puts a dotted host:port
        before the real app target, so take the first candidate that names
        a file in the manifest rather than the first ``word:word``.
        """
        for candidate in _re.finditer(r"([\w.]+):[\w.]+", text or ""):
            hit = _resolve_module(candidate.group(1))
            if hit is not None:
                return hit
        return None

    def _resolve_dir() -> str | None:
        nonlocal cmd
        # `python[3] -m dotted.mod ...` or `python[3] script.py ...`
        m = _re.search(
            r"(?:^|&&\s*|;\s*)\s*python3?\s+(?:-m\s+([\w.]+)|([\w./-]+\.pyw?))(?:\s|$)",
            cmd,
        )
        if m and m.group(1):
            mod = m.group(1)
            if mod.split(".")[0] in _RUNNERS:
                # Runner invocation (`python -m uvicorn pkg.mod:app`):
                # the app is the `dotted:app` argument, not the runner.
                return _runner_dir(cmd)
            if mod.split(".")[0] == "flask":
                # `python -m flask --app pkg.mod run`: --app names the app.
                appm = _re.search(r"--app[\s=]+([\w.]+)", cmd)
                if not appm:
                    return ""  # CLI discovery from the workdir
                return _resolve_module(appm.group(1).split(":")[0])
            return _resolve_module(mod)
        if m and m.group(2):
            hit = _resolve_script(m.group(2))
            if hit is None:
                return None
            appdir, rel_from = hit
            script = m.group(2)
            if rel_from != script.lstrip("./"):
                start, end = m.span(2)
                cmd = cmd[:start] + rel_from + cmd[end:]
            # Run from the manifest-relative script path's parent; the
            # command keeps only the path relative to that parent (never
            # cd into the script's own dir: that would double the path).
            return appdir
        # `uvicorn|gunicorn dotted.mod:app ...`, flags allowed before the app.
        m = _re.search(
            r"(?:^|&&\s*|;\s*)\s*(?:uvicorn|gunicorn|hypercorn|daphne)\b([^&;]*)",
            cmd,
        )
        if m:
            return _runner_dir(m.group(1))
        # `flask --app pkg.mod run ...` (bare CLI, no python prefix)
        m = _re.search(r"(?:^|&&\s*|;\s*)\s*flask\b[^&;]*--app[\s=]+([\w.]+)", cmd)
        if m:
            return _resolve_module(m.group(1).split(":")[0])
        # `npm start`, `npm run dev`, `node server.js`, `npx ...`
        m = _re.search(r"(?:^|&&\s*|;\s*)\s*(?:npm|npx|yarn|pnpm|node)\b", cmd)
        if m:
            pkg_pool = [
                p for p in paths if p == "package.json" or p.endswith("/package.json")
            ]
            if base_dir:
                under = [
                    p
                    for p in pkg_pool
                    if p == base_dir + "/package.json" or p.startswith(base_dir + "/")
                ]
                if under:
                    pkg_pool = under
            pkg = (
                sorted(set(pkg_pool), key=lambda p: (p.count("/"), p))[0]
                if pkg_pool
                else None
            )
            if pkg is None:
                return None
            return pkg[: -len("package.json")].rstrip("/")
        return None

    appdir = _resolve_dir()
    if appdir is None:
        return None
    workdir = (
        host_root.rstrip("/") if not appdir else host_root.rstrip("/") + "/" + appdir
    )
    quoted = f'cd "{workdir}"'
    pretty = cmd
    import shlex as _shlex

    try:
        args = _shlex.split(pretty, posix=True)
    except ValueError:
        args = None
    if args:
        # `cd /dir && cmd` (models sometimes paste their own cd): workdir
        # already covers the cd, so drop it and keep the real head.
        while len(args) > 2 and args[0] == "cd" and "&&" in args:
            args = args[args.index("&&") + 1 :]
    head = _os.path.basename(args[0]) if args else ""
    node_cmd = head in ("npm", "npx", "yarn", "pnpm", "node")
    # Display commands are pasted on the reader's own machine, while the
    # supervised process owns `.venv` inside its container. A separate
    # folder for the pasteable setup means running it can never replace
    # the supervised interpreter with one the container cannot execute
    # (seen live: a host-built 3.14 venv broke the next Start).
    dvenv = ".venv-local"
    setup = None
    req = next(
        (p for p in paths if _re.search(r"(^|/)requirements[^/]*\.txt$", p or "")),
        None,
    )
    if req is not None:
        rel = _os.path.relpath(req, appdir) if appdir else req
        resolved = (
            _os.path.normpath(_os.path.join(appdir, rel))
            if appdir
            else _os.path.normpath(rel)
        )
        # A nested workdir such as backend/src may sit beside the
        # requirements file (rel ../requirements.txt); allow that as long
        # as the normalized path stays inside the build root.
        if not resolved.startswith("..") and not _os.path.isabs(resolved):
            setup = (
                f"{quoted} && rm -rf {dvenv} && python3 -m venv {dvenv} "
                f"&& . {dvenv}/bin/activate && {dvenv}/bin/pip install -r {rel}"
            )
    use_venv = setup is not None
    # Node projects install their own way; only when no venv already owns
    # the setup step (a manifest with both is a Python app with a frontend).
    npm_pkg = next(
        (p for p in paths if p == "package.json" or p.endswith("/package.json")),
        None,
    )
    npm_setup = None
    if node_cmd and npm_pkg is not None and not use_venv:
        npm_setup = f"{quoted} && npm install"
        setup = npm_setup
    # Supervised processes run inside worker containers, where host paths
    # do not exist: argv uses the container twin when one was provided.
    # Display strings above stay host-native for pasting.
    cworkdir = None
    if container_root:
        cworkdir = (
            container_root.rstrip("/")
            if not appdir
            else container_root.rstrip("/") + "/" + appdir
        )
    eworkdir = cworkdir or workdir
    evenv = eworkdir.rstrip("/") + "/.venv" if use_venv else ""
    # Bare interpreter for the setup-less case: the runner resolves it
    # against its own PATH (absolute host paths do not exist there).
    epython = evenv + "/bin/python" if use_venv else "python3"
    venv_dir = workdir.rstrip("/") + "/.venv" if use_venv else ""
    venv_python = venv_dir + "/bin/python" if use_venv else "/usr/bin/python3"
    run_argv = None
    if args:
        rest = args[1:]
        if _re.match(r"^python3?(\.\d+)?$", head):
            run_argv = [epython] + rest
        elif head in _RUNNERS:
            # Bare runner (`uvicorn pkg.mod:app`): invoke it as a module so
            # the venv (or the runner's PATH) interpreter resolves it.
            run_argv = [epython, "-m", head] + rest
        elif head == "flask":
            run_argv = [epython, "-m", "flask"] + rest
        elif head in ("npm", "npx", "yarn", "pnpm", "node"):
            run_argv = [head] + rest
    setup_argv = (
        ["python3", "-m", "venv", "--upgrade", evenv]
        if use_venv
        else (["npm", "install"] if npm_setup else [])
    )
    pip_argv = [evenv + "/bin/pip", "install", "-r", rel] if use_venv else []
    # Fallback for newer Pythons the pinned versions no longer build on:
    # same packages, unpinned. Parsed from the requirements content so it
    # can never name something the manifest does not use.
    setup_fallback = None
    pip_fallback_argv = []
    if use_venv:
        req_entry = next(
            (
                e
                for e in files or []
                if isinstance(e, dict) and str(e.get("path") or "") == req
            ),
            None,
        )
        names = []
        for line in str((req_entry or {}).get("content") or "").splitlines():
            line = line.split("#", 1)[0].split(";", 1)[0].strip()
            m = _re.match(r"^([A-Za-z0-9_.-]+(?:\[[^\]]*\])?)", line)
            if m and not line.startswith("-"):
                names.append(m.group(1))
        if names:
            # Unpinned installs work on newer Pythons where the old pins
            # no longer build (e.g. pydantic-core on 3.14). Make that the
            # primary, paste-and-run command; keep the pinned one as the
            # reproducibility fallback.
            pinned = setup
            setup = (
                f"{quoted} && rm -rf {dvenv} && python3 -m venv {dvenv} "
                f"&& . {dvenv}/bin/activate && {dvenv}/bin/pip install "
                + " ".join(names)
            )
            setup_fallback = pinned
            pip_fallback_argv = [evenv + "/bin/pip", "install"] + names
    if run_argv is None:
        # No safe argv (non-python command without installable requirements):
        # the raw fields stay the only source.
        return None
    if use_venv:
        # Display form stays pasteable; argv form is resolved by the
        # runner inside its own container (absolute host python paths do
        # not exist there).
        run = f"{quoted} && . {dvenv}/bin/activate && {cmd}"
    else:
        run = f"{quoted} && {cmd}"
    return {
        "setup": setup,
        "setup_fallback": setup_fallback,
        "run": run,
        "command": cmd,
        "workdir": workdir,
        "workdir_container": cworkdir,
        "venv_dir": venv_dir,
        "setup_argv": setup_argv,
        "pip_argv": pip_argv,
        "pip_fallback_argv": pip_fallback_argv,
        "run_argv": run_argv,
    }
