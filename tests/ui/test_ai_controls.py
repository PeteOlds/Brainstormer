"""Shared AI controls: model dropdown + skills/guidelines multiselects.

Every surface that picks a model must behave the same way (Admin -> AI
Settings is the reference): a <select> of the provider's catalogue, with a
"Custom model..." escape hatch, and multiselect dropdowns for skills and
guidelines. Free-text model ids and comma-separated skill strings were the
bug these tests pin down.
"""

import pytest

from tests.ui.conftest import assert_no_page_errors

pytestmark = pytest.mark.ui

DETAIL = "[data-testid='detail-modal']"
SCALE_REF = "IDEA-9005"


def _seed_release(live_app, name="Release 1.0"):
    """A release on the seeded SCALE idea, so the override panel renders."""
    from app.extensions import db
    from app.models import Idea, Release

    with live_app.app_context():
        parent = Idea.query.filter_by(reference_code=SCALE_REF).first()
        release = Release.query.filter_by(
            parent_idea_id=parent.id, name=name
        ).first()
        if release is None:
            release = Release(
                parent_idea_id=parent.id,
                instance_id=parent.instance_id,
                name=name,
                status="planned",
            )
            db.session.add(release)
            db.session.commit()
        return str(parent.id), str(release.id)


def test_release_ai_settings_use_shared_controls(
    admin_page, live_server, live_app, seeded
):
    parent_id, _release_id = _seed_release(live_app)
    page = admin_page
    page.goto(f"{live_server}/ideas?idea={parent_id}", wait_until="domcontentloaded")
    page.wait_for_selector(DETAIL, state="visible", timeout=15000)
    page.locator(DETAIL).locator("button:has-text('Scale')").first.click()
    page.wait_for_timeout(1500)

    panel = page.locator("[data-testid='release-ai']").first
    assert panel.is_visible()

    # Model is a dropdown fed by the shared catalogue, not a free-text box.
    model = panel.locator("[data-testid='release-ai-model']").first
    assert "Custom model" in model.inner_text()
    assert "Stage default" in model.inner_text()

    # The custom id input only appears after choosing "Custom model...".
    custom = panel.locator("input[placeholder^='model id']").first
    assert not custom.is_visible()
    model.select_option("__custom__")
    page.wait_for_timeout(300)
    assert custom.is_visible()

    # Skills and Guidelines are multiselect dropdowns with their own panels.
    for testid in ("release-ai-skills", "release-ai-guidelines"):
        assert panel.locator(f"[data-testid='{testid}']").first.is_visible()

    guidelines_btn = panel.locator("[data-testid='release-ai-guidelines']").first
    guidelines_btn.click()
    page.wait_for_timeout(200)
    choices = guidelines_btn.locator("xpath=..").locator("input[type='checkbox']")
    if choices.count():
        choices.first.check()
        guidelines_btn.click()  # collapse again before clicking Save
        page.wait_for_timeout(100)
        panel.locator("button:has-text('Save')").first.click()
        page.wait_for_timeout(2000)

        page.goto(
            f"{live_server}/ideas?idea={parent_id}", wait_until="domcontentloaded"
        )
        page.wait_for_selector(DETAIL, state="visible", timeout=15000)
        page.locator(DETAIL).locator("button:has-text('Scale')").first.click()
        page.wait_for_timeout(1500)
        saved = page.locator("[data-testid='release-ai-guidelines']").first.inner_text()
        assert "1 selected" in saved

    assert_no_page_errors(page)


def test_run_dialog_model_is_a_dropdown(admin_page, live_server, seeded):
    """The run dialog uses the same control (no provider-specific free text)."""
    idea_id = seeded["idea_ids"][SCALE_REF]
    page = admin_page
    page.goto(f"{live_server}/ideas?idea={idea_id}", wait_until="domcontentloaded")
    page.wait_for_selector(DETAIL, state="visible", timeout=15000)
    # Open the run dialog through the component (same call the buttons make).
    page.evaluate(
        """(id) => {
            const root = Array.from(document.querySelectorAll('[x-data]'))
                .find((el) => (el.getAttribute('x-data') || '').startsWith('ideasApp'));
            return Alpine.$data(root).openRunDialog(id, 'PRD_DOC');
        }""",
        idea_id,
    )
    dialog = page.locator("[data-testid='run-dialog']")
    dialog.wait_for(state="visible", timeout=10000)
    page.locator("text=Advanced settings").click()
    page.wait_for_timeout(500)
    texts = " ".join(
        dialog.locator("select").nth(i).inner_text()
        for i in range(dialog.locator("select").count())
    )
    assert "Custom model" in texts
    assert_no_page_errors(page)


def test_admin_stage_defaults_use_shared_controls(admin_page, live_server):
    """The reference pattern: model dropdown + multiselects in AI Settings."""
    page = admin_page
    page.goto(f"{live_server}/admin/ai", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    page.locator("button:has-text('Edit stage settings')").first.click()
    page.wait_for_timeout(500)
    assert "Custom model" in page.locator("[data-testid='stage-ai-model']").inner_text()
    for testid in ("stage-ai-skills", "stage-ai-guidelines"):
        assert page.locator(f"[data-testid='{testid}']").is_visible()
    assert_no_page_errors(page)
