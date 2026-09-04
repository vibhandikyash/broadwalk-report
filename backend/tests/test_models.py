# backend/tests/test_models.py
from app.models import Column, Field, ReportData, Section, Table


def sample() -> ReportData:
    t = Table(title="T", columns=[Column(key="label", label="Label", kind="text"), Column(key="amt", label="Amount"),
                                  Column(key="var", label="Var", derived=True)])
    row = t.new_row("r1", label="Row one")
    row["amt"].value, row["amt"].status = 10, "extracted"
    t.totals["amt"] = Field(label="Amount", kind="money", status="derived")
    sec = Section(key="s", title="S", page=1, fields={"x": Field(label="X", kind="money", value=5, status="extracted")}, tables={"t": t})
    return ReportData(sections={"s": sec})


def test_path_lookup_and_effective_value():
    d = sample()
    assert d.value("s.fields.x") == 5 and d.value("s.tables.t.rows.r1.amt") == 10
    assert d.field("s.tables.t.totals.amt").status == "derived" and d.field("nope.fields.x") is None
    d.field("s.fields.x").override = 7
    assert d.value("s.fields.x") == 7 and d.field("s.fields.x").value == 5


def test_set_derived_only_touches_derived_fields():
    d = sample()
    d.set_derived("s.tables.t.rows.r1.var", 3)
    d.set_derived("s.fields.x", 99)
    assert d.value("s.tables.t.rows.r1.var") == 3 and d.value("s.fields.x") == 5


def test_new_row_statuses_and_iter_fields():
    d = sample()
    row = d.table("s.tables.t").rows["r1"]
    assert row["label"].status == "missing" and row["var"].status == "derived"
    paths = [p for p, _ in d.iter_fields()]
    assert paths == ["s.fields.x", "s.tables.t.rows.r1.label", "s.tables.t.rows.r1.amt", "s.tables.t.rows.r1.var", "s.tables.t.totals.amt"]
    assert d.model_validate(d.model_dump()).value("s.fields.x") == 5
