"""Static guards for frontend regressions that are hard to catch in browser tests."""


def test_pending_run_extra_merged_in_execute_action():
    src = open("app/static/js/dashboard.js").read()
    assert "extra = { ...(this.pendingRunExtra || {}), ...(extra || {}) };" in src, (
        "executeAction must merge pendingRunExtra (e.g. PRD answers) into the "
        "request body, otherwise user answers are silently dropped."
    )


def test_txt_upload_regex_not_double_escaped():
    src = open("app/static/js/dashboard.js").read()
    assert (
        r"match(/\.(md|txt)$/)" in src
    ), "upload extension check must use a single-escaped regex."
    assert r"match(/\\.(md|txt)$/)" not in src


def test_managed_app_xtext_guarded():
    src = open("app/templates/ideas/dashboard.html").read()
    assert "x-text=\"managedApp ? managedApp.last_error : ''" in src
    assert (
        "x-text=\"managedApp && managedApp.spec ? managedApp.spec.port_note : ''" in src
    )
