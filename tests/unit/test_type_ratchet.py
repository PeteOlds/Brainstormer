"""Type-check ratchet: only new errors fail."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import check_types as ratchet  # noqa: E402


def _entry(path, code, message):
    return json.dumps(
        {"file": path, "code": code, "message": message, "severity": "error"}
    )


def _setup(tmp_path, monkeypatch, entries, baseline):
    baseline_file = tmp_path / "baseline.txt"
    baseline_file.write_text("\n".join(baseline) + "\n")
    monkeypatch.setattr(ratchet, "BASELINE", baseline_file)
    monkeypatch.setattr(
        ratchet.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            stdout="\n".join(entries), stderr="", returncode=1
        ),
    )


def test_known_errors_pass(tmp_path, monkeypatch, capsys):
    sig = "app/a.py|no-untyped-def"
    _setup(
        tmp_path,
        monkeypatch,
        [_entry("app/a.py", "no-untyped-def", "missing annotation")],
        [f"1\t{sig}"],
    )
    assert ratchet.main() == 0
    assert "0 new" in capsys.readouterr().out


def test_new_error_fails(tmp_path, monkeypatch, capsys):
    sig = "app/a.py|no-untyped-def"
    _setup(
        tmp_path,
        monkeypatch,
        [
            _entry("app/a.py", "no-untyped-def", "missing annotation"),
            _entry("app/b.py", "assignment", "bad type"),
        ],
        [f"1\t{sig}"],
    )
    assert ratchet.main() == 1
    assert "app/b.py" in capsys.readouterr().out
