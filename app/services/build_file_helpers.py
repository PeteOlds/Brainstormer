"""File-level helpers for generated build manifests.

Moved out of build_runtime.py to keep modules focused. Re-exported there
so existing callers keep working.
"""

import ast
import sys

_IMPORT_TO_PACKAGE = {
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "bs4": "beautifulsoup4",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "dotenv": "python-dotenv",
    "jwt": "PyJWT",
    "fitz": "PyMuPDF",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "serial": "pyserial",
    "usb": "pyusb",
    "magic": "python-magic",
    "dateutil": "python-dateutil",
    "exifread": "exifread",
    "pytesseract": "pytesseract",
    "flask": "Flask",
    "werkzeug": "werkzeug",
    "jinja2": "Jinja2",
    "sqlalchemy": "SQLAlchemy",
    "alembic": "alembic",
    "celery": "celery",
    "redis": "redis",
    "requests": "requests",
    "httpx": "httpx",
    "numpy": "numpy",
    "pandas": "pandas",
    "matplotlib": "matplotlib",
    "scipy": "scipy",
    "bs4": "beautifulsoup4",
}


def _merge_files(base: list, overlay: list) -> list:
    """Repo-context files merged with a build manifest (manifest wins).

    A build preview is usually incremental, so the runtime/runbook sees
    the files already on disk plus the ones this build changes. Insertion
    order follows the base so preference tie-breaks stay stable.
    """
    by_path = {}
    for entry in base or []:
        if isinstance(entry, dict) and entry.get("path"):
            by_path[str(entry["path"])] = entry
    for entry in overlay or []:
        if isinstance(entry, dict) and entry.get("path"):
            by_path[str(entry["path"])] = entry
    return list(by_path.values())


def _inject_root_route(files: list) -> None:
    """Add a simple root route to Flask/FastAPI apps that lack one.

    Non-technical users expect "Open app" to show something. If the app
    has no '/' route, append a minimal one so they don't see a 404.
    """
    import re

    for entry in files or []:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "")
        content = str(entry.get("content") or "")
        if not (path.endswith(".py")):
            continue
        if "Flask(" not in content and "FastAPI(" not in content:
            continue
        if re.search(r"@\w+\.route\(\s*['\"]/?['\"]", content) or re.search(
            r"@\w+\.(get|post)\(\s*['\"]/?['\"]", content, re.I
        ):
            continue
        # Determine the app variable name.
        app_var = "app"
        m = re.search(r"^(\w+)\s*=\s*(?:Flask|FastAPI)\(", content, re.M)
        if m:
            app_var = m.group(1)
        if "Flask(" in content:
            snippet = (
                "\n\nos.makedirs('uploads', exist_ok=True)\n"
                "\n@app.route('/')\n"
                "def _brainstormer_home():\n"
                "    return ('<h1>App is running</h1>'\n"
                "            '<p>Your app is live. Upload an image below:</p>'\n"
                "            '<form action=\"/upload\" method=\"POST\" enctype=\"multipart/form-data\">'\n"
                "            '<input type=\"file\" name=\"image\" accept=\"image/*\">'\n"
                "            '<button type=\"submit\">Upload</button>'\n"
                "            '</form>')\n"
            )
            snippet = snippet.replace("@app.route", f"@{app_var}.route")
        else:
            snippet = (
                "\n\n@{av}.get('/')\n"
                "def _brainstormer_home():\n"
                "    return ('<h1>App is running</h1>'\n"
                "            '<p>Your app is live. Upload an image below:</p>'\n"
                "            '<form action=\"/upload\" method=\"POST\" enctype=\"multipart/form-data\">'\n"
                "            '<input type=\"file\" name=\"image\" accept=\"image/*\">'\n"
                "            '<button type=\"submit\">Upload</button>'\n"
                "            '</form>')\n"
            ).format(av=app_var)
        entry["content"] = content.rstrip() + "\n" + snippet


def _ensure_requirements(files: list) -> None:
    """Make sure requirements.txt covers every third-party import.

    Scans Python files for ``import`` / ``from … import`` statements,
    filters out stdlib modules, and appends any missing packages to the
    requirements.txt entry (creating one if needed). This prevents the
    common 'ModuleNotFoundError' at startup for non-technical users.
    """
    import ast
    import sys

    stdlib = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else set()

    imported = set()
    for entry in files or []:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "")
        if not path.endswith(".py"):
            continue
        content = str(entry.get("content") or "")
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    imported.add(node.module.split(".")[0])

    # Filter to third-party (not stdlib, not local).
    local_modules = set()
    for entry in files or []:
        if isinstance(entry, dict):
            p = str(entry.get("path") or "")
            if p.endswith(".py"):
                local_modules.add(p.rsplit("/", 1)[-1].replace(".py", ""))
                if "/" in p:
                    local_modules.add(p.split("/")[0])
    third_party = imported - stdlib - local_modules - {"os", "sys", "json", "re", "math", "datetime", "typing", "pathlib", "collections", "itertools", "functools", "io", "base64", "hashlib", "uuid", "time", "random", "string", "enum", "dataclasses", "abc", "contextlib", "logging", "warnings", "traceback", "inspect", "textwrap", "shutil", "tempfile", "subprocess", "socket", "http", "urllib", "html", "xml", "csv", "sqlite3", "argparse", "configparser", "secrets", "hmac", "struct", "array", "copy", "pprint", "textwrap", "types", "weakref", "gc", "atexit", "signal", "threading", "multiprocessing", "concurrent", "asyncio", "queue", "heapq", "bisect", "cmath", "decimal", "fractions", "statistics", "numbers", "operator", "pickle", "shelve", "dbm", "gzip", "bz2", "lzma", "zipfile", "tarfile", "csv", "configparser", "netrc", "xdrlib", "plistlib", "hashlib", "hmac", "secrets", "os", "sys"}

    # Find or create requirements.txt entry.
    req_entry = None
    for entry in files or []:
        if isinstance(entry, dict) and str(entry.get("path") or "").rsplit("/", 1)[-1] == "requirements.txt":
            req_entry = entry
            break

    if not third_party:
        return

    existing = set()
    if req_entry is not None:
        for line in str(req_entry.get("content") or "").splitlines():
            line = line.split("#", 1)[0].strip()
            if line and not line.startswith("-"):
                name = line.split("==", 1)[0].split(">=", 1)[0].split("<=", 1)[0].split("!=", 1)[0].split("~=", 1)[0].strip().lower()
                existing.add(name)

    missing = []
    for mod in sorted(third_party):
        pkg = _IMPORT_TO_PACKAGE.get(mod, mod)
        if pkg.lower() not in existing and mod.lower() not in existing:
            missing.append(pkg)

    if not missing:
        return

    new_lines = "\n".join(missing)
    if req_entry is not None:
        content = str(req_entry.get("content") or "").rstrip()
        req_entry["content"] = content + "\n" + new_lines + "\n"
    else:
        files.append({"path": "requirements.txt", "content": new_lines + "\n"})
