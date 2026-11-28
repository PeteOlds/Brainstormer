"""Site-admin API for shared internal prompts."""

from app.extensions import db
from app.models import SitePrompt
from app.services.internal_prompts import default_body, get_internal_prompt


def test_list_prompts_defaults(app, admin_client):
    res = admin_client.get("/api/v1/admin/internal-prompts")
    assert res.status_code == 200
    rows = res.get_json()["data"]["prompts"]
    assert rows
    strict = next(r for r in rows if r["key"] == "strict_retry")
    assert strict["source"] == "default"
    assert "${ERRORS}" in strict["body"]
    assert strict["required_placeholders"] == ["ERRORS"]


def test_override_and_reset(app, admin_client):
    body = default_body("strict_retry").replace(
        "Output ONLY valid JSON", "Output ONLY valid JSON (site override)"
    )
    res = admin_client.put(
        "/api/v1/admin/internal-prompts/strict_retry", json={"body": body}
    )
    assert res.status_code == 200, res.get_json()
    with app.app_context():
        assert SitePrompt.query.filter_by(key="strict_retry").one().body == body
        assert "site override" in get_internal_prompt("strict_retry").render(ERRORS="x")

    res = admin_client.delete("/api/v1/admin/internal-prompts/strict_retry")
    assert res.status_code == 200
    with app.app_context():
        assert SitePrompt.query.filter_by(key="strict_retry").first() is None
        assert "site override" not in get_internal_prompt("strict_retry").render(
            ERRORS="x"
        )


def test_validation_rejects_missing_placeholder(app, admin_client):
    res = admin_client.put(
        "/api/v1/admin/internal-prompts/strict_retry",
        json={"body": "No placeholders here."},
    )
    assert res.status_code == 400
    assert "ERRORS" in res.get_json()["message"]


def test_validation_rejects_token_pattern(app, admin_client):
    body = default_body("strict_retry") + "\nghp_" + "a" * 40
    res = admin_client.put(
        "/api/v1/admin/internal-prompts/strict_retry", json={"body": body}
    )
    assert res.status_code == 400
    assert "token" in res.get_json()["message"]


def test_non_admin_cannot_manage_prompts(app, client):
    res = client.get("/api/v1/admin/internal-prompts")
    assert res.status_code in (401, 403)
