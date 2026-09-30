from unittest.mock import patch


def test_health_ok(client):
    # No real Redis/beat in the test env; stub the checks and verify the
    # endpoint reports healthy when all dependencies pass.
    with (
        patch("app.routes.health.check_redis", return_value=True),
        patch("app.routes.health.check_scheduler", return_value=True),
    ):
        res = client.get("/api/health")
    assert res.status_code == 200
    assert res.get_json()["data"]["status"] == "healthy"


def test_health_degraded_without_redis(client):
    # Intended prod behaviour: Redis down -> 503 degraded (not 200).
    # Stubbed: a real Redis may be reachable from some dev hosts.
    with patch("app.routes.health.check_redis", return_value=False):
        res = client.get("/api/health")
    assert res.status_code == 503
    assert res.get_json()["data"]["status"] == "degraded"


def test_unknown_route_404(client):
    res = client.get("/api/nonexistent")
    assert res.status_code == 404


def test_html_pages_not_cached(client):
    res = client.get("/ideas")
    assert res.status_code == 200
    assert res.headers["Cache-Control"] == "no-cache, no-store, must-revalidate"


def test_legacy_web_gate_410(app, client):
    app.config["LEGACY_WEB_ENABLED"] = False
    try:
        assert client.get("/ideas").status_code == 410
        assert client.get("/admin").status_code == 410
        # API is unaffected by the web gate.
        assert client.get("/api/health").status_code in (200, 503)
    finally:
        app.config["LEGACY_WEB_ENABLED"] = True
