from datetime import datetime, timezone

from flask import Blueprint, current_app, request

from app.extensions import db
from app.models import Instance, Membership
from app.utils.decorators import site_admin_required, token_required
from app.utils.responses import api_error, api_ok
from app.utils.tenancy import current_instance_id, is_site_admin

bp = Blueprint("instances", __name__)


def _instance_admin(user, instance_id):
    """Instance admins (or site admins) for one instance, else None."""
    if is_site_admin(user):
        return "SITE_ADMIN"
    return Membership.get_role(user.id, instance_id)


def _require_instance_admin(user, instance_id):
    instance = Instance.query.get(instance_id)
    if instance is None:
        return None, api_error("Not found.", 404)
    role = _instance_admin(user, instance.id)
    if role not in ("INSTANCE_ADMIN", "SITE_ADMIN"):
        if role is None:
            return None, api_error("Not found.", 404)
        return None, api_error("Instance admin access required.", 403)
    return instance, None


@bp.route("/instances", methods=["GET"])
@token_required
def list_instances(user):
    """Own instances (memberships); site admins see everything."""
    if is_site_admin(user):
        instances = Instance.query.order_by(Instance.number.asc()).all()
    else:
        memberships = Membership.query.filter_by(user_id=user.id).all()
        ids = [m.instance_id for m in memberships if m.instance_id is not None]
        instances = (
            Instance.query.filter(Instance.id.in_(ids))
            .order_by(Instance.number.asc())
            .all()
            if ids
            else []
        )
    return api_ok({"instances": [i.to_dict() for i in instances]})


@bp.route("/instances", methods=["POST"])
@site_admin_required
def create_instance_route(user):
    """Create an instance (number, name); config copies from Instance 1."""
    from app.services import instances as instance_svc

    data = request.get_json(silent=True) or {}
    raw_number = data.get("number")
    if raw_number is None or isinstance(raw_number, bool):
        return api_error("number is required and must be an integer.", 400)
    try:
        number = int(raw_number)
    except (TypeError, ValueError):
        return api_error("number is required and must be an integer.", 400)
    name = (data.get("name") or "").strip()
    if not name:
        return api_error("name is required.", 400)
    if len(name) > 200:
        return api_error("name must be 200 characters or fewer.", 400)

    try:
        instance = instance_svc.create_instance(number, name)
    except instance_svc.InstanceError as exc:
        return api_error(str(exc), 409)
    return api_ok({"instance": instance.to_dict()}, "Instance created.", 201)


@bp.route("/instances/<uuid:instance_id>", methods=["GET"])
@token_required
def get_instance(user, instance_id):
    """One instance: members of it, or site admins. Else 404 (no leaking)."""
    instance = Instance.query.get(instance_id)
    if instance is None:
        return api_error("Not found.", 404)
    if not is_site_admin(user):
        role = Membership.get_role(user.id, instance.id)
        if role is None:
            return api_error("Not found.", 404)
        if current_instance_id() is not None and current_instance_id() != instance.id:
            return api_error("Not found.", 404)
    return api_ok({"instance": instance.to_dict()})


@bp.route("/instances/<uuid:instance_id>/ai-configs", methods=["GET"])
@token_required
def list_ai_configs(user, instance_id):
    """Provider configs for one instance (keys never leave the server)."""
    from app.models import InstanceAIConfig

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    configs = InstanceAIConfig.query.filter_by(instance_id=instance.id).all()
    return api_ok({"configs": [c.to_dict() for c in configs]})


@bp.route("/instances/<uuid:instance_id>/ai-configs", methods=["PUT"])
@token_required
def upsert_ai_config(user, instance_id):
    """Create or update one provider config. `key` is write-only."""
    from app.models import (
        CUTOFF_BEHAVIOURS,
        OPENCODE_WORKSPACES,
        PROVIDERS,
        InstanceAIConfig,
    )

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    provider = (data.get("provider") or "").strip().lower()
    if provider not in PROVIDERS:
        return api_error(
            f"provider is required and must be one of {', '.join(PROVIDERS)}.",
            status_code=400,
        )
    config = InstanceAIConfig.query.filter_by(
        instance_id=instance.id, provider=provider
    ).first()
    if config is None:
        config = InstanceAIConfig(instance_id=instance.id, provider=provider)
        db.session.add(config)

    if "key" in data:
        key = data["key"]
        if key is not None and not isinstance(key, str):
            return api_error("key must be a string or null.", status_code=400)
        if key:
            config.api_key = key
        elif key is None:
            config._api_key = None
    if "endpoint" in data:
        endpoint = data["endpoint"]
        if endpoint is not None and (
            not isinstance(endpoint, str) or len(endpoint) > 255
        ):
            return api_error(
                "endpoint must be a string up to 255 chars or null.", status_code=400
            )
        if endpoint:
            from app.utils.net import UnsafeEndpoint, validate_llm_endpoint

            try:
                validate_llm_endpoint(
                    endpoint,
                    allow_hosts={current_app.config.get("OLLAMA_BASE_URL", "")},
                )
            except UnsafeEndpoint as exc:
                return api_error(f"endpoint is not allowed: {exc}", status_code=400)
        config.endpoint = endpoint or None
    if "model_allowlist" in data:
        allowlist = data["model_allowlist"]
        if not isinstance(allowlist, list) or any(
            not isinstance(m, str) for m in allowlist
        ):
            return api_error(
                "model_allowlist must be a list of strings.", status_code=400
            )
        config.model_allowlist = list(allowlist)
    if "embedding_model" in data:
        embedding_model = data["embedding_model"]
        if embedding_model is not None and not isinstance(embedding_model, str):
            return api_error(
                "embedding_model must be a string or null.", status_code=400
            )
        config.embedding_model = embedding_model or None
    if "budget_cents" in data:
        budget = data["budget_cents"]
        if budget is not None and (
            isinstance(budget, bool) or not isinstance(budget, int) or budget < 0
        ):
            return api_error(
                "budget_cents must be a non-negative integer or null.", status_code=400
            )
        config.budget_cents = budget
    if "cutoff_behaviour" in data:
        if data["cutoff_behaviour"] not in CUTOFF_BEHAVIOURS:
            return api_error(
                f"cutoff_behaviour must be one of {', '.join(CUTOFF_BEHAVIOURS)}.",
                status_code=400,
            )
        config.cutoff_behaviour = data["cutoff_behaviour"]
    if "degrade_model" in data:
        degrade_model = data["degrade_model"]
        if degrade_model is not None and (
            not isinstance(degrade_model, str) or len(degrade_model) > 100
        ):
            return api_error(
                "degrade_model must be a string up to 100 chars or null.",
                status_code=400,
            )
        config.degrade_model = degrade_model or None
    if "chat_enabled" in data:
        if not isinstance(data["chat_enabled"], bool):
            return api_error("chat_enabled must be a boolean.", status_code=400)
        config.chat_enabled = data["chat_enabled"]
    if "opencode_workspace" in data:
        # Repo mode grants filesystem access, so only a Site Admin may
        # change it. Re-stating the current value is a no-op anyone may do
        # (otherwise instance admins could never save an opencode config,
        # since edit forms always submit the field).
        if data["opencode_workspace"] not in OPENCODE_WORKSPACES:
            return api_error(
                f"opencode_workspace must be one of {', '.join(OPENCODE_WORKSPACES)}.",
                status_code=400,
            )
        if data["opencode_workspace"] != (
            config.opencode_workspace or "sandbox"
        ) and not is_site_admin(user):
            return api_error(
                "opencode_workspace can only be changed by a Site Admin.",
                status_code=403,
            )
        config.opencode_workspace = data["opencode_workspace"]
    if "use_proxy" in data:
        if not isinstance(data["use_proxy"], bool):
            return api_error("use_proxy must be a boolean.", status_code=400)
        if data["use_proxy"] and not config.virtual_key:
            return api_error(
                "Provision a proxy key first (provision-proxy-key CLI).",
                status_code=400,
            )
        config.use_proxy = data["use_proxy"]
    db.session.commit()
    return api_ok({"config": config.to_dict()})


@bp.route("/instances/<uuid:instance_id>/spend", methods=["GET"])
@token_required
def instance_spend(user, instance_id):
    """Spend totals (rolling 30d) + budget status per configured provider."""
    from sqlalchemy import func

    from app.models import AISpendLedger, InstanceAIConfig
    from app.services.llm_backends import SPEND_WINDOW_DAYS, instance_spend_cents

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    rows = (
        db.session.query(
            AISpendLedger.provider,
            func.coalesce(func.sum(AISpendLedger.prompt_tokens), 0),
            func.coalesce(func.sum(AISpendLedger.completion_tokens), 0),
            func.coalesce(func.sum(AISpendLedger.cost_cents), 0),
        )
        .filter(AISpendLedger.instance_id == instance.id)
        .group_by(AISpendLedger.provider)
        .all()
    )
    by_provider = {
        provider: {
            "prompt_tokens": int(pt or 0),
            "completion_tokens": int(ct or 0),
            "cost_cents": int(cost or 0),
        }
        for provider, pt, ct, cost in rows
    }
    budgets = {}
    for config in InstanceAIConfig.query.filter_by(instance_id=instance.id).all():
        spent = instance_spend_cents(instance.id) if config.budget_cents else None
        budgets[config.provider] = {
            "budget_cents": config.budget_cents,
            "spent_cents": spent,
            "exhausted": spent is not None and spent >= config.budget_cents,
        }
    return api_ok(
        {
            "instance_id": str(instance.id),
            "window_days": SPEND_WINDOW_DAYS,
            "by_provider": by_provider,
            "budgets": budgets,
        }
    )


@bp.route("/instances/<uuid:instance_id>/build-targets", methods=["GET"])
@token_required
def list_build_targets(user, instance_id):
    """Named repos BUILD_CODE runs may write into (this instance)."""
    from app.models import InstanceBuildTarget

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    targets = (
        InstanceBuildTarget.query.filter_by(instance_id=instance.id)
        .order_by(InstanceBuildTarget.name)
        .all()
    )
    from app.services.build_service import build_roots

    roots = build_roots()
    from app.models import SystemSettings

    settings = SystemSettings.get_instance()
    configured = ((settings.builds or {}).get("default_root") or "").strip() or None
    return api_ok(
        {
            "targets": [t.to_dict() for t in targets],
            "defaults": {
                "projects_root": roots[0] if roots else None,
                "configured_root": configured,
            },
        }
    )


@bp.route("/instances/<uuid:instance_id>/build-targets", methods=["POST"])
@token_required
def create_build_target(user, instance_id):
    """Register a repo for BUILD_CODE runs. Path must resolve under
    OPENCODE_BUILD_ROOTS and be an existing directory (fail closed)."""
    from app.models import InstanceBuildTarget
    from app.services.build_service import BuildError, ensure_target_path

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name or len(name) > 100:
        return api_error("name is required (up to 100 chars).", status_code=400)
    if InstanceBuildTarget.query.filter_by(instance_id=instance.id, name=name).first():
        return api_error(
            f"A build target named '{name}' already exists.", status_code=409
        )
    try:
        path = ensure_target_path(data.get("path"))
    except BuildError as exc:
        return api_error(str(exc), status_code=400)
    target = InstanceBuildTarget(
        instance_id=instance.id,
        name=name,
        path=path,
        created_by_id=user.id,
    )
    db.session.add(target)
    db.session.commit()
    return api_ok({"target": target.to_dict()}, status_code=201)


@bp.route(
    "/instances/<uuid:instance_id>/build-targets/<uuid:target_id>",
    methods=["DELETE"],
)
@token_required
def delete_build_target(user, instance_id, target_id):
    """Remove a build target (pending previews for it can no longer write)."""
    from app.models import InstanceBuildTarget

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    target = InstanceBuildTarget.query.filter_by(
        id=target_id, instance_id=instance.id
    ).first()
    if target is None:
        return api_error("Unknown build target for this instance.", status_code=404)
    db.session.delete(target)
    db.session.commit()
    return api_ok({"deleted": str(target_id)})


def _managed_row(instance_id, app_id):
    from app.models import ManagedApp

    return ManagedApp.query.filter_by(id=app_id, instance_id=instance_id).first()


def _managed_live(row):
    """Stored fields plus fresh status. Health-first: pid checks are
    container-local, so a pid the web container cannot see proves
    nothing — an answering health endpoint means running (this adopts
    processes orphaned by earlier failures instead of misreporting
    them stopped). Only a silent health endpoint + dead pid reconciles
    a `running` row back to stopped."""
    from app.services.runner import get_runner, poll_health

    data = row.to_dict()
    healthy = poll_health(row.health_url)
    if healthy is True:
        if row.state != "running":
            row.state = "running"
            row.last_error = None
            db.session.commit()
            data = row.to_dict()
        data["live"] = {
            "state": "running",
            "healthy": True,
            "pid": row.pid,
        }
        return data
    live = get_runner().status(row.pid, row.health_url)
    if row.state == "running" and live["state"] == "stopped":
        row.state = "stopped"
        row.pid = None
        row.stopped_at = datetime.now(timezone.utc)
        db.session.commit()
        data = row.to_dict()
        live = {"state": "stopped", "healthy": None, "pid": None}
    data["live"] = live
    return data


def _spec_from_build_version(version_row, target, idea_ref):
    """Runnable spec from a written BUILD_CODE version. Returns (spec dict,
    display command, error message). Never executes anything.

    Paths here are worker-visible (container) paths: supervised processes
    run inside worker containers, where host paths do not exist. Display
    strings stay host-native in the runbook itself.
    """
    import os
    import sys

    from app.services.build_service import container_path, server_path
    from app.tasks.ollama_tasks import _derive_runbook

    out = version_row.result_data or {}
    if not out.get("written"):
        return None, None, "Only confirmed builds can run — confirm the preview first."
    host_root = out.get("target_host_path") or server_path(
        out.get("target_path") or (target.path if target else "")
    )
    files = out.get("files") or []
    manifest = [
        {"path": f.get("path"), "content": f.get("content", "")}
        for f in files
        if isinstance(f, dict) and f.get("path")
    ]
    runbook = out.get("runbook") if isinstance(out.get("runbook"), dict) else None
    if runbook is None or not (runbook or {}).get("workdir_container"):
        # Missing or pre-container-shape runbook: re-derive so argv is
        # container-native. Stored display strings stay untouched.
        try:
            runbook = _derive_runbook(
                manifest,
                out.get("start_command"),
                host_root,
                out.get("target_path") or (target.path if target else ""),
            )
        except Exception:
            runbook = None
    argv = (runbook or {}).get("run_argv") if runbook else None
    if not argv:
        return (
            None,
            None,
            (
                "This build has no runnable command recorded — "
                "recreate it with the current builder."
            ),
        )
    setup_argv = (runbook or {}).get("setup_argv") or []
    pip_argv = (runbook or {}).get("pip_argv") or []
    venv_dir = (runbook or {}).get("workdir") or ""
    # Container working folder first (runner context); host path only as
    # a last resort for rows predating container-native runbooks.
    workdir = (
        (runbook or {}).get("workdir_container")
        or container_path((runbook or {}).get("workdir") or "")
        or None
    )
    if not workdir:
        workdir = out.get("target_path") or (target.path if target else "") or None
    if not workdir:
        return None, None, "This build has no working folder recorded."
    try:
        port = int(out.get("port")) if out.get("port") else None
    except (TypeError, ValueError):
        port = None
    from app.tasks.ollama_tasks import _host_network_ip

    def _network_url(url):
        if not isinstance(url, str) or not url.strip():
            return None
        import re

        ip = _host_network_ip()
        return re.sub(r"^(https?://)(?:localhost|127\.0\.0\.1)(?=[:/])", r"\g<1>" + ip, url.strip(), count=1)

    app_url = _network_url(out.get("app_url")) or (out.get("app_url") or "").strip() or None
    frontend_url = _network_url(out.get("frontend_url")) or (out.get("frontend_url") or "").strip() or None
    try:
        frontend_port = int(out.get("frontend_port")) if out.get("frontend_port") else None
    except (TypeError, ValueError):
        frontend_port = None
    project_root = (out.get("target_path") or (target.path if target else "") or "").strip()
    frontend_root = None
    has_frontend = False
    for entry in files:
        path = str((entry or {}).get("path") or "").replace("\\", "/")
        if path == "frontend/src/index.html" or path.startswith("frontend/src/"):
            frontend_root = os.path.join(project_root, "frontend", "src")
            has_frontend = True
            break
    if not has_frontend:
        for entry in files:
            path = str((entry or {}).get("path") or "").replace("\\", "/")
            if path == "frontend/index.html" or path.startswith("frontend/"):
                frontend_root = os.path.join(project_root, "frontend")
                has_frontend = True
                break
    if frontend_root is None:
        for rel in ("frontend/src", "frontend", "src"):
            cand = os.path.join(project_root, rel) if project_root else ""
            if cand and os.path.isfile(os.path.join(cand, "index.html")):
                frontend_root = cand
                has_frontend = True
                break
    frontend_run_argv = None
    if has_frontend and frontend_root and frontend_port:
        backend_for_proxy = app_url or (
            f"http://127.0.0.1:{port}" if port else "http://127.0.0.1:8000"
        )
        frontend_run_argv = [
            sys.executable,
            "/app/app/services/frontend_proxy.py",
            "--port",
            str(frontend_port),
            "--root",
            frontend_root,
            "--backend",
            backend_for_proxy,
        ]
    # Open goes to the human UI when this runner can serve it; otherwise
    # fall back to the API root.
    open_url = frontend_url if frontend_run_argv else app_url
    log_path = workdir.rstrip("/") + "/.brainstormer/" + idea_ref + ".log"
    display = (runbook or {}).get("run") or str(out.get("start_command") or "")
    spec = {
        "workdir": workdir,
        "venv_dir": venv_dir,
        "run_argv": argv,
        "setup_argv": setup_argv,
        "pip_argv": pip_argv,
        "log_path": log_path,
        "health_url": app_url,
        "open_url": open_url,
        "frontend_run_argv": frontend_run_argv,
        "frontend_workdir": frontend_root,
        "frontend_log_path": log_path if frontend_run_argv else None,
    }
    return spec, display, None


@bp.route("/instances/<uuid:instance_id>/managed-apps", methods=["GET"])
@token_required
def list_managed_apps(user, instance_id):
    """Supervised apps with live status (stale running rows reconcile)."""
    from app.models import ManagedApp

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    rows = (
        ManagedApp.query.filter_by(instance_id=instance.id)
        .order_by(ManagedApp.updated_at.desc())
        .all()
    )
    return api_ok({"apps": [_managed_live(r) for r in rows]})


@bp.route("/instances/<uuid:instance_id>/managed-apps", methods=["POST"])
@token_required
def upsert_managed_app(user, instance_id):
    """Point supervision at a confirmed build (creates or reconfigures).
    Body: {idea_id, target_id}. Only written versions can run."""
    import uuid as uuid_mod

    from app.models import Idea, InstanceBuildTarget, ManagedApp, SecondaryActionResult

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    try:
        idea_id = uuid_mod.UUID(str(data.get("idea_id")))
        target_id = uuid_mod.UUID(str(data.get("target_id")))
    except (ValueError, TypeError, AttributeError):
        return api_error("idea_id and target_id are required.", status_code=400)
    idea = Idea.query.filter_by(id=idea_id, instance_id=instance.id).first()
    if idea is None:
        return api_error("Unknown idea for this instance.", status_code=404)
    target = InstanceBuildTarget.query.filter_by(
        id=target_id, instance_id=instance.id
    ).first()
    if target is None:
        return api_error("Unknown build target for this instance.", status_code=404)
    versions = (
        SecondaryActionResult.query.filter_by(idea_id=idea.id, action_type="BUILD_CODE")
        .order_by(SecondaryActionResult.version.desc())
        .all()
    )
    version_row = next(
        (
            r
            for r in versions
            if (r.result_data or {}).get("written")
            and str(r.target_id or "") == str(target.id)
        ),
        None,
    )
    if version_row is None:
        return api_error(
            "Nothing runnable here yet — confirm a build for this repo first.",
            status_code=400,
        )
    spec, display, spec_err = _spec_from_build_version(
        version_row, target, idea.reference_code
    )
    if spec_err:
        return api_error(spec_err, status_code=400)
    out = version_row.result_data or {}
    try:
        port = int(out.get("port")) if out.get("port") else None
    except (TypeError, ValueError):
        port = None
    row = ManagedApp.query.filter_by(idea_id=idea.id, target_id=target.id).first()
    created = row is None
    if created:
        row = ManagedApp(
            instance_id=instance.id,
            idea_id=idea.id,
            target_id=target.id,
            state="stopped",
        )
        db.session.add(row)
    row.target_name = target.name
    row.build_version = version_row.version
    row.port = port
    row.workdir = spec["workdir"]
    row.command = display
    row.health_url = spec["health_url"]
    row.open_url = spec.get("open_url") or spec["health_url"]
    row.log_path = spec["log_path"]
    row.spec = spec
    db.session.commit()
    return api_ok(
        {"app": _managed_live(row), "reconfigured": not created},
        status_code=201 if created else 200,
    )


@bp.route(
    "/instances/<uuid:instance_id>/managed-apps/<uuid:app_id>/start",
    methods=["POST"],
)
@token_required
def start_managed_app_route(user, instance_id, app_id):
    """Enqueue the (slow) bring-up: venv setup, install, launch, record."""
    from app.models import ManagedApp
    from app.tasks.supervision_tasks import start_managed_app

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    row = _managed_row(instance.id, app_id)
    if row is None:
        return api_error("Unknown supervised app for this instance.", status_code=404)
    if not (row.spec or {}).get("run_argv"):
        return api_error(
            "The recorded start command cannot be run safely — "
            "reconfigure from a current build first.",
            status_code=400,
        )
    # Double presses must not launch twins. Two signals, either wins:
    # an answering health endpoint (cross-container truth), or a live
    # pid in this namespace (same-process truth, e.g. tests). A starting
    # row older than 30 minutes is an orphaned task (see:
    # unregistered-task loss) — allow a retry.
    from app.services.runner import get_runner, poll_health

    if poll_health(row.health_url) is True:
        row.state = "running"
        row.last_error = None
        db.session.commit()
        return api_ok({"app": _managed_live(row), "already": True})
    live = get_runner().status(row.pid, None)
    if live["state"] == "running" and live["pid"] == row.pid:
        row.state = "running"
        row.last_error = None
        db.session.commit()
        return api_ok({"app": _managed_live(row), "already": True})
    if row.state == "starting" and row.updated_at is not None:
        from app.models.types import ensure_aware

        age = datetime.now(timezone.utc) - ensure_aware(row.updated_at)
        if age.total_seconds() < 30 * 60:
            return api_ok({"app": _managed_live(row), "already": True})
    row.state = "starting"
    row.last_error = None
    from app.models import PromptRun, PromptRunStatus

    run = PromptRun(
        instance_id=instance.id,
        action_type="APP_START",
        triggered_by="manual",
        idea_id=row.idea_id,
        status=PromptRunStatus.PENDING,
        job_type="app",
        queue="default",
    )
    db.session.add(run)
    db.session.commit()
    start_managed_app.apply_async(
        args=[str(row.id), str(run.id)],
        queue="default",
        soft_time_limit=1500,
        time_limit=1620,
    )
    return api_ok({"app": _managed_live(row)}, status_code=202)


@bp.route(
    "/instances/<uuid:instance_id>/managed-apps/<uuid:app_id>/stop",
    methods=["POST"],
)
@token_required
def stop_managed_app_route(user, instance_id, app_id):
    """Enqueue the stop on a worker: pids are container-local, so only a
    worker sharing the spawner's PID namespace may signal the process
    group (a direct kill from the web container could hit an unrelated
    process reusing the same pid)."""
    from app.models import ManagedApp
    from app.tasks.supervision_tasks import stop_managed_app

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    row = _managed_row(instance.id, app_id)
    if row is None:
        return api_error("Unknown supervised app for this instance.", status_code=404)
    row.state = "stopping"
    from app.models import PromptRun, PromptRunStatus

    run = PromptRun(
        instance_id=instance.id,
        action_type="APP_STOP",
        triggered_by="manual",
        idea_id=row.idea_id,
        status=PromptRunStatus.PENDING,
        job_type="app",
        queue="default",
    )
    db.session.add(run)
    db.session.commit()
    stop_managed_app.apply_async(
        args=[str(row.id), str(run.id)],
        queue="default",
        soft_time_limit=120,
        time_limit=180,
    )
    return api_ok({"app": _managed_live(row)}, status_code=202)


@bp.route(
    "/instances/<uuid:instance_id>/managed-apps/<uuid:app_id>/logs",
    methods=["GET"],
)
@token_required
def managed_app_logs(user, instance_id, app_id):
    """Tail the app's stdout/stderr log (newest last, capped)."""
    from app.models import ManagedApp
    from app.services.runner import get_runner

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    row = _managed_row(instance.id, app_id)
    if row is None:
        return api_error("Unknown supervised app for this instance.", status_code=404)
    try:
        lines = max(1, min(int(request.args.get("lines", 200)), 500))
    except (TypeError, ValueError):
        lines = 200
    return api_ok(
        {"lines": get_runner().tail(row.log_path or "", lines), "state": row.state}
    )


@bp.route("/instances/<uuid:instance_id>/oauth", methods=["GET"])
@token_required
def list_oauth_configs(user, instance_id):
    """Social login credentials per provider (secrets never leave)."""
    from app.models import TenantOAuthConfig

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    configs = TenantOAuthConfig.query.filter_by(instance_id=instance.id).all()
    return api_ok({"configs": [c.to_dict() for c in configs]})


@bp.route("/instances/<uuid:instance_id>/oauth", methods=["PUT"])
@token_required
def upsert_oauth_config(user, instance_id):
    """Create or update one provider's OAuth credentials (secret write-only).

    Apple note: paste a generated client-secret JWT (Apple has no static
    secret); rotation happens at Apple, then update here.
    """
    from app.models import OAUTH_PROVIDERS, TenantOAuthConfig

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    provider = (data.get("provider") or "").strip().lower()
    if provider not in OAUTH_PROVIDERS:
        return api_error(
            f"provider is required and must be one of {', '.join(OAUTH_PROVIDERS)}.",
            status_code=400,
        )
    client_id = (data.get("client_id") or "").strip()
    if not client_id or len(client_id) > 255:
        return api_error("client_id is required (max 255 chars).", status_code=400)
    secret = data.get("client_secret")
    if secret is not None and not isinstance(secret, str):
        return api_error("client_secret must be a string or null.", status_code=400)
    config = TenantOAuthConfig.query.filter_by(
        instance_id=instance.id, provider_name=provider
    ).first()
    if config is None:
        config = TenantOAuthConfig(instance_id=instance.id, provider_name=provider)
        db.session.add(config)
    config.client_id = client_id
    if secret:
        config.client_secret = secret
    elif secret is None:
        config._client_secret = None
    db.session.commit()
    return api_ok({"config": config.to_dict()})


def _member_entry(membership):
    from app.models import User as UserModel

    member = UserModel.query.get(membership.user_id)
    return {
        "user_id": str(membership.user_id),
        "email": member.email if member else None,
        "name": member.name if member else None,
        "role": membership.role,
    }


@bp.route("/instances/<uuid:instance_id>/members", methods=["GET"])
@token_required
def list_members(user, instance_id):
    """Membership roster for one instance."""
    from app.models import Membership as MembershipModel

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    memberships = MembershipModel.query.filter_by(instance_id=instance.id).all()
    return api_ok({"members": [_member_entry(m) for m in memberships]})


@bp.route("/instances/<uuid:instance_id>/members", methods=["POST"])
@token_required
def add_member(user, instance_id):
    """Add an existing user to an instance (by email)."""
    from app.models import (
        ASSIGNABLE_ROLES,
        Membership as MembershipModel,
        User as UserModel,
    )

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return api_error("email is required.", 400)
    target = UserModel.query.filter_by(email=email).first()
    if target is None:
        return api_error("No user with that email.", 404)
    role = data.get("role", "USER")
    if role not in ASSIGNABLE_ROLES:
        return api_error(f"role must be one of {ASSIGNABLE_ROLES}.", 400)
    existing = MembershipModel.query.filter_by(
        user_id=target.id, instance_id=instance.id
    ).first()
    if existing is not None:
        return api_error("User is already a member of this instance.", 409)
    m = MembershipModel(user_id=target.id, instance_id=instance.id, role=role)
    db.session.add(m)
    db.session.commit()
    return api_ok({"member": _member_entry(m)}, "Added.", 201)


def _last_admin_guard(instance_id, target_user_id):
    from app.models import Membership as MembershipModel
    from app.models import ROLE_INSTANCE_ADMIN

    others = MembershipModel.query.filter(
        MembershipModel.instance_id == instance_id,
        MembershipModel.role == ROLE_INSTANCE_ADMIN,
        MembershipModel.user_id != target_user_id,
    ).count()
    if others == 0:
        return api_error("Cannot remove the last instance admin.", 409)
    return None


@bp.route("/instances/<uuid:instance_id>/members/<uuid:member_id>", methods=["PATCH"])
@token_required
def update_member(user, instance_id, member_id):
    """Change a member's role (any assignable role; SITE_ADMIN is global-only)."""
    from app.models import (
        ASSIGNABLE_ROLES,
        ROLE_INSTANCE_ADMIN,
        ROLE_USER,
        Membership as MembershipModel,
    )

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    if data.get("role") not in ASSIGNABLE_ROLES:
        return api_error(
            f"role must be one of {', '.join(ASSIGNABLE_ROLES)}.", status_code=400
        )
    membership = MembershipModel.query.filter_by(
        user_id=member_id, instance_id=instance.id
    ).first()
    if membership is None:
        return api_error("Member not found.", 404)
    if str(member_id) == str(user.id) and not is_site_admin(user):
        return api_error("You cannot change your own membership.", 403)
    if membership.role == ROLE_INSTANCE_ADMIN and data["role"] == ROLE_USER:
        blocked = _last_admin_guard(instance.id, member_id)
        if blocked:
            return blocked
    membership.role = data["role"]
    db.session.commit()
    return api_ok({"member": _member_entry(membership)})


@bp.route("/instances/<uuid:instance_id>/members/<uuid:member_id>", methods=["DELETE"])
@token_required
def remove_member(user, instance_id, member_id):
    """Remove a membership (never yourself, never the last admin)."""
    from app.models import ROLE_INSTANCE_ADMIN, Membership as MembershipModel

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    membership = MembershipModel.query.filter_by(
        user_id=member_id, instance_id=instance.id
    ).first()
    if membership is None:
        return api_error("Member not found.", 404)
    if str(member_id) == str(user.id):
        return api_error("You cannot remove your own membership.", 403)
    if membership.role == ROLE_INSTANCE_ADMIN:
        blocked = _last_admin_guard(instance.id, member_id)
        if blocked:
            return blocked
    db.session.delete(membership)
    db.session.commit()
    return api_ok({"removed": str(member_id)})


@bp.route("/instances/<uuid:instance_id>/export", methods=["GET"])
@token_required
def export_instance_bundle(user, instance_id):
    """Download this instance's JSON bundle (self-service export)."""
    from flask import jsonify

    from app.services import backup as backup_svc

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    try:
        bundle = backup_svc.export_instance(instance.id)
    except backup_svc.BackupIntegrityError as exc:
        return api_error(str(exc), 404)
    response = jsonify(bundle)
    response.headers["Content-Disposition"] = (
        f"attachment; filename=instance-{instance.number}.json"
    )
    return response


@bp.route("/instances/<uuid:instance_id>/entitlements", methods=["GET"])
@token_required
def list_entitlements(user, instance_id):
    """Granted keys (resolved) plus stored overrides and billing flags."""
    from app.models import InstanceEntitlement, resolve_entitlements

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    rows = InstanceEntitlement.query.filter_by(instance_id=instance.id).all()
    return api_ok(
        {
            "instance_id": str(instance.id),
            "is_free": instance.is_free,
            "status": instance.status,
            "granted": sorted(resolve_entitlements(instance)),
            "overrides": [r.to_dict() for r in rows],
        }
    )


@bp.route("/instances/<uuid:instance_id>/entitlements", methods=["PUT"])
@site_admin_required
def set_entitlement(user, instance_id):
    """Grant/revoke one entitlement (site admin; billing is manual)."""
    from app.models import ENTITLEMENTS, InstanceEntitlement

    instance = Instance.query.get(instance_id)
    if instance is None:
        return api_error("Not found.", 404)
    data = request.get_json(silent=True) or {}
    key = (data.get("key") or "").strip()
    if key not in ENTITLEMENTS:
        return api_error(
            f"key must be one of {', '.join(ENTITLEMENTS)}.", status_code=400
        )
    granted = data.get("granted", True)
    if not isinstance(granted, bool):
        return api_error("granted must be a boolean.", status_code=400)
    limits = data.get("limits", {})
    if not isinstance(limits, dict):
        return api_error("limits must be an object.", status_code=400)
    row = InstanceEntitlement.query.filter_by(instance_id=instance.id, key=key).first()
    if row is None:
        row = InstanceEntitlement(instance_id=instance.id, key=key)
        db.session.add(row)
    row.granted = granted
    row.limits = dict(limits)
    db.session.commit()
    return api_ok({"entitlement": row.to_dict()})


@bp.route("/instances/<uuid:instance_id>/github-config", methods=["GET"])
@token_required
def get_github_config(user, instance_id):
    """Per-instance GitHub push settings (PAT never returned)."""
    from app.models import InstanceGitHubConfig

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    row = InstanceGitHubConfig.query.filter_by(instance_id=instance.id).first()
    return api_ok({"github_config": row.to_dict() if row else None})


@bp.route("/instances/<uuid:instance_id>/github-config", methods=["PUT"])
@token_required
def upsert_github_config(user, instance_id):
    """Create or update the instance's GitHub repo + PAT (admin)."""
    import re

    from app.models import InstanceGitHubConfig

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    row = InstanceGitHubConfig.query.filter_by(instance_id=instance.id).first()
    if row is None:
        row = InstanceGitHubConfig(instance_id=instance.id, repo="", branch="main")
        db.session.add(row)
    if "repo" in data:
        repo = (data.get("repo") or "").strip()
        if repo and not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            return api_error("repo must look like 'owner/name'.", status_code=400)
        if repo:
            row.repo = repo
    if "branch" in data:
        branch = (data.get("branch") or "").strip() or "main"
        if len(branch) > 100:
            return api_error("branch must be 100 characters or fewer.", status_code=400)
        row.branch = branch
    if "pat" in data:
        pat = data.get("pat")
        if pat is None or (isinstance(pat, str) and not pat.strip()):
            row.pat = None
        elif isinstance(pat, str):
            row.pat = pat.strip()
        else:
            return api_error("pat must be text.", status_code=400)
    if not row.repo:
        db.session.rollback()
        return api_error("repo is required (e.g. 'my-org/my-app').", status_code=400)
    db.session.commit()
    return api_ok({"github_config": row.to_dict()})


@bp.route("/instances/<uuid:instance_id>/github-config", methods=["DELETE"])
@token_required
def delete_github_config(user, instance_id):
    """Remove the instance's GitHub settings (pushes stop working)."""
    from app.models import InstanceGitHubConfig

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    InstanceGitHubConfig.query.filter_by(instance_id=instance.id).delete()
    db.session.commit()
    return api_ok({"cleared": str(instance.id)})


@bp.route("/instances/<uuid:instance_id>/stage-config", methods=["GET"])
@token_required
def list_stage_configs(user, instance_id):
    """Per-stage AI settings for one instance (stages without rows inherit)."""
    from app.models import STAGES, StageAIConfig

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    rows = StageAIConfig.query.filter_by(instance_id=instance.id).all()
    by_stage = {r.stage: r.to_dict() for r in rows}
    return api_ok(
        {
            # Return an entry for every stage: configured ones carry their
            # settings, unconfigured ones carry just the stage name so the
            # frontend can render an "inherits" card with an edit button.
            "stages": [by_stage.get(stage) or {"stage": stage} for stage in STAGES],
        }
    )


@bp.route("/instances/<uuid:instance_id>/stage-config", methods=["PUT"])
@token_required
def upsert_stage_config(user, instance_id):
    """Create or update one stage's AI settings (unchecked keys inherit)."""
    from app.models import PROVIDERS, STAGES, StageAIConfig

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    stage = (data.get("stage") or "").strip().upper()
    if stage not in STAGES:
        return api_error(
            f"stage is required and must be one of {', '.join(STAGES)}.",
            status_code=400,
        )
    provider = data.get("provider")
    if provider is not None:
        provider = str(provider).strip().lower() or None
        if provider is not None and provider not in PROVIDERS:
            return api_error(
                f"provider must be one of {', '.join(PROVIDERS)}.",
                status_code=400,
            )
    temperature = _optional_float(data.get("temperature"), "temperature", 0, 2)
    if isinstance(temperature, tuple):
        return temperature
    top_p = _optional_float(data.get("top_p"), "top_p", 0, 1)
    if isinstance(top_p, tuple):
        return top_p
    num_predict = data.get("num_predict")
    if num_predict is not None:
        try:
            num_predict = int(num_predict)
        except (TypeError, ValueError):
            return api_error("num_predict must be an integer.", status_code=400)
        if not 1 <= num_predict <= 4096:
            return api_error("num_predict must be 1-4096.", status_code=400)
    for list_key in ("skills", "guidelines"):
        if list_key in data and (
            not isinstance(data[list_key], list)
            or any(not isinstance(v, str) for v in data[list_key])
        ):
            return api_error(f"{list_key} must be a list of strings.", status_code=400)
    model_name = data.get("model_name")
    if model_name is not None:
        model_name = str(model_name).strip() or None
        if model_name is not None and len(model_name) > 100:
            return api_error(
                "model_name must be 100 characters or fewer.", status_code=400
            )
    row = StageAIConfig.query.filter_by(instance_id=instance.id, stage=stage).first()
    if row is None:
        row = StageAIConfig(instance_id=instance.id, stage=stage)
        db.session.add(row)
    if "provider" in data:
        row.provider = provider
    if "model_name" in data:
        row.model_name = model_name
    if "temperature" in data:
        row.temperature = temperature
    if "top_p" in data:
        row.top_p = top_p
    if "num_predict" in data:
        row.num_predict = num_predict
    if "skills" in data:
        row.skills = list(data["skills"])
    if "guidelines" in data:
        row.guidelines = list(data["guidelines"])
    db.session.commit()
    return api_ok({"stage_config": row.to_dict()})


def _optional_float(value, name, lo, hi):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return api_error(f"{name} must be a number.", status_code=400)
    if not lo <= number <= hi:
        return api_error(f"{name} must be between {lo} and {hi}.", status_code=400)
    return number
