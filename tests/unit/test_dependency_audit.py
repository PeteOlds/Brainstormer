"""Dependency audit gate: only new advisories fail."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import check_dependencies as audit  # noqa: E402


def _report(ids):
    return {
        "dependencies": [
            {"name": "pkg", "version": "1.0", "vulns": [{"id": i} for i in ids]}
        ]
    }


def _setup(tmp_path, monkeypatch, ids, baseline):
    baseline_file = tmp_path / "baseline.txt"
    baseline_file.write_text("\n".join(baseline) + "\n")
    monkeypatch.setattr(audit, "BASELINE", baseline_file)
    monkeypatch.setattr(
        audit.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            stdout=json.dumps(_report(ids)), stderr="", returncode=1
        ),
    )


def test_known_advisories_pass(tmp_path, monkeypatch, capsys):
    _setup(tmp_path, monkeypatch, ["CVE-1", "CVE-2"], ["CVE-1", "CVE-2"])
    assert audit.main() == 0
    assert "0 new" in capsys.readouterr().out


def test_new_advisory_fails(tmp_path, monkeypatch, capsys):
    _setup(tmp_path, monkeypatch, ["CVE-1", "CVE-NEW"], ["CVE-1"])
    assert audit.main() == 1
    assert "CVE-NEW" in capsys.readouterr().out


def test_empty_baseline_fails_on_everything(tmp_path, monkeypatch, capsys):
    _setup(tmp_path, monkeypatch, ["CVE-1"], [])
    assert audit.main() == 1
