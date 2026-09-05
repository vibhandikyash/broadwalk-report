"""Jinja filters for the report. Every filter accepts None and renders an em dash placeholder."""
from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

MINUS = "−"
NONE = "—"


def _round(x: float, decimals: int) -> float:
    """Round half away from zero (1,424.5 -> 1,425), the convention of financial statements; Python's
    default is half-to-even. Twelve significant digits first, to shed binary noise such as 90.4999999."""
    return float(Decimal(f"{x:.12g}").quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP))


def _num(v) -> float | None:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def num(v, decimals: int = 0) -> str:
    x = _num(v)
    if x is None:
        return NONE
    x = _round(x, decimals)
    s = f"{abs(x):,.{decimals}f}"
    return f"({s})" if x < 0 else s


def money(v, decimals: int = 0) -> str:
    x = _num(v)
    if x is None:
        return NONE
    x = _round(x, decimals)
    s = f"${abs(x):,.{decimals}f}"
    return f"{MINUS}{s}" if x < 0 else s


def money_m(v, decimals: int = 1) -> str:
    x = _num(v)
    return NONE if x is None else f"${_round(x / 1e6, decimals):,.{decimals}f}M"


def money_k(v) -> str:
    x = _num(v)
    if x is None:
        return NONE
    return f"${_round(x / 1e6, 2):,.2f}M" if abs(x) >= 1e6 else f"${_round(x / 1e3, 1):,.1f}K"


def signed_money(v, decimals: int = 0) -> str:
    x = _num(v)
    if x is None:
        return NONE
    x = _round(x, decimals)
    sign = "+" if x > 0 else (MINUS if x < 0 else "")
    return f"{sign}${abs(x):,.{decimals}f}"


def signed_num(v, decimals: int = 0) -> str:
    x = _num(v)
    if x is None:
        return NONE
    x = _round(x, decimals)
    if x == 0:
        return "0"
    s = f"{abs(x):,.{decimals}f}"
    return f"+{s}" if x > 0 else f"({s})"


def pct(v, decimals: int = 1, signed: bool = False) -> str:
    x = _num(v)
    if x is None:
        return NONE
    p = _round(x * 100, decimals)
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
    x = _round(x, 0)
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
    return NONE if x is None else f"{_round(x, 0):,.0f}"


def text(v) -> str:
    return NONE if v in (None, "") else str(v)


def sf(v) -> str:
    x = _num(v)
    return NONE if x is None else f"{_round(x, 0):,.0f} sf"


def psf(v) -> str:
    x = _num(v)
    return NONE if x is None else f"${_round(x, 2):,.2f}"


FILTERS = {"num": num, "money": money, "money_m": money_m, "money_k": money_k, "signed_money": signed_money,
           "signed_num": signed_num, "pct": pct, "var_pct": var_pct, "bps": bps, "date_long": date_long,
           "date_short": date_short, "integer": integer, "text": text, "sf": sf, "psf": psf}
