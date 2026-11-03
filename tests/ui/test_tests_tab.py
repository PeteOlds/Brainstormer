"""The Tests tab renders build-seeded checks.

Regression: the tab queried a table no migration created (blank tab on
Postgres) and nothing populated it after a build. This seeds the same rows
the confirm build writes and checks the browser shows them with their
"build" provenance badge.
"""

import pytest

from tests.ui.conftest import assert_no_page_errors

pytestmark = pytest.mark.ui

DETAIL = "[data-testid='detail-modal']"
REF = "IDEA-9005"


def _seed_rows(live_app):
    from app.extensions import db
    from app.models import Idea, IdeaTest, SecondaryActionResult, TestStatus, TestType

    with live_app.app_context():
        idea = Idea.query.filter_by(reference_code=REF).first()
        if not SecondaryActionResult.query.filter_by(
            idea_id=idea.id, action_type="BUILD_CODE"
        ).first():
            db.session.add(
                SecondaryActionResult(
                    idea_id=idea.id,
                    action_type="BUILD_CODE",
                    model_used="seed",
                    result_data={"written": True, "files": [], "summary": "seed"},
                    version=1,
                    is_current=True,
                    instance_id=idea.instance_id,
                )
            )
        if not IdeaTest.query.filter_by(idea_id=idea.id).first():
            db.session.add_all(
                [
                    IdeaTest(
                        idea_id=idea.id,
                        instance_id=idea.instance_id,
                        name="UI: main screen loads in a browser",
                        description="Open the app and expect the form.",
                        test_type=TestType.E2E,
                        status=TestStatus.NOT_RUN,
                        source="build",
                    ),
                    IdeaTest(
                        idea_id=idea.id,
                        instance_id=idea.instance_id,
                        name="POST /describe returns a valid response",
                        test_type=TestType.INTEGRATION,
                        status=TestStatus.NOT_RUN,
                        source="build",
                    ),
                ]
            )
        db.session.commit()
        return str(idea.id)


def test_tests_tab_lists_seeded_checks(admin_page, live_server, live_app, seeded):
    idea_id = _seed_rows(live_app)
    page = admin_page
    page.goto(f"{live_server}/ideas?idea={idea_id}", wait_until="domcontentloaded")
    page.wait_for_selector(DETAIL, state="visible", timeout=15000)

    page.get_by_role("tab", name="Tests").click()
    page.wait_for_timeout(1200)

    detail = page.locator(DETAIL)
    assert detail.get_by_text("UI: main screen loads in a browser").is_visible()
    assert detail.get_by_text(
        "POST /describe returns a valid response"
    ).is_visible()
    # Generated checks are labelled so they are not mistaken for manual ones.
    assert detail.get_by_text("build", exact=True).first.is_visible()
    assert_no_page_errors(page)
