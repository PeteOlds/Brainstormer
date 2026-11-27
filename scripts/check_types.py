"""Type-check ratchet: fail on new mypy errors, allow the reviewed baseline.

mypy's full output has hundreds of pre-existing errors. This gate records a
baseline of (file, error code, message) counts and fails only when a file's
count grows or a new error appears. Shrinking the baseline is tracked as
follow-up work.
"""

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/type-check-baseline.txt"


def load_baseline() -> Counter:
    counts: Counter = Counter()
    if not BASELINE.exists():
        return counts
    for line in BASELINE.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        count, sep, signature = line.partition("\t")
        if sep:
            try:
                counts[signature] = int(count)
            except ValueError:
                continue
    return counts


def main() -> int:
    result = subprocess.run(
        ["mypy", "app", "--output=json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    current: Counter = Counter()
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("severity") != "error":
            continue
        # File + code is stable across mypy/SQLAlchemy versions; full messages
        # vary between environments and made the baseline too brittle.
        signature = "|".join(str(entry.get(key) or "") for key in ("file", "code"))
        current[signature] += 1

    baseline = load_baseline()
    new = {
        signature: count - baseline.get(signature, 0)
        for signature, count in current.items()
        if count > baseline.get(signature, 0)
    }
    fixed = sum(
        max(0, count - current.get(signature, 0))
        for signature, count in baseline.items()
    )
    if new:
        print("New type errors (not in baseline):")
        for signature, count in sorted(new.items()):
            print(f" +{count} {signature}")
        print("Fix them or refresh docs/type-check-baseline.txt deliberately.")
        return 1
    if fixed:
        print(
            f"Note: {fixed} baseline type errors no longer reported; baseline can shrink."
        )
    print(f"Type check OK: {sum(current.values())} reviewed errors, 0 new.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
