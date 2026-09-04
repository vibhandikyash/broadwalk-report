"""TOML mapping loaders and the label-pattern matcher used by the builder."""
from __future__ import annotations

import re
import tomllib
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=4)
def load_pl_mapping(config_dir: Path) -> list[dict]:
    return tomllib.loads((config_dir / "pl_mapping.toml").read_text())["rows"]


@lru_cache(maxsize=4)
def load_capex_mapping(config_dir: Path) -> dict:
    return tomllib.loads((config_dir / "capex_mapping.toml").read_text())


def match_lines(lines: list[dict], patterns: list[str], prefer_total: bool = False) -> list[dict]:
    """Patterns are tried in order; the first that hits any line returns all its hits (totals first if asked)."""
    for p in patterns:
        rx = re.compile(p, re.I)
        hits = [ln for ln in lines if not ln.get("unlabeled") and rx.search(ln["norm"])]
        if hits:
            if prefer_total:
                totals = [h for h in hits if h["is_total"]]
                hits = totals or hits
            return hits
    return []


def section_matches(section: list[str], include: list[str], exclude: list[str]) -> bool:
    """Innermost header decides: the first header (from the deepest outward) matching exclude rejects,
    the first matching include accepts. Empty paths never match."""
    for header in reversed(section):
        h = header.lower()
        if any(re.search(x, h) for x in exclude):
            return False
        if any(re.search(x, h) for x in include):
            return True
    return False


def consume_capex(lines: list[dict], mapping_rows: list[dict]) -> tuple[list[tuple[dict, list[dict]]], list[dict]]:
    """Group lines by mapping rows in order; each line is consumed once. Returns (groups, leftover)."""
    remaining = list(lines)
    groups: list[tuple[dict, list[dict]]] = []
    for row in mapping_rows:
        rxs = [re.compile(p, re.I) for p in row["match"]]
        hit = [ln for ln in remaining if any(rx.search(ln["norm"]) for rx in rxs)]
        remaining = [ln for ln in remaining if ln not in hit]
        groups.append((row, hit))
    return groups, remaining
