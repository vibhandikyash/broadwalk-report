"""ReportData -> the JSON shape the review screen renders (flat lists, paths on every leaf)."""
from __future__ import annotations

from ..consolidate.completeness import evaluate
from ..consolidate.provenance import counts, describe, source_files
from ..consolidate.validate import summary
from ..models import Field, Issue, ReportData
from ..report.render import appendix_items, number_pages


def field_json(path: str, key: str, f: Field, data: ReportData) -> dict:
    return {
        "path": path, "key": key, "label": f.label, "kind": f.kind, "value": f.value, "override": f.override,
        "effective": f.effective, "status": "manual" if f.override is not None else f.status,
        "source": f.source.model_dump() if f.source else None, "provenance": describe(path, f, data).to_json(),
        "alternatives": [a.model_dump() for a in f.alternatives], "note": f.note, "readonly": f.status == "derived",
    }


def to_ui(data: ReportData, issues: list[Issue], row: dict) -> dict:
    # Which sheet of the live preview each section lands on. The data-sources sheets between the fixed
    # pages mean a report page is not the n-th sheet, so the review screen cannot work this out itself.
    printed, _sheets, preview_total = number_pages(appendix_items(data))
    sections = []
    for sk, sec in data.sections.items():
        fields = [field_json(f"{sk}.fields.{k}", k, f, data) for k, f in sec.fields.items()]
        tables = []
        for tk, t in sec.tables.items():
            tp = f"{sk}.tables.{tk}"
            rows = []
            for rk, r in t.rows.items():
                meta = t.row_meta.get(rk, {})
                rows.append({"key": rk, "label": meta.get("label", rk), "manual": bool(meta.get("manual")), "subject": bool(meta.get("subject")),
                             "cells": [field_json(f"{tp}.rows.{rk}.{c.key}", c.key, r[c.key], data) for c in t.columns if c.key in r]})
            totals = [field_json(f"{tp}.totals.{c.key}", c.key, t.totals[c.key], data) for c in t.columns if c.key in t.totals]
            tables.append({"path": tp, "key": tk, "title": t.title, "columns": [c.model_dump() for c in t.columns],
                           "rows": rows, "totals": totals, "editable_rows": t.editable_rows})
        sections.append({"key": sk, "title": sec.title, "page": sec.page, "preview_page": printed.get(sec.page, sec.page),
                         "fields": fields, "tables": tables})
    return {"built_at": row.get("built_at"), "summary": {**summary(data, issues), "completeness": evaluate(data, issues).to_json()},
            "issues": [i.model_dump() for i in issues],
            "sections": sections, "meta": data.meta, "narrative_status": row.get("narrative_status"),
            "narrative_error": row.get("narrative_error"), "preview_total_pages": preview_total,
            "provenance": {"counts": counts(data), "files": source_files(data)}}
