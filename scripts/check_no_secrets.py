"""Guardrail: no secrets committed. Scans tracked text files for
high-confidence secret patterns (keys, tokens, private key blocks).
Allowlist: .env.example (dummy values), tests, docs examples.
"""

import re
import subprocess
import sys

PATTERNS = {
    # Separator matches both `.env` (`KEY=value`) and YAML (`KEY: value`).
    # The old regexes only matched `=`, so a key hardcoded in a workflow
    # (e.g. `FERNET_KEY: <key>`) slipped through — the GitGuardian finding.
    "fernet_key": re.compile(r"FERNET_KEY\s*[:=]\s*['\"]?[A-Za-z0-9_+/=-]{40,}"),
    "jwt_secret": re.compile(
        r"JWT_SECRET_KEY\s*[:=]\s*['\"]?[A-Za-z0-9_.+/-]{24,}"
    ),
    "secret_key": re.compile(
        r"(?<!JWT_)(?<!FERNET_)SECRET_KEY\s*[:=]\s*['\"]?[A-Za-z0-9_.+/-]{24,}"
    ),
    "openai_key": re.compile(
        r"sk-(live|test|proj)-[A-Za-z0-9]{10,}|sk-[A-Za-z0-9]{20,}"
    ),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "slack_app_token": re.compile(r"xapp-[A-Za-z0-9-]{10,}"),
    "github_token": re.compile(
        r"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}"
    ),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
}

SKIP_DIRS = ("venv/", ".git/", "__pycache__/", ".mypy_cache/", ".pytest_cache/")
SKIP_FILES = {".env.example", "CHANGELOG.md"}


def tracked_files():
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    )
    return [f for f in out.stdout.splitlines() if f.strip()]


failures = []
for path in tracked_files():
    if path.startswith(SKIP_DIRS) or path.rsplit("/", 1)[-1] in SKIP_FILES:
        continue
    try:
        text = open(path, encoding="utf-8", errors="strict").read()
    except (OSError, ValueError):
        continue  # binaries, fixtures with odd encodings
    for name, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            # Dummy/placeholder values are fine.
            snippet = match.group(0)
            if any(
                mark in snippet
                for mark in (
                    "your-",
                    "example",
                    "dummy",
                    "xxx",
                    "test-secret",
                    "sk-test",
                    "change-in-production",
                    "dev-secret",
                    "dev-jwt",
                    "dev-fernet",
                )
            ):
                continue
            line = text.count("\n", 0, match.start()) + 1
            failures.append(f"{path}:{line}: possible {name}")

if failures:
    print("Possible committed secrets:")
    print("\n".join(failures))
    sys.exit(1)
print("OK: no secret patterns in tracked files.")
