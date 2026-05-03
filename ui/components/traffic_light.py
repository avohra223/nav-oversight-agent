"""Traffic-light indicator for severity / confidence."""
from __future__ import annotations

from ..styling import SEVERITY_COLOR


def traffic_light_html(
    severity: str, confidence: float | None = None, size: int = 12,
) -> str:
    """Return inline HTML for a colour-coded indicator.

    Severity drives the colour; confidence drives the opacity (so a low-
    confidence HIGH is paler than a high-confidence HIGH).
    """
    severity = (severity or "NONE").upper()
    color = SEVERITY_COLOR.get(severity, "#52525b")
    if confidence is None:
        opacity = 0.85
    else:
        opacity = max(0.35, min(1.0, 0.45 + 0.55 * float(confidence)))
    return (
        f'<span style="display:inline-block; width:{size}px; height:{size}px; '
        f'background:{color}; opacity:{opacity:.2f}; border-radius:50%; '
        f'vertical-align:middle; box-shadow: 0 0 0 1px #292524 inset;"></span>'
    )
