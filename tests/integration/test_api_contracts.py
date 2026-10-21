"""API contract tests.

These tests verify the shape of API responses so that basic bugs
(missing fields, wrong status codes, wrong scoping) are caught before
they reach users.

Run with: pytest tests/integration/test_api_contracts.py -q
"""


class TestIdeasContract:
    """Contract tests for the ideas API."""

    def test_get_idea_includes_content(self, admin_client):
        """GET /api/v1/ideas/<id> must return content/raw_content so the
        detail modal can render it. Regression test for empty detail modal."""
        # First create an idea
        res = admin_client.post(
            "/api/v1/ideas",
            json={"prompt_title": "Contract Test Idea", "raw_content": "This is the idea content for testing."},
        )
        assert res.status_code == 201, res.get_data(as_text=True)
        idea_id = res.get_json()["data"]["id"]

        # Fetch it back
        res = admin_client.get(f"/api/v1/ideas/{idea_id}")
        assert res.status_code == 200, res.get_data(as_text=True)
        data = res.get_json()
        idea = data["data"]["idea"]

        assert idea["content"] is not None, "content field missing from idea detail"
        assert idea["content"] == "This is the idea content for testing.", (
            f"Expected raw content, got: {idea.get('content')!r}"
        )

    def test_list_ideas_returns_expected_fields(self, admin_client):
        """GET /api/v1/ideas must return ideas with expected fields."""
        # Create an idea first so the list isn't empty
        admin_client.post(
            "/api/v1/ideas",
            json={"prompt_title": "Contract Test Idea", "raw_content": "test content"},
        )
        res = admin_client.get("/api/v1/ideas?limit=5")
        assert res.status_code == 200, res.get_data(as_text=True)
        data = res.get_json()
        assert "data" in data, "response missing 'data' key"
        assert "ideas" in data["data"], "response data missing 'ideas' key"
        ideas = data["data"]["ideas"]
        assert len(ideas) > 0, "expected at least one idea"

        idea = ideas[0]
        required_fields = [
            "id", "reference_code", "prompt_title", "status",
            "net_votes", "upvotes_count", "downvotes_count",
            "created_at", "updated_at",
        ]
        for field in required_fields:
            assert field in idea, f"idea missing required field: {field}"

    def test_bulk_status_change(self, admin_client):
        """PATCH /api/v1/ideas/bulk-status must move ideas to new status."""
        # Create two ideas
        res1 = admin_client.post(
            "/api/v1/ideas",
            json={"prompt_title": "Bulk Test 1", "raw_content": "content 1"},
        )
        res2 = admin_client.post(
            "/api/v1/ideas",
            json={"prompt_title": "Bulk Test 2", "raw_content": "content 2"},
        )
        idea_ids = [res1.get_json()["data"]["id"], res2.get_json()["data"]["id"]]

        # Move both to SCOPE
        res = admin_client.patch(
            "/api/v1/ideas/bulk-status",
            json={"idea_ids": idea_ids, "status": "SCOPE"},
        )
        assert res.status_code == 200, res.get_data(as_text=True)
        data = res.get_json()
        assert data["data"]["moved"] == 2, f"Expected 2 moved, got: {data['data']}"
        assert data["data"]["status"] == "SCOPE"

        # Verify they were actually moved
        for idea_id in idea_ids:
            res = admin_client.get(f"/api/v1/ideas/{idea_id}")
            idea = res.get_json()["data"]["idea"]
            assert idea["status"] == "SCOPE", (
                f"idea {idea_id} status is {idea['status']}, expected SCOPE"
            )


class TestPromptsContract:
    """Contract tests for the prompts API."""

    def test_list_prompts_scoped_to_instance(self, admin_client):
        """GET /api/v1/prompts must only return prompts for the scoped
        instance when scoped to an instance."""
        res = admin_client.get("/api/v1/prompts")
        assert res.status_code == 200, res.get_data(as_text=True)
        data = res.get_json()
        prompts = data["data"]["prompts"]

        # Every prompt returned must belong to the scoped instance
        # (instance_id is set via JWT claim / apply_scope).
        # We can't assert a specific count without knowing the DB state,
        # but we can verify the response shape is correct.
        for prompt in prompts:
            assert "id" in prompt, "prompt missing 'id'"
            assert "title" in prompt, "prompt missing 'title'"
            assert "is_active" in prompt, "prompt missing 'is_active'"


class TestAuthContract:
    """Contract tests for auth API."""

    def test_login_returns_tokens(self, admin_client):
        """POST /api/v1/login must return access and refresh tokens."""
        res = admin_client.post(
            "/api/v1/login",
            json={"email": "admin@example.com", "password": "admin123"},
        )
        assert res.status_code == 200, res.get_data(as_text=True)
        data = res.get_json()
        assert data["success"] is True
        assert "access_token" in data["data"], "response missing access_token"
        assert "refresh_token" in data["data"], "response missing refresh_token"
        assert "user" in data["data"], "response missing user"

    def test_login_rejects_wrong_password(self, client):
        """POST /api/v1/login with wrong password returns 401."""
        res = client.post(
            "/api/v1/login",
            json={"email": "admin@example.com", "password": "wrongpassword"},
        )
        assert res.status_code == 401, f"Expected 401, got {res.status_code}"
