"""Optional structured tracing for narrow-heuristic decisions.

Enabled by setting the ``CONVERTER_TRACE`` environment variable to any
non-empty value (typically ``CONVERTER_TRACE=1``). When disabled (default),
``trace`` is a near-zero-cost noop — guards short-circuit before formatting.

Used by phase_rules / voice_policy to surface which narrow heuristic fired
on a given save, so unfamiliar games can be triaged without shotgun-debugging
the entire converter.

Output format (one line per event)::

    TRACE category key=value key=value ...

Default sink is stderr. Override by assigning ``_trace.sink`` to any callable
``f(line: str) -> None``.
"""
from __future__ import annotations
import os
import sys
from typing import Any, Callable

# Read once at import time; toggling mid-run requires re-import.
ENABLED = bool(os.environ.get("CONVERTER_TRACE"))


def _default_sink(line: str) -> None:
    sys.stderr.write(line + "\n")


sink: Callable[[str], None] = _default_sink


def trace(category: str, **fields: Any) -> None:
    """Emit a trace event.  Noop unless ``CONVERTER_TRACE`` is set."""
    if not ENABLED:
        return
    parts = [f"{k}={_format_value(v)}" for k, v in fields.items()]
    sink(f"TRACE {category} " + " ".join(parts))


def _format_value(v: Any) -> str:
    if isinstance(v, int):
        # Hex form for register-shaped values; decimal otherwise.
        if v >= 0x100:
            return f"0x{v:X}"
        return str(v)
    if isinstance(v, bytes):
        return v.hex()
    return repr(v)
