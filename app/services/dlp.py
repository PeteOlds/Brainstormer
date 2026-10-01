"""DLP masking ahead of hosted providers (Phase 10).

Local Ollama calls are untouched (data never leaves the box). Anything
headed to OpenAI/Anthropic/Gemini — direct or via the proxy — passes
through `mask_text` first: emails, phone numbers, API-key-shaped
secrets, Slack tokens and JWT-like blobs become `[redacted:<kind>]`.
Only counts cross into logs; values never do.
"""

import re

_PATTERNS = (
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("phone", re.compile(r"\+?\d[\d .()-]{7,}\d")),
    ("api_key", re.compile(r"\b(sk|pk|rk|AKIA|xox[baprs])[-_A-Za-z0-9]{8,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")),
    ("fernet_token", re.compile(r"gAAAAA[A-Za-z0-9_-]+=*")),
)


def mask_text(text: str) -> tuple[str, dict[str, int]]:
    """Return (masked_text, {kind: count}). No-op on empty input."""
    if not text:
        return text, {}
    counts: dict[str, int] = {}
    masked = text
    for kind, pattern in _PATTERNS:
        masked, n = pattern.subn(f"[redacted:{kind}]", masked)
        if n:
            counts[kind] = n
    return masked, counts
