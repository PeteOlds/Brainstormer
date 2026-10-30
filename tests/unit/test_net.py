"""SSRF guard for tenant-supplied LLM endpoints."""

import pytest

from app.utils.net import UnsafeEndpoint, validate_llm_endpoint

OLLAMA = "http://localhost:11434"


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://10.1.2.3/v1",
        "http://192.168.1.10/v1",
        "http://172.16.5.4/v1",
        "http://127.0.0.1:6379/",
        "http://[::1]:8080/",
        "http://0.0.0.0:8000/",
        "file:///etc/passwd",
        "ftp://example.com/",
        "gopher://example.com/",
    ],
)
def test_private_and_non_http_endpoints_are_rejected(url):
    with pytest.raises(UnsafeEndpoint):
        validate_llm_endpoint(url)


def test_public_https_endpoint_is_allowed():
    assert (
        validate_llm_endpoint("https://api.openai.com/v1")
        == "https://api.openai.com/v1"
    )


def test_configured_ollama_endpoint_is_allowed():
    """The server's own Ollama lives on loopback; that one is trusted."""
    assert validate_llm_endpoint(OLLAMA, allow_hosts={OLLAMA}) == OLLAMA


def test_loopback_that_is_not_the_configured_host_is_rejected():
    with pytest.raises(UnsafeEndpoint):
        validate_llm_endpoint("http://127.0.0.1:6379/", allow_hosts={OLLAMA})


def test_endpoint_without_host_is_rejected():
    with pytest.raises(UnsafeEndpoint):
        validate_llm_endpoint("http:///v1")
