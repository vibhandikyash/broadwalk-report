"""Dependency-free SVG line chart for the rent trend on page 3.

Every string that comes from data (series names, axis labels) is XML-escaped; the markup is later
inserted with Jinja's `safe`, so this module is the one place responsible for making it inert.
"""
from __future__ import annotations

import re
from xml.sax.saxutils import escape as _xml_escape

_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")


def escape(s: str) -> str:
    return _xml_escape(s, {'"': "&quot;", "'": "&#39;"})


def _color(c: str) -> str:
    return c if _COLOR_RE.match(c or "") else "#000000"


def line_chart_svg(labels: list[str], series: list[dict], width: int = 760, height: int = 380) -> str:
    """series: [{"name": str, "values": [float | None, ...], "color": "#hex", "dash": bool}]"""
    vals = [v for s in series for v in s.get("values", []) if v is not None]
    if not labels or not vals:
        return ""
    pad_l, pad_r, pad_t, pad_b = 56, 16, 20, 62
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 0.1
    lo, hi = lo - span * 0.15, hi + span * 0.15
    n = len(labels)

    def x(i: int) -> float:
        return pad_l + (width - pad_l - pad_r) * (i / max(n - 1, 1))

    def y(v: float) -> float:
        return pad_t + (height - pad_t - pad_b) * (1 - (v - lo) / (hi - lo))

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" class="chart" role="img">']
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        yy = y(v)
        out.append(f'<line x1="{pad_l}" x2="{width - pad_r}" y1="{yy:.1f}" y2="{yy:.1f}" class="grid"/>')
        out.append(f'<text x="{pad_l - 8}" y="{yy + 4:.1f}" class="ylab">${v:.2f}</text>')
    step = max(1, n // 12)
    for i, lab in enumerate(labels):
        if i % step == 0 or i == n - 1:
            out.append(f'<text x="{x(i):.1f}" y="{height - pad_b + 18}" class="xlab">{escape(str(lab))}</text>')
    for s in series:
        dash = ' stroke-dasharray="5,4"' if s.get("dash") else ""
        color = _color(s.get("color", ""))
        pts = [(x(i), y(v)) for i, v in enumerate(s.get("values", [])) if v is not None]
        if not pts:
            continue
        d = " ".join(f"{'M' if j == 0 else 'L'}{px:.1f},{py:.1f}" for j, (px, py) in enumerate(pts))
        out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2"{dash}/>')
        out.extend(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2.5" fill="{color}"/>' for px, py in pts)
    lx, ly = pad_l, height - 14
    for s in series:
        dash = ' stroke-dasharray="5,4"' if s.get("dash") else ""
        name = str(s.get("name", ""))
        out.append(f'<line x1="{lx}" x2="{lx + 22}" y1="{ly}" y2="{ly}" stroke="{_color(s.get("color", ""))}" stroke-width="2"{dash}/>')
        out.append(f'<text x="{lx + 28}" y="{ly + 4}" class="legend">{escape(name)}</text>')
        lx += 28 + int(6.2 * len(name)) + 22
    out.append("</svg>")
    return "".join(out)
