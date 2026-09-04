"""Jinja filters for the report. Every filter accepts None and renders an em dash placeholder."""
from __future__ import annotations

import datetime as dt

MINUS = "−"
NONE = "—"


def _num(v) -> float | None:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def num(v, decimals: int = 0) -> str:
    x = _num(v)
    if x is None:
        return NONE
    s = f"{abs(x):,.{decimals}f}"
    return f"({s})" if x < 0 else s


def money(v, decimals: int = 0) -> str:
    x = _num(v)
    if x is None:
        return NONE
    s = f"${abs(x):,.{decimals}f}"
    return f"{MINUS}{s}" if x < 0 else s


def money_m(v, decimals: int = 1) -> str:
    x = _num(v)
    return NONE if x is None else f"${x / 1e6:,.{decimals}f}M"


def money_k(v) -> str:
    x = _num(v)
    if x is None:
        return NONE
    return f"${x / 1e6:,.2f}M" if abs(x) >= 1e6 else f"${x / 1e3:,.1f}K"


def signed_money(v, decimals: int = 0) -> str:
    x = _num(v)
    if x is None:
        return NONE
    sign = "+" if x > 0 else (MINUS if x < 0 else "")
    return f"{sign}${abs(x):,.{decimals}f}"


def signed_num(v, decimals: int = 0) -> str:
    x = _num(v)
    if x is None:
        return NONE
    if x == 0:
        return "0"
    s = f"{abs(x):,.{decimals}f}"
    return f"+{s}" if x > 0 else f"({s})"


def pct(v, decimals: int = 1, signed: bool = False) -> str:
    x = _num(v)
    if x is None:
        return NONE
    p = x * 100
    if signed:
        sign = "+" if p > 0 else (MINUS if p < 0 else "")
        return f"{sign}{abs(p):.{decimals}f}%"
    return f"{MINUS}{abs(p):.{decimals}f}%" if p < 0 else f"{p:.{decimals}f}%"


def var_pct(v) -> str:
    x = _num(v)
    if x is None:
        return NONE
    return "flat" if abs(x) < 0.0005 else pct(x, 1, True)


def bps(v) -> str:
    x = _num(v)
    if x is None:
        return NONE
    sign = "+" if x > 0 else (MINUS if x < 0 else "")
    return f"{sign}{abs(x):,.0f} bps"


def _date(v) -> dt.date | None:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def date_long(v) -> str:
    d = _date(v)
    return NONE if d is None else f"{d:%b} {d.day}, {d.year}"


def date_short(v) -> str:
    d = _date(v)
    return NONE if d is None else f"{d:%b} ’{d.year % 100:02d}"


def integer(v) -> str:
    x = _num(v)
    return NONE if x is None else f"{x:,.0f}"


def text(v) -> str:
    return NONE if v in (None, "") else str(v)


def sf(v) -> str:
    x = _num(v)
    return NONE if x is None else f"{x:,.0f} sf"


def psf(v) -> str:
    x = _num(v)
    return NONE if x is None else f"${x:,.2f}"


FILTERS = {"num": num, "money": money, "money_m": money_m, "money_k": money_k, "signed_money": signed_money,
           "signed_num": signed_num, "pct": pct, "var_pct": var_pct, "bps": bps, "date_long": date_long,
           "date_short": date_short, "integer": integer, "text": text, "sf": sf, "psf": psf}
