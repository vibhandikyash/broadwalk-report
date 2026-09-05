"""The completeness specification: one place decides what a finished investor report needs."""
import pytest

from app.consolidate.builder import apply_overrides, build
from app.consolidate.calc import recompute
from app.consolidate.completeness import REQUIREMENTS, evaluate, is_required, fill_gaps_for_test
from tests.test_builder import sample_files


def _data(overrides=None):
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    apply_overrides(data, overrides or {})
    recompute(data)
    return data


def test_sample_data_reports_every_manual_group_as_a_gap():
    result = evaluate(_data())
    assert not result.complete and result.gap_count == len(result.gaps) > 20
    groups = {g.group for g in result.gaps}
    assert {"property", "business_plan", "underwriting", "financing", "status", "goals", "narratives"} <= groups
    paths = {g.path for g in result.gaps}
    assert {"financing.fields.lender", "capital.fields.business_plan_summary", "underwriting.tables.budget", "status.fields.status1_title",
            "status.fields.goal1_title", "commentary.fields.takeaway", "property.fields.building_class"} <= paths
    assert all(g.page in range(1, 11) and g.label and g.reason for g in result.gaps)
    assert [g.key for g in REQUIREMENTS][:3] == ["property", "in_place_rent", "capital"]


def test_filling_every_gap_through_overrides_makes_the_report_complete():
    data = _data()
    overrides = fill_gaps_for_test(data)  # plausible typed values for every gap, as a reviewer would enter them
    assert overrides["fields"]["financing.fields.lender"] and overrides["rows"]["underwriting.tables.budget"]
    result = evaluate(_data(overrides))
    assert result.complete and result.gap_count == 0 and result.ai_drafts_pending == 0
    assert all(g.complete for g in result.groups)


def test_zero_no_activity_and_missing_stay_distinct():
    data = _data()
    base = fill_gaps_for_test(data)
    # a genuine zero satisfies a capital requirement; None does not
    zero = {**base, "fields": {**base["fields"], "capital.fields.quarter_distributions": 0}}
    assert "capital.fields.quarter_distributions" not in {g.path for g in evaluate(_data(zero)).gaps}
    none = {**base, "fields": {k: v for k, v in base["fields"].items() if k != "capital.fields.quarter_distributions"}}
    d = _data(none)
    d.field("capital.fields.quarter_distributions").value = None
    d.field("capital.fields.quarter_distributions").override = None
    assert "capital.fields.quarter_distributions" in {g.path for g in evaluate(d).gaps}
    # leasing: rows = activity; empty + reviewed note = no activity; empty without note = missing
    d = _data(base)
    for key in ("new_leases", "renewals"):
        d.table(f"occupancy.tables.{key}").rows.clear()
    recompute(d)
    gaps = {g.path for g in evaluate(d).gaps}
    assert "occupancy.tables.new_leases" in gaps and "occupancy.fields.no_activity_note" in gaps
    d.field("occupancy.fields.no_activity_note").override = "No new leases or renewals commenced in the quarter; the rent roll was fully stabilised."
    gaps = {g.path for g in evaluate(d).gaps}
    assert "occupancy.tables.new_leases" not in gaps and "occupancy.fields.no_activity_note" not in gaps
    assert "occupancy.fields.new_lease_narrative" not in gaps  # table-bound narratives are not required when the table is empty


def test_optional_fields_are_never_gaps_and_drafts_count_as_populated():
    data = _data()
    assert not is_required("underwriting.fields.business_plan_title") and not is_required("status.fields.status1_subtitle")
    assert not is_required("in_place_rent.fields.prior_variance_note") and is_required("financing.fields.lender")
    paths = {g.path for g in evaluate(data).gaps}
    assert "underwriting.fields.business_plan_title" not in paths and "status.fields.status1_subtitle" not in paths
    overrides = fill_gaps_for_test(data)
    overrides["fields"].pop("commentary.fields.takeaway")
    overrides["ai_drafts"] = {"commentary.fields.takeaway": "Revenue finished below budget."}
    result = evaluate(_data(overrides))
    assert result.complete and result.ai_drafts_pending == 1


def test_reconciliation_warnings_block_completeness():
    from app.models import Issue

    data = _data(fill_gaps_for_test(_data()))
    ok = evaluate(data, issues=[Issue(path="occupancy.fields.current_date", severity="warning", message="dated differently")])
    assert ok.complete
    bad = evaluate(data, issues=[Issue(path="financials.tables.lines.rows.total_revenue.ptd_actual", severity="warning", message="Total revenue does not equal the sum of its lines")])
    assert not bad.complete and any(g.group == "financials" and "reconcil" in g.reason.lower() for g in bad.gaps)
