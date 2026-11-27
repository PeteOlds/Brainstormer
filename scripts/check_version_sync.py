"""Guardrail: the Flutter footer version must match the backend VERSION.

The two values are independent constants. When they drift, a hard refresh
still shows the old build number even though the backend has shipped a new
release, which is confusing during support and verification.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
TOKENS_FILE = ROOT / "flutter/lib/core/theme/tokens.dart"
CONSTANT_RE = re.compile(r"const\s+String\s+kAppVersion\s*=\s*'([^']+)'")


def read_versions():
    backend = VERSION_FILE.read_text().strip()
    match = CONSTANT_RE.search(TOKENS_FILE.read_text())
    flutter = match.group(1) if match else None
    return backend, flutter


def main() -> int:
    backend, flutter = read_versions()
    if flutter is None:
        print("kAppVersion not found in flutter/lib/core/theme/tokens.dart")
        return 1
    if backend != flutter:
        print(
            f"Version mismatch: VERSION={backend}, "
            f"kAppVersion={flutter}. Bump both together."
        )
        return 1
    print(f"Version sync OK: v{backend}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
