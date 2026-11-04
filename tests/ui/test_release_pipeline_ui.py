"""Scale tab: put several children in a release, then run the release.

These are browser tests (``pytest -m ui``). They seed a SCALE idea with
children directly in the file-backed UI database, then drive the real
Alpine controls. Starting a release in this harness only persists the
pipeline row (Celery is eager and the tick schedules nothing), so no LLM
is touched — that side is covered by the integration tests.
"""

import time

import pytest

from tests.ui.conftest import assert_no_page_errors

pytestmark = pytest.mark.ui

DETAIL = "[data-testid='detail-modal']"
CONFIRM = "[aria-labelledby='confirm-modal-title']"
SCALE_REF = "IDEA-9005"
REF_A = "IDEA-9201"
REF_B = "IDEA-9202"


def _seed_release(
    live_app, name="Release 1.1", statuses=("SCOPE", "SPARK"), assign=False
):
    from app.extensions import db
    from app.models import Idea, Release

    with live_app.app_context():
        parent = Idea.query.filter_by(reference_code=SCALE_REF).one()
        release = Release(
            parent_idea_id=parent.id,
            instance_id=parent.instance_id,
            name=name,
            created_by_id=parent.created_by_id,
        )
        db.session.add(release)
        db.session.flush()
        kids = []
        for i, status in enumerate(statuses):
            ref = REF_A if i == 0 else REF_B
            kid = Idea(
                reference_code=ref,
                prompt_title=f"Fix {i}",
                raw_content=f"## Fix {i}\n\nThe export button fails.",
                status=status,
                instance_id=parent.instance_id,
                created_by_id=parent.created_by_id,
                parent_id=parent.id,
                child_kind="bugfix",
                release_id=release.id if assign else None,
            )
            db.session.add(kid)
            db.session.flush()
            kids.append(kid)
        db.session.commit()
        return str(release.id), [str(k.id) for k in kids]


def _open_scale(page, live_server, seeded):
    idea_id = seeded["idea_ids"][SCALE_REF]
    page.goto(f"{live_server}/ideas?idea={idea_id}", wait_until="domcontentloaded")
    page.wait_for_selector(DETAIL, state="visible", timeout=15000)
    page.locator(DETAIL).locator("button:has-text('Scale')").first.click()
    page.wait_for_timeout(1200)
    return page.locator(DETAIL)


def _wait_for(predicate, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.2)
    return False


def test_selected_children_can_be_added_to_a_release(
    admin_page, live_server, live_app, seeded
):
    from app.extensions import db
    from app.models import Idea, Release

    release_id, kid_ids = _seed_release(live_app, assign=False)
    detail = _open_scale(admin_page, live_server, seeded)

    detail.locator(f"input[aria-label='Select {REF_A}']").check()
    detail.locator(f"input[aria-label='Select {REF_B}']").check()
    assert detail.get_by_text("2 selected").is_visible()

    select = detail.locator("select[x-model='assignTarget']")
    select.wait_for(state="visible", timeout=5000)
    select.select_option(release_id)
    detail.get_by_role("button", name="Add selected").click()

    def assigned():
        with live_app.app_context():
            rows = Idea.query.filter(Idea.id.in_([kid_ids[0], kid_ids[1]])).all()
            return all(str(row.release_id) == release_id for row in rows)

    assert _wait_for(assigned), "selected children were not assigned"
    with live_app.app_context():
        release = db.session.get(Release, __import__("uuid").UUID(release_id))
        assert release is not None
    assert_no_page_errors(admin_page)


def test_release_card_shows_pipeline_progress(
    admin_page, live_server, live_app, seeded
):
    from app.extensions import db
    from app.models import Release

    release_id, kid_ids = _seed_release(live_app, assign=True)
    with live_app.app_context():
        release = db.session.get(Release, __import__("uuid").UUID(release_id))
        release.pipeline_status = "running"
        release.pipeline_phase = "design"
        release.pipeline_state = {
            "children": {
                kid_ids[0]: {
                    "reference_code": REF_A,
                    "prd": "done",
                    "design": "running",
                    "build": "pending",
                    "test": "pending",
                    "reason": None,
                },
                kid_ids[1]: {
                    "reference_code": REF_B,
                    "prd": "done",
                    "design": "pending",
                    "build": "pending",
                    "test": "pending",
                    "reason": None,
                },
            }
        }
        db.session.commit()

    detail = _open_scale(admin_page, live_server, seeded)
    assert detail.get_by_text("Running · Design").first.is_visible()
    assert detail.get_by_text("2/2").first.is_visible()  # both PRDs done
    assert detail.get_by_role("button", name="Stop").first.is_visible()
    detail.get_by_text("Per-idea progress").click()
    assert detail.get_by_text(f"PRD done").first.is_visible()
    assert_no_page_errors(admin_page)


def test_run_and_stop_release_from_the_card(
    admin_page, live_server, live_app, seeded
):
    from app.extensions import db
    from app.models import Release

    release_id, _ = _seed_release(live_app, assign=True)
    detail = _open_scale(admin_page, live_server, seeded)

    run_button = detail.get_by_role("button", name="Run release")
    assert run_button.first.is_visible()
    run_button.first.click()
    confirm = admin_page.locator(CONFIRM)
    confirm.wait_for(state="visible", timeout=5000)
    confirm.get_by_role("button", name="Run release").click()

    assert _wait_for(
        lambda: "Running · PRD"
        in detail.inner_text(),
    ), "release did not show as running after start"

    with live_app.app_context():
        release = db.session.get(Release, __import__("uuid").UUID(release_id))
        assert release.pipeline_status == "running"
        assert release.pipeline_phase == "prd"

    detail.get_by_role("button", name="Stop").first.click()
    confirm = admin_page.locator(CONFIRM)
    confirm.wait_for(state="visible", timeout=5000)
    confirm.get_by_role("button", name="Stop").click()

    assert _wait_for(
        lambda: "Stopping after this step" in detail.inner_text(),
    ), "release did not show the stop request"
    assert_no_page_errors(admin_page)
