"""Shared types for extractors."""
from __future__ import annotations

from pydantic import BaseModel, Field as PField


class ExtractionError(ValueError):
    """The part was recognised, but the structure the extractor needs is not there."""


class Extraction(BaseModel):
    doc_type: str
    locator: str
    data: dict
    warnings: list[str] = PField(default_factory=list)
    # How the text this extraction read was obtained; set centrally by registry.run_extractor so no
    # extractor has to remember it. See registry.part_provenance for the shape.
    provenance: dict = PField(default_factory=dict)
