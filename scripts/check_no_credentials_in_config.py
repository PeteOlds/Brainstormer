"""Guardrail: git config must not contain credential-bearing remote URLs.

A PAT in ``remote.*.url`` bypasses the credential helper, outlives the user's
shell, and is invisible to ``check_no_secrets.py`` (which only scans tracked
files). Run this locally via pre-commit and in CI via guardrails.yml.

Values are never printed — only the config file and key name are reported.
"""

import subprocess
import sys

TOKEN_PREFIXES = ("ghp_", "github_pat_", "gho_", "ghu_", "ghs_", "ghr_")
HTTP_SCHEMES = ("http", "https")


def url_has_credentials(url: str) -> bool:
    """True for http(s) URLs carrying userinfo (e.g. a token before '@').

    SSH URLs such as ``git@github.com:owner/repo.git`` are not flagged:
    ``git@`` is a username, not a secret.
    """
    scheme, sep, rest = url.partition("://")
    if not sep or scheme.lower() not in HTTP_SCHEMES:
        return False
    _, at, _ = rest.partition("/")[0].partition("@")
    return at == "@"


def offending_entries(config: str) -> list[tuple[str, str]]:
    """Return ``(origin, key)`` pairs for config entries holding credentials.

    ``config`` is the output of ``git config --list --show-origin``. Only
    keys are returned, so callers cannot accidentally echo a token.
    """
    bad: list[tuple[str, str]] = []
    for line in config.splitlines():
        origin, tab, entry = line.partition("\t")
        if not tab:
            continue
        key, equals, value = entry.partition("=")
        if not equals:
            continue
        is_remote_url = key.startswith("remote.") and key.endswith(".url")
        if (is_remote_url and url_has_credentials(value)) or any(
            prefix in value for prefix in TOKEN_PREFIXES
        ):
            bad.append((origin, key))
    return bad


def main() -> int:
    result = subprocess.run(
        ["git", "config", "--list", "--show-origin"],
        capture_output=True,
        text=True,
        check=True,
    )
    problems = offending_entries(result.stdout)
    if problems:
        print("Credentials in git config — use 'gh auth setup-git', not a token in the URL:")
        for origin, key in problems:
            print(f"  {origin}: {key}")
        return 1
    print("OK: no credentials in git config.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
