"""OpenCode CLI backend: parsing, error mapping, isolation, timeouts."""

import json
import os
import subprocess

import pytest

from app.services import opencode_backend as ob
from app.services.llm_backends import ProviderError


def _events(*events):
    return "\n".join(json.dumps(e) for e in events)


class FakeProc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.pid = 4242

    def communicate(self, timeout=None):
        return self.stdout, self.stderr

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        pass

    def kill(self):
        pass


def test_parse_events_collects_text_and_usage():
    stdout = _events(
        {"type": "step_start", "part": {}},
        {"type": "text", "part": {"text": "Hello "}},
        {"type": "text", "part": {"text": "world"}},
        {
            "type": "step_finish",
            "part": {"tokens": {"input": 100, "output": 7}, "cost": 0.0123},
        },
    )
    text, prompt_tokens, completion_tokens, cost_cents = ob._parse_events(stdout)
    assert text == "Hello world"
    assert (prompt_tokens, completion_tokens, cost_cents) == (100, 7, 1)


def test_parse_events_ignores_non_json_lines():
    stdout = "not json\n" + json.dumps({"type": "text", "part": {"text": "ok"}})
    text, *_ = ob._parse_events(stdout)
    assert text == "ok"


def test_parse_events_raises_non_retryable_on_403():
    stdout = _events(
        {
            "type": "error",
            "error": {
                "name": "APIError",
                "data": {
                    "message": "no access",
                    "statusCode": 403,
                    "isRetryable": False,
                },
            },
        }
    )
    with pytest.raises(ProviderError) as exc:
        ob._parse_events(stdout)
    assert exc.value.retryable is False
    assert exc.value.status == 403


def test_parse_events_raises_retryable_on_503():
    stdout = _events(
        {
            "type": "error",
            "error": {
                "name": "APIError",
                "data": {"message": "boom", "statusCode": 503},
            },
        }
    )
    with pytest.raises(ProviderError) as exc:
        ob._parse_events(stdout)
    assert exc.value.retryable is True


def test_opencode_generate_success_uses_sandbox(monkeypatch):
    captured = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["cwd"] = kwargs["cwd"]
        captured["agent_file"] = os.path.exists(
            os.path.join(kwargs["cwd"], ".opencode", "agent", "brainstormer-sandbox.md")
        )
        stdout = _events(
            {"type": "text", "part": {"text": '{"ok": true}'}},
            {
                "type": "step_finish",
                "part": {"tokens": {"input": 5, "output": 2}, "cost": 0},
            },
        )
        return FakeProc(stdout=stdout)

    monkeypatch.setattr(ob.shutil, "which", lambda binary: "/usr/bin/opencode")
    monkeypatch.setattr(ob.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ob, "_sandbox_agent_name", lambda: "brainstormer-sandbox")

    result = ob.opencode_generate("opencode/big-pickle", "hi", system="sys")

    assert result.text == '{"ok": true}'
    assert (result.prompt_tokens, result.completion_tokens) == (5, 2)
    assert "--agent" in captured["argv"]
    assert (
        captured["argv"][captured["argv"].index("--agent") + 1]
        == "brainstormer-sandbox"
    )
    assert captured["agent_file"] is True
    # Sandbox directory is cleaned up after the run.
    assert not os.path.exists(captured["cwd"])


def test_opencode_generate_agent_disabled_omits_flag(monkeypatch):
    captured = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        return FakeProc(stdout=_events({"type": "text", "part": {"text": "ok"}}))

    monkeypatch.setattr(ob.shutil, "which", lambda binary: "/usr/bin/opencode")
    monkeypatch.setattr(ob.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ob, "_sandbox_agent_name", lambda: "")

    ob.opencode_generate("opencode/big-pickle", "hi")

    assert "--agent" not in captured["argv"]


def test_opencode_generate_missing_binary(monkeypatch):
    monkeypatch.setattr(ob.shutil, "which", lambda binary: None)
    monkeypatch.setattr(ob, "_binary", lambda: "opencode-not-installed")

    with pytest.raises(ProviderError) as exc:
        ob.opencode_generate("m", "hi")
    assert exc.value.retryable is False


def test_opencode_generate_timeout_kills_process_group(monkeypatch):
    killed = {}

    class TimeoutProc(FakeProc):
        def communicate(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd="opencode", timeout=timeout)

    monkeypatch.setattr(ob.shutil, "which", lambda binary: "/usr/bin/opencode")
    monkeypatch.setattr(ob.subprocess, "Popen", lambda argv, **k: TimeoutProc())
    monkeypatch.setattr(ob.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(
        ob.os, "killpg", lambda pid, sig: killed.setdefault("called", True)
    )

    with pytest.raises(ProviderError) as exc:
        ob.opencode_generate("m", "hi", timeout=1)
    assert exc.value.retryable is True
    assert killed.get("called") is True


def test_opencode_generate_nonzero_exit_raises(monkeypatch):
    monkeypatch.setattr(ob.shutil, "which", lambda binary: "/usr/bin/opencode")
    monkeypatch.setattr(
        ob.subprocess,
        "Popen",
        lambda argv, **k: FakeProc(stdout="", stderr="boom", returncode=1),
    )

    with pytest.raises(ProviderError) as exc:
        ob.opencode_generate("m", "hi")
    assert exc.value.retryable is True


def test_repo_workspace_requires_configured_dir(monkeypatch):
    monkeypatch.setattr(ob.shutil, "which", lambda binary: "/usr/bin/opencode")
    monkeypatch.setattr(ob, "_workspace_dir", lambda: "")

    with pytest.raises(ProviderError) as exc:
        ob.opencode_generate("m", "hi", workspace="repo")
    assert exc.value.retryable is False


def test_clean_env_excludes_app_secrets(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "topsecret")
    monkeypatch.setenv("FERNET_KEY", "fern")
    monkeypatch.setenv("DATABASE_URL", "postgres://secret")
    monkeypatch.setenv("OPENCODE_BIN", "/x/opencode")

    env = ob._clean_env()

    assert "SECRET_KEY" not in env
    assert "FERNET_KEY" not in env
    assert "DATABASE_URL" not in env
    assert env.get("OPENCODE_BIN") == "/x/opencode"


def _attach_popen(captured, stdout=None):
    stdout = stdout or _events(
        {"type": "text", "part": {"text": "ok"}},
        {
            "type": "step_finish",
            "part": {"tokens": {"input": 1, "output": 1}, "cost": 0},
        },
    )

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["cwd"] = kwargs["cwd"]
        return FakeProc(stdout=stdout)

    return fake_popen


def test_opencode_generate_attach_sandbox(monkeypatch, tmp_path):
    captured = {}
    server_root = "/srv/oc-sandbox"
    monkeypatch.setenv("OPENCODE_SERVER_SANDBOX_ROOT", server_root)
    monkeypatch.setenv("OPENCODE_SANDBOX_ROOT", str(tmp_path))
    monkeypatch.setattr(ob.shutil, "which", lambda binary: "/usr/bin/opencode")
    monkeypatch.setattr(ob.subprocess, "Popen", _attach_popen(captured))
    monkeypatch.setattr(ob, "_sandbox_agent_name", lambda: "brainstormer-sandbox")

    result = ob.opencode_generate(
        "opencode/big-pickle", "hi", endpoint="http://192.168.1.130:4096"
    )

    argv = captured["argv"]
    assert argv[argv.index("--attach") + 1] == "http://192.168.1.130:4096"
    # Attached servers reject project-local agents: never pass --agent.
    assert "--agent" not in argv
    assert argv[argv.index("--dir") + 1].startswith(server_root + "/brainstormer-")
    assert captured["cwd"].startswith(str(tmp_path))
    # Local side cleaned up afterwards.
    assert not os.path.exists(captured["cwd"])
    assert result.text == "ok"


def test_opencode_generate_attach_requires_server_root(monkeypatch):
    monkeypatch.delenv("OPENCODE_SERVER_SANDBOX_ROOT", raising=False)
    monkeypatch.setattr(ob.shutil, "which", lambda binary: "/usr/bin/opencode")

    with pytest.raises(ProviderError) as exc:
        ob.opencode_generate("m", "hi", endpoint="http://x:4096")
    assert exc.value.retryable is False
    assert "OPENCODE_SERVER_SANDBOX_ROOT" in str(exc.value)


def test_opencode_attach_url_env_fallback(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setenv("OPENCODE_SERVER_URL", "http://srv:4096")
    monkeypatch.setenv("OPENCODE_SERVER_SANDBOX_ROOT", "/srv/oc-sandbox")
    monkeypatch.setenv("OPENCODE_SANDBOX_ROOT", str(tmp_path))
    monkeypatch.setattr(ob.shutil, "which", lambda binary: "/usr/bin/opencode")
    monkeypatch.setattr(ob.subprocess, "Popen", _attach_popen(captured))

    ob.opencode_generate("m", "hi")

    argv = captured["argv"]
    assert argv[argv.index("--attach") + 1] == "http://srv:4096"


def test_opencode_generate_attach_repo(monkeypatch):
    captured = {}
    # Server-side path: must NOT be required to exist in this worker.
    monkeypatch.setenv("OPENCODE_WORKSPACE_DIR", "/srv/repo")
    monkeypatch.setattr(ob.shutil, "which", lambda binary: "/usr/bin/opencode")
    monkeypatch.setattr(ob.subprocess, "Popen", _attach_popen(captured))

    ob.opencode_generate("m", "hi", workspace="repo", endpoint="http://x:4096")

    argv = captured["argv"]
    assert argv[argv.index("--dir") + 1] == "/srv/repo"
    assert "--agent" not in argv


_CATALOG = {
    "data": [
        {
            "id": "big-pickle",
            "providerID": "opencode",
            "status": "active",
            "enabled": True,
        },
        {
            "id": "aaa-model",
            "providerID": "opencode",
            "status": "active",
            "enabled": True,
        },
        {
            "id": "old-model",
            "providerID": "opencode",
            "status": "deprecated",
            "enabled": True,
        },
        {
            "id": "off-model",
            "providerID": "opencode",
            "status": "active",
            "enabled": False,
        },
        {
            "id": "llama3:8b",
            "providerID": "ollama",
            "status": "active",
            "enabled": True,
        },
        {"id": "", "providerID": "opencode", "status": "active", "enabled": True},
        "junk",
    ]
}


class _FakeCatalogResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


class _FakeCatalogClient:
    calls = 0

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url):
        _FakeCatalogClient.calls += 1
        return _FakeCatalogResponse(_CATALOG)


def test_list_server_models_filters_and_sorts(monkeypatch):
    import httpx

    _FakeCatalogClient.calls = 0
    monkeypatch.setattr(httpx, "Client", _FakeCatalogClient)
    got = ob.list_server_models("http://srv:4096", provider="opencode")
    assert got == ["opencode/aaa-model", "opencode/big-pickle"]
    assert _FakeCatalogClient.calls == 1
    # Second call is served from cache: no further HTTP.
    assert ob.list_server_models("http://srv:4096", provider="opencode") == got
    assert _FakeCatalogClient.calls == 1


def test_list_server_models_failure_returns_empty(monkeypatch):
    import httpx

    class _Boom:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url):
            raise ConnectionError("down")

    monkeypatch.setattr(httpx, "Client", _Boom)
    assert ob.list_server_models("http://other:4096") == []


def test_list_server_models_empty_url_no_http(monkeypatch):
    import httpx

    def _fail(*a, **k):
        raise AssertionError("must not issue HTTP")

    monkeypatch.setattr(httpx, "Client", _fail)
    assert ob.list_server_models("") == []
    assert ob.list_server_models("   ") == []
