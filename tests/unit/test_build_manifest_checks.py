"""Deterministic guardrails for generated build manifests."""

from app.services.build_agents import render_agents_md
from app.services.build_manifest_checks import (
    BuildManifestError,
    check_manifest_files,
    ensure_manifest_files,
)


def _files(**overrides):
    base = [
        {"path": "app.py", "content": "print('hello')\n"},
        {"path": "requirements.txt", "content": "flask\n"},
        {"path": "AGENTS.md", "content": "# AGENTS.md\n\nRun python app.py.\n"},
    ]
    base.extend(overrides.get("extra", []))
    return base


def test_clean_manifest_has_no_problems():
    assert check_manifest_files(_files(), require_agents_md=True) == []


def test_long_source_file_is_rejected():
    files = _files(extra=[{"path": "big.py", "content": "x = 1\n" * 301}])
    problems = check_manifest_files(files)
    assert any("big.py has 301 lines" in p for p in problems)


def test_long_data_file_is_allowed():
    files = _files(extra=[{"path": "package-lock.json", "content": "x\n" * 500}])
    assert check_manifest_files(files) == []


def test_placeholder_marker_is_rejected():
    files = _files(extra=[{"path": "stub.py", "content": "# TODO: implement later\n"}])
    problems = check_manifest_files(files)
    assert any("stub.py contains" in p for p in problems)


def test_unsafe_path_is_rejected():
    files = _files(extra=[{"path": "../escape.py", "content": "x = 1\n"}])
    assert any("unsafe file path" in p for p in check_manifest_files(files))


def test_missing_agents_md_is_reported():
    files = [f for f in _files() if f["path"] != "AGENTS.md"]
    problems = check_manifest_files(files, require_agents_md=True)
    assert any("AGENTS.md is missing" in p for p in problems)


def test_ensure_raises_with_all_problems():
    files = _files(
        extra=[
            {"path": "stub.py", "content": "TODO\n"},
            {"path": "big.py", "content": "x\n" * 301},
        ]
    )
    try:
        ensure_manifest_files(files)
    except BuildManifestError as exc:
        message = str(exc)
        assert "stub.py" in message and "big.py" in message
    else:
        raise AssertionError("expected BuildManifestError")


def test_agents_md_is_server_authored_and_compact():
    content = render_agents_md(
        _files()[:2], target_name="IDEA-1234"
    )
    assert "# AGENTS.md" in content
    assert "IDEA-1234" in content
    assert "python app.py" in content
    assert "pip install" in content
    assert len(content.splitlines()) < 60
    assert not check_manifest_files([{"path": "AGENTS.md", "content": content}])


def test_node_stack_detected():
    content = render_agents_md(
        [
            {"path": "package.json", "content": "{}"},
            {"path": "src/index.js", "content": "console.log(1)"},
        ]
    )
    assert "Node.js" in content
    assert "npm start" in content
