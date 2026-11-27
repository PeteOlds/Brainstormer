import os
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from flask import Blueprint, current_app, request

from app.extensions import db
from app.models import Instance, Membership
from app.utils.decorators import admin_required, site_admin_required, token_required
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


def _runbook_entry_exists(runbook, host_root):
    """Whether a stored runbook still points at a real entry point."""
    if not isinstance(runbook, dict):
        return False
    argv = runbook.get("run_argv")
    if not isinstance(argv, list) or not argv:
        return False
    workdir = (
        runbook.get("workdir_container") or runbook.get("workdir") or host_root or ""
    )
    script = None
    for token in argv:
        if isinstance(token, str) and token.endswith(".py"):
            script = token
            break
    if script is None:
        for token in argv:
            if isinstance(token, str) and ":" in token and not token.startswith("http"):
                module = token.split(":", 1)[0]
                candidate = os.path.join(workdir, module.replace(".", os.sep) + ".py")
                if os.path.isfile(candidate):
                    return True
        return True
    return os.path.isfile(os.path.join(workdir, script))


def _spec_from_build_version(version_row, target, idea_ref):
    """Runnable spec from a written BUILD_CODE version. Returns (spec dict,
    display command, error message). Never executes anything.

    Paths here are worker-visible (container) paths: supervised processes
    run inside worker containers, where host paths do not exist. Display
    strings stay host-native in the runbook itself.
    """
    import os
    import sys

    from app.services.build_runtime import (
        _derive_runbook,
        _extract_runtime_info,
        _merge_files,
    )
    from app.services.build_service import (
        container_path,
        existing_repo_files,
        server_path,
    )

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
    # Stored builds are often incremental, and old rows may carry a
    # runbook derived from the preview alone. Merge the repo on disk so
    # both runtime detection and runbook repair see the real entry points.
    try:
        repo_files = existing_repo_files(out.get("target_path") or host_root)
    except Exception:
        repo_files = []
    context = _merge_files(repo_files, manifest)
    preferred_paths = [f["path"] for f in manifest]
    try:
        runtime = _extract_runtime_info(context, preferred_paths=preferred_paths)
    except Exception:
        runtime = {}
    start_command = out.get("start_command") or runtime.get("start_command")
    inferred_port = runtime.get("port")
    runbook = out.get("runbook") if isinstance(out.get("runbook"), dict) else None
    needs_repair = (
        runbook is None
        or not (runbook or {}).get("workdir_container")
        or not _runbook_entry_exists(runbook, host_root)
    )
    fresh = None
    if needs_repair:
        try:
            fresh = _derive_runbook(
                context,
                start_command,
                host_root,
                out.get("target_path") or (target.path if target else ""),
                start_dir=runtime.get("start_dir"),
            )
        except Exception:
            fresh = None
        if fresh and fresh.get("run_argv"):
            runbook = fresh
            start_command = fresh.get("command") or start_command
        elif runbook is None or not (runbook or {}).get("workdir_container"):
            try:
                runbook = _derive_runbook(
                    context,
                    start_command,
                    host_root,
                    out.get("target_path") or (target.path if target else ""),
                    start_dir=runtime.get("start_dir"),
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
    if port is None and inferred_port:
        # Older rows never stored the inferred port; keep the URL honest.
        port = int(inferred_port)
    from app.services.build_runtime import _host_network_ip

    def _network_url(url):
        if not isinstance(url, str) or not url.strip():
            return None
        import re

        ip = _host_network_ip()
        return re.sub(
            r"^(https?://)(?:localhost|127\.0\.0\.1)(?=[:/])",
            r"\g<1>" + ip,
            url.strip(),
            count=1,
        )

    app_url = (
        _network_url(out.get("app_url")) or (out.get("app_url") or "").strip() or None
    )
    if app_url is None and port:
        app_url = f"http://{_host_network_ip()}:{port}"
    frontend_url = (
        _network_url(out.get("frontend_url"))
        or (out.get("frontend_url") or "").strip()
        or None
    )
    try:
        frontend_port = (
            int(out.get("frontend_port")) if out.get("frontend_port") else None
        )
    except (TypeError, ValueError):
        frontend_port = None
    project_root = (
        out.get("target_path") or (target.path if target else "") or ""
    ).strip()
    frontend_root = None
    has_frontend = False
    for entry in context:
        path = str((entry or {}).get("path") or "").replace("\\", "/")
        if path == "frontend/src/index.html" or path.startswith("frontend/src/"):
            frontend_root = os.path.join(project_root, "frontend", "src")
            has_frontend = True
            break
    if not has_frontend:
        for entry in context:
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


def _member_entry(membership):
    from app.models import User as UserModel

    member = UserModel.query.get(membership.user_id)
    return {
        "user_id": str(membership.user_id),
        "email": member.email if member else None,
        "name": member.name if member else None,
        "role": membership.role,
    }


def _last_admin_guard(instance_id, target_user_id):
    from app.models import ROLE_INSTANCE_ADMIN
    from app.models import Membership as MembershipModel

    others = MembershipModel.query.filter(
        MembershipModel.instance_id == instance_id,
        MembershipModel.role == ROLE_INSTANCE_ADMIN,
        MembershipModel.user_id != target_user_id,
    ).count()
    if others == 0:
        return api_error("Cannot remove the last instance admin.", 409)
    return None


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
