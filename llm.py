"""Optional language-model layer.

PawPal+ works fully without this module. If ``ANTHROPIC_API_KEY`` is set
and the ``anthropic`` package is installed, ``write_explanation`` asks the
model to turn the agent's verified facts into a friendly summary. Any
failure (no key, no package, network error) returns ``None`` and the
caller falls back to a built-in template.
"""
import os
from typing import Optional

DEFAULT_MODEL = os.environ.get("PAWPAL_MODEL", "claude-sonnet-5-5")

SYSTEM_PROMPT = (
    "You write short, friendly pet-care schedule summaries. Use ONLY the "
    "facts and guidance snippets provided. Never give medication doses. "
    "Never invent veterinary advice. If a health concern appears, tell the "
    "owner to contact a veterinarian. Keep it under 120 words."
)


def is_available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def write_explanation(facts: str) -> Optional[str]:
    """Return model text for ``facts``, or ``None`` if unavailable."""
    if not is_available():
        return None
    try:
        import anthropic

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": facts}],
        )
        return "".join(
            block.text for block in response.content
            if getattr(block, "type", "") == "text"
        ).strip() or None
    except Exception:
        return None
