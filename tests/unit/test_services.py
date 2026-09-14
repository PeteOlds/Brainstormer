import pytest
from unittest.mock import AsyncMock, Mock, patch
import json

from app.services.ollama_client import OllamaClient, OllamaError
from app.services.prompt_templates import (
    PromptTemplate, get_base_prompt, get_refine_prompt,
    get_competitors_prompt, get_feasibility_prompt, get_prompt_template
)
from app.utils.markdown import render_markdown_safe, render_markdown_to_text
from app.schemas.ollama_schemas import (
    RefineOutput, CompetitorsOutput, FeasibilityOutput,
    validate_ollama_output, Verdict
)


class TestOllamaClient:
    @pytest.fixture
    def client(self):
        return OllamaClient(base_url="http://localhost:11434", timeout=30.0)

    @pytest.mark.asyncio
    async def test_list_models(self, client):
        mock_response = Mock()
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3:8b", "modified_at": "2024-01-01", "size": 4000000000},
                {"name": "mistral:7b", "modified_at": "2024-01-02", "size": 3000000000},
            ]
        }
        mock_response.raise_for_status = Mock()
        
        with patch.object(client._client, 'get', return_value=mock_response):
            models = await client.list_models()
            assert len(models) == 2
            assert models[0]["name"] == "llama3:8b"

    @pytest.mark.asyncio
    async def test_generate_success(self, client):
        mock_response = Mock()
        mock_response.json.return_value = {
            "response": '{"elevator_pitch": "Test", "target_audience": "Devs", "core_value_proposition": "Speed", "monetization_strategy": "SaaS"}',
            "done": True
        }
        mock_response.raise_for_status = Mock()
        
        with patch.object(client._client, 'post', return_value=mock_response):
            result = await client.generate(
                model="llama3:8b",
                prompt="Test prompt",
                system="System prompt",
                format="json"
            )
            assert "response" in result
            assert result["done"] is True

    @pytest.mark.asyncio
    async def test_generate_error(self, client):
        with patch.object(client._client, 'post', side_effect=Exception("Connection failed")):
            with pytest.raises(Exception):
                await client.generate(model="llama3:8b", prompt="Test")

    def test_generate_sync(self, client):
        with patch.object(client, 'generate', new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = {"response": "test", "done": True}
            result = client.generate_sync(model="llama3:8b", prompt="Test")
            assert result == {"response": "test", "done": True}


class TestPromptTemplates:
    def test_base_prompt(self):
        prompt = get_base_prompt()
        assert "expert startup advisor" in prompt.lower()
        assert "json" in prompt.lower()

    def test_refine_prompt(self):
        template = get_refine_prompt()
        rendered = template.render(ORIGINAL_IDEA_CONTENT="Test business idea")
        assert "Test business idea" in rendered
        assert "elevator_pitch" in rendered

    def test_competitors_prompt(self):
        template = get_competitors_prompt()
        rendered = template.render(ORIGINAL_IDEA_CONTENT="Test business idea")
        assert "Test business idea" in rendered
        assert "direct_competitors" in rendered

    def test_feasibility_prompt(self):
        template = get_feasibility_prompt()
        rendered = template.render(ORIGINAL_IDEA_CONTENT="Test business idea")
        assert "Test business idea" in rendered
        assert "technical_feasibility" in rendered

    def test_get_prompt_template(self):
        template = get_prompt_template("REFINE")
        assert isinstance(template, PromptTemplate)
        
        template = get_prompt_template("COMPETITORS")
        assert isinstance(template, PromptTemplate)
        
        template = get_prompt_template("FEASIBILITY_SCORE")
        assert isinstance(template, PromptTemplate)

    def test_invalid_prompt_template(self):
        with pytest.raises(ValueError):
            get_prompt_template("INVALID")


class TestMarkdownService:
    def test_render_markdown_safe_basic(self):
        md = "# Hello\n\nThis is **bold** and *italic* text."
        html = render_markdown_safe(md)
        assert "<h1>Hello</h1>" in html
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html

    def test_render_markdown_safe_code(self):
        md = "Inline `code` and\n```python\nprint('hello')\n```"
        html = render_markdown_safe(md)
        assert "<code>code</code>" in html
        assert "<pre>" in html

    def test_render_markdown_safe_links(self):
        md = "[Link](https://example.com)"
        html = render_markdown_safe(md)
        assert 'href="https://example.com"' in html
        assert 'target="_blank"' in html
        assert 'rel="noopener noreferrer"' in html

    def test_render_markdown_safe_sanitizes(self):
        md = '<script>alert("xss")</script>'
        html = render_markdown_safe(md)
        assert "<script>" not in html

    def test_render_markdown_to_text(self):
        md = "# Title\n\nContent with **bold**."
        text = render_markdown_to_text(md, max_length=100)
        assert "Title" in text
        assert "Content with bold" in text

    def test_render_markdown_truncates(self):
        md = "A" * 200
        text = render_markdown_to_text(md, max_length=50)
        assert len(text) <= 53


class TestOllamaSchemas:
    def test_refine_output_valid(self):
        data = {
            "elevator_pitch": "A test elevator pitch that is long enough",
            "target_audience": "Developers",
            "core_value_proposition": "A core value proposition that is long enough",
            "monetization_strategy": "SaaS model"
        }
        output = RefineOutput(**data)
        assert output.elevator_pitch == "A test elevator pitch that is long enough"

    def test_refine_output_invalid(self):
        with pytest.raises(Exception):
            RefineOutput(elevator_pitch="Short", target_audience="Devs", core_value_proposition="Speed", monetization_strategy="SaaS")

    def test_competitors_output_valid(self):
        data = {
            "direct_competitors": [
                {"name": "Competitor A", "description": "A description", "advantage_over_idea": "An advantage"}
            ],
            "indirect_competitors": ["Excel"],
            "differentiator": "Unique feature",
            "barriers_to_entry": ["High cost"]
        }
        output = CompetitorsOutput(**data)
        assert len(output.direct_competitors) == 1

    def test_feasibility_output_valid(self):
        data = {
            "overall_score": 7.5,
            "scores": {
                "technical_feasibility": {"score": 8, "reasoning": "Easy to build with standard tools"},
                "market_demand": {"score": 7, "reasoning": "Good demand in the market"},
                "capital_efficiency": {"score": 8, "reasoning": "Low capital requirement"}
            },
            "verdict": "RECOMMENDED"
        }
        output = FeasibilityOutput(**data)
        assert output.overall_score == 7.5
        assert output.verdict == Verdict.RECOMMENDED

    def test_validate_ollama_output(self):
        json_str = '{"elevator_pitch": "A test elevator pitch long enough", "target_audience": "Developers", "core_value_proposition": "A core value prop long enough", "monetization_strategy": "SaaS model"}'
        result = validate_ollama_output("REFINE", json_str)
        assert isinstance(result, RefineOutput)

    def test_validate_five_forces_output(self):
        from app.schemas.ollama_schemas import FiveForcesOutput
        json_str = '{"competitive_rivalry": "Several entrenched players compete on price and features in a growing market.", "threat_of_substitutes": "Spreadsheets and manual processes remain common workarounds.", "threat_of_new_entrants": "Moderate capital needs but strong brand loyalty protects incumbents.", "bargaining_power_of_buyers": "Fragmented buyers with low switching costs are price sensitive.", "bargaining_power_of_suppliers": "Commodity inputs from many vendors keep supplier power low.", "market_attractiveness": "Attractive niche with clear differentiation openings.", "primary_risks": ["Price war", "Platform dependency"], "recommendations": ["Own a narrow vertical first", "Build switching costs via integrations"]}'
        result = validate_ollama_output("FIVE_FORCES", json_str)
        assert isinstance(result, FiveForcesOutput)
        assert len(result.primary_risks) == 2

    def test_validate_five_forces_missing_field(self):
        import pytest as _pytest
        with _pytest.raises(Exception):
            validate_ollama_output("FIVE_FORCES", '{"competitive_rivalry": "x"}')

    def test_validate_pestel_output(self):
        from app.schemas.ollama_schemas import PestelOutput
        json_str = '{"political": "Stable policy environment with supportive startup legislation in place.", "economic": "Moderate inflation with steady consumer spending power overall.", "social": "Growing sustainability culture among younger demographics today.", "technological": "Rapid AI tooling advances lower build costs significantly.", "environmental": "Tightening packaging rules raise compliance costs somewhat.", "legal": "Standard consumer protection plus GDPR-style privacy duties.", "opportunities": ["Green subsidies"], "threats": ["Recession"], "recommendations": ["Launch in subsidised regions"]}'
        result = validate_ollama_output("PESTEL", json_str)
        assert isinstance(result, PestelOutput)
        assert result.opportunities == ["Green subsidies"]

    def test_validate_ollama_output_invalid(self):
        with pytest.raises(Exception):
            validate_ollama_output("REFINE", "invalid json")

class TestTokenLifetime:
    def test_access_token_honours_config_expiry(self, app):
        """Regression: create_tokens hardcoded 15min, ignoring
        JWT_ACCESS_TOKEN_EXPIRES (users logged out every 15min)."""
        import jwt as pyjwt
        with app.app_context():
            from app.extensions import db
            from app.models import User
            from app.utils.auth import create_tokens

            user = User(email="tokenlife@test.com")
            user.set_password("password123")
            db.session.add(user)
            db.session.commit()

            tokens = create_tokens(str(user.id), "USER", user.email)
            payload = pyjwt.decode(tokens["access_token"], options={"verify_signature": False})
            expected = app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds()
            assert payload["exp"] - payload["iat"] == expected


class TestBeatHeartbeat:
    def test_write_then_check_fresh(self):
        from app.tasks.maintenance_tasks import (
            write_beat_heartbeat, check_beat_heartbeat, HEARTBEAT_KEY)

        class FakeRedis:
            def __init__(self):
                self.d = {}
            def set(self, k, v):
                self.d[k] = v
            def get(self, k):
                return self.d.get(k)

        r = FakeRedis()
        write_beat_heartbeat(r)
        assert HEARTBEAT_KEY in r.d
        assert check_beat_heartbeat(r) is True

    def test_missing_key_grace_passes(self):
        from app.tasks.maintenance_tasks import check_beat_heartbeat

        class FakeRedis:
            def get(self, k):
                return None

        assert check_beat_heartbeat(FakeRedis()) is True

    def test_stale_heartbeat_fails(self):
        from datetime import datetime, timezone, timedelta
        from app.tasks.maintenance_tasks import check_beat_heartbeat

        class FakeRedis:
            def get(self, k):
                return (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()

        assert check_beat_heartbeat(FakeRedis()) is False

    def test_broken_redis_fails(self):
        from app.tasks.maintenance_tasks import check_beat_heartbeat

        class FakeRedis:
            def get(self, k):
                raise ConnectionError("down")

        assert check_beat_heartbeat(FakeRedis()) is False
