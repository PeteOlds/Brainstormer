"""Version sync guardrail tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import check_version_sync as sync  # noqa: E402


def test_live_versions_match():
    backend, flutter = sync.read_versions()
    assert backend == flutter
    assert sync.main() == 0


def test_mismatch_is_detected(tmp_path, monkeypatch, capsys):
    version_file = tmp_path / "VERSION"
    version_file.write_text("1.2.3\n")
    tokens = tmp_path / "tokens.dart"
    tokens.write_text("const String kAppVersion = '1.2.2';\n")
    monkeypatch.setattr(sync, "VERSION_FILE", version_file)
    monkeypatch.setattr(sync, "TOKENS_FILE", tokens)
    assert sync.main() == 1
    assert "Version mismatch" in capsys.readouterr().out


def test_missing_constant_is_detected(tmp_path, monkeypatch, capsys):
    version_file = tmp_path / "VERSION"
    version_file.write_text("1.2.3\n")
    tokens = tmp_path / "tokens.dart"
    tokens.write_text("// no constant here\n")
    monkeypatch.setattr(sync, "VERSION_FILE", version_file)
    monkeypatch.setattr(sync, "TOKENS_FILE", tokens)
    assert sync.main() == 1
    assert "kAppVersion not found" in capsys.readouterr().out
