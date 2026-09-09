"""The structured intermediate representation: sections of fields and tables.

Every leaf is a Field with a value, a status, a source locator and an optional user override.
Paths: '<section>.fields.<name>' | '<section>.tables.<table>.rows.<row>.<col>' | '<section>.tables.<table>.totals.<col>'.
"""
from __future__ import annotations

from typing import Any, Iterator, Literal

from pydantic import BaseModel, Field as PField

Kind = Literal["money", "number", "integer", "percent", "date", "text", "longtext"]
Status = Literal["extracted", "derived", "manual", "ai_draft", "missing", "conflict"]
# How the text a value was read from reached the extractor. 'mixed' means the file needed OCR on some
# page but this value's page could not be pinned down, so it must be reviewed as if it were OCR.
Method = Literal["native", "ocr", "mixed"]


class Source(BaseModel):
    file_id: str | None = None
    filename: str | None = None
    locator: str | None = None
    text: str | None = None
    doc_type: str | None = None
    method: Method = "native"
    ocr_confidence: float | None = None


class Alternative(BaseModel):
    value: Any = None
    source: Source | None = None
    note: str | None = None


class Field(BaseModel):
    label: str
    kind: Kind = "text"
    value: Any = None
    status: Status = "missing"
    source: Source | None = None
    alternatives: list[Alternative] = PField(default_factory=list)
    override: Any = None
    note: str | None = None

    @property
    def effective(self) -> Any:
        return self.override if self.override is not None else self.value


class Column(BaseModel):
    key: str
    label: str
    kind: Kind = "money"
    derived: bool = False


class Table(BaseModel):
    title: str
    columns: list[Column]
    rows: dict[str, dict[str, Field]] = PField(default_factory=dict)
    row_meta: dict[str, dict[str, Any]] = PField(default_factory=dict)
    totals: dict[str, Field] = PField(default_factory=dict)
    editable_rows: bool = False

    def new_row(self, key: str, label: str | None = None, manual: bool = False) -> dict[str, Field]:
        row = {
            c.key: Field(label=c.label, kind=c.kind, status="derived" if c.derived else ("manual" if manual else "missing"))
            for c in self.columns
        }
        self.rows[key] = row
        self.row_meta[key] = {"label": label or key, "manual": manual}
        return row


class Section(BaseModel):
    key: str
    title: str
    page: int
    fields: dict[str, Field] = PField(default_factory=dict)
    tables: dict[str, Table] = PField(default_factory=dict)


class Issue(BaseModel):
    path: str | None = None
    severity: Literal["error", "warning", "info"] = "warning"
    message: str


class ReportData(BaseModel):
    sections: dict[str, Section] = PField(default_factory=dict)
    meta: dict[str, Any] = PField(default_factory=dict)

    def table(self, path: str) -> Table | None:
        p = path.split(".")
        if len(p) < 3 or p[1] != "tables" or p[0] not in self.sections:
            return None
        return self.sections[p[0]].tables.get(p[2])

    def field(self, path: str) -> Field | None:
        p = path.split(".")
        try:
            sec = self.sections[p[0]]
            if p[1] == "fields":
                return sec.fields.get(p[2])
            if p[1] == "tables":
                t = sec.tables[p[2]]
                if p[3] == "rows":
                    return t.rows[p[4]].get(p[5])
                if p[3] == "totals":
                    return t.totals.get(p[4])
        except (KeyError, IndexError):
            return None
        return None

    def value(self, path: str) -> Any:
        f = self.field(path)
        return None if f is None else f.effective

    def set_derived(self, path: str, value: Any) -> None:
        f = self.field(path)
        if f is not None and f.status == "derived":
            f.value = value

    def iter_fields(self) -> Iterator[tuple[str, Field]]:
        for sk, sec in self.sections.items():
            for fk, f in sec.fields.items():
                yield f"{sk}.fields.{fk}", f
            for tk, t in sec.tables.items():
                for rk, row in t.rows.items():
                    for ck, f in row.items():
                        yield f"{sk}.tables.{tk}.rows.{rk}.{ck}", f
                for ck, f in t.totals.items():
                    yield f"{sk}.tables.{tk}.totals.{ck}", f
