"""Guardrail: app code may only reach the network through approved modules.

Approved: app/services/ollama_client.py (local Ollama),
app/services/social_auth.py (OIDC provider endpoints),
app/services/slack_service.py (Slack SDK), LiteLLM via
app/services/llm_backends.py. Everything else must stay offline
(per-instance opt-in lives in those modules, never scattered).
"""

import re
import sys
from pathlib import Path

APPROVED = {
    "app/services/ollama_client.py",
    "app/services/social_auth.py",
    "app/services/slack_service.py",
    "app/services/llm_backends.py",
    "app/services/embedding_service.py",  # httpx only to local Ollama
    "app/routes/health.py",  # httpx only to local Ollama readiness probe
    "app/routes/prompts.py",  # httpx only to local Ollama test-stream
    "app/routes/billing.py",  # httpx only to api.stripe.com (portal link)
}

PATTERN = re.compile(
    r"^\s*(import\s+(requests|httpx|urllib[A-Za-z_.]*)|"
    r"from\s+(requests|httpx|urllib[A-Za-z_.]*)\s+import)"
)

failures = []
for path in sorted(Path("app").rglob("*.py")):
    rel = path.as_posix()
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        if PATTERN.match(line) and rel not in APPROVED:
            failures.append(f"{rel}:{lineno}: {line.strip()}")

if failures:
    print("Unapproved network imports (route via the provider interface):")
    print("\n".join(failures))
    sys.exit(1)
print(f"OK: network imports confined to {len(APPROVED)} approved modules.")
