# backend/tests/test_extract_registry.py
import pytest

from app.classify.classifier import DocType
from app.extract.base import ExtractionError
from app.extract.registry import EXTRACTORS, run_extractor
from tests.helpers import BUDGET_ROWS, sheet_part


def test_every_known_doc_type_has_an_extractor():
    missing = [t.value for t in DocType if t is not DocType.UNKNOWN and t.value not in EXTRACTORS]
    assert missing == []


def test_run_extractor_dispatches_and_rejects_unknown():
    ex = run_extractor(sheet_part(BUDGET_ROWS, DocType.YARDI_BUDGET_COMPARISON))
    assert ex.doc_type == DocType.YARDI_BUDGET_COMPARISON and ex.data["lines"]
    with pytest.raises(ExtractionError):
        run_extractor(sheet_part([["x"]], DocType.UNKNOWN))
