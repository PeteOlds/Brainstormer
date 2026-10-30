"""Security response headers."""

import re


def _script_src(csp: str) -> str:
    for part in csp.split(";"):
        if part.strip().startswith("script-src"):
            return part
    return ""


def test_csp_blocks_inline_scripts_without_a_nonce(client):
    res = client.get("/login")
    assert res.status_code == 200
    csp = res.headers.get("Content-Security-Policy", "")
    assert csp, "no Content-Security-Policy header"

    script_src = _script_src(csp)
    assert "unsafe-inline" not in script_src
    assert "nonce-" in script_src

    # Every inline script in the page must carry the matching nonce.
    html = res.get_data(as_text=True)
    nonce_match = re.search(r"'nonce-([A-Za-z0-9_\-]+)'", script_src)
    assert nonce_match, script_src
    nonce = nonce_match.group(1)
    inline_scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", html)
    assert inline_scripts, "expected at least one inline script"
    for tag in inline_scripts:
        assert f'nonce="{nonce}"' in tag, tag


def test_csp_nonce_changes_per_request(client):
    first = client.get("/login").headers["Content-Security-Policy"]
    second = client.get("/login").headers["Content-Security-Policy"]
    assert re.search(r"'nonce-([^']+)'", first).group(1) != re.search(
        r"'nonce-([^']+)'", second
    ).group(1)


def test_framing_and_sniffing_headers_present(client):
    res = client.get("/login")
    csp = res.headers.get("Content-Security-Policy", "")
    assert "frame-ancestors 'none'" in csp
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
