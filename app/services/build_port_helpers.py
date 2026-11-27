"""Host/port allocation helpers for generated builds.

Moved out of build_runtime.py to keep modules focused. Re-exported there
so existing callers keep working.
"""

import os
import re

def _host_network_ip() -> str:
    """Best-effort LAN IP of this machine (never 127.x) for shareable URLs."""
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
        finally:
            sock.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return "localhost"


def _rewrite_compose_host_port(files: list, old: int, new: int) -> tuple[list, int]:
    """Point a compose manifest's published host ports at ``new``.

    Only entries publishing ``old`` are touched; the container side is
    never changed, so the app's own code keeps working unmodified.
    Returns (files, changed_count). Unparseable compose files are left
    alone (0 changes) rather than risked.
    """
    try:
        import yaml
    except ImportError:
        return files, 0
    changed = 0
    out = []
    for entry in files or []:
        if not isinstance(entry, dict):
            out.append(entry)
            continue
        low = str(entry.get("path") or "").lower()
        if not (
            low.endswith("docker-compose.yml") or low.endswith("docker-compose.yaml")
        ):
            out.append(entry)
            continue
        try:
            compose = yaml.safe_load(entry.get("content") or "") or {}
        except Exception:
            out.append(entry)
            continue
        if not isinstance(compose, dict):
            out.append(entry)
            continue
        touched = False
        services = compose.get("services") or {}
        if isinstance(services, dict):
            for _name, svc in services.items():
                if not isinstance(svc, dict) or not isinstance(svc.get("ports"), list):
                    continue
                rewritten = []
                for mapping in svc["ports"]:
                    if isinstance(mapping, int) and mapping == old:
                        # Expose-only form pins nothing: pin HOST:new so
                        # the URL we show actually reaches the app.
                        rewritten.append(f"{new}:{mapping}")
                        touched = True
                    elif isinstance(mapping, str) and mapping.strip():
                        raw = mapping.strip()
                        quote = ""
                        if raw[:1] in "\"'" and raw[-1:] == raw[:1]:
                            quote = raw[:1]
                            raw = raw[1:-1]
                        parts = raw.split(":")
                        try:
                            if len(parts) >= 2 and int(parts[-2]) == old:
                                parts[-2] = str(new)
                                rewritten.append(quote + ":".join(parts) + quote)
                                touched = True
                            elif len(parts) == 1 and int(parts[0]) == old:
                                rewritten.append(quote + f"{new}:{parts[0]}" + quote)
                                touched = True
                            else:
                                rewritten.append(mapping)
                        except ValueError:
                            rewritten.append(mapping)
                    elif isinstance(mapping, dict):
                        try:
                            if (
                                mapping.get("published") is not None
                                and int(mapping["published"]) == old
                            ):
                                mapping = dict(mapping, published=new)
                                touched = True
                        except (TypeError, ValueError):
                            pass
                        rewritten.append(mapping)
                    else:
                        rewritten.append(mapping)
                svc["ports"] = rewritten
        if touched:
            try:
                entry = dict(
                    entry,
                    content=yaml.safe_dump(
                        compose, sort_keys=False, default_flow_style=False
                    ),
                )
                changed += 1
            except Exception:
                pass
        out.append(entry)
    return out, changed


def _rewrite_source_port(files: list, old: int, new: int) -> tuple[list, int]:
    """Point a build's hard-coded listener port at a free one.

    Only files in the write manifest are touched, and only narrow
    patterns that clearly set a listening port (``app.run(... port=8000)``,
    ``uvicorn.run(...)``, ``PORT = 8000``, Node ``.listen(8000)`` / JS
    ``port: 8000``). Returns (files, changed_count). A start command that
    does not name its port is only honest once this rewrite has run.
    """
    import re

    patterns = {
        ".py": (
            re.compile(
                r"(\b(?:app|application|server)\.run\([^)]{0,300}?\bport\s*=\s*)"
                + str(old)
                + r"\b",
                re.S,
            ),
            re.compile(
                r"(\buvicorn\.run\([^)]{0,300}?\bport\s*=\s*)" + str(old) + r"\b",
                re.S,
            ),
            re.compile(r"(\bPORT\s*=\s*)" + str(old) + r"\b"),
        ),
        ".js": (
            re.compile(r"(\.listen\(\s*)" + str(old) + r"\b"),
            re.compile(r"(\bport\s*:\s*)" + str(old) + r"\b"),
        ),
        ".ts": (
            re.compile(r"(\.listen\(\s*)" + str(old) + r"\b"),
            re.compile(r"(\bport\s*:\s*)" + str(old) + r"\b"),
        ),
    }
    changed = 0
    out = []
    for entry in files or []:
        if not isinstance(entry, dict):
            out.append(entry)
            continue
        suffix = os.path.splitext(str(entry.get("path") or "").lower())[1]
        pats = patterns.get(suffix)
        if not pats:
            out.append(entry)
            continue
        text = str(entry.get("content") or "")
        updated = text
        for pattern in pats:
            updated, count = pattern.subn(r"\g<1>" + str(new), updated)
            changed += count
        if updated != text:
            entry = dict(entry, content=updated)
        out.append(entry)
    return out, changed


def _allocate_build_port(runtime: dict, files: list) -> tuple[dict, list, list]:
    """Give a confirmed build a free host port, rewriting host-side refs.

    Checks ``runtime['port']`` against this machine. When busy, allocates
    the next free port and rewrites the app URL, explicit ``--port`` flags
    in the start command, and compose published ports (container side
    untouched). Returns (runtime, files, report_lines) in plain language
    for non-technical users. Never raises: worst case the conflict is
    recorded in the notes and the original port kept.
    """
    from app.services.build_service import allocate_port, port_in_use

    report = []
    try:
        port = int(runtime.get("port")) if runtime.get("port") else None
    except (TypeError, ValueError):
        port = None
    try:
        fport = (
            int(runtime.get("frontend_port")) if runtime.get("frontend_port") else None
        )
    except (TypeError, ValueError):
        fport = None
    try:
        busy = port_in_use(port) if port else False
    except Exception:
        busy = False
    try:
        fbusy = port_in_use(fport) if fport else False
    except Exception:
        fbusy = False
    if not busy and not fbusy:
        return runtime, files, report
    if fbusy:
        # Same for the frontend/dashboard port: the UI URL must open
        # something, so a busy dashboard port moves too.
        import re

        fnew, _ = allocate_port(fport)
        if fnew == fport:
            line = (
                f"Dashboard port {fport} is already in use and no free "
                "port was found nearby — stop the other program first."
            )
        else:
            files, _ = _rewrite_compose_host_port(files, fport, fnew)
            files, _ = _rewrite_source_port(files, fport, fnew)
            runtime = dict(
                runtime,
                frontend_port=fnew,
                frontend_url=f"http://{_host_network_ip()}:{fnew}",
            )
            existing = runtime.get("run_notes")
            if isinstance(existing, str) and existing:
                runtime["run_notes"] = re.sub(
                    r"((?:localhost|127\.0\.0\.1|\d{1,3}(?:\.\d{1,3}){3}))"
                    + r":"
                    + str(fport)
                    + r"\b",
                    lambda m: f"{_host_network_ip()}:{fnew}",
                    existing,
                )
            line = (
                f"Dashboard port {fport} is already in use, so the dashboard "
                f"moved to port {fnew} — the Open link below already uses {fnew}."
            )
        runtime["run_notes"] = "\n".join(
            [n for n in [runtime.get("run_notes"), line] if n]
        )
        report.append(line)
    if not busy:
        return runtime, files, report
    new_port, _changed = allocate_port(port)
    if new_port == port:
        line = (
            f"Port {port} is already in use on this machine and no free "
            "port was found nearby — stop the other program first, then run."
        )
        runtime["run_notes"] = "\n".join(
            [n for n in [runtime.get("run_notes"), line] if n]
        )
        report.append(line)
        return runtime, files, report
    old, new = port, new_port
    runtime = dict(runtime, port=new, port_requested=old, port_changed=True)
    url = runtime.get("app_url")
    if isinstance(url, str) and f":{old}" in url:
        import re

        runtime["app_url"] = re.sub(
            r"(://[^/:]+)" + r":" + str(old) + r"(?=/|$)",
            r"\g<1>" + f":{new}",
            url,
            count=1,
        )
    cmd = runtime.get("start_command")
    cmd_rewritten = False
    if isinstance(cmd, str) and cmd:
        import re

        # Separator class covers `--port 8000`, `--port=8000` and the
        # Dockerfile-CMD JSON-array form `"--port", "8000"`.
        rewritten, n = re.subn(
            r"(--port)([\"',\s=]+)" + str(old) + r"\b",
            lambda m: m.group(1) + m.group(2) + str(new),
            cmd,
        )
        if not n:
            rewritten, n = re.subn(
                r"(PORT=|localhost:|127\.0\.0\.1:)" + str(old) + r"\b",
                lambda m: m.group(1) + str(new),
                cmd,
            )
        if n:
            runtime["start_command"] = rewritten
            cmd_rewritten = True
    files, compose_rewritten = _rewrite_compose_host_port(files, old, new)
    files, source_rewritten = _rewrite_source_port(files, old, new)
    # Notes prose written before allocation names the old port (model and
    # extractor output); point localhost URLs at the new one BEFORE
    # appending the allocation notice (which must keep naming the old).
    existing_notes = runtime.get("run_notes")
    if isinstance(existing_notes, str) and existing_notes:
        import re

        runtime["run_notes"] = re.sub(
            r"((?:localhost|127\.0\.0\.1|\d{1,3}(?:\.\d{1,3}){3}))"
            + r":"
            + str(old)
            + r"\b",
            lambda m: f"{_host_network_ip()}:{new}",
            existing_notes,
        )
    line = (
        f"Port {old} is already in use on this machine, so this build was "
        f"set to port {new} — the commands below already use {new}."
    )
    if not cmd_rewritten and not compose_rewritten and not source_rewritten and cmd:
        line += (
            " The start command does not name its port, so if the app itself "
            f"fixes its port, change that setting to {new} as well."
        )
    runtime["run_notes"] = "\n".join([n for n in [runtime.get("run_notes"), line] if n])
    report.append(line)
    if source_rewritten:
        report.append(
            f"Updated the app's hard-coded listener port from {old} to {new}."
        )
    if compose_rewritten:
        report.append(
            f"docker-compose.yml now publishes {new} on this machine "
            f"(the app inside still uses {old})."
        )
    return runtime, files, report
