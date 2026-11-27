"""Dependency audit gate with a reviewed baseline.

pip-audit reports every known advisory for the pinned lockfile. The baseline
file records advisories already reviewed and accepted for this release; the
gate fails only on *new* advisories, so a newly published CVE cannot ship
silently. Shrinking the baseline is tracked as RM-070.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/dependency-audit-baseline.txt"


def load_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return {
        line.strip()
        for line in BASELINE.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def main() -> int:
    try:
        result = subprocess.run(
            ["pip-audit", "-r", "requirements.lock", "--format", "json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        print("pip-audit is not installed; add it to requirements-dev.txt")
        return 1

    if not result.stdout.strip():
        print("Dependency audit produced no output:", result.stderr[:500])
        return 1
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("Dependency audit output was not JSON:", result.stdout[:500])
        return 1

    ids = {
        str(vuln.get("id") or "")
        for dep in report.get("dependencies", [])
        for vuln in dep.get("vulns", [])
        if vuln.get("id")
    }
    baseline = load_baseline()
    new = sorted(ids - baseline)
    stale = sorted(baseline - ids)
    if new:
        print("New dependency advisories (not in baseline):")
        for advisory in new:
            print(" -", advisory)
        print("Triage them and update docs/dependency-audit-baseline.txt.")
        return 1
    if stale:
        print(f"Note: {len(stale)} baseline advisories no longer reported (can be removed).")
    print(f"Dependency audit OK: {len(ids)} known advisories, 0 new.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
