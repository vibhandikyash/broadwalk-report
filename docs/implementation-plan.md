# Investor Report Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A locally runnable Angular + FastAPI application that ingests a set of multifamily source files (Yardi, HelloData, CoStar, Slate exports), extracts the data behind a quarterly LP investor report, lets a user review and correct every value with source traceability, and renders the 10-page report as a PDF that can be regenerated after edits.

**Architecture:** Files are read into a neutral `Document` (sheets of cells, or pages of text), each sheet/document is classified by content into a `DocType`, a per-type extractor turns it into a typed JSON payload with row/page provenance, and a builder consolidates all payloads into one generic `ReportData` model (sections of `Field`s and `Table`s, every leaf carrying value, status, and source). Derived numbers are recomputed from effective values on every read so user overrides propagate; validation flags missing, conflicting, and non-reconciling values. An in-process thread pool processes files as isolated jobs; a Jinja HTML template rendered by headless Chromium produces the PDF.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, stdlib sqlite3, openpyxl, pdfplumber, Jinja2, Playwright (Chromium), pytest; Angular (latest stable, standalone components, signals), TypeScript, plain CSS. Optional: `anthropic` SDK for drafting narrative paragraphs.

**Deadline context:** Delivery is Friday 2026-09-11 12:00 PM ET; budget is 40 labor hours. Time estimates per task are given so the build order can be cut from the tail (narratives, then polish) if needed.

---

## 0. Orientation for the implementer

### 0.1 What the report is

Read `OUTPUT-FILE-Boardwalk-2Q26 Quarterly Investor Reporting.pdf` (10 landscape pages, 720x405pt, rendered from HTML by Chrome). Page by page, with the source that feeds it:

| Page | Section key | Content | Feeds from |
|---|---|---|---|
| 1 | `property` | Cover: name, city, units, vintage, acquired, purchase price, prepared by | Rent roll, CoStar PDF sale comps, balance sheet |
| 2 | `property`, `in_place_rent` | Description facts, in-place rent by floor-plan group QoQ | Market Rent Schedules (two dates), HelloData comps (address) |
| 3 | `capital`, `underwriting`, `rent_trend` | Purchase price, equity, contributions, distributions; original underwriting budget; rent trend chart | Balance sheet, Slate PDFs, Rent Chart workbook |
| 4 | `financing` | Loan terms | Balance sheet (principal, accrued interest), Slate (borrower entity); the rest is manual |
| 5 | `commentary` | Narrative variance commentary | Derived KPIs from `financials`/`capex`; prose is manual or AI-drafted |
| 6 | `financials` | 2Q and YTD actual vs budget table | Yardi Budget Comparison |
| 7 | `capex` | Capital projects table | Yardi Budget Comparison capex sections |
| 8 | `submarket` | CoStar KPIs, comp table | CoStar Excel + PDF, HelloData listings + comps metadata, rent roll (subject occupancy) |
| 9 | `occupancy` | Occupancy at two dates, lease trade-out by floor plan | Rent rolls, Yardi Lease Trade-Out |
| 10 | `status` | Status update and next-quarter goals | Manual or AI-drafted; two numbers from the P&L |

Verified derivations (they reproduce the example to the dollar) are encoded in the builder. Values the example report shows but no file contains (loan terms, underwriting budget, acreage, class, insurance renewal, comp unit counts) become **manual fields flagged `missing`**. Never hard-code them.

### 0.2 Source dataset

`SOURCE FILES/` next to this plan is dataset 1. Two unseen datasets will be used for grading, with different filenames, file counts, values, layouts, and missing pieces. Rules that follow from that:

- Never key on filenames, sheet names, cell positions, unit-type codes (`BWK.A1`), or GL account numbers. Locate by header text and label text.
- Every extractor must fail on its own (raise `ExtractionError`) without failing the file or the project.
- Every extracted value must carry `{file, sheet or page, row}` provenance.
- When two files could feed the same section, pick deterministically, record the alternative, and let the user switch.

### 0.3 Repository layout

The repo root is `Claude/` next to `SOURCE FILES/` (the implementation was placed there on the user's instruction; the plan originally named it `investor-report-app/`). All paths below are relative to that root unless they start with `/`.

```
investor-report-app/
  .gitignore
  .env.example
  README.md
  backend/
    pyproject.toml
    requirements.txt
    requirements-dev.txt
    config/
      pl_mapping.toml            # P&L canonical rows -> label patterns
      capex_mapping.toml         # capex sections + optional regrouping rows
    app/
      __init__.py
      main.py                    # FastAPI app, lifespan, health
      config.py                  # Settings from env / .env
      db.py                      # sqlite3 schema + thin data-access functions
      models.py                  # Field, Table, Section, ReportData, Issue
      readers/
        __init__.py
        document.py              # Sheet/Page/Document + cell helpers (norm, to_number, header_block)
        xlsx_reader.py
        pdf_reader.py
        registry.py              # extension -> reader
      classify/
        __init__.py
        classifier.py            # DocType, Part, classify(document)
      extract/
        __init__.py
        base.py                  # Extraction, ExtractionError, provenance helpers
        yardi_common.py          # period/as-of parsing, line walker with section stack
        yardi_budget.py
        yardi_balance_sheet.py
        yardi_rent_roll.py
        yardi_rent_schedule.py
        yardi_lto.py
        hellodata_listings.py
        hellodata_comps.py
        costar_excel.py
        costar_pdf.py
        rent_chart.py
        slate.py
        registry.py              # DocType -> extractor function
      consolidate/
        __init__.py
        select.py                # choose sources when several files could feed a section
        mapping.py               # TOML mapping loader + label matcher
        calc.py                  # pure math + recompute(data)
        builder.py               # extractions -> ReportData
        validate.py              # Issues: missing, conflict, reconciliation
      report/
        __init__.py
        formatters.py            # Jinja filters
        chart.py                 # SVG line chart
        render.py                # HTML render + Playwright PDF
        templates/report.html
        static/report.css
        static/fonts/            # optional bundled fonts (see Task 24)
      services/
        __init__.py
        narrative.py             # optional Claude drafting
      workers/
        __init__.py
        pool.py                  # ThreadPoolExecutor job runner
        jobs.py                  # process_file, build, generate_report, draft_narratives
      api/
        __init__.py
        serialize.py             # ReportData -> UI JSON
        projects.py
        files.py
        report_data.py
        report.py
    tests/
      conftest.py
      helpers.py                 # make_xlsx(), sample sheets
      test_db.py ... test_dataset.py
    data/                        # runtime, gitignored: app.db, projects/<id>/uploads, reports
  frontend/
    (Angular CLI workspace)
    proxy.conf.json
    src/app/
      app.config.ts, app.routes.ts, app.component.ts
      core/models.ts, core/api.service.ts
      shared/stepper.component.ts, shared/status-chip.component.ts, shared/source-popover.component.ts
      pages/projects/projects.component.ts
      pages/files/files.component.ts
      pages/review/review.component.ts, field-editor.component.ts, table-editor.component.ts
      pages/report/report.component.ts
    src/styles.css
```

### 0.4 Data contracts used by every task

**Path grammar** (used by overrides, validation issues, the UI, and the template):

```
<section>.fields.<field>
<section>.tables.<table>.rows.<rowKey>.<column>
<section>.tables.<table>.totals.<column>
```
Table path for row operations: `<section>.tables.<table>`.

**Field statuses:** `extracted` (read from a file), `derived` (computed, read-only in UI), `manual` (typed by user), `ai_draft` (drafted by LLM, must be reviewed), `missing` (required but not found), `conflict` (two sources disagree; alternatives listed).

**Percent convention:** every `percent` field stores a fraction (`0.9053`), never `90.53`. Formatters multiply by 100.

**Money convention:** floats in dollars, signs as in the report (expenses positive, credits negative, variances favorable-positive per Yardi).

**Overrides JSON** (stored per project, survives re-processing):
```json
{
  "fields": {"financing.fields.lender": "Fannie Mae"},
  "rows": {"underwriting.tables.budget": {"manual_a1b2c3": {"category": "Amenity Upkeep", "section": "value_add", "original_budget": 75000, "spent_to_date": 0}}},
  "deleted_rows": {"submarket.tables.comps": ["westwood-apartments"]},
  "ai_drafts": {"commentary.fields.takeaway": "Revenue finished ..."}
}
```

**Extraction payload** (stored per file, list of):
```json
{"doc_type": "yardi_budget_comparison", "locator": "sheet 'Report1'", "data": {...type specific...}, "warnings": []}
```

**HTTP API** (all under `/api`):

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | `{ok, llm_enabled, pdf_renderer, workers}` |
| GET | `/doc-types` | list of `{key, label}` for the override dropdown |
| POST | `/projects` | body `{name}` → project |
| GET | `/projects` | list with `file_count` |
| GET | `/projects/{pid}` | project + `files[]` + `stage` (`upload`/`processing`/`review`/`generated`) + `report_built` + `reports[]` |
| DELETE | `/projects/{pid}` | removes rows and files on disk |
| POST | `/projects/{pid}/files` | multipart `files[]` → file records; queues processing |
| GET | `/projects/{pid}/files` | file records |
| PATCH | `/projects/{pid}/files/{fid}` | `{ignored?, doc_type_override?}` → re-process / rebuild |
| POST | `/projects/{pid}/files/{fid}/reprocess` | re-run reader+classify+extract |
| DELETE | `/projects/{pid}/files/{fid}` | remove file, rebuild |
| GET | `/projects/{pid}/files/{fid}/extraction` | `{parts, extractions}` raw payload |
| GET | `/projects/{pid}/report-data` | UI shape (sections/fields/tables/issues/summary) |
| POST | `/projects/{pid}/report-data/rebuild` | force consolidation |
| PATCH | `/projects/{pid}/report-data` | `{changes[], add_rows[], delete_rows[]}` → UI shape |
| POST | `/projects/{pid}/narratives` | queue AI drafting (503 if no key) |
| GET | `/projects/{pid}/report/preview` | rendered HTML |
| POST | `/projects/{pid}/reports` | create version, queue PDF render |
| GET | `/projects/{pid}/reports` | versions |
| GET | `/projects/{pid}/reports/{rid}` | one version (status/error) |
| GET | `/projects/{pid}/reports/{rid}/download` | the PDF |

### 0.5 Conventions

- Python: type hints everywhere, `from __future__ import annotations`, no global mutable state except the worker pool singleton, log with `logging.getLogger(__name__)`.
- Tests: pytest; synthetic workbooks built in-test with openpyxl (client data is never committed). Run from `backend/`: `pytest -q`.
- Commits after every task, plain messages (`feat: ...`, `test: ...`), no AI co-author trailers.
- Mark deliberate shortcuts with a `# ponytail:` comment naming the upgrade path.

### 0.6 Build order and time budget (40 h)

| Milestone | Tasks | Hours | Calendar |
|---|---|---|---|
| A. Scaffold, DB, readers, classifier | 1-5 | 4 | Fri 9/5 |
| B. Yardi extractors | 6-10 | 7 | Fri 9/5 to Sat 9/6 |
| C. Market extractors + registry | 11-14 | 4 | Sat 9/6 |
| D. Model, selection, calc, builder, validation | 15-19 | 7 | Sun 9/7 |
| E. Workers + API | 20-22 | 4 | Mon 9/8 |
| F. Template, chart, PDF | 23-25 | 5 | Mon 9/8 to Tue 9/9 |
| G. Narratives (optional), dataset test, README | 26-28 | 3 | Tue 9/9 |
| H. Frontend | 29-34 | 6 | Wed 9/10 |
| Buffer / packaging | | 2 | Thu 9/11 AM |

If behind schedule after milestone F, skip Task 26 (narratives) and document it as a limitation.

---

# Part A: Backend

### Task 1: Repository scaffold and health endpoint

**Files:**
- Create: `.gitignore`, `.env.example`, `backend/pyproject.toml`, `backend/requirements.txt`, `backend/requirements-dev.txt`, `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/main.py`, `backend/tests/conftest.py`, `backend/tests/test_health.py`

- [ ] **Step 1: Create the repo and Python environment**

```bash
cd "/Users/yashvibhandik/Desktop/Yash/Work/1.) The Boardwalk_2Q26 Source Files"
mkdir investor-report-app && cd investor-report-app && git init -b main
mkdir -p backend/app backend/tests backend/config
python3 -m venv backend/.venv && source backend/.venv/bin/activate
```

- [ ] **Step 2: Write `.gitignore`**

```gitignore
# python
backend/.venv/
__pycache__/
*.pyc
.pytest_cache/
# runtime data
backend/data/
# node
frontend/node_modules/
frontend/dist/
frontend/.angular/
# env
.env
# os
.DS_Store
```

- [ ] **Step 3: Write `.env.example`**

```dotenv
# Where uploads, the SQLite DB, and generated reports live (default: backend/data)
APP_DATA_DIR=./backend/data
# Parallel file-processing workers
APP_WORKERS=3
# Max upload size per file, MB
APP_MAX_UPLOAD_MB=50
# Comma-separated origins allowed by CORS (Angular dev server)
APP_CORS_ORIGINS=http://localhost:4200
# OPTIONAL: enables the "Draft narratives with AI" button. Leave unset to run fully offline.
# ANTHROPIC_API_KEY=sk-ant-...
# ANTHROPIC_MODEL=claude-opus-5
```

- [ ] **Step 4: Write `backend/requirements.txt` and `backend/requirements-dev.txt`**

```text
fastapi>=0.115
uvicorn[standard]>=0.30
python-multipart>=0.0.9
pydantic>=2.7
openpyxl>=3.1
pdfplumber>=0.11
jinja2>=3.1
playwright>=1.45
```

```text
-r requirements.txt
pytest>=8
httpx>=0.27
anthropic>=0.86
```

- [ ] **Step 5: Write `backend/pyproject.toml`** (pytest config only; no packaging needed)

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-q"
```

- [ ] **Step 6: Install dependencies**

```bash
cd backend && pip install -r requirements-dev.txt && python -m playwright install chromium
```
Expected: pip finishes without error; Playwright downloads Chromium (~150 MB) once.

- [ ] **Step 7: Write `backend/app/__init__.py`** (empty file)

- [ ] **Step 8: Write `backend/app/config.py`**

```python
"""Settings read from environment variables (and a .env file if present)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Minimal .env loader: KEY=VALUE lines, existing env vars win."""
    for candidate in (Path.cwd() / ".env", BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
        break


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("APP_DATA_DIR", str(BACKEND_DIR / "data"))).resolve()
    workers: int = int(os.getenv("APP_WORKERS", "3"))
    max_upload_mb: int = int(os.getenv("APP_MAX_UPLOAD_MB", "50"))
    cors_origins: tuple[str, ...] = tuple(
        o.strip() for o in os.getenv("APP_CORS_ORIGINS", "http://localhost:4200").split(",") if o.strip()
    )
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-opus-5")
    config_dir: Path = BACKEND_DIR / "config"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


settings = Settings()
```

- [ ] **Step 9: Write `backend/tests/conftest.py`** (isolates the data dir before `app` is imported)

```python
import os
import tempfile

os.environ["APP_DATA_DIR"] = tempfile.mkdtemp(prefix="irg-test-")
os.environ["APP_WORKERS"] = "2"
os.environ.pop("ANTHROPIC_API_KEY", None)
```

- [ ] **Step 10: Write the failing test `backend/tests/test_health.py`**

```python
from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_status():
    with TestClient(app) as client:
        r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert set(body) >= {"ok", "llm_enabled", "pdf_renderer", "workers"}
```

- [ ] **Step 11: Run it to verify it fails**

Run: `pytest tests/test_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 12: Write the minimal `backend/app/main.py`**

```python
"""FastAPI application entry point."""
from __future__ import annotations

import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Investor Report Generator", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"], allow_headers=["*"]
)


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "llm_enabled": settings.llm_enabled,
        "pdf_renderer": shutil.which("chromium") is not None or True,  # replaced in Task 25
        "workers": settings.workers,
    }
```

- [ ] **Step 13: Run the test**

Run: `pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 14: Start the server once to confirm it boots**

Run: `uvicorn app.main:app --reload --port 8000` then `curl -s localhost:8000/api/health`
Expected: `{"ok":true,"llm_enabled":false,"pdf_renderer":true,"workers":3}`. Stop the server.

- [ ] **Step 15: Commit**

```bash
cd .. && git add -A && git commit -m "chore: scaffold backend with settings and health endpoint"
```

---

### Task 2: SQLite persistence layer

**Files:**
- Create: `backend/app/db.py`, `backend/tests/test_db.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_db.py
from app import db


def setup_module(module):
    db.init_db()


def test_project_and_file_roundtrip():
    p = db.create_project("Boardwalk 2Q26")
    assert p["name"] == "Boardwalk 2Q26" and p["id"]
    fid = db.new_id()
    f = db.add_file(p["id"], fid, "a.xlsx", "/tmp/a.xlsx", ".xlsx", 123)
    assert f["status"] == "queued" and f["parts"] == [] and f["ignored"] is False
    db.update_file(fid, status="processed", parts=[{"doc_type": "x"}], extractions=[{"data": {"a": 1}}])
    f2 = db.get_file(fid)
    assert f2["status"] == "processed" and f2["parts"][0]["doc_type"] == "x"
    assert f2["extractions"][0]["data"]["a"] == 1
    assert db.list_projects()[0]["file_count"] == 1
    db.delete_file(fid)
    assert db.list_files(p["id"]) == []


def test_report_data_upsert_keeps_overrides():
    p = db.create_project("P")
    assert db.get_report_data(p["id"]) is None
    db.save_report_data(p["id"], {"sections": {}}, notes=[{"m": 1}])
    db.save_overrides(p["id"], {"fields": {"a.fields.b": 5}})
    db.save_report_data(p["id"], {"sections": {"x": {}}}, notes=[])
    row = db.get_report_data(p["id"])
    assert row["overrides"] == {"fields": {"a.fields.b": 5}}
    assert row["data"] == {"sections": {"x": {}}}
    assert row["built_at"]


def test_report_versions_increment():
    p = db.create_project("P")
    r1 = db.create_report(p["id"])
    r2 = db.create_report(p["id"])
    assert (r1["version"], r2["version"]) == (1, 2)
    db.update_report(r2["id"], status="done", pdf_path="/x.pdf")
    assert db.get_report(r2["id"])["status"] == "done"
    assert [r["version"] for r in db.list_reports(p["id"])] == [2, 1]
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_db.py -v`
Expected: FAIL with `ImportError: cannot import name 'db'`

- [ ] **Step 3: Write `backend/app/db.py`**

```python
"""SQLite persistence. One short-lived connection per call; JSON columns are decoded on read."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  original_filename TEXT NOT NULL,
  stored_path TEXT NOT NULL,
  ext TEXT NOT NULL,
  size INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  error TEXT,
  parts TEXT NOT NULL DEFAULT '[]',
  extractions TEXT NOT NULL DEFAULT '[]',
  doc_type_override TEXT,
  ignored INTEGER NOT NULL DEFAULT 0,
  uploaded_at TEXT NOT NULL,
  processed_at TEXT
);
CREATE TABLE IF NOT EXISTS report_data (
  project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
  data TEXT,
  overrides TEXT NOT NULL DEFAULT '{}',
  issues TEXT NOT NULL DEFAULT '[]',
  notes TEXT NOT NULL DEFAULT '[]',
  built_at TEXT,
  narrative_status TEXT,
  narrative_error TEXT
);
CREATE TABLE IF NOT EXISTS reports (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  error TEXT,
  html_path TEXT,
  pdf_path TEXT,
  created_at TEXT NOT NULL
);
"""

JSON_COLS = {"parts", "extractions", "data", "overrides", "issues", "notes"}
BOOL_COLS = {"ignored"}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def init_db() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.executescript(SCHEMA)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(settings.db_path, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _decode(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k in JSON_COLS:
        if k in d and isinstance(d[k], str):
            d[k] = json.loads(d[k])
    for k in BOOL_COLS:
        if k in d:
            d[k] = bool(d[k])
    return d


def _encode(cols: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in cols.items():
        if k in JSON_COLS and not isinstance(v, str):
            v = json.dumps(v, default=str)
        if k in BOOL_COLS:
            v = int(bool(v))
        out[k] = v
    return out


def _update(table: str, id_col: str, id_val: str, **cols: Any) -> None:
    if not cols:
        return
    enc = _encode(cols)
    sets = ", ".join(f"{k} = ?" for k in enc)
    with connect() as con:
        con.execute(f"UPDATE {table} SET {sets} WHERE {id_col} = ?", [*enc.values(), id_val])


# ---------- projects ----------
def create_project(name: str) -> dict:
    pid, ts = new_id(), now()
    with connect() as con:
        con.execute("INSERT INTO projects VALUES (?,?,?,?)", (pid, name, ts, ts))
    return get_project(pid)  # type: ignore[return-value]


def get_project(pid: str) -> dict | None:
    with connect() as con:
        return _decode(con.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone())


def list_projects() -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT p.*, (SELECT COUNT(*) FROM files f WHERE f.project_id = p.id) AS file_count "
            "FROM projects p ORDER BY created_at DESC"
        ).fetchall()
    return [_decode(r) for r in rows]  # type: ignore[misc]


def touch_project(pid: str) -> None:
    _update("projects", "id", pid, updated_at=now())


def delete_project(pid: str) -> None:
    with connect() as con:
        con.execute("DELETE FROM projects WHERE id = ?", (pid,))


# ---------- files ----------
def add_file(project_id: str, file_id: str, original_filename: str, stored_path: str, ext: str, size: int) -> dict:
    with connect() as con:
        con.execute(
            "INSERT INTO files (id, project_id, original_filename, stored_path, ext, size, uploaded_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (file_id, project_id, original_filename, stored_path, ext, size, now()),
        )
    touch_project(project_id)
    return get_file(file_id)  # type: ignore[return-value]


def get_file(fid: str) -> dict | None:
    with connect() as con:
        return _decode(con.execute("SELECT * FROM files WHERE id = ?", (fid,)).fetchone())


def list_files(project_id: str) -> list[dict]:
    with connect() as con:
        rows = con.execute("SELECT * FROM files WHERE project_id = ? ORDER BY uploaded_at, id", (project_id,)).fetchall()
    return [_decode(r) for r in rows]  # type: ignore[misc]


def update_file(fid: str, **cols: Any) -> None:
    _update("files", "id", fid, **cols)


def delete_file(fid: str) -> None:
    with connect() as con:
        con.execute("DELETE FROM files WHERE id = ?", (fid,))


# ---------- report data ----------
def get_report_data(project_id: str) -> dict | None:
    with connect() as con:
        return _decode(con.execute("SELECT * FROM report_data WHERE project_id = ?", (project_id,)).fetchone())


def save_report_data(project_id: str, data: dict, notes: list) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO report_data (project_id, data, notes, built_at) VALUES (?,?,?,?) "
            "ON CONFLICT(project_id) DO UPDATE SET data = excluded.data, notes = excluded.notes, built_at = excluded.built_at",
            (project_id, json.dumps(data, default=str), json.dumps(notes, default=str), now()),
        )
    touch_project(project_id)


def save_overrides(project_id: str, overrides: dict) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO report_data (project_id, overrides) VALUES (?,?) "
            "ON CONFLICT(project_id) DO UPDATE SET overrides = excluded.overrides",
            (project_id, json.dumps(overrides, default=str)),
        )
    touch_project(project_id)


def save_issues(project_id: str, issues: list) -> None:
    _update("report_data", "project_id", project_id, issues=issues)


def set_narrative(project_id: str, status: str | None, error: str | None = None) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO report_data (project_id, narrative_status, narrative_error) VALUES (?,?,?) "
            "ON CONFLICT(project_id) DO UPDATE SET narrative_status = excluded.narrative_status, "
            "narrative_error = excluded.narrative_error",
            (project_id, status, error),
        )


# ---------- reports ----------
def create_report(project_id: str) -> dict:
    rid = new_id()
    with connect() as con:
        ver = con.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM reports WHERE project_id = ?", (project_id,)).fetchone()[0]
        con.execute(
            "INSERT INTO reports (id, project_id, version, status, created_at) VALUES (?,?,?,?,?)",
            (rid, project_id, ver, "queued", now()),
        )
    return get_report(rid)  # type: ignore[return-value]


def update_report(rid: str, **cols: Any) -> None:
    _update("reports", "id", rid, **cols)


def get_report(rid: str) -> dict | None:
    with connect() as con:
        return _decode(con.execute("SELECT * FROM reports WHERE id = ?", (rid,)).fetchone())


def list_reports(project_id: str) -> list[dict]:
    with connect() as con:
        rows = con.execute("SELECT * FROM reports WHERE project_id = ? ORDER BY version DESC", (project_id,)).fetchall()
    return [_decode(r) for r in rows]  # type: ignore[misc]
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_db.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: sqlite persistence for projects, files, report data, reports"
```

---

### Task 3: Document model and cell helpers

Every extractor locates data by header and label text through these helpers, so get them right first.

**Files:**
- Create: `backend/app/readers/__init__.py` (empty), `backend/app/readers/document.py`, `backend/tests/test_document.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_document.py
import datetime as dt

from app.readers.document import Sheet, is_number, norm, to_date, to_number


def test_to_number_variants():
    assert to_number("1,234.5") == 1234.5
    assert to_number("(1,234)") == -1234
    assert to_number("$48,000") == 48000
    assert to_number("91.71%") == 91.71
    assert to_number("N/A") is None and to_number(None) is None and to_number(True) is None
    assert to_number(12) == 12.0 and to_number("abc") is None


def test_is_number():
    assert is_number(5) and is_number("1,234") and is_number("(12.5)")
    assert not is_number("4000-0000") and not is_number("Total") and not is_number(None) and not is_number(False)


def test_to_date_variants():
    assert to_date("06/30/2026") == dt.date(2026, 6, 30)
    assert to_date(dt.datetime(2026, 4, 1, 5)) == dt.date(2026, 4, 1)
    assert to_date("Jul-25") == dt.date(2025, 7, 1)
    assert to_date("2026-04") == dt.date(2026, 4, 1)
    assert to_date("not a date") is None


def test_norm_collapses_whitespace():
    assert norm("  PTD   Actual ") == "ptd actual" and norm(None) == ""


def test_header_block_joins_multirow_headers_and_skips_blank_rows():
    rows = [
        ["Rent Roll"], ["The Boardwalk (45726)"], [None],
        ["Summary Groups", None, "Square", "# Of", "% Unit"],
        [None, None, "Footage", "Units", "Occupancy"],
        ["Occupied Units", None, "258,734.00", 310, 91.71],
    ]
    sh = Sheet("Report1", rows)
    start, k, headers = sh.header_block(["summary groups", "# of"], max_rows=3)
    assert (start, k) == (3, 2)
    assert Sheet.col(headers, r"# of units") == 3 and Sheet.col(headers, r"% unit occupancy") == 4
    assert sh.has_numbers(5) and not sh.has_numbers(4)


def test_header_block_requires_token_on_start_row():
    rows = [["Book = Accrual"], [None, None, "Balance", "Beginning", "Net"], [None, None, "Current Period", "Balance", "Change"], ["1000-0000", "Cash", 5, 4, 1]]
    sh = Sheet("R", rows)
    start, k, headers = sh.header_block(["balance", "beginning"], max_rows=2)
    assert (start, k) == (1, 2) and Sheet.col(headers, r"change") == 4


def test_label_column_skips_gl_codes_and_find():
    sh = Sheet("R", [["4000-0000", "  Gross Potential Rent", 5], ["4001-0000", "  Loss to Lease", 6]])
    assert sh.label_column(0) == 1
    assert sh.find(r"loss to lease") == (1, 1, "  Loss to Lease")
    assert sh.find(r"nothing") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_document.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.readers'`

- [ ] **Step 3: Write `backend/app/readers/document.py`**

```python
"""Neutral in-memory representation of an uploaded file, plus the cell helpers every extractor uses."""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any

CODE_RE = re.compile(r"^\d{3,5}-\d{3,5}$")  # Yardi GL account codes such as 4000-0000
_NUM_RE = re.compile(r"^\(?-?\$?\s*[\d,]*\.?\d+\s*%?\)?$")
_NA = {"n/a", "na", "-", "—", "--", ""}
_DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%m/%d/%y", "%b %Y", "%B %Y", "%b-%y", "%Y-%m", "%b %d, %Y")


def norm(s: Any) -> str:
    """Lower-cased, whitespace-collapsed text for matching."""
    return re.sub(r"\s+", " ", str(s if s is not None else "")).strip().lower()


def to_number(v: Any) -> float | None:
    """Parse 1,234 / (1,234) / $1,234 / 12.5% / -3 into a float. None when not numeric."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s.lower() in _NA:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if neg else x


def is_number(v: Any) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    return isinstance(v, str) and bool(_NUM_RE.match(v.strip()))


def to_date(v: Any) -> dt.date | None:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if v is None:
        return None
    s = str(v).strip()
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def as_fraction(x: float | None) -> float | None:
    """Percent values arrive as 91.71 (Yardi) or 0.9171 (CoStar/HelloData); store fractions."""
    if x is None:
        return None
    return x / 100.0 if abs(x) > 1.5 else x


@dataclass
class Sheet:
    name: str
    rows: list[list[Any]]

    @property
    def nrows(self) -> int:
        return len(self.rows)

    def cell(self, r: int, c: int) -> Any:
        if 0 <= r < len(self.rows) and 0 <= c < len(self.rows[r]):
            return self.rows[r][c]
        return None

    def text(self, r: int, c: int) -> str:
        v = self.cell(r, c)
        return "" if v is None else str(v).strip()

    def row_text(self, r: int) -> str:
        if not (0 <= r < self.nrows):
            return ""
        return " | ".join(t for t in (self.text(r, c) for c in range(len(self.rows[r]))) if t)

    def head_text(self, n: int = 15) -> str:
        return "\n".join(self.row_text(r) for r in range(min(n, self.nrows)))

    def has_numbers(self, r: int) -> bool:
        return 0 <= r < self.nrows and any(is_number(v) for v in self.rows[r])

    def find(self, pattern: str, max_row: int | None = None) -> tuple[int, int, str] | None:
        """First cell whose text matches the regex (case-insensitive) as (row, col, text)."""
        rx = re.compile(pattern, re.I)
        for r in range(min(max_row or self.nrows, self.nrows)):
            for c, v in enumerate(self.rows[r]):
                if v is not None and rx.search(str(v)):
                    return r, c, str(v)
        return None

    def _join(self, r: int, k: int) -> list[str]:
        end = min(r + k, self.nrows)
        width = max((len(self.rows[i]) for i in range(r, end)), default=0)
        return [norm(" ".join(self.text(i, c) for i in range(r, end))) for c in range(width)]

    def header_block(self, required: list[str], max_rows: int = 3, search_rows: int = 40) -> tuple[int, int, list[str]] | None:
        """Locate a header that may span several rows.

        Returns (start_row, row_count, headers) where headers are the per-column texts of rows
        start..start+row_count-1 joined and normalised. The start row itself must contain at least one
        required token (so a title line above a header is not swallowed); further rows are joined while
        they contain no numbers, up to max_rows.
        """
        for r in range(min(search_rows, self.nrows)):
            first = norm(self.row_text(r))
            if not first or not any(req in first for req in required):
                continue
            k = 1
            while k < max_rows and r + k < self.nrows and not self.has_numbers(r + k):
                k += 1
            headers = self._join(r, k)
            if all(any(req in h for h in headers) for req in required):
                return r, k, headers
        return None

    @staticmethod
    def col(headers: list[str], *patterns: str) -> int | None:
        """Index of the first header matching any pattern (patterns tried in order)."""
        for p in patterns:
            rx = re.compile(p, re.I)
            for i, h in enumerate(headers):
                if rx.search(h):
                    return i
        return None

    @staticmethod
    def cols_all(headers: list[str], pattern: str) -> list[int]:
        rx = re.compile(pattern, re.I)
        return [i for i, h in enumerate(headers) if rx.search(h)]

    def label_column(self, start: int, end: int | None = None) -> int:
        """Column holding row labels: most non-numeric, non-GL-code strings below `start`."""
        end = end or self.nrows
        width = max((len(x) for x in self.rows[start:end]), default=0)
        best, best_n = 0, -1
        for c in range(width):
            n = 0
            for r in range(start, end):
                v = self.cell(r, c)
                if isinstance(v, str) and v.strip() and not is_number(v) and not CODE_RE.match(v.strip()):
                    n += 1
            if n > best_n:
                best, best_n = c, n
        return best


@dataclass
class Page:
    number: int
    text: str

    @property
    def lines(self) -> list[str]:
        return [ln.rstrip() for ln in self.text.splitlines() if ln.strip()]


@dataclass
class Document:
    file_id: str
    filename: str
    kind: str  # "xlsx" | "pdf"
    sheets: list[Sheet] = field(default_factory=list)
    pages: list[Page] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(p.text for p in self.pages)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_document.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: document model with header-block and number/date helpers"
```

---

### Task 4: xlsx and PDF readers with a format registry

**Files:**
- Create: `backend/app/readers/xlsx_reader.py`, `backend/app/readers/pdf_reader.py`, `backend/app/readers/registry.py`, `backend/tests/helpers.py`, `backend/tests/test_readers.py`

- [ ] **Step 1: Write the test helper `backend/tests/helpers.py`** (used by many later tests)

```python
"""Synthetic workbooks that mirror the layouts of the real Yardi/HelloData/CoStar exports."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import openpyxl

from app.classify.classifier import Part
from app.readers.document import Page, Sheet


def make_xlsx(path: Path, sheets: dict[str, list[list]]) -> Path:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    wb.save(path)
    return path


def sheet_part(rows: list[list], doc_type: str, name: str = "Report1", file_id: str = "f1", filename: str = "file.xlsx") -> Part:
    return Part(doc_type, 1.0, f"sheet '{name}'", file_id, filename, sheet=Sheet(name, rows))


def pdf_part(text: str, doc_type: str, file_id: str = "p1", filename: str = "file.pdf") -> Part:
    pages = [Page(i + 1, t) for i, t in enumerate(text.split("\f"))]
    return Part(doc_type, 1.0, f"pages 1-{len(pages)}", file_id, filename, pages=pages)


BUDGET_ROWS = [
    ["Property =  45726 45726con"],
    ["Budget Comparison"],
    ["Period = Apr 2026-Jun 2026"],
    ["Book = Accrual ; Tree = rp-cashflow"],
    [None, None, " PTD Actual ", " PTD Budget ", " Variance ", " % Var ", " YTD Actual ", " YTD Budget ", " Variance ", " % Var ", " Annual "],
    ["3998-0000", "    REVENUE"],
    ["3999-0000", "      Rental Income"],
    ["4000-0000", "        Gross Potential Rent", 1000, 900, 100, 11.11, 2000, 1800, 200, 11.11, 3600],
    ["4001-0000", "        Loss/Gain to Lease", 10, 50, -40, -80, 20, 100, -80, -80, 200],
    ["4004-0000", "        Less:Concessions-Mthly", 1, 0, 1, "N/A", 1, 0, 1, "N/A", 0],
    ["4005-0000", "        Less:Concessions-One Time", -51, -10, -41, -410, -101, -20, -81, -405, -40],
    ["4006-0000", "        Less:  Vacancy", -100, -110, 10, 9.09, -200, -220, 20, 9.09, -440],
    ["4016-0000", "        Pet Rent", 5, 4, 1, 25, 10, 8, 2, 25, 16],
    ["4060-0000", "        NET RENTAL INCOME", 865, 834, 31, 3.72, 1730, 1668, 62, 3.72, 3336],
    ["4080-9999", "  UTILITY INCOME"],
    ["4081-0005", "        Water Income", 100, 90, 10, 11.11, 200, 180, 20, 11.11, 360],
    ["4081-0100", "        TOTAL UTILITY INCOME", 100, 90, 10, 11.11, 200, 180, 20, 11.11, 360],
    ["4400-0000", "  OTHER INCOME"],
    ["4407-0050", "        Less:Write Off Bad Debt", -10, -5, -5, -100, -20, -10, -10, -100, -20],
    ["4407-0055", "        Former Resident Collections", 7, 3, 4, 133, 14, 6, 8, 133, 12],
    ["4699-0000", "        TOTAL OTHER INCOME", 35, 30, 5, 16.67, 70, 60, 10, 16.67, 120],
    ["4999-0000", "            TOTAL REVENUE", 1000, 954, 46, 4.82, 2000, 1908, 92, 4.82, 3816],
    ["5000-0000", "    EXPENSES"],
    ["5019-0000", "  PAYROLL"],
    ["5020-0000", "        Manager Salaries", 100, 90, -10, -11.11, 200, 180, -20, -11.11, 360],
    ["5055-0000", "          TOTAL PAYROLL", 100, 90, -10, -11.11, 200, 180, -20, -11.11, 360],
    ["5056-0000", "  GENERAL & ADMINISTRATIVE"],
    ["5056-1000", "          TOTAL GENERAL & ADMINISTRATIVE", 20, 25, 5, 20, 40, 50, 10, 20, 100],
    ["5095-0000", "  MARKETING"],
    ["5108-0000", "          TOTAL MARKETING", 10, 10, 0, 0, 20, 20, 0, 0, 40],
    ["5200-0000", "  REPAIRS & MAINTENANCE"],
    ["5215-0000", "          TOTAL REPAIRS & MAINTENANCE", 30, 25, -5, -20, 60, 50, -10, -20, 100],
    ["5299-0000", "  UTILITIES"],
    ["5310-0000", "        Water & Wastewater", 120, 100, -20, -20, 240, 200, -40, -20, 400],
    ["5399-0000", "          TOTAL UTILITIES", 120, 100, -20, -20, 240, 200, -40, -20, 400],
    ["5460-0000", "  MANAGEMENT FEES"],
    ["5465-0000", "          TOTAL MANAGEMENT FEES", 30, 30, 0, 0, 60, 60, 0, 0, 120],
    ["5499-0000", "  TAXES"],
    ["5500-0000", "        Property Taxes", 100, 100, 0, 0, 200, 200, 0, 0, 400],
    ["5515-0000", "          TOTAL TAXES", 100, 100, 0, 0, 200, 200, 0, 0, 400],
    ["5519-9999", "  INSURANCE"],
    ["5520-0000", "        Insurance", 40, 60, 20, 33.33, 80, 120, 40, 33.33, 240],
    ["5520-0010", "          TOTAL INSURANCE", 40, 60, 20, 33.33, 80, 120, 40, 33.33, 240],
    ["6500-0000", "            TOTAL EXPENSES", 450, 440, -10, -2.27, 900, 880, -20, -2.27, 1760],
    ["6700-0000", "            NET OPERATING INCOME/(LOSS)", 550, 514, 36, 7, 1100, 1028, 72, 7, 2056],
    ["6800-0000", "  DEBT SERVICE"],
    ["6801-0000", "        Interest Expense-1st Lien", 300, 300, 0, 0, 600, 600, 0, 0, 1200],
    ["6810-0000", "          TOTAL DEBT SERVICE", 300, 300, 0, 0, 600, 600, 0, 0, 1200],
    ["7000-0000", "            NET INCOME/(LOSS) AFTER DS", 250, 214, 36, 16.82, 500, 428, 72, 16.82, 856],
    ["7001-0000", "    NON-OPERATING EXPENSES"],
    ["7004-0000", "        Legal Fees", 0, 5, 5, 100, 1, 10, 9, 90, 20],
    [None, " INTERIOR & EXTERIOR RENOVATIONS"],
    [None, "      INTERIOR RENOVATIONS"],
    ["7100-0009", "        Paint", 25, 15, -10, -66.67, 48, 38, -10, -26.32, 68],
    ["7100-0016", "        Plumbing Replacement", 20, 17, -3, -17.65, 27, 24, -3, -12.5, 72],
    [None, "          TOTAL INTERIOR RENOVATIONS", 45, 32, -13, -40.63, 75, 62, -13, -20.97, 140],
    [None, "        EXTERIOR RENOVATIONS"],
    ["7200-0000", "      ROOF"],
    ["7200-0002", "        Roof", 3, 0, -3, "N/A", 3, 0, -3, "N/A", 2],
    [None, "          TOTAL ROOF", 3, 0, -3, "N/A", 3, 0, -3, "N/A", 2],
    [None, "          TOTAL EXTERIOR RENOVATIONS", 3, 0, -3, "N/A", 3, 0, -3, "N/A", 2],
    ["7500-0000", "  LEASE UP COSTS"],
    ["7500-0003", "        Marketing & Promotion", 1, 0, -1, "N/A", 2, 1, -1, -100, 1],
    ["7800-0000", "  DEPR/AMORT EXPENSE"],
    ["7810-0065", "        Amortization - Loan Costs", 36, 0, -36, "N/A", 72, 0, -72, "N/A", 0],
    [None, "    NON-OPERATING ITEMS"],
    ["1800-0005", "        EXTERIOR IMPROVEMENTS"],
    ["1811-0005", "      PLUMBING"],
    ["1814-0000", "        Plumbing", -13, 0, -13, "N/A", -20, -7, -13, -185.7, -7],
    ["1820-0010", "          TOTAL PLUMBING", -13, 0, -13, "N/A", -20, -7, -13, -185.7, -7],
    [None, "     TOTAL NON-OPERATING ITEMS", -13, 0, -13, "N/A", -20, -7, -13, -185.7, -7],
    [None, None, 61, 32, None, None, 98, 69],
]

BALANCE_ROWS = [
    ["Property =  45726 45726con"],
    ["Balance Sheet (With Period Change)"],
    ["Period = Apr 2026-Jun 2026"],
    ["Book = Accrual ; Tree = ysi_bs"],
    [None, None, "Balance", "Beginning", "Net"],
    [None, None, "Current Period", "Balance", "Change"],
    ["0999-0000", "                                         ASSETS"],
    ["1000-0100", "        Cash - Operating", 371079.7, 317212.03, 53867.67],
    ["1500-0000", "        Land", 9504000, 9504000, 0],
    ["1500-0021", "        Building", 38016000, 38016000, 0],
    ["1500-0029", "          Total Building", 47520000, 47520000, 0],
    ["1500-0041", "        Furniture, Fixtures & Equipment", 480000, 480000, 0],
    ["1500-0049", "          Total Furniture & Fixtures", 480000, 480000, 0],
    ["1995-0000", "                   TOTAL ASSETS", 51612168.23, 51472851.8, 139316.43],
    ["1997-0000", "     LIABILITIES"],
    ["2139-0001", "        Accrued Interest", 159161.98, 164467.37, -5305.39],
    ["2310-0000", "        Mortgage Payable", 36519000, 36519000, 0],
    ["2310-0020", "          TOTAL MORTGAGE PAYABLE", 36519000, 36519000, 0],
    ["2999-0000", "     EQUITY"],
    ["3015-0000", "        Owner Contributions", 14259605.94, 14259605.94, 0],
    ["3994-0000", "              TOTAL EQUITY", 14076975.24, 14098813.12, -21837.88],
]


def rent_roll_rows(as_of: str, occupied: int, total: int, pct: float, future: int) -> list[list]:
    return [
        ["Rent Roll"], ["The Boardwalk (45726)"], [f"As Of = {as_of}"], [None],
        ["Property", "State", "Total", "Name", "Market", "Resident", "Deposit", "Average", "Average", "Average", "Balance"],
        [None, None, "Units", None, "Rent", "Rent", None, "Market", "Resident", "Deposit"],
        [None, None, None, None, None, None, None, "Rent", "Rent"],
        ["45726", "FL", total, "The Boardwalk", 445390, 405490, 268485.13, 1317.72, 1325.13, 877.4, -53332.85],
        [None, None, total, "Total", 445390, 405490, 268485.13, 1317.72, 1325.13, 877.4, -53332.85],
        [None],
        ["Summary Groups", None, "Square", "Market", "Actual", "Security", "Other", "# Of", "% Unit", "% Sqft", "Balance"],
        [None, None, "Footage", "Rent", "Rent", "Deposit", "Deposits", "Units", "Occupancy", "Occupied"],
        ["Current/Notice/Vacant Residents", None, "284,310.00", "445,390.00", "405,490.00", "268,485.13", "-1,000.00", total, pct, 90.14, "-48,937.14"],
        ["Future Residents/Applicants", None, "10,937.00", "17,594.00", "0.00", "0.00", "0.00", future, None, None, "-4,395.71"],
        ["Occupied Units", None, "256,289.00", "402,494.00", None, None, None, occupied, pct, 90.14],
        ["Total Non Rev Units", None, "0.00", "0.00", None, None, None, 0, "0.00", "0.00"],
        ["Total Vacant Units", None, "28,021.00", "42,896.00", None, None, None, total - occupied, 9.46, 9.85],
        ["Totals:", None, "284,310.00", "445,390.00", "405,490.00", "268,485.13", "-1,000.00", total, "100.00", "100.00", "-53,332.85"],
    ]


def schedule_rows(as_of: str, rents: dict[str, float]) -> list[list]:
    """rents: unit-type label -> average resident rent (occupied units fixed per type below)."""
    return [
        ["Market Rent Schedule"], ["The Boardwalk (45726)"], [f"As Of = {as_of}"],
        ["Unit Type", "Units", "Unit Type", "Unit Type", "Total", "Total Unit", "Average", "Occupied", "Average"],
        [None, None, "Rent", "Sq Ft", "Unit Type", "Rent", "Unit Rent", "Units", "Resident Rent"],
        [None, None, None, None, "Rent"],
        ["1 Bedroom 1 Bathroom (BWK.A1)", 40, 999, 657, 39960, 44690, 1117.25, 38, rents["BWK.A1"]],
        ["2 Bedroom 1 Bathroom (BWK.B0)", 52, 1215, 814, 63180, 70119, 1348.44, 47, rents["BWK.B0"]],
        ["2 Bedroom 2 Bathroom (BWK.B1)", 24, 1209, 875, 29016, 32771, 1365.45, 19, rents["BWK.B1"]],
        ["0 Bedroom 1 Bathroom (BWK.S1)", 23, 901, 550, 20723, 25353, 1102.3, 22, rents["BWK.S1"]],
        ["Grand Total", 139, 1100, 760, 152879, 172933, 1244.11, 126, rents["TOTAL"]],
    ]


LTO_ROWS = [
    [None, "Lease Renewals"],
    [None, "Leases Expiring between 2026-04-01 and 2026-06-30"],
    [None],
    [None, None, None, None, None, "New Lease Term", None, None, None, None, None, None, None, None, None, "Previous Lease Term"],
    [None, "Resident Name", "Unit Type", "Sqft", "Unit", "Renewal Start", "Lease Term", "Market Rent", "Lease Rent", "Up-Front Concessions", "Total Recurring Concessions", "Total Concessions", "# Months Free", "Effective Rent", "EFF Rent PSF", "Lease Rent", "Total Concessions", "Lease Term", "Effective Rent", "Eff Rent PSF", "Rent Change", "% Change", "Eff Rent % Change"],
    ["The Boardwalk", "A Renter", "BWK.A1   ", 657, "4715D125", dt.datetime(2026, 4, 22), 12, 1264, 1425, 1425, 0, 1425, 1, 1306.25, 1.99, 1405, 0, 12, 1405, 2.14, 20, 0.01, -0.07],
    [None, None, "Averages for BWK.A1   ", None, None, None, 12, 1264, 1425, 1425, 0, 1425, 1, 1306.25, 1.99, 1405, 0, 12, 1405, 2.14, 20, 0.01, -0.07],
    ["The Boardwalk", "B Renter", "BWK.S1   ", 550, "4640H240", dt.datetime(2026, 5, 1), 12, 986, 1055, 1055, 0, 1055, 1, 967.08, 1.76, 1035, 0, 12, 1035, 1.88, 20, 0.02, -0.07],
    [None, "Averages for The Boardwalk", None, None, None, None, 12, 1125, 1240, 1240, 0, 1240, 1, 1136.67, 1.88, 1220, 0, 12, 1220, 2.01, 20, 0.02, -0.07],
    [None],
    [None, "Move Ins"],
    [None, "Move In between 2026-04-01 and 2026-06-30"],
    [None],
    [None, None, None, None, None, "New Lease Term", None, None, None, None, None, None, None, None, None, "Previous Lease Term"],
    [None, "Resident Name", "Unit Type", "Sqft", "Unit", "Lease Start", "Lease Term", "Market Rent", "Lease Rent", "Up-Front Concessions", "Total Recurring Concessions", "Total Concessions", "# Months Free", "Effective Rent", "EFF Rent PSF", "Lease Rent", "Total Concessions", "Lease Term", "Effective Rent", "Eff Rent PSF", "Rent Change", "% Change", "Eff Rent % Change"],
    ["The Boardwalk", "C Renter", "BWK.A1   ", 657, "4715D130", dt.datetime(2026, 6, 26), 12, 1094, 1000, 0, 0, 0, 0, 1000, 1.52, 1200, 0, 12, 1200, 1.83, -200, -0.17, -0.17],
    ["The Boardwalk", "D Renter", "BWK.A1   ", 657, "4755B110", dt.datetime(2026, 4, 1), 15, 1219, 1100, 0, 0, 0, 0, 1100, 1.67, 1300, 0, 12, 1300, 1.98, -200, -0.15, -0.15],
    ["The Boardwalk", "E Renter", "BWK.S1   ", 550, "4654L165", dt.datetime(2026, 6, 6), 12, 1181, 900, 0, 0, 0, 0, 900, 1.64, 1000, 0, 12, 1000, 1.82, -100, -0.1, -0.1],
]

LISTINGS_ROWS = [
    [None],
    [None, "Unit-Level Data"],
    [None, "Property Name", "Address", "Floorplan Name", "Unit #", "Floor #", "Beds", "Baths", "Partial Baths", "Sqft", "First Listed", "Leased Date", "Active Listing?", "Days on Mkt", "Asking Rent", "Asking PSF", "Effective Rent", "Effective PSF"],
    [None, "The Boardwalk", "4637 Deleon Street, Fort Myers, FL 33907", "A1", "101", None, 1, 1, None, 657, dt.datetime(2026, 3, 1), dt.datetime(2026, 4, 10), False, 40, 1300, 1.98, 1300, 1.98],
    [None, "The Boardwalk", "4637 Deleon Street, Fort Myers, FL 33907", "A1", "102", None, 1, 1, None, 657, dt.datetime(2026, 5, 1), None, True, 60, 1200, 1.83, 1100, 1.67],
    [None, "The Ashlar", "1 Ashlar Way, Fort Myers, FL 33907", "B2", "201", None, 2, 2, None, 900, dt.datetime(2026, 2, 1), dt.datetime(2026, 5, 20), False, 108, 1800, 2.0, 1600, 1.78],
    [None, "The Ashlar", "1 Ashlar Way, Fort Myers, FL 33907", "B2", "202", None, 2, 2, None, 900, dt.datetime(2026, 2, 1), dt.datetime(2026, 6, 1), False, 120, 1600, 1.78, 1500, 1.67],
    [None, "The Ashlar", "1 Ashlar Way, Fort Myers, FL 33907", "B2", "203", None, 2, 2, None, 900, dt.datetime(2026, 6, 1), None, True, 30, 1700, 1.89, 1700, 1.89],
]

COMPS_ROWS = [
    [None],
    [None, "Rent Comps", None, None, None, None, None, None, None, None, None, None, "30-Day Avg Rents"],
    [None, "Property", "Address", "Similarity", "Dist. (mi)", "Quality", "Yr Built", "# Units", "Stories", "Avg Sqft", "Leased %", "Exposure %", "Studio", "1BR"],
    [None, "The Boardwalk", "4637 Deleon Street, Fort Myers, FL 33907", "--", "--", 0.68, 1973, 338, 2, 843.73, 0.9, 0.14, 1118.92, 1174.43],
    [None, "Comp Average", "--", 0.87, 1.9, 0.68, 1990.5, 298.2, 2.4, 911.27, 0.96, 0.06, None, 1222.11],
    [None, "The Ashlar", "1 Ashlar Way, Fort Myers, FL 33907", 0.93, 1.29, 0.68, 1998, 428, 2, 840.9, 0.94, 0.07, None, 1177.83],
]

COSTAR_ROWS = [
    ["Period", "Asset Value", "Vacancy Rate", "Market Asking Rent/Unit", "Annual Rent Growth", "Inventory Units", "Under Constr Units", "Under Constr % of Inventory", "12 Mo Absorp Units", "Market Sale Price/Unit", "12 Mo Sales Vol", "12 Mo Sales Vol Growth", "Market Cap Rate"],
    ["2026 Q3 QTD", 1669351601.81, 0.158960965, 1563.89, -0.0447, 9571, 0, 0, 449.6, 174417.68, 120625000, 6.94, 0.061],
    ["2026 Q2", 1666065327.07, 0.163390659, 1555.10427, -0.054240721, 9571, 0, 0, 406, 174074.32, 116325000, 6.66, 0.061],
    ["2026 Q1", 1664655603.69, 0.147119114, 1539.90268, -0.083991131, 9250, 321, 0.0347, 222, 173927.03, 119360000, 0.72, 0.061],
    ["2025 Q4", 1672689470.22, 0.151147114, 1543.05826, -0.07498583, 9250, 321, 0.0347, 350, 174766.43, 119360000, 0.7, 0.061],
]

RENT_CHART_ROWS = [
    ["The Boardwalk vs. HelloData Comp Set"],
    ["July 2025 – June 2026"],
    ["Rent chart only considers new leases"],
    [None],
    ["Month", "The Boardwalk / Lease Count", "The Boardwalk / Gross PSF", "The Boardwalk / Effective PSF", "Comp Set / Lease Count", "Comp Set / Gross PSF", "Comp Set / Effective PSF"],
    [dt.datetime(2025, 7, 1), 12, 1.83, 1.63, 42, 1.71, 1.5],
    [dt.datetime(2025, 8, 1), 18, 1.75, 1.58, 61, 1.62, 1.45],
    ["T12 Total / SF-Wtd", 30, 1.78, 1.6, 103, 1.66, 1.47],
    [None],
    ["Methodology"],
    ["Source: Yardi LTO report — 12-month+ term new leases."],
]

COSTAR_PDF_TEXT = """Multi-Family Submarket Report
Western Lee County
Fort Myers - FL USA
PREPARED BY
Megan Burrows
7/21/2026
© 2026 CoStar Group - Licensed to ZMR Capital - 473560
\fOverview
Western Lee County Multi-Family
12 Mo Delivered Units    12 Mo Absorption Units    Vacancy Rate    12 Mo Asking Rent Growth
674    449    15.9%    -4.4%
KEY INDICATORS
Current Quarter    Units    Vacancy Rate    Asking Rent    Effective Rent    Absorption    Delivered Units    Under Constr
Submarket    9,571    15.9%    $1,564    $1,399    42    0    0
Annual Trends    12 Month    Historical    Forecast    Peak    When    Trough    When
Vacancy    1.3% (YOY)    8.2%    11.9%    16.3%    2026 Q2    4.2%    2015 Q1
Asking Rent Growth    -4.4%    2.2%    1.4%    16.0%    2021 Q4    -8.4%    2026 Q1
\fConstruction
RECENT DELIVERIES
Property Name/Address    Rating    Units    Stories    Start    Complete    Developer/Owner
Montage at Midtown    Catalyst Capital Management
1    321    4    Apr 2024    Jun 2026
2330 Union St
\fSales Past 12 Months
RECENT SIGNIFICANT SALES
Property Name/Address    Rating    Yr Built    Units    Vacancy    Sale Date    Price    Price/Unit    Price/SF
West End at City Walk
1    -    2021    319    21.0%    10/29/2025    $71,550,000    $224,294    $287
2250 McGregor Blvd
The Boardwalk
2    -    1973    338    5.9%    7/30/2025    $38,100,000    $112,721    $129
4637 Deleon St
"""

CAPITAL_CALLS_TEXT = """Back to Entities
The Boardwalk Owner, LLC (Slate)    Active
Asset SPV
Transactions
Capital Calls    New Capital Call
Distributions
0 records
Total Called    $0    0%    Callable Capital    $0
Title    Due Date    From    To    Total Called    Contributed    Progress
No Capital Calls Yet
"""

DISTRIBUTIONS_TEXT = """Back to Entities
The Boardwalk Owner, LLC (Slate)    Active
Transactions
Distributions    New Distribution
0 records
Gross Amount    Net Amount
Title    Period    Date    Classes    From    To    Settled
No Distributions Yet
"""

HELLODATA_PDF_TEXT = """The Boardwalk
ZMR Capital
4/1/2026 - 6/30/2026
Rents by Unit Type
# Leased    # Active    Days on Mkt    Min SF    Avg SF    Max SF    Min Rent    Avg Rent    Max Rent    Avg PSF    NER    NER PSF    Concession %    Trend
The Boardwalk    34    45    52    500    841    1,130    $995    $1,314    $1,662    $1.56    $1,178    $1.40    10.4%    +23.9%
Westchase    0    3    328    702    945    1,143    $1,078    $1,289    $1,496    $1.36    $1,289    $1.36    0.0%    +2.2%
Comp Average    105    673    859    1,132    $1,124    $1,368    $1,728    $1.59    $1,172    $1.36    14.0%
"""
```

- [ ] **Step 2: Write the failing tests `backend/tests/test_readers.py`**

```python
import pytest

from app.readers.registry import SUPPORTED_EXTENSIONS, UnsupportedFileType, read_document
from tests.helpers import BUDGET_ROWS, make_xlsx


def test_read_xlsx_keeps_sheet_names_and_values(tmp_path):
    p = make_xlsx(tmp_path / "a.xlsx", {"Report1": BUDGET_ROWS, "Empty": [[None, None]]})
    doc = read_document(p, "f1", "a.xlsx")
    assert doc.kind == "xlsx" and [s.name for s in doc.sheets] == ["Report1", "Empty"]
    sh = doc.sheets[0]
    assert sh.text(1, 0) == "Budget Comparison"
    assert sh.cell(7, 2) == 1000
    assert doc.sheets[1].nrows == 0  # trailing empty rows trimmed


def test_unsupported_extension(tmp_path):
    p = tmp_path / "x.docx"
    p.write_bytes(b"hello")
    with pytest.raises(UnsupportedFileType):
        read_document(p, "f", "x.docx")
    assert ".xlsx" in SUPPORTED_EXTENSIONS and ".pdf" in SUPPORTED_EXTENSIONS


def test_corrupt_xlsx_raises(tmp_path):
    p = tmp_path / "bad.xlsx"
    p.write_bytes(b"not a zip")
    with pytest.raises(Exception):
        read_document(p, "f", "bad.xlsx")
```

- [ ] **Step 3: Run to verify failure**

Run: `pytest tests/test_readers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.classify'` (helpers import Part). That is expected until Task 5; create `backend/app/classify/__init__.py` and a stub `classifier.py` now:

```python
# backend/app/classify/classifier.py  (temporary stub, replaced in Task 5)
from dataclasses import dataclass, field
from ..readers.document import Page, Sheet

@dataclass
class Part:
    doc_type: str
    confidence: float
    locator: str
    file_id: str
    filename: str
    sheet: Sheet | None = None
    pages: list[Page] = field(default_factory=list)
```
Re-run: Expected FAIL with `ModuleNotFoundError: No module named 'app.readers.registry'`

- [ ] **Step 4: Write `backend/app/readers/xlsx_reader.py`**

```python
from __future__ import annotations

from pathlib import Path

import openpyxl

from .document import Document, Sheet


def read_xlsx(path: Path, file_id: str, filename: str) -> Document:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheets: list[Sheet] = []
    try:
        for ws in wb.worksheets:
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            while rows and all(v is None for v in rows[-1]):
                rows.pop()
            sheets.append(Sheet(name=ws.title, rows=rows))
    finally:
        wb.close()
    return Document(file_id=file_id, filename=filename, kind="xlsx", sheets=sheets)
```

- [ ] **Step 5: Write `backend/app/readers/pdf_reader.py`**

```python
from __future__ import annotations

from pathlib import Path

import pdfplumber

from .document import Document, Page


class NoTextError(ValueError):
    """The PDF has no text layer (scanned image). OCR is not implemented."""


def read_pdf(path: Path, file_id: str, filename: str) -> Document:
    pages: list[Page] = []
    with pdfplumber.open(path) as pdf:
        for i, p in enumerate(pdf.pages, start=1):
            pages.append(Page(number=i, text=p.extract_text(layout=True) or ""))
    if not any(p.text.strip() for p in pages):
        raise NoTextError("PDF has no extractable text (scanned image?). OCR is not supported in this version.")
    return Document(file_id=file_id, filename=filename, kind="pdf", pages=pages)
```

- [ ] **Step 6: Write `backend/app/readers/registry.py`**

```python
"""Extension -> reader. Add a new format by adding one entry."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .document import Document
from .pdf_reader import read_pdf
from .xlsx_reader import read_xlsx

READERS: dict[str, Callable[[Path, str, str], Document]] = {
    ".xlsx": read_xlsx,
    ".xlsm": read_xlsx,
    ".pdf": read_pdf,
}
SUPPORTED_EXTENSIONS = tuple(READERS)


class UnsupportedFileType(ValueError):
    pass


def read_document(path: Path, file_id: str, filename: str) -> Document:
    ext = Path(filename).suffix.lower() or path.suffix.lower()
    reader = READERS.get(ext)
    if reader is None:
        raise UnsupportedFileType(f"Unsupported file type '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}")
    return reader(path, file_id, filename)
```

- [ ] **Step 7: Run the tests**

Run: `pytest tests/test_readers.py -v`
Expected: 3 PASS

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: xlsx/pdf readers with format registry and synthetic test fixtures"
```

---

### Task 5: Content-based classifier

**Files:**
- Modify: `backend/app/classify/classifier.py` (replace the stub)
- Create: `backend/tests/test_classifier.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_classifier.py
from app.classify.classifier import DocType, classify
from app.readers.document import Document, Page, Sheet
from tests.helpers import (BALANCE_ROWS, BUDGET_ROWS, CAPITAL_CALLS_TEXT, COMPS_ROWS, COSTAR_PDF_TEXT, COSTAR_ROWS,
                           DISTRIBUTIONS_TEXT, HELLODATA_PDF_TEXT, LISTINGS_ROWS, LTO_ROWS, RENT_CHART_ROWS,
                           rent_roll_rows, schedule_rows)


def xdoc(**sheets):
    return Document("f", "f.xlsx", "xlsx", sheets=[Sheet(k, v) for k, v in sheets.items()])


def pdoc(text):
    return Document("p", "p.pdf", "pdf", pages=[Page(1, text)])


def test_classifies_each_sheet_type():
    doc = xdoc(
        b=BUDGET_ROWS, bs=BALANCE_ROWS, rr=rent_roll_rows("06/30/2026", 306, 338, 90.53, 14),
        sch=schedule_rows("06/30/2026", {"BWK.A1": 1, "BWK.B0": 1, "BWK.B1": 1, "BWK.S1": 1, "TOTAL": 1}),
        lto=LTO_ROWS, hd=LISTINGS_ROWS, comps=COMPS_ROWS, cs=COSTAR_ROWS, rc=RENT_CHART_ROWS, junk=[["hello"], ["world", 1]],
    )
    got = [p.doc_type for p in classify(doc)]
    assert got == [
        DocType.YARDI_BUDGET_COMPARISON, DocType.YARDI_BALANCE_SHEET, DocType.YARDI_RENT_ROLL,
        DocType.YARDI_MARKET_RENT_SCHEDULE, DocType.YARDI_LEASE_TRADE_OUT, DocType.HELLODATA_LISTINGS,
        DocType.HELLODATA_COMPS, DocType.COSTAR_SUBMARKET_EXCEL, DocType.RENT_CHART, DocType.UNKNOWN,
    ]
    assert classify(doc)[0].locator == "sheet 'b'"


def test_classifies_pdfs():
    assert classify(pdoc(COSTAR_PDF_TEXT))[0].doc_type == DocType.COSTAR_SUBMARKET_PDF
    assert classify(pdoc(CAPITAL_CALLS_TEXT))[0].doc_type == DocType.SLATE_CAPITAL_CALLS
    assert classify(pdoc(DISTRIBUTIONS_TEXT))[0].doc_type == DocType.SLATE_DISTRIBUTIONS
    assert classify(pdoc(HELLODATA_PDF_TEXT))[0].doc_type == DocType.HELLODATA_COMPS
    assert classify(pdoc("lorem ipsum"))[0].doc_type == DocType.UNKNOWN


def test_part_json_shape():
    p = classify(xdoc(b=BUDGET_ROWS))[0]
    assert set(p.to_json()) == {"doc_type", "confidence", "locator"} and 0.6 <= p.to_json()["confidence"] <= 1
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_classifier.py -v`
Expected: FAIL with `ImportError: cannot import name 'DocType'`

- [ ] **Step 3: Write `backend/app/classify/classifier.py`**

```python
"""Content-based document classification: one Part per xlsx sheet, one Part per PDF.

Signatures are substrings of the normalised head of the sheet (first 25 rows) or of the PDF text.
`must` substrings all have to appear; each `any_of` hit raises confidence. Filenames are never used.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..readers.document import Document, Page, Sheet, norm


class DocType(str, Enum):
    YARDI_BUDGET_COMPARISON = "yardi_budget_comparison"
    YARDI_BALANCE_SHEET = "yardi_balance_sheet"
    YARDI_RENT_ROLL = "yardi_rent_roll"
    YARDI_MARKET_RENT_SCHEDULE = "yardi_market_rent_schedule"
    YARDI_LEASE_TRADE_OUT = "yardi_lease_trade_out"
    HELLODATA_LISTINGS = "hellodata_listings"
    HELLODATA_COMPS = "hellodata_comps"
    COSTAR_SUBMARKET_EXCEL = "costar_submarket_excel"
    COSTAR_SUBMARKET_PDF = "costar_submarket_pdf"
    RENT_CHART = "rent_chart"
    SLATE_CAPITAL_CALLS = "slate_capital_calls"
    SLATE_DISTRIBUTIONS = "slate_distributions"
    UNKNOWN = "unknown"


DOC_TYPE_LABELS: dict[DocType, str] = {
    DocType.YARDI_BUDGET_COMPARISON: "Yardi Budget Comparison (P&L and capital)",
    DocType.YARDI_BALANCE_SHEET: "Yardi Balance Sheet",
    DocType.YARDI_RENT_ROLL: "Yardi Rent Roll summary (occupancy)",
    DocType.YARDI_MARKET_RENT_SCHEDULE: "Yardi Market Rent Schedule (rent by unit type)",
    DocType.YARDI_LEASE_TRADE_OUT: "Yardi Lease Trade-Out (renewals / move-ins)",
    DocType.HELLODATA_LISTINGS: "HelloData unit-level listings",
    DocType.HELLODATA_COMPS: "HelloData comp set summary",
    DocType.COSTAR_SUBMARKET_EXCEL: "CoStar submarket data table",
    DocType.COSTAR_SUBMARKET_PDF: "CoStar submarket report (PDF)",
    DocType.RENT_CHART: "Rent trend chart workbook",
    DocType.SLATE_CAPITAL_CALLS: "Slate capital calls",
    DocType.SLATE_DISTRIBUTIONS: "Slate distributions",
    DocType.UNKNOWN: "Unrecognized",
}

Signature = tuple[DocType, list[str], list[str]]

SHEET_SIGNATURES: list[Signature] = [
    (DocType.YARDI_BUDGET_COMPARISON, ["budget comparison"], ["ptd actual", "ytd actual", "mtd actual", "% var", "annual"]),
    (DocType.YARDI_BALANCE_SHEET, ["balance sheet"], ["beginning", "net change", "total assets", "current period"]),
    (DocType.YARDI_RENT_ROLL, ["rent roll", "summary groups"], ["% unit occupancy", "occupied units", "future residents", "# of units"]),
    (DocType.YARDI_MARKET_RENT_SCHEDULE, ["market rent schedule"], ["unit type", "occupied units", "average resident rent", "sq ft"]),
    (DocType.YARDI_LEASE_TRADE_OUT, ["resident name", "lease rent"], ["lease renewals", "move ins", "renewal start", "previous lease term", "effective rent"]),
    (DocType.HELLODATA_LISTINGS, ["property name", "asking rent", "effective rent"], ["leased date", "first listed", "days on mkt", "floorplan", "active listing"]),
    (DocType.HELLODATA_COMPS, ["rent comps", "yr built"], ["# units", "leased %", "similarity", "exposure"]),
    (DocType.COSTAR_SUBMARKET_EXCEL, ["period", "vacancy rate", "market asking rent"], ["inventory units", "under constr", "market cap rate", "absorp"]),
    (DocType.RENT_CHART, ["gross psf", "effective psf", "lease count"], ["comp set", "t12", "month"]),
]

PDF_SIGNATURES: list[Signature] = [
    (DocType.COSTAR_SUBMARKET_PDF, ["submarket report", "costar"], ["vacancy rate", "asking rent", "sale comparables", "key indicators"]),
    (DocType.HELLODATA_COMPS, ["rents by unit type"], ["ner", "concession", "# leased", "hellodata"]),
    (DocType.SLATE_CAPITAL_CALLS, ["new capital call"], ["total called", "callable capital", "no capital calls yet", "contributed"]),
    (DocType.SLATE_DISTRIBUTIONS, ["new distribution"], ["no distributions yet", "gross amount", "net amount", "settled"]),
]

MIN_CONFIDENCE = 0.6


@dataclass
class Part:
    """One classified unit of a file: a sheet (xlsx) or the whole document (pdf)."""

    doc_type: str
    confidence: float
    locator: str
    file_id: str
    filename: str
    sheet: Sheet | None = None
    pages: list[Page] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"doc_type": self.doc_type, "confidence": round(self.confidence, 2), "locator": self.locator}


def score(text: str, must: list[str], any_of: list[str]) -> float:
    if not all(m in text for m in must):
        return 0.0
    hits = sum(1 for a in any_of if a in text)
    return 0.6 + 0.4 * hits / max(len(any_of), 1)


def best_match(text: str, signatures: list[Signature]) -> tuple[DocType, float]:
    ranked = sorted(((score(text, must, anyof), t) for t, must, anyof in signatures), key=lambda x: -x[0])
    conf, t = ranked[0]
    return (t, conf) if conf >= MIN_CONFIDENCE else (DocType.UNKNOWN, conf)


def classify(doc: Document) -> list[Part]:
    parts: list[Part] = []
    if doc.kind == "xlsx":
        for sh in doc.sheets:
            t, conf = best_match(norm(sh.head_text(25)), SHEET_SIGNATURES)
            parts.append(Part(t.value, conf, f"sheet '{sh.name}'", doc.file_id, doc.filename, sheet=sh))
    else:
        t, conf = best_match(norm(doc.text[:30000]), PDF_SIGNATURES)
        parts.append(Part(t.value, conf, f"pages 1-{len(doc.pages)}", doc.file_id, doc.filename, pages=doc.pages))
    return parts
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_classifier.py tests/test_readers.py -v`
Expected: all PASS. Note `DocType` is a `str` enum, so `p.doc_type == DocType.X` compares equal to the stored string.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: keyword-signature classifier for Yardi, HelloData, CoStar, Slate documents"
```

---

### Task 6: Extraction base, Yardi common helpers, Budget Comparison extractor

The Budget Comparison feeds pages 5, 6, 7 and the debt-service line, so it gets the most careful treatment. Yardi exports carry hierarchy as leading spaces in the label cell; headers (rows with a label and no numbers) are tracked on a stack, and every numeric line records its section path.

**Files:**
- Create: `backend/app/extract/__init__.py` (empty), `backend/app/extract/base.py`, `backend/app/extract/yardi_common.py`, `backend/app/extract/yardi_budget.py`, `backend/tests/test_extract_yardi_budget.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_extract_yardi_budget.py
import pytest

from app.classify.classifier import DocType
from app.extract.base import ExtractionError
from app.extract.yardi_budget import extract
from app.extract.yardi_common import parse_period, walk_lines
from tests.helpers import BUDGET_ROWS, sheet_part


def test_parse_period():
    assert parse_period("Period = Apr 2026-Jun 2026") == {"start": "2026-04-01", "end": "2026-06-30", "label": "Apr 2026 - Jun 2026"}
    assert parse_period("Period = January 2026 - March 2026")["end"] == "2026-03-31"
    assert parse_period("no period here") is None


def test_budget_extractor_lines_sections_and_period():
    ex = extract(sheet_part(BUDGET_ROWS, DocType.YARDI_BUDGET_COMPARISON))
    d = ex.data
    assert d["period"] == {"start": "2026-04-01", "end": "2026-06-30", "label": "Apr 2026 - Jun 2026"}
    assert d["property_ref"] == "45726"
    assert d["columns"] == ["annual_budget", "ptd_actual", "ptd_budget", "ytd_actual", "ytd_budget"]
    by = {ln["norm"]: ln for ln in d["lines"] if not ln["unlabeled"]}
    gpr = by["gross potential rent"]
    assert gpr["values"]["ptd_actual"] == 1000 and gpr["values"]["ytd_budget"] == 1800 and gpr["code"] == "4000-0000"
    assert gpr["section"] == ["REVENUE", "Rental Income"] and gpr["is_total"] is False and gpr["row"] == 7
    assert by["total payroll"]["is_total"] is True and by["net rental income"]["is_total"] is True
    assert by["less:concessions-mthly"]["values"]["ptd_budget"] == 0
    assert by["roof"]["values"]["ptd_budget"] == 0 and "INTERIOR & EXTERIOR RENOVATIONS" in by["roof"]["section"]
    assert by["plumbing"]["section"][-2:] == ["NON-OPERATING ITEMS", "PLUMBING"]
    assert by["marketing & promotion"]["section"][-1] == "LEASE UP COSTS"
    unlabeled = [ln for ln in d["lines"] if ln["unlabeled"]]
    assert unlabeled and unlabeled[-1]["values"]["ptd_actual"] == 61 and unlabeled[-1]["values"]["ytd_budget"] == 69


def test_budget_extractor_requires_actual_and_budget_columns():
    with pytest.raises(ExtractionError):
        extract(sheet_part([["Budget Comparison"], ["Something", "Else"], ["x", 1]], DocType.YARDI_BUDGET_COMPARISON))


def test_walk_lines_handles_missing_leading_spaces():
    rows = [[None, None, "PTD Actual", "PTD Budget"], [None, "REVENUE"], ["4000-0000", "Gross Potential Rent", 5, 4], [None, "EXPENSES"], ["5000-0000", "Payroll", 3, 2]]
    from app.readers.document import Sheet
    lines = walk_lines(Sheet("R", rows), 0, {"ptd_actual": 2, "ptd_budget": 3})
    assert [ln["section"] for ln in lines] == [["REVENUE"], ["EXPENSES"]]
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_extract_yardi_budget.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.extract'`

- [ ] **Step 3: Write `backend/app/extract/base.py`**

```python
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
```

- [ ] **Step 4: Write `backend/app/extract/yardi_common.py`**

```python
"""Helpers shared by the Yardi report extractors (Budget Comparison, Balance Sheet, Rent Roll, Rent Schedule)."""
from __future__ import annotations

import calendar
import datetime as dt
import re

from ..readers.document import CODE_RE, Sheet, norm, to_date, to_number

PERIOD_RE = re.compile(r"period\s*=\s*([A-Za-z]{3,9}\s+\d{4})\s*-\s*([A-Za-z]{3,9}\s+\d{4})", re.I)
AS_OF_RE = re.compile(r"as\s*of\s*=?\s*(\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})", re.I)
PROPERTY_RE = re.compile(r"^(?P<name>[^()]+?)\s*\((?P<ref>[A-Za-z0-9]+)\)\s*$")
PROPERTY_REF_RE = re.compile(r"property\s*=\s*(\S+)", re.I)
TOTAL_RE = re.compile(r"\btotal\b|^net |^cash flow$", re.I)


def _month(s: str) -> dt.date:
    for fmt in ("%b %Y", "%B %Y"):
        try:
            return dt.datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"not a month: {s}")


def parse_period(text: str) -> dict | None:
    """'Period = Apr 2026-Jun 2026' -> {'start': '2026-04-01', 'end': '2026-06-30', 'label': ...}."""
    m = PERIOD_RE.search(text)
    if not m:
        return None
    try:
        start = _month(m.group(1)).replace(day=1)
        end_m = _month(m.group(2))
    except ValueError:
        return None
    end = end_m.replace(day=calendar.monthrange(end_m.year, end_m.month)[1])
    return {"start": start.isoformat(), "end": end.isoformat(), "label": f"{m.group(1).strip()} - {m.group(2).strip()}"}


def find_as_of(sheet: Sheet) -> str | None:
    hit = sheet.find(r"as\s*of", max_row=8)
    if not hit:
        return None
    m = AS_OF_RE.search(hit[2])
    d = to_date(m.group(1)) if m else None
    return d.isoformat() if d else None


def find_property(sheet: Sheet) -> tuple[str | None, str | None]:
    """(name, ref) from a title cell such as 'The Boardwalk (45726)' in the first rows."""
    for r in range(min(6, sheet.nrows)):
        for c in range(len(sheet.rows[r])):
            m = PROPERTY_RE.match(sheet.text(r, c))
            if m and not norm(m.group("name")).startswith(("property", "as of", "month", "period", "book")):
                return m.group("name").strip(), m.group("ref")
    return None, None


def find_property_ref(text: str) -> str | None:
    m = PROPERTY_REF_RE.search(text)
    return m.group(1) if m else None


def walk_lines(sheet: Sheet, header_row: int, colmap: dict[str, int]) -> list[dict]:
    """Turn a Yardi report body into line records carrying a section path.

    A row with a label and no numbers is a section header. Headers nest by the leading-space indent of
    the label cell: a new header pops headers with an indent >= its own. Numeric lines never pop the
    stack because Yardi indents are not strictly hierarchical. Rows with numbers but no label (the
    summary block Yardi appends at the bottom) are kept with `unlabeled=True`.
    """
    label_col = sheet.label_column(header_row + 1)
    code_col = None
    for c in range(label_col):
        if any(CODE_RE.match(sheet.text(r, c)) for r in range(header_row + 1, min(header_row + 80, sheet.nrows))):
            code_col = c
            break
    lines: list[dict] = []
    stack: list[tuple[int, str]] = []
    for r in range(header_row + 1, sheet.nrows):
        raw = sheet.cell(r, label_col)
        label = sheet.text(r, label_col)
        values = {k: to_number(sheet.cell(r, c)) for k, c in colmap.items()}
        has_vals = any(v is not None for v in values.values())
        if not label:
            if has_vals:
                lines.append({"code": "", "label": "", "norm": "", "indent": 0, "section": [s for _, s in stack],
                              "is_total": False, "unlabeled": True, "values": values, "row": r})
            continue
        indent = len(raw) - len(raw.lstrip(" ")) if isinstance(raw, str) else 0
        code = sheet.text(r, code_col) if code_col is not None else ""
        if not CODE_RE.match(code):
            code = ""
        if not has_vals:
            while stack and stack[-1][0] >= indent:
                stack.pop()
            stack.append((indent, label))
            continue
        nl = norm(label)
        lines.append({"code": code, "label": label, "norm": nl, "indent": indent, "section": [s for _, s in stack],
                      "is_total": bool(TOTAL_RE.search(nl)), "unlabeled": False, "values": values, "row": r})
    return lines
```

- [ ] **Step 5: Write `backend/app/extract/yardi_budget.py`**

```python
"""Yardi 'Budget Comparison' (P&L with PTD/YTD or MTD/PTD actual vs budget, plus capital sections)."""
from __future__ import annotations

from ..classify.classifier import Part
from ..readers.document import Sheet
from .base import Extraction, ExtractionError
from .yardi_common import find_property_ref, parse_period, walk_lines

COLUMN_PATTERNS = [
    ("mtd_actual", r"^mtd actual"), ("mtd_budget", r"^mtd budget"),
    ("ptd_actual", r"^ptd actual"), ("ptd_budget", r"^ptd budget"),
    ("ytd_actual", r"^ytd actual"), ("ytd_budget", r"^ytd budget"),
    ("annual_budget", r"^annual"),
]


def extract(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    hb = sh.header_block(["actual", "budget"], max_rows=1, search_rows=15)
    if hb is None:
        raise ExtractionError("No header row containing 'Actual' and 'Budget' found in the first 15 rows")
    hrow, _, headers = hb
    colmap = {key: c for key, rx in COLUMN_PATTERNS if (c := Sheet.col(headers, rx)) is not None}
    if not ({"ptd_actual", "mtd_actual"} & colmap.keys()):
        raise ExtractionError("No 'PTD Actual' or 'MTD Actual' column found")
    lines = walk_lines(sh, hrow, colmap)
    if not lines:
        raise ExtractionError("No line items found under the header row")
    head = sh.head_text(6)
    period = parse_period(head)
    warnings = [] if period else ["Reporting period not found in the header; it will be taken from another file"]
    return Extraction(
        doc_type=part.doc_type, locator=part.locator, warnings=warnings,
        data={"period": period, "property_ref": find_property_ref(head), "columns": sorted(colmap),
              "header_row": hrow, "lines": lines},
    )
```

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_extract_yardi_budget.py -v`
Expected: 4 PASS

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: Yardi budget comparison extractor with section-aware line walker"
```

---

### Task 7: Balance Sheet extractor

**Files:**
- Create: `backend/app/extract/yardi_balance_sheet.py`, `backend/tests/test_extract_yardi_balance_sheet.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_extract_yardi_balance_sheet.py
from app.classify.classifier import DocType
from app.extract.yardi_balance_sheet import extract
from tests.helpers import BALANCE_ROWS, sheet_part


def test_balance_sheet_lines():
    ex = extract(sheet_part(BALANCE_ROWS, DocType.YARDI_BALANCE_SHEET))
    by = {ln["norm"]: ln for ln in ex.data["lines"]}
    assert by["mortgage payable"]["values"]["current"] == 36519000
    assert by["total building"]["is_total"] is True and by["total building"]["values"]["current"] == 47520000
    assert by["owner contributions"]["values"]["current"] == 14259605.94
    assert by["accrued interest"]["values"] == {"current": 159161.98, "beginning": 164467.37, "change": -5305.39}
    assert by["accrued interest"]["section"] == ["LIABILITIES"]
    assert ex.data["period"]["end"] == "2026-06-30"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_extract_yardi_balance_sheet.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `backend/app/extract/yardi_balance_sheet.py`**

```python
"""Yardi 'Balance Sheet (With Period Change)'."""
from __future__ import annotations

from ..classify.classifier import Part
from ..readers.document import Sheet
from .base import Extraction, ExtractionError
from .yardi_common import parse_period, walk_lines


def extract(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    hb = sh.header_block(["balance", "beginning"], max_rows=2, search_rows=15)
    if hb is None:
        raise ExtractionError("No 'Balance' / 'Beginning' header found")
    hrow, k, headers = hb
    colmap = {
        "current": Sheet.col(headers, r"^balance", r"current"),
        "beginning": Sheet.col(headers, r"beginning"),
        "change": Sheet.col(headers, r"change"),
    }
    colmap = {a: b for a, b in colmap.items() if b is not None}
    if "current" not in colmap:
        raise ExtractionError("No current-balance column found")
    lines = walk_lines(sh, hrow + k - 1, colmap)
    if not lines:
        raise ExtractionError("No balance sheet lines found")
    return Extraction(doc_type=part.doc_type, locator=part.locator,
                      data={"period": parse_period(sh.head_text(6)), "columns": sorted(colmap), "lines": lines})
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/test_extract_yardi_balance_sheet.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: Yardi balance sheet extractor"
```

---

### Task 8: Rent Roll (occupancy) extractor

**Files:**
- Create: `backend/app/extract/yardi_rent_roll.py`, `backend/tests/test_extract_yardi_rent_roll.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_extract_yardi_rent_roll.py
import pytest

from app.classify.classifier import DocType
from app.extract.base import ExtractionError
from app.extract.yardi_rent_roll import extract
from tests.helpers import rent_roll_rows, sheet_part


def test_rent_roll_summary():
    d = extract(sheet_part(rent_roll_rows("06/30/2026", 306, 338, 90.53, 14), DocType.YARDI_RENT_ROLL)).data
    assert d["as_of"] == "2026-06-30" and d["property_name"] == "The Boardwalk" and d["property_ref"] == "45726"
    assert d["total_units"] == 338 and d["occupied_units"] == 306 and d["vacant_units"] == 32
    assert d["future_applicants"] == 14 and abs(d["occupancy_pct"] - 0.9053) < 1e-9
    assert d["avg_market_rent"] == 1317.72 and d["avg_resident_rent"] == 1325.13
    assert d["prov"]["occupied_row"] == 14


def test_rent_roll_without_summary_block_raises():
    with pytest.raises(ExtractionError):
        extract(sheet_part([["Rent Roll"], ["Nothing", 1]], DocType.YARDI_RENT_ROLL))
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_extract_yardi_rent_roll.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `backend/app/extract/yardi_rent_roll.py`**

```python
"""Yardi 'Rent Roll' summary block: occupancy, vacant and future/applicant counts, average rents."""
from __future__ import annotations

import re

from ..classify.classifier import Part
from ..readers.document import Sheet, as_fraction, norm, to_number
from .base import Extraction, ExtractionError
from .yardi_common import find_as_of, find_property

_ROW_PATTERNS = {
    "occupied": [r"^occupied units"],
    "vacant": [r"^total vacant", r"^vacant units"],
    "future": [r"^future residents", r"applicants"],
    "totals": [r"^totals?:?$"],
    "current": [r"^current/notice/vacant", r"^current residents"],
}


def _pick(found: dict[str, tuple], patterns: list[str]) -> tuple:
    for p in patterns:
        rx = re.compile(p)
        for label, v in found.items():
            if rx.search(label):
                return v
    return (None, None, None)


def extract(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    name, ref = find_property(sh)
    as_of = find_as_of(sh)
    hb = sh.header_block(["summary groups", "# of"], max_rows=3, search_rows=120)
    if hb is None:
        raise ExtractionError("Rent Roll summary block ('Summary Groups' with '# Of Units') not found")
    hrow, k, headers = hb
    c_units = Sheet.col(headers, r"# of units", r"^units$")
    c_pct = Sheet.col(headers, r"% unit occupancy", r"occupancy")
    if c_units is None:
        raise ExtractionError("'# Of Units' column not found in the summary block")
    found: dict[str, tuple] = {}
    for r in range(hrow + k, min(hrow + k + 20, sh.nrows)):
        label = norm(sh.text(r, 0))
        if not label:
            continue
        pct = to_number(sh.cell(r, c_pct)) if c_pct is not None else None
        found[label] = (to_number(sh.cell(r, c_units)), pct, r)
        if re.match(r"^totals?:?$", label):
            break
    occ_units, occ_pct, occ_row = _pick(found, _ROW_PATTERNS["occupied"])
    if occ_units is None:
        raise ExtractionError("'Occupied Units' row not found in the summary block")
    vac_units, _, _ = _pick(found, _ROW_PATTERNS["vacant"])
    fut_units, _, _ = _pick(found, _ROW_PATTERNS["future"])
    tot_units, _, _ = _pick(found, _ROW_PATTERNS["totals"])
    if tot_units is None:
        tot_units, _, _ = _pick(found, _ROW_PATTERNS["current"])
    total_units = tot_units if tot_units else ((occ_units or 0) + (vac_units or 0)) or None
    occupancy = as_fraction(occ_pct) if occ_pct is not None else (occ_units / total_units if total_units else None)

    avg_market = avg_resident = None
    pb = sh.header_block(["property", "total"], max_rows=3, search_rows=hrow)
    if pb is not None:
        prow, pk, ph = pb
        c_name, c_tot = Sheet.col(ph, r"^name$"), Sheet.col(ph, r"total units")
        c_mkt, c_res = Sheet.col(ph, r"average market rent"), Sheet.col(ph, r"average resident rent")
        for r in range(prow + pk, hrow):
            row_name = norm(sh.text(r, c_name)) if c_name is not None else ""
            is_property_row = bool(name) and row_name == norm(name)
            is_total_row = c_tot is not None and total_units and to_number(sh.cell(r, c_tot)) == total_units and bool(row_name)
            if is_property_row or is_total_row:
                avg_market = to_number(sh.cell(r, c_mkt)) if c_mkt is not None else None
                avg_resident = to_number(sh.cell(r, c_res)) if c_res is not None else None
                break
    warnings = [] if as_of else ["'As Of' date not found; this rent roll cannot be placed in time automatically"]
    return Extraction(
        doc_type=part.doc_type, locator=part.locator, warnings=warnings,
        data={"as_of": as_of, "property_name": name, "property_ref": ref, "total_units": total_units,
              "occupied_units": occ_units, "occupancy_pct": occupancy, "vacant_units": vac_units,
              "future_applicants": fut_units, "avg_market_rent": avg_market, "avg_resident_rent": avg_resident,
              "prov": {"occupied_row": occ_row, "summary_header_row": hrow}},
    )
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_extract_yardi_rent_roll.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: Yardi rent roll occupancy extractor"
```

---

### Task 9: Market Rent Schedule extractor (rent by unit type)

**Files:**
- Create: `backend/app/extract/yardi_rent_schedule.py`, `backend/tests/test_extract_yardi_rent_schedule.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_extract_yardi_rent_schedule.py
from app.classify.classifier import DocType
from app.extract.yardi_rent_schedule import extract, parse_unit_type
from tests.helpers import schedule_rows, sheet_part

RENTS = {"BWK.A1": 1172.47, "BWK.B0": 1331.04, "BWK.B1": 1370.84, "BWK.S1": 1108.31, "TOTAL": 1250.5}


def test_parse_unit_type():
    assert parse_unit_type("1 Bedroom 1 Bathroom (BWK.A1)") == ("1 Bedroom 1 Bathroom", "BWK.A1", 1, 1.0)
    assert parse_unit_type("0 Bedroom 1 Bathroom (BWK.S2)")[2] == 0
    assert parse_unit_type("Studio (S1)") == ("Studio", "S1", 0, None)
    assert parse_unit_type("2x2 - Deluxe")[2:] == (2, 2.0)
    assert parse_unit_type("3BR/2.5BA")[2:] == (3, 2.5)
    assert parse_unit_type("Penthouse")[2:] == (None, None)


def test_schedule_rows_and_total():
    d = extract(sheet_part(schedule_rows("06/30/2026", RENTS), DocType.YARDI_MARKET_RENT_SCHEDULE)).data
    assert d["as_of"] == "2026-06-30" and d["property_name"] == "The Boardwalk"
    ut = d["unit_types"]
    assert [u["code"] for u in ut] == ["BWK.A1", "BWK.B0", "BWK.B1", "BWK.S1"]
    a1 = ut[0]
    assert (a1["bedrooms"], a1["bathrooms"], a1["units"], a1["sqft"], a1["occupied_units"]) == (1, 1.0, 40, 657, 38)
    assert a1["avg_resident_rent"] == 1172.47 and a1["market_rent"] == 999 and a1["row"] == 6
    assert ut[3]["bedrooms"] == 0 and ut[1]["bathrooms"] == 1.0 and ut[2]["bathrooms"] == 2.0
    assert d["total"] == {"units": 139, "sqft": 760, "occupied_units": 126, "avg_resident_rent": 1250.5, "market_rent": 1100, "row": 10}


def test_modified_schedule_variant_without_market_rent_column():
    rows = [["Market Rent Schedule"], ["For Selected Properties"], ["As Of = 03/31/2026"],
            ["Unit Type", "Units", "Unit Type", "Occupied", "Average", None, "Average"],
            [None, None, "Sq Ft", "Units", "Resident Rent", None, "Resident Rent (RR)"],
            ["1 Bedroom 1 Bathroom (BWK.A1)", 40, 657, 38, 1205.1, None, 1204.55, 0.55],
            ["Grand Total", 40, 657, 38, 1205.1, None, 1204.55, 0.55]]
    d = extract(sheet_part(rows, DocType.YARDI_MARKET_RENT_SCHEDULE)).data
    assert d["unit_types"][0]["avg_resident_rent"] == 1205.1 and d["unit_types"][0]["market_rent"] is None
    assert d["property_name"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_extract_yardi_rent_schedule.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `backend/app/extract/yardi_rent_schedule.py`**

```python
"""Yardi 'Market Rent Schedule': per unit type units, sqft, market rent, occupied units, average resident rent."""
from __future__ import annotations

import re

from ..classify.classifier import Part
from ..readers.document import Sheet, norm, to_number
from .base import Extraction, ExtractionError
from .yardi_common import find_as_of, find_property

_CODE_RE = re.compile(r"^(?P<label>.*?)\s*\((?P<code>[A-Za-z0-9.\-_/ ]+)\)\s*$")
_X_RE = re.compile(r"^\s*(\d+)\s*x\s*(\d+(?:\.\d)?)", re.I)
_BED_RE = re.compile(r"(\d+)\s*(?:bed|br\b|bd\b|bdrm)", re.I)
_BATH_RE = re.compile(r"(\d+(?:\.\d)?)\s*(?:bath|ba\b)", re.I)


def parse_unit_type(label: str) -> tuple[str, str | None, int | None, float | None]:
    """'1 Bedroom 1 Bathroom (BWK.A1)' -> ('1 Bedroom 1 Bathroom', 'BWK.A1', 1, 1.0)."""
    label = label.strip()
    code = None
    m = _CODE_RE.match(label)
    if m:
        label, code = m.group("label").strip(), m.group("code").strip()
    low = label.lower()
    beds: int | None = None
    baths: float | None = None
    if (mx := _X_RE.match(low)):
        beds, baths = int(mx.group(1)), float(mx.group(2))
    else:
        if (mb := _BED_RE.search(low)):
            beds = int(mb.group(1))
        elif "studio" in low or "efficiency" in low:
            beds = 0
        if (mt := _BATH_RE.search(low)):
            baths = float(mt.group(1))
    return label, code, beds, baths


def extract(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    name, ref = find_property(sh)
    as_of = find_as_of(sh)
    hb = sh.header_block(["unit type", "units"], max_rows=3, search_rows=20)
    if hb is None:
        raise ExtractionError("No 'Unit Type' / 'Units' header found")
    hrow, k, headers = hb
    c_label = Sheet.col(headers, r"^unit type$")
    c_units = Sheet.col(headers, r"^units$")
    if c_label is None or c_units is None:
        raise ExtractionError("'Unit Type' or 'Units' column not found")
    c_sqft = Sheet.col(headers, r"sq ?ft|sqft|square")
    c_occ = Sheet.col(headers, r"occupied")
    c_arr = Sheet.col(headers, r"^average resident rent", r"^avg resident rent", r"resident rent")
    c_mkt = Sheet.col(headers, r"^unit type rent$", r"^market rent")
    unit_types: list[dict] = []
    total: dict | None = None
    for r in range(hrow + k, sh.nrows):
        label = sheet_text = sh.text(r, c_label)
        if not label:
            continue
        rec = {
            "units": to_number(sh.cell(r, c_units)),
            "sqft": to_number(sh.cell(r, c_sqft)) if c_sqft is not None else None,
            "market_rent": to_number(sh.cell(r, c_mkt)) if c_mkt is not None else None,
            "occupied_units": to_number(sh.cell(r, c_occ)) if c_occ is not None else None,
            "avg_resident_rent": to_number(sh.cell(r, c_arr)) if c_arr is not None else None,
            "row": r,
        }
        nl = norm(label)
        if nl.startswith("grand total") or nl.startswith("total"):
            total = rec
            break
        if rec["units"] is None:
            continue
        clean, code, beds, baths = parse_unit_type(sheet_text)
        unit_types.append({"label": clean, "code": code, "bedrooms": beds, "bathrooms": baths, **rec})
    if not unit_types:
        raise ExtractionError("No unit-type rows found")
    warnings = [] if as_of else ["'As Of' date not found"]
    if any(u["bedrooms"] is None for u in unit_types):
        warnings.append("Bedroom count could not be parsed for some unit types; they are grouped as 'Other'")
    return Extraction(doc_type=part.doc_type, locator=part.locator, warnings=warnings,
                      data={"as_of": as_of, "property_name": name, "property_ref": ref, "unit_types": unit_types, "total": total})
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_extract_yardi_rent_schedule.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: Yardi market rent schedule extractor with unit-type parsing"
```

---

### Task 10: Lease Trade-Out extractor (renewals, move-ins, transfers)

**Files:**
- Create: `backend/app/extract/yardi_lto.py`, `backend/tests/test_extract_yardi_lto.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_extract_yardi_lto.py
from app.classify.classifier import DocType
from app.extract.yardi_lto import extract
from tests.helpers import LTO_ROWS, sheet_part


def test_lto_sections_rows_and_previous_term_columns():
    d = extract(sheet_part(LTO_ROWS, DocType.YARDI_LEASE_TRADE_OUT)).data
    assert d["period"] == {"start": "2026-04-01", "end": "2026-06-30"}
    assert d["property_name"] == "The Boardwalk"
    ren, mi = d["sections"]["renewals"]["rows"], d["sections"]["move_ins"]["rows"]
    assert len(ren) == 2 and len(mi) == 3
    r0 = ren[0]
    assert r0["unit_type"] == "BWK.A1" and r0["sqft"] == 657 and r0["unit"] == "4715D125"
    assert r0["lease_rent"] == 1425 and r0["prev_lease_rent"] == 1405
    assert r0["effective_rent"] == 1306.25 and r0["prev_effective_rent"] == 1405
    assert r0["start"] == "2026-04-22" and r0["term"] == 12 and r0["prev_term"] == 12
    assert r0["concessions"] == 1425 and r0["months_free"] == 1 and r0["market_rent"] == 1264
    assert r0["row"] == 5
    assert mi[2]["unit_type"] == "BWK.S1" and mi[2]["lease_rent"] == 900 and mi[2]["prev_lease_rent"] == 1000
    assert d["sections"]["renewals"]["header_row"] == 4


def test_lto_without_group_row_uses_duplicate_header_rule():
    rows = [[None, "Move Ins"], [None, "Move In between 2026-01-01 and 2026-03-31"],
            [None, "Resident Name", "Unit Type", "Sqft", "Unit", "Lease Start", "Lease Term", "Lease Rent", "Effective Rent", "Lease Rent", "Effective Rent"],
            ["P", "X", "A1", 600, "101", "2026-02-01", 12, 1000, 950, 1200, 1150]]
    d = extract(sheet_part(rows, DocType.YARDI_LEASE_TRADE_OUT)).data
    row = d["sections"]["move_ins"]["rows"][0]
    assert row["lease_rent"] == 1000 and row["prev_lease_rent"] == 1200 and row["prev_effective_rent"] == 1150
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_extract_yardi_lto.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `backend/app/extract/yardi_lto.py`**

```python
"""Yardi Lease Trade-Out report (RRG-10658 style): 'Lease Renewals', 'Move Ins', 'Unit Transfers' sections.

Each section has a header row with 'Resident Name' and 'Lease Rent'. A group row above it says where the
'Previous Lease Term' columns start; when that row is absent, the second occurrence of a duplicated header
name is treated as the previous-term column.
"""
from __future__ import annotations

import re

from ..classify.classifier import Part
from ..readers.document import norm, to_date, to_number
from .base import Extraction, ExtractionError

SECTION_TITLES = {"renewals": r"lease renewals?", "move_ins": r"move[- ]?ins?", "transfers": r"unit transfers?"}
RANGE_RE = re.compile(r"between\s+(\d{4}-\d{2}-\d{2})\s+and\s+(\d{4}-\d{2}-\d{2})", re.I)
HEADER_MAP = [
    ("resident_name", r"^resident name"), ("unit_type", r"^unit type"), ("sqft", r"^sq ?ft"), ("unit", r"^unit$"),
    ("start", r"renewal start|lease start|move.?in date|start date"), ("term", r"^lease term"),
    ("market_rent", r"^market rent"), ("lease_rent", r"^lease rent"), ("concessions", r"^total concessions"),
    ("months_free", r"months free"), ("effective_rent", r"^effective rent$"), ("rent_change", r"^rent change"),
    ("pct_change", r"^% change"),
]
PREV_KEYS = {"lease_rent", "concessions", "term", "effective_rent"}


def _map_columns(headers: list[str], prev_start: int | None) -> dict[str, int]:
    colmap: dict[str, int] = {}
    for i, h in enumerate(headers):
        for key, rx in HEADER_MAP:
            if re.search(rx, h):
                if key in PREV_KEYS and ((prev_start is not None and i >= prev_start) or key in colmap):
                    key = "prev_" + key
                colmap.setdefault(key, i)
                break
    return colmap


def _section_title(sh, hrow: int) -> tuple[str | None, dict | None]:
    title, period = None, None
    for r in range(hrow - 1, max(-1, hrow - 8), -1):
        t = norm(sh.row_text(r))
        if not t:
            continue
        m = RANGE_RE.search(t)
        if m and period is None:
            period = {"start": m.group(1), "end": m.group(2)}
        for key, rx in SECTION_TITLES.items():
            if re.search(rx, t) and title is None:
                title = key
        if title and period:
            break
    return title, period


def extract(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    header_rows = [r for r in range(sh.nrows)
                   if "resident name" in norm(sh.row_text(r)) and "lease rent" in norm(sh.row_text(r))]
    if not header_rows:
        raise ExtractionError("No section header with 'Resident Name' and 'Lease Rent' found")
    header_set = set(header_rows)
    sections: dict[str, dict] = {}
    period: dict | None = None
    property_name: str | None = None
    for hrow in header_rows:
        headers = [norm(sh.text(hrow, c)) for c in range(len(sh.rows[hrow]))]
        group = [norm(sh.text(hrow - 1, c)) for c in range(len(sh.rows[hrow - 1]))] if hrow > 0 else []
        prev_start = next((i for i, g in enumerate(group) if "previous" in g), None)
        cm = _map_columns(headers, prev_start)
        if "unit_type" not in cm or "lease_rent" not in cm:
            continue
        title, sec_period = _section_title(sh, hrow)
        period = period or sec_period
        title = title or f"section_{hrow}"
        rows: list[dict] = []
        for r in range(hrow + 1, sh.nrows):
            if r in header_set:
                break
            rt = norm(sh.row_text(r))
            if not rt:
                continue
            if "averages for" in rt:
                continue
            if not sh.has_numbers(r) and any(re.search(rx, rt) for rx in SECTION_TITLES.values()):
                break
            unit_type = sh.text(r, cm["unit_type"])
            num = lambda key: to_number(sh.cell(r, cm[key])) if key in cm else None  # noqa: E731
            lease_rent, prev_rent = num("lease_rent"), num("prev_lease_rent")
            if not unit_type or (lease_rent is None and prev_rent is None):
                continue
            if property_name is None and sh.text(r, 0) and to_number(sh.cell(r, 0)) is None:
                property_name = sh.text(r, 0)
            start = to_date(sh.cell(r, cm["start"])) if "start" in cm else None
            rows.append({
                "unit_type": unit_type, "sqft": num("sqft"), "unit": sh.text(r, cm["unit"]) if "unit" in cm else None,
                "start": start.isoformat() if start else None, "term": num("term"), "market_rent": num("market_rent"),
                "lease_rent": lease_rent, "concessions": num("concessions"), "months_free": num("months_free"),
                "effective_rent": num("effective_rent"), "prev_lease_rent": prev_rent,
                "prev_concessions": num("prev_concessions"), "prev_term": num("prev_term"),
                "prev_effective_rent": num("prev_effective_rent"), "rent_change": num("rent_change"),
                "pct_change": num("pct_change"), "row": r,
            })
        sections[title] = {"rows": rows, "header_row": hrow, "columns": sorted(cm)}
    if not sections:
        raise ExtractionError("No usable trade-out sections found")
    warnings = [] if period else ["Lease date range not found above the section headers"]
    return Extraction(doc_type=part.doc_type, locator=part.locator, warnings=warnings,
                      data={"period": period, "property_name": property_name, "sections": sections})
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_extract_yardi_lto.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: Yardi lease trade-out extractor"
```

---

### Task 11: HelloData extractors (unit-level listings, comp summary sheet or PDF)

**Files:**
- Create: `backend/app/extract/hellodata_listings.py`, `backend/app/extract/hellodata_comps.py`, `backend/tests/test_extract_hellodata.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_extract_hellodata.py
from app.classify.classifier import DocType
from app.extract.hellodata_comps import extract as extract_comps
from app.extract.hellodata_listings import extract as extract_listings
from tests.helpers import COMPS_ROWS, HELLODATA_PDF_TEXT, LISTINGS_ROWS, pdf_part, sheet_part


def test_listings_aggregate_per_property():
    d = extract_listings(sheet_part(LISTINGS_ROWS, DocType.HELLODATA_LISTINGS)).data
    assert d["row_count"] == 5 and set(d["properties"]) == {"The Boardwalk", "The Ashlar"}
    b = d["properties"]["The Boardwalk"]
    assert b["rows"] == 2 and b["leased"] == 1 and b["active"] == 1
    assert b["asking_sum"] == 2500 and b["asking_n"] == 2 and b["effective_sum"] == 2400
    assert b["address"].startswith("4637") and b["first_row"] == 3
    assert b["monthly"] == {"2026-04": {"n": 1, "asking_sum": 1300.0, "effective_sum": 1300.0, "sqft_sum": 657.0}}
    a = d["properties"]["The Ashlar"]
    assert a["rows"] == 3 and a["leased"] == 2 and a["active"] == 1 and a["max_leased"] == "2026-06-01"


def test_comps_from_sheet():
    d = extract_comps(sheet_part(COMPS_ROWS, DocType.HELLODATA_COMPS)).data
    assert d["source"] == "sheet" and [c["name"] for c in d["comps"]] == ["The Boardwalk", "The Ashlar"]
    b = d["comps"][0]
    assert (b["year_built"], b["units"], b["avg_sqft"], b["leased_pct"]) == (1973, 338, 843.73, 0.9)
    assert d["average"]["units"] == 298 and d["comps"][1]["row"] == 5


def test_comps_from_pdf():
    d = extract_comps(pdf_part(HELLODATA_PDF_TEXT, DocType.HELLODATA_COMPS)).data
    assert d["source"] == "pdf" and [c["name"] for c in d["comps"]] == ["The Boardwalk", "Westchase"]
    b = d["comps"][0]
    assert (b["leased_count"], b["active_count"], b["avg_sqft"], b["avg_rent"], b["ner"]) == (34, 45, 841, 1314, 1178)
    assert abs(b["concession_pct"] - 0.104) < 1e-9 and b["units"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_extract_hellodata.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `backend/app/extract/hellodata_listings.py`**

```python
"""HelloData unit-level listings export: one row per listing for the subject and its comps.

The payload is aggregated per property (counts and sums) so it stays small; monthly sums of leased
listings feed the rent-trend chart when no pre-built chart workbook is supplied.
"""
from __future__ import annotations

from ..classify.classifier import Part
from ..readers.document import Sheet, to_date, to_number
from .base import Extraction, ExtractionError


def _new_property(address: str | None, row: int) -> dict:
    return {"address": address, "first_row": row, "rows": 0, "leased": 0, "active": 0,
            "asking_sum": 0.0, "asking_n": 0, "effective_sum": 0.0, "effective_n": 0,
            "sqft_sum": 0.0, "sqft_n": 0, "monthly": {}, "min_leased": None, "max_leased": None}


def extract(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    hb = sh.header_block(["property name", "asking rent", "effective rent"], max_rows=1, search_rows=15)
    if hb is None:
        raise ExtractionError("No header with 'Property Name', 'Asking Rent' and 'Effective Rent' found")
    hrow, _, headers = hb
    c_name = Sheet.col(headers, r"^property name")
    c_addr = Sheet.col(headers, r"^address")
    c_sqft = Sheet.col(headers, r"^sqft$|^sq ?ft|square")
    c_leased = Sheet.col(headers, r"leased date")
    c_active = Sheet.col(headers, r"active listing")
    c_ask = Sheet.col(headers, r"^asking rent$")
    c_eff = Sheet.col(headers, r"^effective rent$")
    if c_name is None or c_ask is None:
        raise ExtractionError("'Property Name' or 'Asking Rent' column not found")
    props: dict[str, dict] = {}
    total = 0
    for r in range(hrow + 1, sh.nrows):
        name = sh.text(r, c_name)
        if not name:
            continue
        total += 1
        p = props.setdefault(name, _new_property(sh.text(r, c_addr) or None if c_addr is not None else None, r))
        p["rows"] += 1
        asking = to_number(sh.cell(r, c_ask))
        eff = to_number(sh.cell(r, c_eff)) if c_eff is not None else None
        sqft = to_number(sh.cell(r, c_sqft)) if c_sqft is not None else None
        if asking is not None:
            p["asking_sum"] += asking
            p["asking_n"] += 1
        if eff is not None:
            p["effective_sum"] += eff
            p["effective_n"] += 1
        if sqft:
            p["sqft_sum"] += sqft
            p["sqft_n"] += 1
        if c_active is not None and str(sh.cell(r, c_active)).strip().lower() in ("true", "1", "yes"):
            p["active"] += 1
        leased = to_date(sh.cell(r, c_leased)) if c_leased is not None else None
        if leased:
            p["leased"] += 1
            iso = leased.isoformat()
            p["min_leased"] = iso if p["min_leased"] is None or iso < p["min_leased"] else p["min_leased"]
            p["max_leased"] = iso if p["max_leased"] is None or iso > p["max_leased"] else p["max_leased"]
            if asking is not None and sqft:
                m = p["monthly"].setdefault(leased.strftime("%Y-%m"), {"n": 0, "asking_sum": 0.0, "effective_sum": 0.0, "sqft_sum": 0.0})
                m["n"] += 1
                m["asking_sum"] += asking
                m["effective_sum"] += eff if eff is not None else asking
                m["sqft_sum"] += sqft
    if not props:
        raise ExtractionError("No listing rows found under the header")
    return Extraction(doc_type=part.doc_type, locator=part.locator,
                      data={"properties": props, "row_count": total, "header_row": hrow})
```

- [ ] **Step 4: Write `backend/app/extract/hellodata_comps.py`**

```python
"""HelloData comp-set summary.

Two shapes feed the same payload: the 'Rent Comps' sheet of the full report workbook (year built, units,
leased %) and the one-page 'Rents by Unit Type' PDF (leased/active counts, average rent, NER, concession %).
"""
from __future__ import annotations

import re

from ..classify.classifier import Part
from ..readers.document import Sheet, as_fraction, norm, to_number
from .base import Extraction, ExtractionError

_PDF_ROW = re.compile(
    r"^(?P<name>.+?) (?P<leased>\d+) (?P<active>\d+) (?P<dom>\d+) (?P<minsf>[\d,]+) (?P<avgsf>[\d,]+) (?P<maxsf>[\d,]+) "
    r"\$(?P<minrent>[\d,]+) \$(?P<avgrent>[\d,]+) \$(?P<maxrent>[\d,]+) \$(?P<psf>[\d.]+) \$(?P<ner>[\d,]+) "
    r"\$(?P<nerpsf>[\d.]+) (?P<conc>[\d.]+)%"
)


def _int(v: float | None) -> int | None:
    return int(round(v)) if v is not None else None


def _from_sheet(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    hb = sh.header_block(["property", "built"], max_rows=1, search_rows=15)
    if hb is None:
        raise ExtractionError("No 'Property' / 'Yr Built' header found")
    hrow, _, headers = hb
    c_name = Sheet.col(headers, r"^property$", r"^property name")
    c_addr, c_built = Sheet.col(headers, r"^address"), Sheet.col(headers, r"built")
    c_units = Sheet.col(headers, r"^# ?units$", r"^units$")
    c_sqft, c_leased = Sheet.col(headers, r"avg sqft|avg sf"), Sheet.col(headers, r"^leased %")
    c_stories = Sheet.col(headers, r"stories")
    if c_name is None:
        raise ExtractionError("'Property' column not found")
    comps: list[dict] = []
    average: dict | None = None
    blanks = 0
    for r in range(hrow + 1, sh.nrows):
        name = sh.text(r, c_name)
        if not name:
            blanks += 1
            if blanks > 2:
                break
            continue
        blanks = 0
        rec = {
            "name": name, "address": (sh.text(r, c_addr) or None) if c_addr is not None else None,
            "year_built": _int(to_number(sh.cell(r, c_built))) if c_built is not None else None,
            "units": _int(to_number(sh.cell(r, c_units))) if c_units is not None else None,
            "stories": _int(to_number(sh.cell(r, c_stories))) if c_stories is not None else None,
            "avg_sqft": to_number(sh.cell(r, c_sqft)) if c_sqft is not None else None,
            "leased_pct": as_fraction(to_number(sh.cell(r, c_leased))) if c_leased is not None else None,
            "row": r,
        }
        if norm(name).startswith("comp average"):
            average = rec
        else:
            comps.append(rec)
    if not comps:
        raise ExtractionError("No comp rows found")
    return Extraction(doc_type=part.doc_type, locator=part.locator, data={"comps": comps, "average": average, "source": "sheet"})


def _from_pdf(part: Part) -> Extraction:
    comps: list[dict] = []
    for page in part.pages:
        for line in page.lines:
            m = _PDF_ROW.match(re.sub(r"\s+", " ", line).strip())
            if not m:
                continue
            g = m.groupdict()
            comps.append({
                "name": g["name"].strip(), "address": None, "year_built": None, "units": None, "stories": None,
                "avg_sqft": to_number(g["avgsf"]), "leased_pct": None,
                "leased_count": int(g["leased"]), "active_count": int(g["active"]),
                "avg_rent": to_number(g["avgrent"]), "ner": to_number(g["ner"]),
                "concession_pct": (to_number(g["conc"]) or 0) / 100, "page": page.number,
            })
    if not comps:
        raise ExtractionError("No 'Rents by Unit Type' rows found in the PDF")
    return Extraction(doc_type=part.doc_type, locator=part.locator, data={"comps": comps, "average": None, "source": "pdf"})


def extract(part: Part) -> Extraction:
    return _from_sheet(part) if part.sheet is not None else _from_pdf(part)
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_extract_hellodata.py -v`
Expected: 3 PASS

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: HelloData listings and comp summary extractors"
```

---

### Task 12: CoStar extractors (submarket Excel table and submarket report PDF)

**Files:**
- Create: `backend/app/extract/costar_excel.py`, `backend/app/extract/costar_pdf.py`, `backend/tests/test_extract_costar.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_extract_costar.py
from app.classify.classifier import DocType
from app.extract.costar_excel import extract as extract_excel
from app.extract.costar_pdf import extract as extract_pdf, parse_costar_text
from tests.helpers import COSTAR_PDF_TEXT, COSTAR_ROWS, pdf_part, sheet_part


def test_costar_excel_series():
    d = extract_excel(sheet_part(COSTAR_ROWS, DocType.COSTAR_SUBMARKET_EXCEL)).data
    s = d["series"]
    assert [x["period"] for x in s] == ["2026 Q3 QTD", "2026 Q2", "2026 Q1", "2025 Q4"]
    q2 = s[1]
    assert (q2["year"], q2["quarter"], q2["flag"]) == (2026, 2, "") and s[0]["flag"] == "QTD"
    assert abs(q2["vacancy"] - 0.16339) < 1e-4 and abs(q2["asking_rent"] - 1555.1) < 0.01
    assert abs(q2["rent_growth"] + 0.05424) < 1e-4 and q2["under_construction"] == 0 and q2["uc_pct"] == 0
    assert q2["absorption_12m"] == 406 and q2["row"] == 2 and abs(q2["cap_rate"] - 0.061) < 1e-9


def test_costar_pdf_parsing():
    d = parse_costar_text(COSTAR_PDF_TEXT.split("\f"))
    assert d["submarket"] == "Western Lee County" and d["market"] == "Fort Myers" and d["state"] == "FL"
    assert d["report_date"] == "2026-07-21" and d["licensed_to"] == "ZMR Capital"
    assert d["overview"] == {"delivered_12m": 674, "absorption_12m": 449, "vacancy": 0.159, "rent_growth_12m": -0.044}
    assert d["key_stats"]["inventory"] == 9571 and d["key_stats"]["asking_rent"] == 1564 and d["key_stats"]["under_construction"] == 0
    assert d["trends"]["vacancy"]["peak"] == 0.163 and d["trends"]["vacancy"]["peak_when"] == "2026 Q2"
    assert d["trends"]["asking_rent_growth"]["trough"] == -0.084
    sale = d["sales"][1]
    assert sale["name"] == "The Boardwalk" and sale["year_built"] == 1973 and sale["units"] == 338
    assert sale["sale_date"] == "2025-07-30" and sale["price"] == 38100000 and sale["price_per_unit"] == 112721
    assert d["deliveries"][0] == {"name": "Montage at Midtown", "units": 321, "stories": 4, "start": "Apr 2024", "complete": "Jun 2026", "page": 3}
    ex = extract_pdf(pdf_part(COSTAR_PDF_TEXT, DocType.COSTAR_SUBMARKET_PDF))
    assert ex.data["submarket"] == "Western Lee County"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_extract_costar.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `backend/app/extract/costar_excel.py`**

```python
"""CoStar submarket 'DataTable' export: one row per quarter with vacancy, asking rent, growth, pipeline."""
from __future__ import annotations

import re

from ..classify.classifier import Part
from ..readers.document import Sheet, as_fraction, to_number
from .base import Extraction, ExtractionError

PERIOD_RE = re.compile(r"^(\d{4})\s*Q([1-4])\s*([A-Za-z]+)?$")
COLUMNS = [
    ("vacancy", r"vacancy rate"), ("asking_rent", r"asking rent"), ("rent_growth", r"rent growth"),
    ("inventory", r"inventory"), ("under_construction", r"under constr(uction)? units"),
    ("uc_pct", r"under constr(uction)? %"), ("absorption_12m", r"absorp"),
    ("sale_price_unit", r"sale price/unit|price/unit"), ("sales_vol_12m", r"^12 mo sales vol$|sales vol(ume)?$"),
    ("cap_rate", r"cap rate"),
]
FRACTION_KEYS = ("vacancy", "rent_growth", "uc_pct", "cap_rate")


def extract(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    hb = sh.header_block(["period", "vacancy rate"], max_rows=1, search_rows=10)
    if hb is None:
        raise ExtractionError("No 'Period' / 'Vacancy Rate' header found")
    hrow, _, headers = hb
    c_period = Sheet.col(headers, r"^period$")
    colmap = {k: c for k, rx in COLUMNS if (c := Sheet.col(headers, rx)) is not None}
    if c_period is None or "vacancy" not in colmap:
        raise ExtractionError("'Period' or 'Vacancy Rate' column not found")
    series: list[dict] = []
    for r in range(hrow + 1, sh.nrows):
        m = PERIOD_RE.match(sh.text(r, c_period))
        if not m:
            continue
        rec: dict = {"period": sh.text(r, c_period), "year": int(m.group(1)), "quarter": int(m.group(2)),
                     "flag": (m.group(3) or "").upper(), "row": r}
        for k, c in colmap.items():
            rec[k] = to_number(sh.cell(r, c))
        for k in FRACTION_KEYS:
            if rec.get(k) is not None:
                rec[k] = as_fraction(rec[k])
        series.append(rec)
    if not series:
        raise ExtractionError("No quarterly rows found")
    return Extraction(doc_type=part.doc_type, locator=part.locator, data={"series": series, "columns": sorted(colmap)})
```

- [ ] **Step 4: Write `backend/app/extract/costar_pdf.py`**

```python
"""CoStar 'Multi-Family Submarket Report' PDF: submarket name, market, report date, licensee, key stats,
annual trend peaks/troughs, recent deliveries, and the sale-comps table (which lists the subject's own trade)."""
from __future__ import annotations

import re

from ..classify.classifier import Part
from ..readers.document import to_date, to_number
from .base import Extraction, ExtractionError

_DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
_LICENSED_RE = re.compile(r"licensed to (.+?)\s+-\s+\d+", re.I)
_MARKET_RE = re.compile(r"^(?P<market>.+?)\s*-\s*(?P<state>[A-Z]{2})\s+USA$")
_OVERVIEW_HDR = re.compile(r"12 mo delivered units.*12 mo absorption units.*vacancy rate.*asking rent growth", re.I)
_OVERVIEW_VALS = re.compile(r"^([\d,]+) ([\d,()-]+) (-?[\d.]+)% (-?[\d.]+)%$")
_SUBMARKET_ROW = re.compile(r"^Submarket ([\d,]+) ([\d.]+)% \$([\d,]+) \$([\d,]+) \(?(-?[\d,]+)\)? ([\d,]+) ([\d,]+)$")
_TREND_ROW = re.compile(
    r"^(Vacancy|Asking Rent Growth|Effective Rent Growth) (-?[\d.]+)% \(YOY\) (-?[\d.]+)% (-?[\d.]+)% "
    r"(-?[\d.]+)% (\d{4} Q\d) (-?[\d.]+)% (\d{4} Q\d)$"
)
_SALE_ROW = re.compile(r"^(\d+) (\S+) (\d{4}) ([\d,]+) ([\d.]+)% (\d{1,2}/\d{1,2}/\d{4}) \$([\d,]+) \$([\d,]+) \$([\d,]+)$")
_DELIVERY_ROW = re.compile(r"^(\d+) (\d+) (\d+) ([A-Z][a-z]{2} \d{4}) ([A-Z][a-z]{2} \d{4})$")


def _pct(s: str) -> float | None:
    v = to_number(s)
    return None if v is None else round(v / 100, 6)


def parse_costar_text(pages: list[str]) -> dict:
    out: dict = {"submarket": None, "market": None, "state": None, "report_date": None, "licensed_to": None,
                 "overview": {}, "key_stats": {}, "trends": {}, "sales": [], "deliveries": []}
    for pno, text in enumerate(pages, start=1):
        raw_lines = [ln for ln in text.splitlines() if ln.strip()]
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in raw_lines]
        for i, line in enumerate(lines):
            low = line.lower()
            if out["submarket"] is None and "multi-family submarket report" in low and i + 1 < len(lines):
                out["submarket"] = lines[i + 1]
                if i + 2 < len(lines) and (mm := _MARKET_RE.match(lines[i + 2])):
                    out["market"], out["state"] = mm.group("market").strip(), mm.group("state")
            if out["report_date"] is None and (md := _DATE_RE.search(line)):
                d = to_date(md.group(1))
                out["report_date"] = d.isoformat() if d else None
            if out["licensed_to"] is None and (ml := _LICENSED_RE.search(line)):
                out["licensed_to"] = ml.group(1).strip()
            if _OVERVIEW_HDR.search(line) and i + 1 < len(lines) and (mo := _OVERVIEW_VALS.match(lines[i + 1])):
                out["overview"] = {"delivered_12m": to_number(mo.group(1)), "absorption_12m": to_number(mo.group(2)),
                                   "vacancy": _pct(mo.group(3)), "rent_growth_12m": _pct(mo.group(4))}
            if not out["key_stats"] and (ms := _SUBMARKET_ROW.match(line)):
                out["key_stats"] = {"inventory": to_number(ms.group(1)), "vacancy": _pct(ms.group(2)),
                                    "asking_rent": to_number(ms.group(3)), "effective_rent": to_number(ms.group(4)),
                                    "absorption": to_number(ms.group(5)), "delivered": to_number(ms.group(6)),
                                    "under_construction": to_number(ms.group(7))}
            if (mt := _TREND_ROW.match(line)):
                key = mt.group(1).lower().replace(" ", "_")
                out["trends"][key] = {"yoy": _pct(mt.group(2)), "historical": _pct(mt.group(3)), "forecast": _pct(mt.group(4)),
                                      "peak": _pct(mt.group(5)), "peak_when": mt.group(6), "trough": _pct(mt.group(7)),
                                      "trough_when": mt.group(8)}
            if i > 0 and (msale := _SALE_ROW.match(line)):
                d = to_date(msale.group(6))
                out["sales"].append({"rank": int(msale.group(1)), "name": lines[i - 1], "year_built": int(msale.group(3)),
                                     "units": to_number(msale.group(4)), "vacancy": _pct(msale.group(5)),
                                     "sale_date": d.isoformat() if d else None, "price": to_number(msale.group(7)),
                                     "price_per_unit": to_number(msale.group(8)), "price_psf": to_number(msale.group(9)),
                                     "page": pno})
            if i > 0 and (mdel := _DELIVERY_ROW.match(line)):
                name = re.split(r"\s{2,}", raw_lines[i - 1].strip())[0]
                out["deliveries"].append({"name": name, "units": int(mdel.group(2)), "stories": int(mdel.group(3)),
                                          "start": mdel.group(4), "complete": mdel.group(5), "page": pno})
    return out


def extract(part: Part) -> Extraction:
    data = parse_costar_text([p.text for p in part.pages])
    if not (data["submarket"] or data["key_stats"] or data["sales"]):
        raise ExtractionError("No submarket name, key statistics or sale comps found in the PDF")
    warnings = [] if data["sales"] else ["No sale comps table found; acquisition date and year built need another source"]
    return Extraction(doc_type=part.doc_type, locator=part.locator, data=data, warnings=warnings)
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_extract_costar.py -v`
Expected: 2 PASS

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: CoStar submarket Excel and PDF extractors"
```

---

### Task 13: Rent chart workbook and Slate capital-flow extractors

**Files:**
- Create: `backend/app/extract/rent_chart.py`, `backend/app/extract/slate.py`, `backend/tests/test_extract_misc.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_extract_misc.py
from app.classify.classifier import DocType
from app.extract.rent_chart import extract as extract_chart
from app.extract.slate import extract_capital_calls, extract_distributions, parse_capital_calls_text, parse_distributions_text
from tests.helpers import CAPITAL_CALLS_TEXT, DISTRIBUTIONS_TEXT, RENT_CHART_ROWS, pdf_part, sheet_part


def test_rent_chart_months_totals_and_names():
    d = extract_chart(sheet_part(RENT_CHART_ROWS, DocType.RENT_CHART)).data
    assert d["subject_name"] == "The Boardwalk" and d["comp_name"] == "Comp Set"
    assert d["title"] == "The Boardwalk vs. HelloData Comp Set"
    assert [m["month"] for m in d["months"]] == ["2025-07", "2025-08"]
    m0 = d["months"][0]
    assert (m0["subject_n"], m0["subject_gross_psf"], m0["subject_eff_psf"], m0["comp_n"], m0["comp_gross_psf"], m0["comp_eff_psf"]) == (12, 1.83, 1.63, 42, 1.71, 1.5)
    assert d["totals"]["subject_gross_psf"] == 1.78 and d["months"][1]["row"] == 6
    assert d["notes"][0] == "Methodology"


def test_slate_capital_calls_none():
    d = parse_capital_calls_text(CAPITAL_CALLS_TEXT)
    assert d == {"entity": "The Boardwalk Owner, LLC", "total_called": 0.0, "calls": [], "none": True}
    assert extract_capital_calls(pdf_part(CAPITAL_CALLS_TEXT, DocType.SLATE_CAPITAL_CALLS)).data["none"] is True


def test_slate_capital_calls_rows():
    text = "Capital Calls    New Capital Call\nTotal Called    $250,000    100%\nTitle    Due Date    From    To    Total Called\nQ3 Reno Call    07/15/2026    Fund I    LP    $250,000.00    100%\n"
    d = parse_capital_calls_text(text)
    assert d["total_called"] == 250000 and d["calls"] == [{"title": "Q3 Reno Call", "due_date": "2026-07-15", "amount": 250000.0}]


def test_slate_distributions():
    d = parse_distributions_text(DISTRIBUTIONS_TEXT)
    assert d == {"entity": "The Boardwalk Owner, LLC", "distributions": [], "total_gross": 0.0, "none": True}
    text = "Distributions    New Distribution\nTitle Period Date\nQ2 Distribution    2Q26    07/20/2026    Class A    Fund    LP    Yes    $100,000.00    $95,000.00\n"
    d2 = parse_distributions_text(text)
    assert d2["distributions"] == [{"title": "Q2 Distribution", "date": "2026-07-20", "gross": 100000.0, "net": 95000.0}]
    assert d2["total_gross"] == 100000.0 and d2["none"] is False
    assert extract_distributions(pdf_part(DISTRIBUTIONS_TEXT, DocType.SLATE_DISTRIBUTIONS)).data["entity"] == "The Boardwalk Owner, LLC"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_extract_misc.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `backend/app/extract/rent_chart.py`**

```python
"""Pre-built rent trend workbook: monthly subject vs comp-set lease counts and gross/effective $/SF."""
from __future__ import annotations

from ..classify.classifier import Part
from ..readers.document import Sheet, norm, to_date, to_number
from .base import Extraction, ExtractionError


def _month_key(v) -> str | None:
    d = to_date(v)
    return d.strftime("%Y-%m") if d else None


def extract(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    hb = sh.header_block(["month", "gross psf", "effective psf"], max_rows=1, search_rows=15)
    if hb is None:
        raise ExtractionError("No 'Month' / 'Gross PSF' / 'Effective PSF' header found")
    hrow, _, headers = hb
    c_month = Sheet.col(headers, r"^month")
    counts = Sheet.cols_all(headers, r"lease count|# ?leases|\bcount\b")
    gross = Sheet.cols_all(headers, r"gross psf")
    eff = Sheet.cols_all(headers, r"effective psf")
    if c_month is None or not gross or not eff:
        raise ExtractionError("Month, Gross PSF or Effective PSF column missing")

    def series_name(c: int) -> str:
        return sh.text(hrow, c).split("/")[0].strip()

    months: list[dict] = []
    totals: dict | None = None
    last_row = hrow
    for r in range(hrow + 1, sh.nrows):
        txt = sh.text(r, c_month)
        if not txt:
            if months:
                last_row = r
                break
            continue
        num = lambda cols, i: to_number(sh.cell(r, cols[i])) if len(cols) > i else None  # noqa: E731
        rec = {"subject_n": num(counts, 0), "subject_gross_psf": num(gross, 0), "subject_eff_psf": num(eff, 0),
               "comp_n": num(counts, 1), "comp_gross_psf": num(gross, 1), "comp_eff_psf": num(eff, 1), "row": r}
        if "total" in norm(txt):
            totals = rec
            last_row = r
            break
        key = _month_key(sh.cell(r, c_month))
        if key is None:
            continue
        months.append({"month": key, **rec})
    if not months:
        raise ExtractionError("No monthly rows found")
    notes = []
    for r in range(last_row + 1, sh.nrows):
        t = sh.text(r, 0) or sh.text(r, 1)
        if t and not sh.has_numbers(r):
            notes.append(t)
        if len(notes) >= 60:
            break
    return Extraction(doc_type=part.doc_type, locator=part.locator, data={
        "title": sh.text(0, 0), "subtitle": sh.text(1, 0), "subject_name": series_name(gross[0]),
        "comp_name": series_name(gross[1]) if len(gross) > 1 else None, "months": months, "totals": totals, "notes": notes,
    })
```

- [ ] **Step 4: Write `backend/app/extract/slate.py`**

```python
"""Slate investor-portal exports (capital calls and distributions), typically printed pages."""
from __future__ import annotations

import re

from ..classify.classifier import Part
from ..readers.document import to_date, to_number
from .base import Extraction, ExtractionError

ENTITY_RE = re.compile(r"([A-Z][A-Za-z0-9&.,' -]*?(?:LLC|L\.L\.C\.|L\.P\.|LP|Inc\.?|Ltd\.?|LLP))(?=\s|\(|$)")
TOTAL_CALLED_RE = re.compile(r"total called\s+\$?\s*([\d,]+(?:\.\d+)?)", re.I)
CALL_ROW_RE = re.compile(r"^(?P<title>.+?)\s+(?P<due>\d{1,2}/\d{1,2}/\d{4})\s+.*?\$(?P<amount>[\d,]+(?:\.\d+)?)", re.M)
DIST_ROW_RE = re.compile(
    r"^(?P<title>.+?)\s+(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+.*?\$(?P<gross>[\d,]+(?:\.\d+)?)\s+\$(?P<net>[\d,]+(?:\.\d+)?)", re.M
)
_SKIP_TITLES = ("title", "total", "date")


def _entity(text: str) -> str | None:
    m = ENTITY_RE.search(text)
    return m.group(1).strip() if m else None


def _iso(s: str) -> str | None:
    d = to_date(s)
    return d.isoformat() if d else None


def _clean_title(s: str) -> str:
    """Drop a trailing period token ('2Q26', 'Q2 2026', '2026') that Slate prints between title and date."""
    return re.sub(r"\s+(\d[qQ]\d{2,4}|[qQ]\d\s*\d{4}|\d{4})$", "", s.strip())


def parse_capital_calls_text(text: str) -> dict:
    flat = re.sub(r"[ \t]+", " ", text)
    m = TOTAL_CALLED_RE.search(flat)
    none = "no capital calls" in flat.lower()
    calls = [{"title": _clean_title(g["title"]), "due_date": _iso(g["due"]), "amount": to_number(g["amount"])}
             for g in (mm.groupdict() for mm in CALL_ROW_RE.finditer(flat))
             if not g["title"].strip().lower().startswith(_SKIP_TITLES)]
    total = to_number(m.group(1)) if m else (0.0 if none else None)
    return {"entity": _entity(text), "total_called": total, "calls": calls, "none": none}


def parse_distributions_text(text: str) -> dict:
    flat = re.sub(r"[ \t]+", " ", text)
    none = "no distributions yet" in flat.lower()
    dists = [{"title": _clean_title(g["title"]), "date": _iso(g["date"]), "gross": to_number(g["gross"]), "net": to_number(g["net"])}
             for g in (mm.groupdict() for mm in DIST_ROW_RE.finditer(flat))
             if not g["title"].strip().lower().startswith(_SKIP_TITLES)]
    total = sum(d["gross"] or 0 for d in dists) if dists else (0.0 if none else None)
    return {"entity": _entity(text), "distributions": dists, "total_gross": total, "none": none}


def extract_capital_calls(part: Part) -> Extraction:
    data = parse_capital_calls_text("\n".join(p.text for p in part.pages))
    if data["total_called"] is None and not data["calls"]:
        raise ExtractionError("Neither a 'Total Called' amount nor capital call rows found")
    return Extraction(doc_type=part.doc_type, locator=part.locator, data=data)


def extract_distributions(part: Part) -> Extraction:
    data = parse_distributions_text("\n".join(p.text for p in part.pages))
    if data["total_gross"] is None:
        raise ExtractionError("Neither 'No Distributions Yet' nor distribution rows found")
    return Extraction(doc_type=part.doc_type, locator=part.locator, data=data)
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_extract_misc.py -v`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: rent chart workbook and Slate capital-flow extractors"
```

---

### Task 14: Extractor registry

**Files:**
- Create: `backend/app/extract/registry.py`, `backend/tests/test_extract_registry.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_extract_registry.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `backend/app/extract/registry.py`**

```python
"""DocType -> extractor. Add a new document type by adding a classifier signature and one entry here."""
from __future__ import annotations

from typing import Callable

from ..classify.classifier import DocType, Part
from . import (costar_excel, costar_pdf, hellodata_comps, hellodata_listings, rent_chart, slate, yardi_balance_sheet,
               yardi_budget, yardi_lto, yardi_rent_roll, yardi_rent_schedule)
from .base import Extraction, ExtractionError

EXTRACTORS: dict[str, Callable[[Part], Extraction]] = {
    DocType.YARDI_BUDGET_COMPARISON.value: yardi_budget.extract,
    DocType.YARDI_BALANCE_SHEET.value: yardi_balance_sheet.extract,
    DocType.YARDI_RENT_ROLL.value: yardi_rent_roll.extract,
    DocType.YARDI_MARKET_RENT_SCHEDULE.value: yardi_rent_schedule.extract,
    DocType.YARDI_LEASE_TRADE_OUT.value: yardi_lto.extract,
    DocType.HELLODATA_LISTINGS.value: hellodata_listings.extract,
    DocType.HELLODATA_COMPS.value: hellodata_comps.extract,
    DocType.COSTAR_SUBMARKET_EXCEL.value: costar_excel.extract,
    DocType.COSTAR_SUBMARKET_PDF.value: costar_pdf.extract,
    DocType.RENT_CHART.value: rent_chart.extract,
    DocType.SLATE_CAPITAL_CALLS.value: slate.extract_capital_calls,
    DocType.SLATE_DISTRIBUTIONS.value: slate.extract_distributions,
}


def run_extractor(part: Part) -> Extraction:
    fn = EXTRACTORS.get(part.doc_type)
    if fn is None:
        raise ExtractionError(f"No extractor for document type '{part.doc_type}'")
    return fn(part)
```

- [ ] **Step 4: Run all tests so far**

Run: `pytest -q`
Expected: all PASS (about 30 tests)

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: extractor registry"
```

---

### Task 15: The structured intermediate model

One generic `Field` type carries value, status, source, alternatives and an override; sections hold fields and tables. The review UI, the validator and the template all walk this model by path, so nothing downstream needs domain-specific classes.

**Files:**
- Create: `backend/app/models.py`, `backend/tests/test_models.py`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models'`

- [ ] **Step 3: Write `backend/app/models.py`**

```python
"""The structured intermediate representation: sections of fields and tables.

Every leaf is a Field with a value, a status, a source locator and an optional user override.
Paths: '<section>.fields.<name>' | '<section>.tables.<table>.rows.<row>.<col>' | '<section>.tables.<table>.totals.<col>'.
"""
from __future__ import annotations

from typing import Any, Iterator, Literal

from pydantic import BaseModel, Field as PField

Kind = Literal["money", "number", "integer", "percent", "date", "text", "longtext"]
Status = Literal["extracted", "derived", "manual", "ai_draft", "missing", "conflict"]


class Source(BaseModel):
    file_id: str | None = None
    filename: str | None = None
    locator: str | None = None
    text: str | None = None


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
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_models.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: generic Field/Table/Section report data model with path access"
```

---

### Task 16: Source selection and label mappings

**Files:**
- Create: `backend/app/consolidate/__init__.py` (empty), `backend/app/consolidate/select.py`, `backend/app/consolidate/mapping.py`, `backend/config/pl_mapping.toml`, `backend/config/capex_mapping.toml`, `backend/tests/test_select_mapping.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_select_mapping.py
from app.classify.classifier import DocType
from app.config import settings
from app.consolidate.mapping import consume_capex, load_capex_mapping, load_pl_mapping, match_lines, section_matches
from app.consolidate.select import Src, collect, select


def line(label, section=(), total=False, **values):
    return {"code": "", "label": label, "norm": label.lower(), "indent": 0, "section": list(section),
            "is_total": total, "unlabeled": False, "values": values, "row": 1}


def test_match_lines_pattern_order_and_totals():
    lines = [line("Property Taxes", ptd_actual=5), line("TOTAL TAXES", total=True, ptd_actual=5)]
    assert match_lines(lines, [r"^total taxes$", r"^property taxes$"])[0]["label"] == "TOTAL TAXES"
    assert match_lines(lines, [r"taxes"], prefer_total=True)[0]["label"] == "TOTAL TAXES"
    assert match_lines(lines, [r"insurance"]) == []


def test_section_matches_innermost_wins():
    cfg = load_capex_mapping(settings.config_dir)["sections"]
    assert section_matches(["INTERIOR & EXTERIOR RENOVATIONS", "ROOF"], cfg["include"], cfg["exclude"])
    assert not section_matches(["INTERIOR & EXTERIOR RENOVATIONS", "LEASE UP COSTS"], cfg["include"], cfg["exclude"])
    assert not section_matches(["DEBT SERVICE", "NON-OPERATING EXPENSES"], cfg["include"], cfg["exclude"])
    assert section_matches(["RENO - X", "DEPR/AMORT EXPENSE", "NON-OPERATING ITEMS", "PLUMBING"], cfg["include"], cfg["exclude"])
    assert section_matches(["NON-OPERATING ITEMS", "PLUMBING"], cfg["negate"], [])


def test_consume_capex_consumes_each_line_once_in_order():
    rows = load_capex_mapping(settings.config_dir)["rows"]
    lines = [line("Reno - Plumbing"), line("Plumbing Replacement"), line("Boiler/Water Heater"), line("Paint"), line("Something Odd")]
    groups, leftover = consume_capex(lines, rows)
    by = {m["key"]: [ln["label"] for ln in hit] for m, hit in groups if hit}
    assert by["renovation_plumbing"] == ["Reno - Plumbing"]
    assert by["plumbing_water_heaters"] == ["Plumbing Replacement", "Boiler/Water Heater"]
    assert by["paint"] == ["Paint"] and [ln["label"] for ln in leftover] == ["Something Odd"]


def test_pl_mapping_has_all_report_rows():
    keys = [m["key"] for m in load_pl_mapping(settings.config_dir)]
    assert keys == ["gpr", "gain_loss_to_lease", "concessions", "vacancy", "pet_rent", "net_rental_income", "utility_income",
                    "other_income", "total_revenue", "payroll", "g_and_a", "marketing", "r_and_m", "utilities",
                    "management_fees", "property_taxes", "insurance", "total_opex", "noi", "debt_service", "net_cash_flow"]


def test_select_prefers_ytd_budget_single_part_listings_and_notes_alternatives():
    files = [
        {"id": "a", "original_filename": "ptd.xlsx", "status": "processed", "ignored": False, "parts": [{}],
         "extractions": [{"doc_type": DocType.YARDI_BUDGET_COMPARISON, "locator": "sheet 'R'", "data": {"columns": ["mtd_actual", "ptd_actual"], "period": {"end": "2026-06-30"}}}]},
        {"id": "b", "original_filename": "ytd.xlsx", "status": "processed", "ignored": False, "parts": [{}],
         "extractions": [{"doc_type": DocType.YARDI_BUDGET_COMPARISON, "locator": "sheet 'R'", "data": {"columns": ["ptd_actual", "ytd_actual"], "period": {"end": "2026-06-30"}}}]},
        {"id": "c", "original_filename": "full.xlsx", "status": "processed", "ignored": False, "parts": [{}, {}, {}],
         "extractions": [{"doc_type": DocType.HELLODATA_LISTINGS, "locator": "sheet 'U'", "data": {"row_count": 5000}}]},
        {"id": "d", "original_filename": "leasing.xlsx", "status": "processed", "ignored": False, "parts": [{}],
         "extractions": [{"doc_type": DocType.HELLODATA_LISTINGS, "locator": "sheet 'U'", "data": {"row_count": 2600}}]},
        {"id": "e", "original_filename": "ignored.xlsx", "status": "processed", "ignored": True, "parts": [{}],
         "extractions": [{"doc_type": DocType.COSTAR_SUBMARKET_EXCEL, "locator": "sheet 'D'", "data": {"series": [1]}}]},
        {"id": "f", "original_filename": "failed.xlsx", "status": "failed", "ignored": False, "parts": [], "extractions": []},
    ]
    srcs = collect(files)
    assert {s.file_id for s in srcs} == {"a", "b", "c", "d"}
    sel = select(srcs)
    assert sel.budget.file_id == "b" and sel.listings.file_id == "d" and sel.costar_excel is None
    assert len(sel.notes) == 2 and all(n["severity"] == "warning" for n in sel.notes)
    assert Src("x", "f.xlsx", "t", "sheet 'S'", {}).source("row 3", "GPR") == {"file_id": "x", "filename": "f.xlsx", "locator": "sheet 'S' row 3", "text": "GPR"}
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_select_mapping.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `backend/config/pl_mapping.toml`**

```toml
# Canonical rows of the financial performance table, in report order.
# `match` patterns are regexes tried in order against the normalised (lower-case) source label;
# the first pattern that hits any line wins. `total = true` prefers lines whose label contains "total".
# `sum = true` adds every line matched by the winning pattern (e.g. monthly + one-time concessions).
# `expense = true` flips the variance sign so favourable is positive (Yardi convention).

[[rows]]
key = "gpr"
label = "Gross Potential Rent"
group = "revenue"
match = ["^gross potential rent$", "^gross potential rent", "^gpr$"]

[[rows]]
key = "gain_loss_to_lease"
label = "Loss/Gain to Lease"
group = "revenue"
match = ["loss/gain to lease", "gain/loss to lease", "^loss to lease", "^gain to lease"]

[[rows]]
key = "concessions"
label = "Concessions"
group = "revenue"
sum = true
match = ["^less:?\\s*concessions", "^concessions"]

[[rows]]
key = "vacancy"
label = "Vacancy"
group = "revenue"
match = ["^less:?\\s*vacancy", "^vacancy loss", "^vacancy"]

[[rows]]
key = "pet_rent"
label = "Pet Rent"
group = "revenue"
match = ["^pet rent"]

[[rows]]
key = "net_rental_income"
label = "Net Rental Income"
group = "revenue"
total = true
match = ["^net rental income", "^total rental income", "^net rent"]

[[rows]]
key = "utility_income"
label = "Utility Income"
group = "revenue"
total = true
match = ["^total utility income", "^utility income", "^total utilities income"]

[[rows]]
key = "other_income"
label = "Other Income (net of bad debt)"
group = "revenue"
total = true
match = ["^total other income", "^other income"]

[[rows]]
key = "total_revenue"
label = "Total Revenue"
group = "revenue"
total = true
match = ["^total revenue", "^total income", "^effective gross income"]

[[rows]]
key = "payroll"
label = "Payroll"
group = "opex"
expense = true
total = true
match = ["^total payroll", "^payroll", "^salaries"]

[[rows]]
key = "g_and_a"
label = "General & Administrative"
group = "opex"
expense = true
total = true
match = ["^total general (&|and) admin", "^general (&|and) admin", "^total administrative", "^administrative"]

[[rows]]
key = "marketing"
label = "Marketing"
group = "opex"
expense = true
total = true
match = ["^total marketing", "^marketing$", "^total advertising", "^advertising"]

[[rows]]
key = "r_and_m"
label = "Repairs & Maintenance"
group = "opex"
expense = true
total = true
match = ["^total repairs", "^repairs (&|and) maintenance", "^total maintenance", "^maintenance"]

[[rows]]
key = "utilities"
label = "Utilities"
group = "opex"
expense = true
total = true
match = ["^total utilities$", "^utilities$", "^total utility expense", "^utilities expense"]

[[rows]]
key = "management_fees"
label = "Management Fees"
group = "opex"
expense = true
total = true
match = ["^total management fee", "^management fee"]

[[rows]]
key = "property_taxes"
label = "Property Taxes"
group = "opex"
expense = true
total = true
match = ["^total taxes", "^total property tax", "^property tax", "^real estate tax"]

[[rows]]
key = "insurance"
label = "Insurance"
group = "opex"
expense = true
total = true
match = ["^total insurance", "^insurance"]

[[rows]]
key = "total_opex"
label = "Total Operating Expenses"
group = "opex"
expense = true
total = true
match = ["^total expenses", "^total operating expenses", "^total opex"]

[[rows]]
key = "noi"
label = "NOI"
group = "noi"
total = true
match = ["^net operating income", "^noi"]

[[rows]]
key = "debt_service"
label = "Debt Service"
group = "noi"
expense = true
total = true
match = ["^total debt service", "^debt service", "interest expense"]

[[rows]]
key = "net_cash_flow"
label = "Net Cash Flow After Debt Service"
group = "noi"
total = true
match = ["after ds", "after debt service", "^net cash flow"]
```

- [ ] **Step 4: Write `backend/config/capex_mapping.toml`**

```toml
# Which Budget Comparison sections count as capital spend, and how detail lines are regrouped.
# Section decision walks the line's section path from the innermost header outward: the first header
# matching an `exclude` pattern rejects the line; the first matching an `include` pattern accepts it.
# Lines under a `negate` section are sign-flipped (Yardi shows balance-sheet capital items as negatives).
[sections]
include = ["renovation", "improvement", "capital", "non-operating items"]
exclude = ["lease.?up", "depr", "amort", "non-operating expenses", "operating expenses"]
negate = ["non-operating items"]

# Regrouping rows, applied in order; each source line is consumed by the first row that matches it.
# Lines matched by no row are shown under their own label. Edit freely for another property.
[[rows]]
key = "renovation_plumbing"
label = "Renovation Program - Plumbing"
match = ["^reno\\s*-\\s*plumbing"]

[[rows]]
key = "renovation_pm"
label = "Renovation Program - Project Mgmt"
match = ["^reno\\s*-\\s*project management"]

[[rows]]
key = "plumbing_water_heaters"
label = "Plumbing & Water Heaters"
match = ["plumbing", "water heater", "boiler"]

[[rows]]
key = "hvac"
label = "HVAC Additions"
match = ["hvac"]

[[rows]]
key = "paint"
label = "Paint"
match = ["^paint$", "^painting"]

[[rows]]
key = "appliances_equipment"
label = "Appliances & Equipment"
match = ["equipment/appliances", "appliance", "refrigerator", "stove", "dishwasher", "washer/dryer", "washer"]

[[rows]]
key = "interior_renovation_labor"
label = "Interior Renovation & Labor"
match = ["^labor$", "^materials$", "^interior renovation$"]

[[rows]]
key = "tub_resurfacing"
label = "Resurfacing - Tub"
match = ["resurfacing"]

[[rows]]
key = "flooring"
label = "Flooring - Carpet & Vinyl"
match = ["flooring", "carpet", "vinyl"]

[[rows]]
key = "paving"
label = "Paving & Flatwork"
match = ["paving", "flatwork"]

[[rows]]
key = "blinds"
label = "Blinds"
match = ["^blinds"]

[[rows]]
key = "electrical_lighting"
label = "Electrical & Lighting"
match = ["electrical", "lighting", "light bulbs"]

[[rows]]
key = "signage"
label = "Signage"
match = ["signage"]

[[rows]]
key = "roof"
label = "Roof"
match = ["^roof"]

[[rows]]
key = "windows_glass"
label = "Windows & Glass"
match = ["windows", "glass", "solar screens"]

[[rows]]
key = "structures"
label = "Structures"
match = ["^structures"]

[[rows]]
key = "landscape"
label = "Landscape Additions"
match = ["landscap"]

[[rows]]
key = "powerwashing"
label = "Powerwashing"
match = ["power ?wash"]

[[rows]]
key = "pool"
label = "Pool Improvements"
match = ["pool"]

[[rows]]
key = "irrigation"
label = "Irrigation"
match = ["irrigation"]

[[rows]]
key = "gutters"
label = "Gutters & Downspouts"
match = ["gutter"]

[[rows]]
key = "dog_park"
label = "Dog Park"
match = ["dog park"]

[[rows]]
key = "fire_control"
label = "Fire Control"
match = ["fire"]

[[rows]]
key = "office"
label = "Office Furniture & Equipment"
match = ["office furniture", "office equipment"]

[[rows]]
key = "golf_carts"
label = "Golf Carts"
match = ["golf cart"]

[[rows]]
key = "project_management"
label = "Project Management"
match = ["^project management"]

[[rows]]
key = "fencing"
label = "Perimeter Fencing"
match = ["fenc"]

[[rows]]
key = "fitness"
label = "Fitness Center Equipment"
match = ["fitness"]
```

- [ ] **Step 5: Write `backend/app/consolidate/mapping.py`**

```python
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
```

- [ ] **Step 6: Write `backend/app/consolidate/select.py`**

```python
"""Choose which extraction feeds which section when several files could, and record the alternatives."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..classify.classifier import DocType


@dataclass
class Src:
    file_id: str
    filename: str
    doc_type: str
    locator: str
    data: dict
    parts_in_file: int = 1

    def source(self, suffix: str = "", text: str = "") -> dict:
        return {"file_id": self.file_id, "filename": self.filename,
                "locator": f"{self.locator} {suffix}".strip(), "text": text or None}


@dataclass
class Selection:
    budget: Src | None = None
    balance_sheet: Src | None = None
    rent_rolls: list[Src] = field(default_factory=list)
    schedules: list[Src] = field(default_factory=list)
    lto: Src | None = None
    listings: Src | None = None
    comps: list[Src] = field(default_factory=list)
    costar_excel: Src | None = None
    costar_pdf: Src | None = None
    rent_chart: Src | None = None
    capital_calls: Src | None = None
    distributions: Src | None = None
    notes: list[dict] = field(default_factory=list)


def collect(files: list[dict]) -> list[Src]:
    out: list[Src] = []
    for f in files:
        if f.get("ignored") or f.get("status") != "processed":
            continue
        n_parts = len(f.get("parts") or [])
        for ex in f.get("extractions") or []:
            out.append(Src(f["id"], f["original_filename"], ex["doc_type"], ex["locator"], ex["data"], n_parts))
    return out


def _by_type(srcs: list[Src], t: DocType) -> list[Src]:
    return [s for s in srcs if s.doc_type == t.value]


def _period_end(s: Src) -> str:
    return (s.data.get("period") or {}).get("end") or ""


def _pick(sel: Selection, cands: list[Src], key: Callable[[Src], tuple], label: str, path: str) -> Src | None:
    if not cands:
        return None
    ranked = sorted(cands, key=key, reverse=True)
    if len(ranked) > 1:
        others = "; ".join(f"{s.filename} ({s.locator})" for s in ranked[1:])
        sel.notes.append({"severity": "warning", "path": path,
                          "message": f"{label}: using {ranked[0].filename} ({ranked[0].locator}). Also found: {others}. "
                                     "Exclude a file on the Files page to switch."})
    return ranked[0]


def select(srcs: list[Src]) -> Selection:
    sel = Selection()
    sel.budget = _pick(sel, _by_type(srcs, DocType.YARDI_BUDGET_COMPARISON),
                       lambda s: ("ytd_actual" in s.data.get("columns", []), _period_end(s)), "Financials source", "financials")
    sel.balance_sheet = _pick(sel, _by_type(srcs, DocType.YARDI_BALANCE_SHEET), lambda s: (_period_end(s),), "Balance sheet", "capital")
    sel.rent_rolls = sorted(_by_type(srcs, DocType.YARDI_RENT_ROLL), key=lambda s: s.data.get("as_of") or "")
    sel.schedules = sorted(_by_type(srcs, DocType.YARDI_MARKET_RENT_SCHEDULE), key=lambda s: s.data.get("as_of") or "")
    budget_end = _period_end(sel.budget) if sel.budget else ""
    sel.lto = _pick(sel, _by_type(srcs, DocType.YARDI_LEASE_TRADE_OUT),
                    lambda s: (_period_end(s) == budget_end, "renewals" in s.data.get("sections", {}), _period_end(s)),
                    "Lease trade-out source", "occupancy")
    sel.listings = _pick(sel, _by_type(srcs, DocType.HELLODATA_LISTINGS),
                         lambda s: (s.parts_in_file == 1, s.data.get("row_count", 0)), "HelloData listings", "submarket")
    sel.comps = sorted(_by_type(srcs, DocType.HELLODATA_COMPS), key=lambda s: s.data.get("source") != "sheet")
    sel.costar_excel = _pick(sel, _by_type(srcs, DocType.COSTAR_SUBMARKET_EXCEL), lambda s: (len(s.data.get("series", [])),), "CoStar table", "submarket")
    sel.costar_pdf = _pick(sel, _by_type(srcs, DocType.COSTAR_SUBMARKET_PDF), lambda s: (s.data.get("report_date") or "",), "CoStar report", "submarket")
    sel.rent_chart = _pick(sel, _by_type(srcs, DocType.RENT_CHART), lambda s: (len(s.data.get("months", [])),), "Rent chart", "rent_trend")
    sel.capital_calls = _pick(sel, _by_type(srcs, DocType.SLATE_CAPITAL_CALLS), lambda s: (len(s.data.get("calls", [])),), "Capital calls", "capital")
    sel.distributions = _pick(sel, _by_type(srcs, DocType.SLATE_DISTRIBUTIONS), lambda s: (len(s.data.get("distributions", [])),), "Distributions", "capital")
    return sel
```

- [ ] **Step 7: Run the tests**

Run: `pytest tests/test_select_mapping.py -v`
Expected: 5 PASS

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: source selection rules and TOML label mappings for P&L and capex"
```

---

### Task 17: Calculations and recompute

Pure functions plus `recompute(data)`, which fills every `derived` field from effective values. It runs after the builder and again after every user edit, so overrides propagate to totals, variances and captions. Section, field and column keys are the ones the builder creates in Task 18.

**Files:**
- Create: `backend/app/consolidate/calc.py`, `backend/tests/test_calc.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_calc.py
import datetime as dt

from app.consolidate import calc
from app.models import Column, Field, ReportData, Section, Table


def test_pure_helpers():
    assert calc.variance(100, 90, expense=False) == 10 and calc.variance(100, 90, expense=True) == -10
    assert calc.variance(None, 5, False) is None
    assert abs(calc.variance_pct(100, 90, False) - 0.1111) < 1e-3 and calc.variance_pct(5, 0, False) is None
    assert calc.wavg([(10, 2), (20, 2)]) == 15 and calc.wavg([]) is None and calc.wavg([(10, None)]) is None
    assert calc.mean([1, None, 3]) == 2 and calc.mean([]) is None
    assert calc.sum_or_none([1, None]) == 1 and calc.sum_or_none([None]) is None
    assert calc.bps(0.9053, 0.9171) == -118 and calc.ratio(48000000, 338) == 48000000 / 338
    assert abs(calc.implied_rate(159161.98, 36519000) - 0.0523) < 1e-4
    assert calc.quarter_end(2026, 2) == dt.date(2026, 6, 30) and calc.quarter_label(dt.date(2026, 6, 30)) == "2Q26"
    assert calc.next_quarter_label(dt.date(2026, 12, 31)) == "1Q27" and calc.month_label("2026-04") == "Apr 2026"


def _financials_table() -> Table:
    cols = [Column(key="ptd_actual", label="A"), Column(key="ptd_budget", label="B"), Column(key="ptd_var", label="V", derived=True),
            Column(key="ptd_var_pct", label="V%", kind="percent", derived=True), Column(key="ytd_actual", label="YA"),
            Column(key="ytd_budget", label="YB"), Column(key="ytd_var", label="YV", derived=True),
            Column(key="ytd_var_pct", label="YV%", kind="percent", derived=True), Column(key="annual_budget", label="AB")]
    t = Table(title="lines", columns=cols)
    for key, expense, a, b in (("total_revenue", False, 1000, 954), ("payroll", True, 100, 90), ("noi", False, 550, 514)):
        row = t.new_row(key, label=key)
        t.row_meta[key]["expense"] = expense
        row["ptd_actual"].value, row["ptd_budget"].value = a, b
        row["ytd_actual"].value, row["ytd_budget"].value = a * 2, b * 2
    return t


def test_recompute_financials_and_commentary_kpis():
    d = ReportData(meta={"period": {"start": "2026-04-01", "end": "2026-06-30", "quarter_label": "2Q26"}})
    d.sections["financials"] = Section(key="financials", title="F", page=6, tables={"lines": _financials_table()},
                                       fields={"period_label": Field(label="P", status="derived"), "ytd_label": Field(label="Y", status="derived")})
    d.sections["commentary"] = Section(key="commentary", title="C", page=5, fields={
        "revenue_var": Field(label="rv", kind="money", status="derived"), "opex_var": Field(label="ov", kind="money", status="derived"),
        "noi_var_pct": Field(label="nv", kind="percent", status="derived")})
    calc.recompute(d)
    assert d.value("financials.tables.lines.rows.total_revenue.ptd_var") == 46
    assert d.value("financials.tables.lines.rows.payroll.ptd_var") == -10 and d.value("financials.tables.lines.rows.payroll.ytd_var") == -20
    assert abs(d.value("financials.tables.lines.rows.noi.ptd_var_pct") - 36 / 514) < 1e-9
    assert d.value("financials.fields.period_label") == "Apr-Jun 2026" and d.value("financials.fields.ytd_label") == "Jan-Jun 2026"
    assert d.value("commentary.fields.revenue_var") == 46 and d.value("commentary.fields.opex_var") is None
    assert abs(d.value("commentary.fields.noi_var_pct") - 36 / 514) < 1e-9
    d.field("financials.tables.lines.rows.total_revenue.ptd_actual").override = 1100
    calc.recompute(d)
    assert d.value("financials.tables.lines.rows.total_revenue.ptd_var") == 146 and d.value("commentary.fields.revenue_var") == 146


def test_recompute_occupancy_lto_and_comps():
    d = ReportData(meta={"period": {"start": "2026-04-01", "end": "2026-06-30", "quarter_label": "2Q26"}})
    occ = Section(key="occupancy", title="O", page=9, fields={
        "prior_pct": Field(label="p", kind="percent", value=0.9171, status="extracted"),
        "current_pct": Field(label="c", kind="percent", value=0.9053, status="extracted"),
        "change_bps": Field(label="b", kind="number", status="derived"),
        "new_lease_count": Field(label="n", kind="integer", status="derived"),
        "new_lease_lto_pct": Field(label="n", kind="percent", status="derived")})
    t = Table(title="nl", columns=[Column(key="floor_plan", label="fp", kind="text"), Column(key="count", label="n", kind="integer"),
                                   Column(key="avg_prior", label="p"), Column(key="avg_current", label="c"),
                                   Column(key="lto", label="l", derived=True), Column(key="lto_pct", label="lp", kind="percent", derived=True)])
    for key, n, p, c in (("a1", 2, 1250, 1050), ("s1", 1, 1000, 900)):
        row = t.new_row(key, label=key)
        row["count"].value, row["avg_prior"].value, row["avg_current"].value = n, p, c
    for ck in ("count", "avg_prior", "avg_current", "lto", "lto_pct"):
        t.totals[ck] = Field(label=ck, status="derived")
    occ.tables["new_leases"] = t
    d.sections["occupancy"] = occ
    comps = Table(title="c", columns=[Column(key="name", label="n", kind="text"), Column(key="units", label="u", kind="integer"),
                                      Column(key="vintage", label="v", kind="integer"), Column(key="leased_pct", label="l", kind="percent"),
                                      Column(key="asking_rent", label="a"), Column(key="effective_rent", label="e"),
                                      Column(key="concession", label="c", derived=True), Column(key="concession_pct", label="cp", kind="percent", derived=True)])
    for key, subject, units, vint, leased, ask, eff in (("subj", True, 338, 1973, 0.9053, 1250, 1200), ("ash", False, 428, 1998, 0.6667, 1700, 1600), ("brant", False, None, 1989, 0.8, 1600, 1400)):
        row = comps.new_row(key, label=key)
        comps.row_meta[key]["subject"] = subject
        row["units"].value, row["vintage"].value, row["leased_pct"].value, row["asking_rent"].value, row["effective_rent"].value = units, vint, leased, ask, eff
    for ck in ("units", "vintage", "leased_pct", "asking_rent", "effective_rent", "concession", "concession_pct"):
        comps.totals[ck] = Field(label=ck, status="derived")
    d.sections["submarket"] = Section(key="submarket", title="S", page=8, tables={"comps": comps},
                                      fields={"pipeline_note": Field(label="pn", status="derived"), "data_quarter": Field(label="dq", status="derived"),
                                              "under_construction": Field(label="uc", kind="integer", value=0, status="extracted"),
                                              "uc_pct": Field(label="ucp", kind="percent", value=0.0, status="extracted"),
                                              "footnote": Field(label="fn", status="derived"), "source_note": Field(label="sn", status="derived")})
    calc.recompute(d)
    assert d.value("occupancy.fields.change_bps") == -118
    assert d.value("occupancy.tables.new_leases.rows.a1.lto") == -200 and abs(d.value("occupancy.tables.new_leases.rows.a1.lto_pct") + 0.16) < 1e-9
    tot = d.table("occupancy.tables.new_leases").totals
    assert tot["count"].value == 3 and abs(tot["avg_prior"].value - 1166.6667) < 1e-3 and tot["avg_current"].value == 1000
    assert abs(tot["lto"].value + 166.6667) < 1e-3 and d.value("occupancy.fields.new_lease_count") == 3
    assert d.value("submarket.tables.comps.rows.ash.concession") == 100
    ct = d.table("submarket.tables.comps").totals
    assert ct["asking_rent"].value == 1650 and ct["units"].value == 428 and ct["vintage"].value == 1994 and abs(ct["leased_pct"].value - 0.73335) < 1e-4
    assert d.value("submarket.fields.pipeline_note") == "0 units under construction (0.0% of inventory)"
    assert d.value("submarket.fields.data_quarter") == "2Q26"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_calc.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.consolidate.calc'`

- [ ] **Step 3: Write `backend/app/consolidate/calc.py`**

```python
"""Pure calculations and recompute(): fills every derived field from effective values.

Signs follow the Yardi convention used by the example report: a variance is favourable-positive,
so revenue variance = actual - budget and expense variance = budget - actual.
"""
from __future__ import annotations

import calendar
import datetime as dt
from typing import Iterable

from ..models import ReportData, Table

Num = float | int | None


def sum_or_none(vals: Iterable[Num]) -> float | None:
    xs = [float(v) for v in vals if v is not None]
    return sum(xs) if xs else None


def mean(vals: Iterable[Num]) -> float | None:
    xs = [float(v) for v in vals if v is not None]
    return sum(xs) / len(xs) if xs else None


def wavg(pairs: Iterable[tuple[Num, Num]]) -> float | None:
    """Weighted average of (value, weight) pairs; pairs with a missing value or weight are skipped."""
    num = den = 0.0
    for v, w in pairs:
        if v is None or w is None:
            continue
        num += float(v) * float(w)
        den += float(w)
    return num / den if den else None


def ratio(a: Num, b: Num) -> float | None:
    return None if a is None or not b else float(a) / float(b)


def variance(actual: Num, budget: Num, expense: bool) -> float | None:
    if actual is None or budget is None:
        return None
    return float(budget) - float(actual) if expense else float(actual) - float(budget)


def variance_pct(actual: Num, budget: Num, expense: bool) -> float | None:
    v = variance(actual, budget, expense)
    return None if v is None or not budget else v / abs(float(budget))


def bps(current: Num, prior: Num) -> float | None:
    return None if current is None or prior is None else round((float(current) - float(prior)) * 10000)


def implied_rate(monthly_interest: Num, principal: Num) -> float | None:
    return None if monthly_interest is None or not principal else float(monthly_interest) * 12 / float(principal)


def quarter_end(year: int, q: int) -> dt.date:
    m = q * 3
    return dt.date(year, m, calendar.monthrange(year, m)[1])


def quarter_label(d: dt.date) -> str:
    return f"{(d.month - 1) // 3 + 1}Q{d.year % 100:02d}"


def next_quarter_label(period_end: dt.date) -> str:
    q, y = (period_end.month - 1) // 3 + 1, period_end.year
    return f"{1}Q{(y + 1) % 100:02d}" if q == 4 else f"{q + 1}Q{y % 100:02d}"


def month_label(ym: str) -> str:
    y, m = ym.split("-")
    return f"{calendar.month_abbr[int(m)]} {y}"


def _row_val(row: dict, key: str):
    f = row.get(key)
    return None if f is None else f.effective


def _set_total(t: Table, key: str, value) -> None:
    f = t.totals.get(key)
    if f is not None and f.status == "derived":
        f.value = value


def _recompute_variances(t: Table, prefixes: tuple[str, ...] = ("ptd", "ytd")) -> None:
    for key, row in t.rows.items():
        expense = bool(t.row_meta.get(key, {}).get("expense"))
        for p in prefixes:
            a, b = _row_val(row, f"{p}_actual"), _row_val(row, f"{p}_budget")
            if f"{p}_var" in row and row[f"{p}_var"].status == "derived":
                row[f"{p}_var"].value = variance(a, b, expense)
            if f"{p}_var_pct" in row and row[f"{p}_var_pct"].status == "derived":
                row[f"{p}_var_pct"].value = variance_pct(a, b, expense)


def _period(d: ReportData) -> tuple[dt.date | None, dt.date | None, str | None]:
    p = d.meta.get("period") or {}
    s = dt.date.fromisoformat(p["start"]) if p.get("start") else None
    e = dt.date.fromisoformat(p["end"]) if p.get("end") else None
    return s, e, p.get("quarter_label")


def recompute(d: ReportData) -> None:  # noqa: C901 - one long, explicit pass over the model
    v, setv = d.value, d.set_derived
    start, end, qlabel = _period(d)
    if start and end:
        period_label = f"{start:%b}-{end:%b} {end:%Y}"
        prior_end = start - dt.timedelta(days=1)
        setv("property.fields.quarter_label", qlabel)
        setv("property.fields.period_label", period_label)
        setv("property.fields.period_end", end.isoformat())
        setv("property.fields.prior_quarter_label", quarter_label(prior_end))
        setv("financials.fields.period_label", period_label)
        setv("financials.fields.ytd_label", f"Jan-{end:%b} {end:%Y}")
        setv("in_place_rent.fields.prior_quarter_label", quarter_label(prior_end))
        setv("status.fields.next_quarter_label", next_quarter_label(end))
        setv("submarket.fields.data_quarter", qlabel)

    # property
    setv("property.fields.density", ratio(v("property.fields.units"), v("property.fields.site_acres")))

    # in-place rent
    t = d.table("in_place_rent.tables.by_floor_plan")
    if t:
        for row in t.rows.values():
            cur, pri = _row_val(row, "current_rent"), _row_val(row, "prior_rent")
            diff = None if cur is None or pri is None else cur - pri
            if "variance" in row:
                row["variance"].value = diff
            if "variance_pct" in row:
                row["variance_pct"].value = ratio(diff, pri)
        _set_total(t, "units", sum_or_none(_row_val(r, "units") for r in t.rows.values()))
        cur, pri = _row_val(t.totals, "current_rent"), _row_val(t.totals, "prior_rent")
        if cur is None:
            cur = wavg((_row_val(r, "current_rent"), _row_val(r, "units")) for r in t.rows.values())
            _set_total(t, "current_rent", cur)
        if pri is None:
            pri = wavg((_row_val(r, "prior_rent"), _row_val(r, "units")) for r in t.rows.values())
            _set_total(t, "prior_rent", pri)
        diff = None if cur is None or pri is None else cur - pri
        _set_total(t, "variance", diff)
        _set_total(t, "variance_pct", ratio(diff, pri))

    # capital
    setv("capital.fields.price_per_unit", ratio(v("capital.fields.purchase_price"), v("property.fields.units")))
    qc = v("capital.fields.quarter_contributions")
    setv("capital.fields.contributions_note", None if qc is None else ("No capital called this quarter" if qc == 0 else f"${qc:,.0f} called this quarter"))
    di = v("capital.fields.distributions_itd")
    setv("capital.fields.distributions_note", None if di is None else ("No distributions issued to date" if di == 0 else f"${di:,.0f} distributed to date"))

    # underwriting budget
    t = d.table("underwriting.tables.budget")
    if t:
        for row in t.rows.values():
            if "pct_spent" in row:
                row["pct_spent"].value = ratio(_row_val(row, "spent_to_date"), _row_val(row, "original_budget"))
        ob = sum_or_none(_row_val(r, "original_budget") for r in t.rows.values())
        sp = sum_or_none(_row_val(r, "spent_to_date") for r in t.rows.values())
        _set_total(t, "original_budget", ob)
        _set_total(t, "spent_to_date", sp)
        _set_total(t, "pct_spent", ratio(sp, ob))

    # financing
    setv("financing.fields.implied_rate", implied_rate(v("financing.fields.interest_monthly"), v("financing.fields.loan_amount")))
    rr = v("financing.fields.replacement_reserve_monthly")
    setv("financing.fields.replacement_reserve_annual", None if rr is None else rr * 12)

    # financials
    t = d.table("financials.tables.lines")
    if t:
        _recompute_variances(t)
    fin = "financials.tables.lines.rows"
    kpis = {
        "revenue_actual": f"{fin}.total_revenue.ptd_actual", "revenue_budget": f"{fin}.total_revenue.ptd_budget",
        "revenue_var": f"{fin}.total_revenue.ptd_var", "revenue_var_pct": f"{fin}.total_revenue.ptd_var_pct",
        "gpr_var_pct": f"{fin}.gpr.ptd_var_pct", "gain_to_lease_actual": f"{fin}.gain_loss_to_lease.ptd_actual",
        "gain_to_lease_budget": f"{fin}.gain_loss_to_lease.ptd_budget", "gain_to_lease_var_pct": f"{fin}.gain_loss_to_lease.ptd_var_pct",
        "concessions_var": f"{fin}.concessions.ptd_var", "opex_actual": f"{fin}.total_opex.ptd_actual",
        "opex_budget": f"{fin}.total_opex.ptd_budget", "opex_var": f"{fin}.total_opex.ptd_var", "opex_var_pct": f"{fin}.total_opex.ptd_var_pct",
        "insurance_var": f"{fin}.insurance.ptd_var", "utilities_var": f"{fin}.utilities.ptd_var",
        "noi_actual": f"{fin}.noi.ptd_actual", "noi_budget": f"{fin}.noi.ptd_budget", "noi_var": f"{fin}.noi.ptd_var",
        "noi_var_pct": f"{fin}.noi.ptd_var_pct", "debt_service_actual": f"{fin}.debt_service.ptd_actual",
        "ncf_actual": f"{fin}.net_cash_flow.ptd_actual", "ncf_budget": f"{fin}.net_cash_flow.ptd_budget",
        "ncf_var": f"{fin}.net_cash_flow.ptd_var", "ncf_var_pct": f"{fin}.net_cash_flow.ptd_var_pct",
        "noi_ytd_var_pct": f"{fin}.noi.ytd_var_pct",
    }
    for key, path in kpis.items():
        setv(f"commentary.fields.{key}", v(path))

    # capex
    t = d.table("capex.tables.lines")
    if t:
        _recompute_variances(t)
        for ck in ("ptd_actual", "ptd_budget", "ptd_var", "ytd_actual", "ytd_budget", "ytd_var", "annual_budget"):
            _set_total(t, ck, sum_or_none(_row_val(r, ck) for r in t.rows.values()))
        cap = "capex.tables.lines.totals"
        for key, col in (("capex_actual", "ptd_actual"), ("capex_budget", "ptd_budget"), ("capex_var", "ptd_var"),
                         ("capex_ytd_actual", "ytd_actual"), ("capex_ytd_budget", "ytd_budget"), ("capex_ytd_var", "ytd_var"),
                         ("capex_annual_budget", "annual_budget")):
            setv(f"commentary.fields.{key}", v(f"{cap}.{col}"))

    # submarket
    uc, ucp = v("submarket.fields.under_construction"), v("submarket.fields.uc_pct")
    if uc is not None:
        setv("submarket.fields.pipeline_note", f"{int(uc):,} units under construction" + (f" ({ucp * 100:.1f}% of inventory)" if ucp is not None else ""))
    t = d.table("submarket.tables.comps")
    if t:
        for row in t.rows.values():
            ask, eff = _row_val(row, "asking_rent"), _row_val(row, "effective_rent")
            conc = None if ask is None or eff is None else ask - eff
            if "concession" in row:
                row["concession"].value = conc
            if "concession_pct" in row:
                row["concession_pct"].value = ratio(conc, ask)
        comps = [r for k, r in t.rows.items() if not t.row_meta.get(k, {}).get("subject")]
        units = [_row_val(r, "units") for r in comps]
        weighted = all(u is not None for u in units) and bool(comps)
        def agg(col: str):
            if weighted:
                return wavg((_row_val(r, col), _row_val(r, "units")) for r in comps)
            return mean(_row_val(r, col) for r in comps)
        _set_total(t, "units", mean(units))
        vint = mean(_row_val(r, "vintage") for r in comps)
        _set_total(t, "vintage", None if vint is None else round(vint))
        for col in ("leased_pct", "asking_rent", "effective_rent"):
            _set_total(t, col, agg(col))
        ta, te = _row_val(t.totals, "asking_rent"), _row_val(t.totals, "effective_rent")
        _set_total(t, "concession", None if ta is None or te is None else ta - te)
        _set_total(t, "concession_pct", ratio(None if ta is None or te is None else ta - te, ta))
        n = len(comps)
        setv("submarket.fields.footnote", f"Comp set average across {n} propert{'y' if n == 1 else 'ies'}"
             + (" (unit-weighted)" if weighted else " (simple average; unit counts incomplete)") + ".")
    setv("submarket.fields.source_note", "Source: HelloData.ai listings and CoStar submarket data")

    # occupancy and trade-out
    setv("occupancy.fields.change_bps", bps(v("occupancy.fields.current_pct"), v("occupancy.fields.prior_pct")))
    for tkey, count_field, pct_field in (("new_leases", "new_lease_count", "new_lease_lto_pct"), ("renewals", "renewal_count", "renewal_lto_pct")):
        t = d.table(f"occupancy.tables.{tkey}")
        if not t:
            continue
        for row in t.rows.values():
            pri, cur = _row_val(row, "avg_prior"), _row_val(row, "avg_current")
            diff = None if pri is None or cur is None else cur - pri
            if "lto" in row:
                row["lto"].value = diff
            if "lto_pct" in row:
                row["lto_pct"].value = ratio(diff, pri)
        n = sum_or_none(_row_val(r, "count") for r in t.rows.values())
        pri = wavg((_row_val(r, "avg_prior"), _row_val(r, "count")) for r in t.rows.values())
        cur = wavg((_row_val(r, "avg_current"), _row_val(r, "count")) for r in t.rows.values())
        diff = None if pri is None or cur is None else cur - pri
        _set_total(t, "count", n)
        _set_total(t, "avg_prior", pri)
        _set_total(t, "avg_current", cur)
        _set_total(t, "lto", diff)
        _set_total(t, "lto_pct", ratio(diff, pri))
        setv(f"occupancy.fields.{count_field}", n)
        setv(f"occupancy.fields.{pct_field}", ratio(diff, pri))
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_calc.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: calculation helpers and derived-field recompute"
```

---

### Task 18: The builder (extractions to ReportData) and override application

This is the consolidation step. It only sets inputs (`extracted`, `missing`, `conflict`) and creates `derived` shells; `calc.recompute` fills the rest. Every value carries the source locator of the line it came from.

**Files:**
- Create: `backend/app/consolidate/builder.py`, `backend/tests/test_builder.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_builder.py
from app.classify.classifier import DocType
from app.consolidate.builder import apply_overrides, build
from app.extract.registry import run_extractor
from tests.helpers import (BALANCE_ROWS, BUDGET_ROWS, CAPITAL_CALLS_TEXT, COMPS_ROWS, COSTAR_PDF_TEXT, COSTAR_ROWS,
                           DISTRIBUTIONS_TEXT, LISTINGS_ROWS, LTO_ROWS, RENT_CHART_ROWS, pdf_part, rent_roll_rows,
                           schedule_rows, sheet_part)

JUN = {"BWK.A1": 1172.47, "BWK.B0": 1331.04, "BWK.B1": 1370.84, "BWK.S1": 1108.31, "TOTAL": 1250.5}
MAR = {"BWK.A1": 1205.1, "BWK.B0": 1357.95, "BWK.B1": 1356.5, "BWK.S1": 1099.72, "TOTAL": 1346.33}


def file_of(fid: str, filename: str, *parts) -> dict:
    exs = [run_extractor(p).model_dump() for p in parts]
    return {"id": fid, "original_filename": filename, "status": "processed", "ignored": False,
            "parts": [{"doc_type": p.doc_type} for p in parts], "extractions": exs}


def sample_files() -> list[dict]:
    return [
        file_of("f1", "financials.xlsx", sheet_part(BUDGET_ROWS, DocType.YARDI_BUDGET_COMPARISON, file_id="f1", filename="financials.xlsx")),
        file_of("f2", "bs.xlsx", sheet_part(BALANCE_ROWS, DocType.YARDI_BALANCE_SHEET, file_id="f2", filename="bs.xlsx")),
        file_of("f3", "rr-jun.xlsx", sheet_part(rent_roll_rows("06/30/2026", 306, 338, 90.53, 14), DocType.YARDI_RENT_ROLL, file_id="f3", filename="rr-jun.xlsx")),
        file_of("f4", "rr-mar.xlsx", sheet_part(rent_roll_rows("03/31/2026", 310, 338, 91.71, 34), DocType.YARDI_RENT_ROLL, file_id="f4", filename="rr-mar.xlsx")),
        file_of("f5", "sch-jun.xlsx", sheet_part(schedule_rows("06/30/2026", JUN), DocType.YARDI_MARKET_RENT_SCHEDULE, file_id="f5", filename="sch-jun.xlsx")),
        file_of("f6", "sch-mar.xlsx", sheet_part(schedule_rows("03/31/2026", MAR), DocType.YARDI_MARKET_RENT_SCHEDULE, file_id="f6", filename="sch-mar.xlsx")),
        file_of("f7", "lto.xlsx", sheet_part(LTO_ROWS, DocType.YARDI_LEASE_TRADE_OUT, file_id="f7", filename="lto.xlsx")),
        file_of("f8", "listings.xlsx", sheet_part(LISTINGS_ROWS, DocType.HELLODATA_LISTINGS, file_id="f8", filename="listings.xlsx")),
        file_of("f9", "comps.xlsx", sheet_part(COMPS_ROWS, DocType.HELLODATA_COMPS, file_id="f9", filename="comps.xlsx")),
        file_of("f10", "costar.xlsx", sheet_part(COSTAR_ROWS, DocType.COSTAR_SUBMARKET_EXCEL, file_id="f10", filename="costar.xlsx")),
        file_of("f11", "costar.pdf", pdf_part(COSTAR_PDF_TEXT, DocType.COSTAR_SUBMARKET_PDF, file_id="f11", filename="costar.pdf")),
        file_of("f12", "chart.xlsx", sheet_part(RENT_CHART_ROWS, DocType.RENT_CHART, file_id="f12", filename="chart.xlsx")),
        file_of("f13", "calls.pdf", pdf_part(CAPITAL_CALLS_TEXT, DocType.SLATE_CAPITAL_CALLS, file_id="f13", filename="calls.pdf")),
        file_of("f14", "dists.pdf", pdf_part(DISTRIBUTIONS_TEXT, DocType.SLATE_DISTRIBUTIONS, file_id="f14", filename="dists.pdf")),
    ]


def test_build_end_to_end():
    data, notes = build({"id": "p1", "name": "Boardwalk"}, sample_files())
    v = data.value
    assert data.meta["period"]["quarter_label"] == "2Q26" and not [n for n in notes if n["severity"] == "error"]
    # property
    assert v("property.fields.name") == "The Boardwalk" and v("property.fields.units") == 338
    assert v("property.fields.year_built") == 1973 and v("property.fields.acquired_date") == "2025-07-30"
    assert v("property.fields.address") == "4637 Deleon Street" and v("property.fields.city_state") == "Fort Myers, FL"
    assert v("property.fields.zip") == "33907" and v("property.fields.submarket") == "Western Lee County"
    assert v("property.fields.prepared_by") == "ZMR Capital" and v("property.fields.avg_unit_sf") == 760
    assert v("property.fields.quarter_label") == "2Q26" and data.field("property.fields.site_acres").status == "missing"
    assert data.field("property.fields.name").source.filename == "rr-jun.xlsx"
    # capital
    pp = data.field("capital.fields.purchase_price")
    assert pp.value == 48000000 and pp.status == "conflict" and pp.alternatives[0].value == 38100000
    assert v("capital.fields.equity_invested") == 14259605.94 and v("capital.fields.quarter_contributions") == 0.0
    assert v("capital.fields.distributions_itd") == 0.0 and abs(v("capital.fields.price_per_unit") - 48000000 / 338) < 1e-6
    assert v("capital.fields.contributions_note") == "No capital called this quarter"
    # financing
    assert v("financing.fields.loan_amount") == 36519000 and v("financing.fields.interest_monthly") == 159161.98
    assert abs(v("financing.fields.implied_rate") - 0.0523) < 1e-4 and v("financing.fields.borrower") == "The Boardwalk Owner, LLC"
    assert data.field("financing.fields.lender").status == "missing"
    # financials
    fin = "financials.tables.lines.rows"
    assert v(f"{fin}.total_revenue.ptd_actual") == 1000 and v(f"{fin}.total_revenue.ptd_var") == 46
    assert v(f"{fin}.payroll.ptd_var") == -10 and v(f"{fin}.concessions.ptd_actual") == -50
    assert v(f"{fin}.net_cash_flow.ptd_var") == 36 and v(f"{fin}.property_taxes.ptd_actual") == 100
    assert v(f"{fin}.debt_service.ptd_actual") == 300 and v(f"{fin}.total_opex.ytd_actual") == 900
    assert data.field(f"{fin}.gpr.ptd_actual").source.locator == "sheet 'Report1' rows 8"
    # capex
    cap = "capex.tables.lines"
    assert set(data.table(cap).rows) == {"plumbing_water_heaters", "paint", "roof"}
    assert v(f"{cap}.rows.plumbing_water_heaters.ptd_actual") == 33 and v(f"{cap}.rows.plumbing_water_heaters.ytd_budget") == 31
    assert v(f"{cap}.totals.ptd_actual") == 61 and v(f"{cap}.totals.ytd_actual") == 98 and v("capex.fields.source_total_ptd") == 61
    assert v("commentary.fields.capex_var") == -29
    # in-place rent
    ipr = "in_place_rent.tables.by_floor_plan"
    assert list(data.table(ipr).rows) == ["0br", "1br", "2br"]
    assert v(f"{ipr}.rows.1br.current_rent") == 1172.47 and v(f"{ipr}.rows.1br.prior_rent") == 1205.1
    assert abs(v(f"{ipr}.rows.2br.current_rent") - 1342.497) < 0.01 and v(f"{ipr}.rows.2br.units") == 76
    assert abs(v(f"{ipr}.rows.1br.variance") + 32.63) < 1e-6 and v(f"{ipr}.rows.2br.type") == "2 BR · 1-2 BA"
    assert v(f"{ipr}.totals.current_rent") == 1250.5 and v(f"{ipr}.totals.units") == 139
    # occupancy and trade-out
    assert abs(v("occupancy.fields.current_pct") - 0.9053) < 1e-9 and abs(v("occupancy.fields.prior_pct") - 0.9171) < 1e-9
    assert v("occupancy.fields.change_bps") == -118 and v("occupancy.fields.future_applicants") == 14
    nl = "occupancy.tables.new_leases"
    assert list(data.table(nl).rows) == ["bwk-s1", "bwk-a1"]
    assert v(f"{nl}.rows.bwk-a1.count") == 2 and v(f"{nl}.rows.bwk-a1.avg_prior") == 1250 and v(f"{nl}.rows.bwk-a1.lto") == -200
    assert v(f"{nl}.totals.count") == 3 and v("occupancy.fields.new_lease_count") == 3 and v("occupancy.fields.renewal_count") == 2
    assert v("occupancy.tables.renewals.rows.bwk-a1.avg_current") == 1425
    # submarket
    assert abs(v("submarket.fields.vacancy") - 0.16339) < 1e-4 and abs(v("submarket.fields.prior_vacancy") - 0.14712) < 1e-4
    assert abs(v("submarket.fields.rent_growth_yoy") + 0.05424) < 1e-4 and v("submarket.fields.under_construction") == 0
    assert v("submarket.fields.submarket_name") == "Western Lee County"
    comps = "submarket.tables.comps"
    assert list(data.table(comps).rows) == ["the-boardwalk", "the-ashlar"]
    assert data.table(comps).row_meta["the-boardwalk"]["subject"] is True
    assert abs(v(f"{comps}.rows.the-boardwalk.leased_pct") - 0.9053) < 1e-9 and v(f"{comps}.rows.the-boardwalk.units") == 338
    assert v(f"{comps}.rows.the-ashlar.asking_rent") == 1700 and v(f"{comps}.rows.the-ashlar.concession") == 100
    assert abs(v(f"{comps}.rows.the-ashlar.leased_pct") - 2 / 3) < 1e-9 and v(f"{comps}.rows.the-ashlar.vintage") == 1998
    assert v(f"{comps}.totals.asking_rent") == 1700
    # rent trend and status
    assert list(data.table("rent_trend.tables.monthly").rows) == ["2025-07", "2025-08"]
    assert v("rent_trend.fields.subject_name") == "The Boardwalk"
    assert v("status.fields.collections_recovered") == 7 and v("status.fields.bad_debt_writeoff") == -10
    assert v("status.fields.next_quarter_label") == "3Q26"


def test_build_with_only_financials_flags_missing_but_does_not_fail():
    data, notes = build({"id": "p", "name": "P"}, sample_files()[:1])
    assert data.value("financials.tables.lines.rows.noi.ptd_actual") == 550
    assert data.field("property.fields.units").status == "missing"
    assert any(n["severity"] == "error" and "Property name" in n["message"] for n in notes)
    assert data.table("submarket.tables.comps").rows == {} and data.table("in_place_rent.tables.by_floor_plan").rows == {}


def test_apply_overrides_fields_rows_deletions_and_ai_drafts():
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    stale = apply_overrides(data, {
        "fields": {"financing.fields.lender": "Fannie Mae", "capital.fields.purchase_price": 38100000, "gone.fields.x": 1},
        "rows": {"underwriting.tables.budget": {"manual_1": {"category": "Amenity Upkeep", "section": "value_add", "original_budget": 75000, "spent_to_date": 0}}},
        "deleted_rows": {"submarket.tables.comps": ["the-ashlar"]},
        "ai_drafts": {"commentary.fields.takeaway": "Revenue finished below budget."},
    })
    assert stale == ["gone.fields.x"]
    assert data.value("financing.fields.lender") == "Fannie Mae" and data.value("capital.fields.purchase_price") == 38100000
    row = data.table("underwriting.tables.budget").rows["manual_1"]
    assert row["category"].value == "Amenity Upkeep" and row["category"].status == "manual" and row["pct_spent"].status == "derived"
    assert "the-ashlar" not in data.table("submarket.tables.comps").rows
    tk = data.field("commentary.fields.takeaway")
    assert tk.value == "Revenue finished below budget." and tk.status == "ai_draft"
    from app.consolidate.calc import recompute
    recompute(data)
    assert data.value("underwriting.tables.budget.totals.original_budget") == 75000 and data.value("underwriting.tables.budget.rows.manual_1.pct_spent") == 0
    assert abs(data.value("capital.fields.price_per_unit") - 38100000 / 338) < 1e-6
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_builder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.consolidate.builder'`

- [ ] **Step 3: Write `backend/app/consolidate/builder.py`**

```python
"""Consolidate the selected extractions into ReportData.

Only inputs are set here (statuses extracted / missing / conflict); derived shells are created and
filled by calc.recompute. Every extracted Field carries the locator of the line it came from.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from ..config import settings
from ..models import Alternative, Column, Field, ReportData, Section, Source, Table
from ..readers.document import norm
from . import calc
from .mapping import consume_capex, load_capex_mapping, load_pl_mapping, match_lines, section_matches
from .select import Selection, Src, collect, select

ADDRESS_RE = re.compile(r"^(?P<street>.+?),\s*(?P<city>[^,]+?),\s*(?P<state>[A-Z]{2})\b\s*(?P<zip>\d{5})?")
VALUE_COLS = ("ptd_actual", "ptd_budget", "ytd_actual", "ytd_budget", "annual_budget")


# ---------- small constructors ----------
def F(label: str, kind: str = "text", value=None, source: dict | None = None, note: str | None = None, status: str | None = None) -> Field:
    st = status or ("extracted" if value is not None else "missing")
    return Field(label=label, kind=kind, value=value, status=st, source=Source(**source) if source else None, note=note)


def D(label: str, kind: str = "number", note: str | None = None) -> Field:
    return Field(label=label, kind=kind, status="derived", note=note)


def M(label: str, kind: str = "text", note: str | None = None) -> Field:
    return Field(label=label, kind=kind, status="missing", note=note or "Not found in any source file; enter manually")


def C(key: str, label: str, kind: str = "money", derived: bool = False) -> Column:
    return Column(key=key, label=label, kind=kind, derived=derived)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(s)).strip("-") or "row"


def names_match(a: str | None, b: str | None) -> bool:
    ka, kb = (re.sub(r"[^a-z0-9]", "", re.sub(r"^the\s+", "", norm(x))) for x in (a or "", b or ""))
    return bool(ka) and bool(kb) and (ka == kb or ka in kb or kb in ka)


def _date(s: str | None) -> dt.date | None:
    return dt.date.fromisoformat(s) if s else None


@dataclass
class Period:
    start: dt.date
    end: dt.date

    @property
    def quarter(self) -> int:
        return (self.end.month - 1) // 3 + 1

    @property
    def year(self) -> int:
        return self.end.year

    @property
    def quarter_label(self) -> str:
        return calc.quarter_label(self.end)

    @property
    def prior_end(self) -> dt.date:
        return self.start - dt.timedelta(days=1)

    @property
    def prior_quarter_label(self) -> str:
        return calc.quarter_label(self.prior_end)

    @property
    def months(self) -> int:
        return (self.end.year - self.start.year) * 12 + self.end.month - self.start.month + 1


@dataclass
class Ctx:
    sel: Selection
    period: Period
    notes: list[dict] = field(default_factory=list)
    property_name: str | None = None
    units: float | None = None

    def note(self, severity: str, message: str, path: str | None = None) -> None:
        self.notes.append({"severity": severity, "message": message, "path": path})


# ---------- source lookups ----------
def _at_or_before(srcs: list[Src], date: dt.date) -> Src | None:
    dated = [s for s in srcs if s.data.get("as_of")]
    on_or_before = [s for s in dated if s.data["as_of"] <= date.isoformat()]
    if on_or_before:
        return max(on_or_before, key=lambda s: s.data["as_of"])
    if dated:
        return max(dated, key=lambda s: s.data["as_of"])
    return srcs[-1] if srcs else None


def _before(srcs: list[Src], as_of: str) -> Src | None:
    earlier = [s for s in srcs if s.data.get("as_of") and s.data["as_of"] < as_of]
    return max(earlier, key=lambda s: s.data["as_of"]) if earlier else None


def _subject_sale(sel: Selection, name: str | None) -> dict | None:
    if not (sel.costar_pdf and name):
        return None
    return next((s for s in sel.costar_pdf.data.get("sales", []) if names_match(s.get("name"), name)), None)


def _comp_meta(sel: Selection, name: str | None) -> dict | None:
    if not name:
        return None
    for src in sel.comps:
        for c in src.data.get("comps", []):
            if names_match(c.get("name"), name):
                loc = f"row {c['row'] + 1}" if c.get("row") is not None else f"page {c.get('page', '')}".strip()
                return {**c, "_src": src.source(loc, c.get("name"))}
    return None


def _subject_listing(sel: Selection, name: str | None) -> tuple[str | None, dict | None]:
    if not (sel.listings and name):
        return None, None
    for pname, prop in sel.listings.data.get("properties", {}).items():
        if names_match(pname, name):
            return pname, prop
    return None, None


def _split_address(addr: str | None) -> tuple[str | None, str | None, str | None, str | None]:
    if not addr:
        return None, None, None, None
    m = ADDRESS_RE.match(addr.strip())
    if not m:
        return addr.strip(), None, None, None
    return m.group("street"), m.group("city"), m.group("state"), m.group("zip")


def _period(sel: Selection) -> tuple[Period, list[dict]]:
    for src in (sel.budget, sel.lto):
        p = src.data.get("period") if src else None
        if p and p.get("start") and p.get("end"):
            return Period(_date(p["start"]), _date(p["end"])), []
    as_ofs = [s.data["as_of"] for s in sel.rent_rolls + sel.schedules if s.data.get("as_of")]
    if as_ofs:
        end = _date(max(as_ofs))
        q = (end.month - 1) // 3 + 1
        note = {"severity": "warning", "path": "financials",
                "message": f"Reporting period inferred from the latest rent roll / rent schedule date ({end.isoformat()})"}
        return Period(dt.date(end.year, (q - 1) * 3 + 1, 1), calc.quarter_end(end.year, q)), [note]
    today = dt.date.today()
    q = (today.month - 1) // 3 + 1
    note = {"severity": "error", "path": "financials",
            "message": "Reporting period could not be determined from any file; defaulted to the current quarter. "
                       "Upload a Budget Comparison, Lease Trade-Out or rent roll."}
    return Period(dt.date(today.year, (q - 1) * 3 + 1, 1), calc.quarter_end(today.year, q)), [note]


def _sources_used(sel: Selection) -> list[dict]:
    out = []
    for key in ("budget", "balance_sheet", "lto", "listings", "costar_excel", "costar_pdf", "rent_chart", "capital_calls", "distributions"):
        src = getattr(sel, key)
        if src:
            out.append({"role": key, "doc_type": src.doc_type, "filename": src.filename, "locator": src.locator})
    for key in ("rent_rolls", "schedules", "comps"):
        for src in getattr(sel, key):
            out.append({"role": key, "doc_type": src.doc_type, "filename": src.filename, "locator": src.locator})
    return out


# ---------- sections ----------
def _property(ctx: Ctx, data: ReportData) -> Section:
    sel, p = ctx.sel, ctx.period
    s = Section(key="property", title="Property", page=1)
    f = s.fields
    rr = _at_or_before(sel.rent_rolls, p.end)
    sch = _at_or_before(sel.schedules, p.end)
    named = [x for x in (rr, sch, *sel.rent_rolls, *sel.schedules) if x and x.data.get("property_name")]
    name_src = named[0] if named else None
    name = name_src.data["property_name"] if name_src else (sel.lto.data.get("property_name") if sel.lto else None)
    ctx.property_name = name
    f["name"] = F("Property name", "text", name,
                  name_src.source("title") if name_src else (sel.lto.source("first row") if sel.lto and name else None))
    units_src = rr or (sel.rent_rolls[-1] if sel.rent_rolls else None)
    if units_src and units_src.data.get("total_units"):
        units, units_source = units_src.data["total_units"], units_src.source("summary block", "Totals")
    elif sch and (sch.data.get("total") or {}).get("units"):
        units, units_source = sch.data["total"]["units"], sch.source("grand total")
    else:
        units, units_source = None, None
    ctx.units = units
    f["units"] = F("Units", "integer", units, units_source)
    sale = _subject_sale(sel, name)
    meta = _comp_meta(sel, name)
    sale_src = sel.costar_pdf.source(f"page {sale['page']}", "sale comps") if sale else None
    yb = sale["year_built"] if sale else (meta.get("year_built") if meta else None)
    f["year_built"] = F("Year built", "integer", yb, sale_src if sale else (meta["_src"] if meta and yb else None))
    f["acquired_date"] = F("Acquisition date", "date", sale["sale_date"] if sale else None, sale_src)
    addr, addr_src = (meta["address"], meta["_src"]) if meta and meta.get("address") else (None, None)
    if addr is None:
        _, prop = _subject_listing(sel, name)
        if prop and prop.get("address"):
            addr, addr_src = prop["address"], sel.listings.source(f"row {prop['first_row'] + 1}", prop["address"])
    street, city, state, zip_ = _split_address(addr)
    f["address"] = F("Street address", "text", street, addr_src)
    city_state, cs_src = (f"{city}, {state}" if city and state else None), addr_src
    cp = sel.costar_pdf
    if city_state is None and cp and cp.data.get("market"):
        city_state = ", ".join(x for x in (cp.data.get("market"), cp.data.get("state")) if x)
        cs_src = cp.source("page 1", "market")
    f["city_state"] = F("City, State", "text", city_state, cs_src)
    f["zip"] = F("ZIP", "text", zip_, addr_src)
    f["submarket"] = F("Submarket", "text", cp.data.get("submarket") if cp else None, cp.source("page 1") if cp and cp.data.get("submarket") else None)
    f["msa"] = F("Market / MSA", "text", cp.data.get("market") if cp else None, cp.source("page 1") if cp and cp.data.get("market") else None)
    sqft = (sch.data.get("total") or {}).get("sqft") if sch else None
    f["avg_unit_sf"] = F("Average unit size (SF)", "number", sqft if sqft else (meta.get("avg_sqft") if meta else None),
                         sch.source("grand total") if sqft else (meta["_src"] if meta and meta.get("avg_sqft") else None))
    f["prepared_by"] = F("Prepared by", "text", cp.data.get("licensed_to") if cp else None,
                         cp.source("footer", "Licensed to") if cp and cp.data.get("licensed_to") else None)
    f["building_class"] = M("Building class", "text")
    f["site_acres"] = M("Site size (acres)", "number")
    f["density"] = D("Density (units per acre)", "number")
    f["hold_period_years"] = M("Hold period (years)", "integer")
    f["description"] = M("Property description", "longtext")
    f["quarter_label"] = D("Quarter", "text")
    f["period_label"] = D("Period", "text")
    f["period_end"] = D("Period end", "date")
    f["prior_quarter_label"] = D("Prior quarter", "text")
    if not name:
        ctx.note("error", "Property name not found in any rent roll, rent schedule or trade-out report", "property.fields.name")
    return s


def _group_label(units: list[dict]) -> str:
    beds = units[0].get("bedrooms")
    baths = sorted({u["bathrooms"] for u in units if u.get("bathrooms") is not None})
    bed_txt = "Other" if beds is None else ("Studio" if beds == 0 else f"{beds} BR")
    if not baths:
        return bed_txt
    bath_txt = f"{baths[0]:g} BA" if len(baths) == 1 else f"{baths[0]:g}-{baths[-1]:g} BA"
    return f"{bed_txt} · {bath_txt}"


def _in_place_rent(ctx: Ctx, data: ReportData) -> Section:
    sel, p = ctx.sel, ctx.period
    s = Section(key="in_place_rent", title="In-Place Rent by Floor Plan", page=2)
    cur = _at_or_before(sel.schedules, p.end)
    prior = _before(sel.schedules, cur.data["as_of"]) if cur and cur.data.get("as_of") else None
    t = Table(title="In-place rent by floor plan", columns=[
        C("type", "Type", "text"), C("units", "Units", "integer"), C("avg_sf", "Avg SF", "number"),
        C("prior_rent", f"{p.prior_quarter_label} in-place rent"), C("current_rent", f"{p.quarter_label} in-place rent"),
        C("variance", "QoQ variance", derived=True), C("variance_pct", "QoQ variance %", "percent", derived=True)])

    def groups(src: Src | None) -> dict[str, list[dict]]:
        g: dict[str, list[dict]] = {}
        for u in (src.data.get("unit_types", []) if src else []):
            key = f"{u['bedrooms']}br" if u.get("bedrooms") is not None else "other"
            g.setdefault(key, []).append(u)
        return g

    cur_groups, prior_groups = groups(cur), groups(prior)
    for key in sorted(cur_groups, key=lambda k: (k == "other", int(k[:-2]) if k != "other" else 99)):
        us = cur_groups[key]
        label = _group_label(us)
        row = t.new_row(key, label=label)
        src = cur.source(f"rows {', '.join(str(u['row'] + 1) for u in us)}", ", ".join(u.get("code") or u["label"] for u in us))
        row["type"] = F("Type", "text", label, src)
        row["units"] = F("Units", "integer", calc.sum_or_none(u.get("units") for u in us), src)
        row["avg_sf"] = F("Avg SF", "number", calc.wavg((u.get("sqft"), u.get("units")) for u in us), src)
        row["current_rent"] = F(f"{p.quarter_label} in-place rent", "money",
                                calc.wavg((u.get("avg_resident_rent"), u.get("occupied_units")) for u in us), src,
                                note="Average resident rent weighted by occupied units")
        pus = prior_groups.get(key, [])
        row["prior_rent"] = F(f"{p.prior_quarter_label} in-place rent", "money",
                              calc.wavg((u.get("avg_resident_rent"), u.get("occupied_units")) for u in pus) if pus else None,
                              prior.source(f"rows {', '.join(str(u['row'] + 1) for u in pus)}") if pus else None,
                              note=None if pus else "No prior-quarter Market Rent Schedule found for this floor plan")
    t.totals["type"] = F("Type", "text", "Total / Weighted", status="derived")
    t.totals["units"] = D("Units", "integer")
    cur_tot, prior_tot = (cur.data.get("total") or {}) if cur else {}, (prior.data.get("total") or {}) if prior else {}
    t.totals["avg_sf"] = F("Avg SF", "number", cur_tot.get("sqft"), cur.source("grand total") if cur_tot.get("sqft") else None)
    t.totals["current_rent"] = F(f"{p.quarter_label} in-place rent", "money", cur_tot.get("avg_resident_rent"),
                                 cur.source("grand total") if cur_tot.get("avg_resident_rent") else None, status="extracted" if cur_tot.get("avg_resident_rent") else "derived")
    t.totals["prior_rent"] = F(f"{p.prior_quarter_label} in-place rent", "money", prior_tot.get("avg_resident_rent"),
                               prior.source("grand total") if prior_tot.get("avg_resident_rent") else None, status="extracted" if prior_tot.get("avg_resident_rent") else "derived")
    t.totals["variance"] = D("QoQ variance", "money")
    t.totals["variance_pct"] = D("QoQ variance %", "percent")
    s.tables["by_floor_plan"] = t
    s.fields["prior_quarter_label"] = D("Prior quarter", "text")
    s.fields["prior_variance_note"] = M("Prior quarter variance note", "text", note="Optional, e.g. 'vs. -$118 / -8.1% (4Q25 to 1Q26)'")
    s.fields["narrative"] = M("In-place rent commentary", "longtext")
    if not cur:
        ctx.note("error", "No Market Rent Schedule found; the in-place rent table is empty", "in_place_rent")
    elif not prior:
        ctx.note("warning", "Only one Market Rent Schedule found; prior-quarter in-place rents are missing", "in_place_rent")
    return s


def _capital(ctx: Ctx, data: ReportData) -> Section:
    sel, p = ctx.sel, ctx.period
    s = Section(key="capital", title="Capital Summary", page=3)
    f = s.fields
    bs = sel.balance_sheet
    lines = bs.data["lines"] if bs else []
    used: list[dict] = []
    price = None
    tb = match_lines(lines, [r"^total building"], prefer_total=True)
    tf = match_lines(lines, [r"^total furniture"], prefer_total=True)
    if tb:
        used = tb + tf
        price = (tb[0]["values"].get("current") or 0) + ((tf[0]["values"].get("current") or 0) if tf else 0)
    else:
        for pat in (r"^land$", r"^buildings?$", r"^furniture"):
            hit = match_lines(lines, [pat])
            if hit:
                used.append(hit[0])
        if used:
            price = sum(h["values"].get("current") or 0 for h in used)
    src = bs.source(f"rows {', '.join(str(h['row'] + 1) for h in used)}", " + ".join(h["label"] for h in used)) if used else None
    f["purchase_price"] = F("Purchase price", "money", price, src, note="Land + Building + FF&E at cost from the balance sheet" if used else None)
    sale = _subject_sale(sel, ctx.property_name)
    if sale and sale.get("price"):
        alt_src = sel.costar_pdf.source(f"page {sale['page']}", "CoStar sale comps")
        if price is None:
            f["purchase_price"] = F("Purchase price", "money", sale["price"], alt_src, note="CoStar recorded sale price")
        elif abs(sale["price"] - price) / price > 0.01:
            f["purchase_price"].status = "conflict"
            f["purchase_price"].alternatives.append(Alternative(value=sale["price"], source=Source(**alt_src), note="CoStar recorded sale price"))
            ctx.note("warning", f"Purchase price: balance sheet basis ${price:,.0f} differs from the CoStar sale price ${sale['price']:,.0f}. "
                                "The balance sheet value is used; choose the alternative to show the contract price.", "capital.fields.purchase_price")
    f["price_per_unit"] = D("Price per unit", "money")
    eq = match_lines(lines, [r"owner'?s? contributions?", r"contributed capital", r"partners?'? contributions?", r"capital contributions?", r"members?'? contributions?"])
    f["equity_invested"] = F("Equity invested (ITD)", "money", eq[0]["values"].get("current") if eq else None,
                             bs.source(f"row {eq[0]['row'] + 1}", eq[0]["label"]) if eq else None)
    cc = sel.capital_calls
    if cc:
        in_q = [c for c in cc.data.get("calls", []) if c.get("due_date") and p.start.isoformat() <= c["due_date"] <= p.end.isoformat()]
        if in_q:
            q_amt = sum(c.get("amount") or 0 for c in in_q)
        elif cc.data.get("none") or cc.data.get("total_called") == 0:
            q_amt = 0.0
        else:
            q_amt = None
        f["quarter_contributions"] = F(f"{p.quarter_label} equity contributions", "money", q_amt, cc.source(),
                                       note=None if q_amt is not None else "Capital calls exist but none fall in the reporting period; confirm")
        f["total_called"] = F("Total called (ITD)", "money", cc.data.get("total_called"), cc.source())
    else:
        f["quarter_contributions"] = M(f"{p.quarter_label} equity contributions", "money")
        f["total_called"] = M("Total called (ITD)", "money")
    dd = sel.distributions
    if dd:
        dl = dd.data.get("distributions", [])
        in_q = [x for x in dl if x.get("date") and p.start.isoformat() <= x["date"] <= p.end.isoformat()]
        f["distributions_itd"] = F("Cash distributions (ITD)", "money", dd.data.get("total_gross"), dd.source())
        f["quarter_distributions"] = F(f"{p.quarter_label} distributions", "money",
                                       sum(x.get("gross") or 0 for x in in_q) if dl else (0.0 if dd.data.get("none") else None), dd.source())
    else:
        f["distributions_itd"] = M("Cash distributions (ITD)", "money")
        f["quarter_distributions"] = M(f"{p.quarter_label} distributions", "money")
    f["contributions_note"] = D("Contributions caption", "text")
    f["distributions_note"] = D("Distributions caption", "text")
    f["business_plan_summary"] = M("Business plan summary", "longtext")
    if not bs:
        ctx.note("warning", "No balance sheet found; purchase price, equity and loan principal are missing", "capital")
    return s


def _underwriting(ctx: Ctx, data: ReportData) -> Section:
    s = Section(key="underwriting", title="Original Underwriting Budget", page=3)
    t = Table(title="Original underwriting budget", columns=[
        C("category", "Category", "text"), C("section", "Section (value_add | recurring)", "text"),
        C("original_budget", "Original budget"), C("spent_to_date", "Spent to date"),
        C("pct_spent", "% spent", "percent", derived=True)], editable_rows=True)
    for ck in ("original_budget", "spent_to_date", "pct_spent"):
        t.totals[ck] = D(t.columns[[c.key for c in t.columns].index(ck)].label, "percent" if ck == "pct_spent" else "money")
    t.totals["category"] = F("Category", "text", "Total Underwritten Capital", status="derived")
    s.tables["budget"] = t
    s.fields["spent_period_note"] = M("Spent-to-date period note", "text", note="e.g. 'Spent to Date reflects the period 08/2025 - 06/2026'")
    s.fields["business_plan_title"] = M("Business plan headline", "text")
    ctx.note("info", "The original underwriting budget is not in any source file; add rows on the review screen", "underwriting")
    return s


def _computed_trend(ctx: Ctx) -> list[dict]:
    sel = ctx.sel
    months: dict[str, dict] = {}

    def slot(ym: str) -> dict:
        return months.setdefault(ym, {"sn": 0, "sr": 0.0, "se": 0.0, "ss": 0.0, "cn": 0, "cr": 0.0, "ce": 0.0, "cs": 0.0})

    if sel.lto:
        for r in sel.lto.data.get("sections", {}).get("move_ins", {}).get("rows", []):
            if not (r.get("start") and r.get("sqft") and r.get("lease_rent") is not None):
                continue
            m = slot(r["start"][:7])
            m["sn"] += 1
            m["sr"] += r["lease_rent"]
            m["se"] += r["effective_rent"] if r.get("effective_rent") is not None else r["lease_rent"]
            m["ss"] += r["sqft"]
    if sel.listings:
        subject, _ = _subject_listing(sel, ctx.property_name)
        for pname, prop in sel.listings.data.get("properties", {}).items():
            if pname == subject:
                continue
            for ym, agg in prop.get("monthly", {}).items():
                m = slot(ym)
                m["cn"] += agg["n"]
                m["cr"] += agg["asking_sum"]
                m["ce"] += agg["effective_sum"]
                m["cs"] += agg["sqft_sum"]
    return [{"month": ym, "subject_n": m["sn"] or None, "subject_gross_psf": calc.ratio(m["sr"], m["ss"]),
             "subject_eff_psf": calc.ratio(m["se"], m["ss"]), "comp_n": m["cn"] or None,
             "comp_gross_psf": calc.ratio(m["cr"], m["cs"]), "comp_eff_psf": calc.ratio(m["ce"], m["cs"])}
            for ym, m in sorted(months.items())]


def _rent_trend(ctx: Ctx, data: ReportData) -> Section:
    sel = ctx.sel
    s = Section(key="rent_trend", title="Submarket Rent Trend", page=3)
    f = s.fields
    t = Table(title="New-lease rent per SF by month", columns=[
        C("month", "Month", "text"), C("subject_n", "Subject leases", "integer"), C("subject_gross_psf", "Subject gross $/SF", "number"),
        C("subject_eff_psf", "Subject effective $/SF", "number"), C("comp_n", "Comp leases", "integer"),
        C("comp_gross_psf", "Comp gross $/SF", "number"), C("comp_eff_psf", "Comp effective $/SF", "number")], editable_rows=True)
    rc = sel.rent_chart
    if rc:
        for m in rc.data.get("months", []):
            row = t.new_row(m["month"], label=calc.month_label(m["month"]))
            src = rc.source(f"row {m['row'] + 1}", m["month"])
            for c in t.columns:
                val = m["month"] if c.key == "month" else m.get(c.key)
                row[c.key] = F(c.label, c.kind, val, src if val is not None else None)
        f["subject_name"] = F("Subject series name", "text", rc.data.get("subject_name") or ctx.property_name, rc.source("header row"))
        f["comp_name"] = F("Comp series name", "text", rc.data.get("comp_name") or "Comp Set", rc.source("header row"))
        f["chart_title"] = F("Chart title", "text", rc.data.get("title") or None, rc.source("row 1"))
        f["chart_subtitle"] = F("Chart subtitle", "text", rc.data.get("subtitle") or None, rc.source("row 2"))
        note = next((n for n in rc.data.get("notes", []) if n.lower().startswith("source")), None)
        f["methodology_note"] = F("Methodology note", "text", note, rc.source("notes") if note else None)
    else:
        months = _computed_trend(ctx)
        base = sel.lto or sel.listings
        src = base.source("computed") if base else None
        for m in months:
            row = t.new_row(m["month"], label=calc.month_label(m["month"]))
            for c in t.columns:
                val = m["month"] if c.key == "month" else m.get(c.key)
                row[c.key] = F(c.label, c.kind, val, src if val is not None else None,
                               note="Computed from LTO move-ins and HelloData leased listings" if val is not None else None)
        f["subject_name"] = F("Subject series name", "text", ctx.property_name)
        f["comp_name"] = F("Comp series name", "text", "HelloData Comp Set" if sel.listings else None)
        f["chart_title"] = F("Chart title", "text", f"{ctx.property_name} vs. HelloData Comp Set" if ctx.property_name and months else None)
        f["chart_subtitle"] = F("Chart subtitle", "text",
                                f"{calc.month_label(months[0]['month'])} - {calc.month_label(months[-1]['month'])}" if months else None)
        f["methodology_note"] = F("Methodology note", "text",
                                  "Computed: SF-weighted new-lease gross and effective rent per month from Yardi LTO move-ins (subject) "
                                  "and HelloData leased listings (comps). Window limited to the files supplied." if months else None)
        if not months:
            ctx.note("warning", "No rent chart workbook and not enough LTO / HelloData data to compute the rent trend; the page 3 chart will be empty", "rent_trend")
    f["caption"] = M("Chart caption", "longtext")
    s.tables["monthly"] = t
    return s


def _financing(ctx: Ctx, data: ReportData) -> Section:
    sel, p = ctx.sel, ctx.period
    s = Section(key="financing", title="Financing", page=4)
    f = s.fields
    bs = sel.balance_sheet
    lines = bs.data["lines"] if bs else []
    loan = match_lines(lines, [r"^total mortgage payable", r"mortgage payable", r"notes? payable", r"loan payable", r"^total long term liabilities"], prefer_total=True)
    f["loan_amount"] = F("Loan principal", "money", loan[0]["values"].get("current") if loan else None,
                         bs.source(f"row {loan[0]['row'] + 1}", loan[0]["label"]) if loan else None)
    interest, i_src, i_note = None, None, None
    acc = match_lines(lines, [r"accrued interest"])
    if acc and acc[0]["values"].get("current"):
        interest, i_src, i_note = acc[0]["values"]["current"], bs.source(f"row {acc[0]['row'] + 1}", acc[0]["label"]), "Accrued interest at period end (one month of interest)"
    elif sel.budget:
        il = match_lines(sel.budget.data["lines"], [r"^total debt service", r"interest expense"], prefer_total=True)
        ptd = il[0]["values"].get("ptd_actual") if il else None
        if ptd is not None:
            interest, i_src = ptd / p.months, sel.budget.source(f"row {il[0]['row'] + 1}", il[0]["label"])
            i_note = f"PTD debt service / {p.months} months (approximate)"
    f["interest_monthly"] = F("Monthly interest (IO payment)", "money", interest, i_src, note=i_note)
    f["implied_rate"] = D("Implied interest rate", "percent", note="interest_monthly x 12 / loan_amount")
    reserve = match_lines(lines, [r"capital improvements? escrow", r"replacement reserve", r"escrow / reserve"])
    f["reserve_balance"] = F("Replacement reserve balance", "money", reserve[0]["values"].get("current") if reserve else None,
                             bs.source(f"row {reserve[0]['row'] + 1}", reserve[0]["label"]) if reserve else None)
    ent = sel.capital_calls or sel.distributions
    f["borrower"] = F("Borrower", "text", ent.data.get("entity") if ent else None, ent.source("entity header") if ent and ent.data.get("entity") else None)
    for key, label, kind in (
        ("lender", "Lender", "text"), ("servicer", "Servicer", "text"), ("rate", "Interest rate", "percent"), ("rate_type", "Rate type", "text"),
        ("effective_date", "Effective date", "date"), ("maturity_date", "Maturity date", "date"), ("term_months", "Loan term (months)", "integer"),
        ("io_months", "Interest-only period (months)", "integer"), ("io_end_date", "IO end date", "date"), ("amort_years", "Amortization (years)", "integer"),
        ("pi_payment", "P&I payment (monthly)", "money"), ("recourse", "Recourse", "text"), ("prepayment", "Prepayment terms", "text"),
        ("yield_maintenance_through", "Yield maintenance through", "date"), ("open_prepay_months", "Open prepayment window (months)", "integer"),
        ("replacement_reserve_monthly", "Replacement reserve (monthly)", "money"), ("repairs_escrow", "Repairs escrow (one-time)", "money"),
    ):
        f[key] = M(label, kind, note="Loan documents were not supplied; enter manually")
    f["replacement_reserve_annual"] = D("Replacement reserve (annual)", "money")
    f["narrative"] = M("Financing commentary", "longtext")
    return s


def _financials(ctx: Ctx, data: ReportData) -> Section:
    sel, p = ctx.sel, ctx.period
    s = Section(key="financials", title="Financial Performance", page=6)
    cols = [C("ptd_actual", f"{p.quarter_label} actual"), C("ptd_budget", f"{p.quarter_label} budget"), C("ptd_var", "Var $", derived=True),
            C("ptd_var_pct", "Var %", "percent", derived=True), C("ytd_actual", "YTD actual"), C("ytd_budget", "YTD budget"),
            C("ytd_var", "YTD var $", derived=True), C("ytd_var_pct", "YTD var %", "percent", derived=True), C("annual_budget", "Annual budget")]
    t = Table(title="Actual vs budget", columns=cols)
    labels = {c.key: c.label for c in cols}
    b = sel.budget
    lines = b.data["lines"] if b else []
    have = set(b.data.get("columns", [])) if b else set()
    key_map = {k: k for k in VALUE_COLS}
    if b and "ptd_actual" not in have and "mtd_actual" in have:
        key_map["ptd_actual"], key_map["ptd_budget"] = "mtd_actual", "mtd_budget"
        ctx.note("warning", "The Budget Comparison has only MTD columns; the quarter columns show one month", "financials")
    for m in load_pl_mapping(settings.config_dir):
        row = t.new_row(m["key"], label=m["label"])
        t.row_meta[m["key"]].update({"group": m["group"], "expense": bool(m.get("expense", False))})
        hits = match_lines(lines, m["match"], prefer_total=bool(m.get("total", False))) if lines else []
        if hits and not m.get("sum"):
            hits = hits[:1]
        src = b.source(f"rows {', '.join(str(h['row'] + 1) for h in hits)}", " + ".join(h["label"] for h in hits)) if hits else None
        for ck in VALUE_COLS:
            vals = [h["values"].get(key_map[ck]) for h in hits]
            val = calc.sum_or_none(vals) if hits else None
            row[ck] = F(labels[ck], "money", val, src if val is not None else None,
                        note=None if hits else "No line in the Budget Comparison matched this row")
    s.tables["lines"] = t
    s.fields["period_label"] = D("Period", "text")
    s.fields["ytd_label"] = D("YTD period", "text")
    if not b:
        ctx.note("error", "No Yardi Budget Comparison found; the financial performance table is empty", "financials")
    return s


KPI_FIELDS = [
    ("revenue_actual", "Revenue actual", "money"), ("revenue_budget", "Revenue budget", "money"), ("revenue_var", "Revenue variance", "money"),
    ("revenue_var_pct", "Revenue variance %", "percent"), ("gpr_var_pct", "GPR variance %", "percent"),
    ("gain_to_lease_actual", "Gain/loss to lease actual", "money"), ("gain_to_lease_budget", "Gain/loss to lease budget", "money"),
    ("gain_to_lease_var_pct", "Gain/loss to lease variance %", "percent"), ("concessions_var", "Concessions variance", "money"),
    ("opex_actual", "Opex actual", "money"), ("opex_budget", "Opex budget", "money"), ("opex_var", "Opex variance", "money"),
    ("opex_var_pct", "Opex variance %", "percent"), ("insurance_var", "Insurance variance", "money"), ("utilities_var", "Utilities variance", "money"),
    ("noi_actual", "NOI actual", "money"), ("noi_budget", "NOI budget", "money"), ("noi_var", "NOI variance", "money"),
    ("noi_var_pct", "NOI variance %", "percent"), ("noi_ytd_var_pct", "NOI YTD variance %", "percent"),
    ("debt_service_actual", "Debt service", "money"), ("ncf_actual", "Net cash flow actual", "money"), ("ncf_budget", "Net cash flow budget", "money"),
    ("ncf_var", "Net cash flow variance", "money"), ("ncf_var_pct", "Net cash flow variance %", "percent"),
    ("capex_actual", "Capital spend actual", "money"), ("capex_budget", "Capital spend budget", "money"), ("capex_var", "Capital spend variance", "money"),
    ("capex_ytd_actual", "Capital spend YTD actual", "money"), ("capex_ytd_budget", "Capital spend YTD budget", "money"),
    ("capex_ytd_var", "Capital spend YTD variance", "money"), ("capex_annual_budget", "Capital annual budget", "money"),
]
NARRATIVE_FIELDS = [
    ("takeaway", "Quarter takeaway"), ("revenue_body", "Revenue commentary"), ("revenue_outlook", "Revenue outlook"),
    ("opex_body", "Operating expense commentary"), ("opex_outlook", "Operating expense outlook"),
    ("noi_body", "NOI and cash flow commentary"), ("noi_outlook", "NOI outlook"),
]


def _commentary(ctx: Ctx, data: ReportData) -> Section:
    s = Section(key="commentary", title="Financial & Capital Commentary", page=5)
    for key, label, kind in KPI_FIELDS:
        s.fields[key] = D(label, kind)
    for key, label in NARRATIVE_FIELDS:
        s.fields[key] = M(label, "longtext", note="Write or draft with AI from the numbers above")
    return s


def _capex(ctx: Ctx, data: ReportData) -> Section:
    sel, p = ctx.sel, ctx.period
    s = Section(key="capex", title="Capital Projects", page=7)
    cfg = load_capex_mapping(settings.config_dir)
    sec = cfg["sections"]
    cols = [C("ptd_actual", f"{p.quarter_label} actual"), C("ptd_budget", f"{p.quarter_label} budget"), C("ptd_var", "Var $", derived=True),
            C("ytd_actual", "YTD actual"), C("ytd_budget", "YTD budget"), C("ytd_var", "YTD var $", derived=True), C("annual_budget", "Annual budget")]
    t = Table(title="Capital projects", columns=cols)
    labels = {c.key: c.label for c in cols}
    b = sel.budget
    if b:
        lines = []
        for ln in b.data["lines"]:
            if ln["is_total"] or ln["unlabeled"] or not section_matches(ln["section"], sec["include"], sec["exclude"]):
                continue
            copy = dict(ln)
            copy["_sign"] = -1 if section_matches(ln["section"], sec["negate"], []) else 1
            lines.append(copy)
        groups, leftover = consume_capex(lines, cfg.get("rows", []))
        entries = [(m["key"], m["label"], hit) for m, hit in groups if hit] + [(slug(ln["label"]), ln["label"], [ln]) for ln in leftover]
        for key, label, hit in entries:
            k, i = key, 2
            while k in t.rows:
                k, i = f"{key}-{i}", i + 1
            row = t.new_row(k, label=label)
            t.row_meta[k].update({"expense": True, "accounts": [h["code"] or h["label"] for h in hit]})
            src = b.source(f"rows {', '.join(str(h['row'] + 1) for h in hit)}", " + ".join(h["label"] for h in hit))
            for ck in VALUE_COLS:
                vals = [(h["values"][ck]) * h["_sign"] for h in hit if h["values"].get(ck) is not None]
                row[ck] = F(labels[ck], "money", sum(vals) if vals else None, src if vals else None)
        unl = [ln for ln in b.data["lines"] if ln["unlabeled"] and ln["values"].get("ptd_actual") is not None]
        if unl:
            s.fields["source_total_ptd"] = F("Source capital total (Yardi summary row)", "money", unl[-1]["values"]["ptd_actual"],
                                             b.source(f"row {unl[-1]['row'] + 1}"), note="Yardi's own capital total; used to cross-check the table")
        if not entries:
            ctx.note("warning", "No capital lines found in the Budget Comparison (no renovation / improvement sections)", "capex")
    for ck in VALUE_COLS + ("ptd_var", "ytd_var"):
        t.totals[ck] = D(labels[ck], "money")
    s.tables["lines"] = t
    s.fields["narrative"] = M("Capital commentary", "longtext")
    return s


def _submarket(ctx: Ctx, data: ReportData) -> Section:  # noqa: C901
    sel, p = ctx.sel, ctx.period
    s = Section(key="submarket", title="Submarket Comparison", page=8)
    f = s.fields
    cx, cp = sel.costar_excel, sel.costar_pdf
    cur = prior = None
    if cx:
        series = cx.data.get("series", [])
        cur = next((r for r in series if r["year"] == p.year and r["quarter"] == p.quarter and not r["flag"]), None)
        pq = (p.year, p.quarter - 1) if p.quarter > 1 else (p.year - 1, 4)
        prior = next((r for r in series if (r["year"], r["quarter"]) == pq and not r["flag"]), None)
        if cur is None:
            ctx.note("warning", f"The CoStar table has no row for {p.year} Q{p.quarter}", "submarket")

    def cs(key: str, label: str, kind: str, rec: dict | None) -> Field:
        val = rec.get(key) if rec else None
        return F(label, kind, val, cx.source(f"row {rec['row'] + 1}", rec["period"]) if rec and val is not None else None)

    f["vacancy"] = cs("vacancy", "Submarket vacancy", "percent", cur)
    f["prior_vacancy"] = cs("vacancy", "Prior quarter vacancy", "percent", prior)
    f["rent_growth_yoy"] = cs("rent_growth", "YoY asking rent growth", "percent", cur)
    f["prior_rent_growth"] = cs("rent_growth", "Prior quarter YoY rent growth", "percent", prior)
    f["avg_asking_rent"] = cs("asking_rent", "Average market asking rent", "money", cur)
    f["under_construction"] = cs("under_construction", "Units under construction", "integer", cur)
    f["uc_pct"] = cs("uc_pct", "Under construction % of inventory", "percent", cur)
    f["inventory"] = cs("inventory", "Submarket inventory (units)", "integer", cur)
    if cp:
        ks = cp.data.get("key_stats") or {}
        for key, ks_key, label, kind in (("vacancy", "vacancy", "Submarket vacancy", "percent"), ("avg_asking_rent", "asking_rent", "Average market asking rent", "money"),
                                         ("under_construction", "under_construction", "Units under construction", "integer"), ("inventory", "inventory", "Submarket inventory (units)", "integer")):
            if f[key].value is None and ks.get(ks_key) is not None:
                f[key] = F(label, kind, ks[ks_key], cp.source("key indicators"), note="From the CoStar PDF key indicators (report date, not quarter end)")
        f["submarket_name"] = F("Submarket", "text", cp.data.get("submarket"), cp.source("page 1"))
        f["market_name"] = F("Market", "text", cp.data.get("market"), cp.source("page 1"))
        dl = cp.data.get("deliveries", [])
        f["recent_deliveries"] = F("Recent deliveries", "text", "; ".join(f"{d['name']} ({d['units']} units, {d['complete']})" for d in dl) or None,
                                   cp.source("recent deliveries") if dl else None)
    else:
        f["submarket_name"], f["market_name"], f["recent_deliveries"] = M("Submarket", "text"), M("Market", "text"), M("Recent deliveries", "text")
    f["pipeline_note"] = D("Pipeline caption", "text")
    f["data_quarter"] = D("CoStar data quarter", "text")
    f["source_note"] = D("Source note", "text")
    f["footnote"] = D("Comp table footnote", "text")
    t = Table(title="Comp set", columns=[
        C("name", "Property", "text"), C("units", "Units", "integer"), C("vintage", "Vintage", "integer"), C("leased_pct", "Leased %", "percent"),
        C("asking_rent", "Asking rent"), C("effective_rent", "Effective rent (NER)"), C("concession", "Concession $/mo", derived=True),
        C("concession_pct", "Concession %", "percent", derived=True)], editable_rows=True)
    cur_rr = _at_or_before(sel.rent_rolls, p.end)
    li = sel.listings
    if li:
        props = li.data.get("properties", {})
        subject = next((n for n in props if names_match(n, ctx.property_name)), None) if ctx.property_name else None
        order = ([subject] if subject else []) + sorted((n for n in props if n != subject),
                                                        key=lambda n: -(props[n]["asking_sum"] / props[n]["asking_n"] if props[n]["asking_n"] else 0))
        for name in order:
            pr = props[name]
            key = slug(name)
            row = t.new_row(key, label=name)
            is_subject = name == subject
            t.row_meta[key]["subject"] = is_subject
            src = li.source(f"rows from {pr['first_row'] + 1}", f"{pr['rows']} listings")
            row["name"] = F("Property", "text", name, src)
            meta = _comp_meta(sel, name)
            row["units"] = F("Units", "integer", meta.get("units") if meta else None, meta["_src"] if meta and meta.get("units") else None,
                             note=None if meta and meta.get("units") else "Unit count is not in the listings export; supply a HelloData comp summary or enter it")
            row["vintage"] = F("Vintage", "integer", meta.get("year_built") if meta else None, meta["_src"] if meta and meta.get("year_built") else None,
                               note=None if meta and meta.get("year_built") else "Year built is not in the listings export; enter it")
            row["asking_rent"] = F("Asking rent", "money", calc.ratio(pr["asking_sum"], pr["asking_n"]), src, note="Mean asking rent across all listing rows")
            row["effective_rent"] = F("Effective rent (NER)", "money", calc.ratio(pr["effective_sum"], pr["effective_n"]), src, note="Mean effective rent across all listing rows")
            if is_subject and cur_rr and cur_rr.data.get("occupancy_pct") is not None:
                row["leased_pct"] = F("Leased %", "percent", cur_rr.data["occupancy_pct"], cur_rr.source("summary block"), note="Physical occupancy per the Yardi rent roll")
            else:
                row["leased_pct"] = F("Leased %", "percent", calc.ratio(pr["leased"], pr["rows"]), src, note="Leased listings / all listings")
    else:
        for src in sel.comps:
            for c in src.data.get("comps", []):
                if c.get("avg_rent") is None:
                    continue
                key = slug(c["name"])
                if key in t.rows:
                    continue
                row = t.new_row(key, label=c["name"])
                t.row_meta[key]["subject"] = names_match(c["name"], ctx.property_name)
                loc = src.source(f"page {c.get('page', '')}".strip(), c["name"])
                row["name"] = F("Property", "text", c["name"], loc)
                row["units"] = F("Units", "integer", c.get("units"), loc if c.get("units") else None)
                row["vintage"] = F("Vintage", "integer", c.get("year_built"), loc if c.get("year_built") else None)
                row["asking_rent"] = F("Asking rent", "money", c.get("avg_rent"), loc)
                row["effective_rent"] = F("Effective rent (NER)", "money", c.get("ner"), loc)
                lc, ac = c.get("leased_count"), c.get("active_count")
                row["leased_pct"] = F("Leased %", "percent", calc.ratio(lc, (lc or 0) + (ac or 0)) if lc is not None else c.get("leased_pct"), loc)
        if not t.rows:
            ctx.note("warning", "No HelloData listings export or comp summary found; the comp table is empty (add rows manually)", "submarket")
    t.totals["name"] = F("Property", "text", "Comp set average", status="derived")
    for ck, label, kind in (("units", "Units", "integer"), ("vintage", "Vintage", "integer"), ("leased_pct", "Leased %", "percent"),
                            ("asking_rent", "Asking rent", "money"), ("effective_rent", "Effective rent (NER)", "money"),
                            ("concession", "Concession $/mo", "money"), ("concession_pct", "Concession %", "percent")):
        t.totals[ck] = D(label, kind)
    s.tables["comps"] = t
    for key, label in (("occupancy_narrative", "Occupancy commentary"), ("rent_narrative", "Effective rent commentary"), ("concession_narrative", "Concessions commentary")):
        f[key] = M(label, "longtext")
    if not cx and not cp:
        ctx.note("warning", "No CoStar submarket data found; vacancy, rent growth and pipeline are missing", "submarket")
    return s


def _occupancy(ctx: Ctx, data: ReportData) -> Section:
    sel, p = ctx.sel, ctx.period
    s = Section(key="occupancy", title="Occupancy & Leasing", page=9)
    f = s.fields
    cur = _at_or_before(sel.rent_rolls, p.end)
    prior = _before(sel.rent_rolls, cur.data["as_of"]) if cur and cur.data.get("as_of") else None

    def rr(rec: Src | None, key: str, label: str, kind: str) -> Field:
        val = rec.data.get(key) if rec else None
        return F(label, kind, val, rec.source("summary block") if rec and val is not None else None)

    f["current_date"] = F("Current as-of date", "date", cur.data.get("as_of") if cur else None, cur.source("header") if cur and cur.data.get("as_of") else None)
    f["current_pct"] = rr(cur, "occupancy_pct", "Occupancy (current)", "percent")
    f["current_occupied"] = rr(cur, "occupied_units", "Occupied units (current)", "integer")
    f["total_units"] = rr(cur, "total_units", "Total units", "integer")
    f["future_applicants"] = rr(cur, "future_applicants", "Future residents / applicants", "integer")
    f["prior_date"] = F("Prior as-of date", "date", prior.data.get("as_of") if prior else None, prior.source("header") if prior and prior.data.get("as_of") else None)
    f["prior_pct"] = rr(prior, "occupancy_pct", "Occupancy (prior)", "percent")
    f["prior_occupied"] = rr(prior, "occupied_units", "Occupied units (prior)", "integer")
    f["change_bps"] = D("Occupancy change (bps)", "number")
    if not cur:
        ctx.note("error", "No rent roll found; occupancy is missing", "occupancy")
    else:
        if cur.data.get("as_of") and cur.data["as_of"] != p.end.isoformat():
            ctx.note("warning", f"The latest rent roll is dated {cur.data['as_of']}, not the period end {p.end.isoformat()}", "occupancy.fields.current_date")
        if not prior:
            ctx.note("warning", "Only one rent roll found; prior-quarter occupancy is missing", "occupancy.fields.prior_pct")
    lto = sel.lto
    for tkey, skey, title in (("new_leases", "move_ins", "New leases by floor plan"), ("renewals", "renewals", "Renewals by floor plan")):
        t = Table(title=title, columns=[
            C("floor_plan", "Floor plan", "text"), C("sqft", "SF", "integer"), C("count", "Count", "integer"), C("avg_prior", "Avg prior rent"),
            C("avg_current", "Avg current rent"), C("lto", "$ trade-out", derived=True), C("lto_pct", "% trade-out", "percent", derived=True)])
        rows = lto.data.get("sections", {}).get(skey, {}).get("rows", []) if lto else []
        groups: dict[str, list[dict]] = {}
        for r in rows:
            groups.setdefault(r["unit_type"], []).append(r)
        for ut, rs in sorted(groups.items(), key=lambda kv: (kv[1][0].get("sqft") or 0, kv[0])):
            key = slug(ut)
            row = t.new_row(key, label=ut)
            src = lto.source(f"rows {rs[0]['row'] + 1}-{rs[-1]['row'] + 1}", ut)
            row["floor_plan"] = F("Floor plan", "text", ut, src)
            row["sqft"] = F("SF", "integer", rs[0].get("sqft"), src)
            row["count"] = F("Count", "integer", len(rs), src)
            row["avg_prior"] = F("Avg prior rent", "money", calc.mean(r.get("prev_lease_rent") for r in rs), src)
            row["avg_current"] = F("Avg current rent", "money", calc.mean(r.get("lease_rent") for r in rs), src)
        t.totals["floor_plan"] = F("Floor plan", "text", "Total", status="derived")
        for ck, label, kind in (("count", "Count", "integer"), ("avg_prior", "Avg prior rent", "money"), ("avg_current", "Avg current rent", "money"),
                                ("lto", "$ trade-out", "money"), ("lto_pct", "% trade-out", "percent")):
            t.totals[ck] = D(label, kind)
        s.tables[tkey] = t
    f["new_lease_count"] = D("New leases executed", "integer")
    f["renewal_count"] = D("Renewals executed", "integer")
    f["new_lease_lto_pct"] = D("New lease trade-out %", "percent")
    f["renewal_lto_pct"] = D("Renewal trade-out %", "percent")
    lp = (lto.data.get("period") or {}) if lto else {}
    f["lto_period_note"] = F("Trade-out period note", "text",
                             f"LTO reflects leases of all terms with a renewal commencement or new lease start date within {p.quarter_label} "
                             f"({lp.get('start', p.start.isoformat())} to {lp.get('end', p.end.isoformat())}). Source: Yardi Lease Trade-Out report." if lto else None,
                             lto.source("section headers") if lto else None)
    if not lto:
        ctx.note("warning", "No Lease Trade-Out report found; new-lease and renewal tables are empty", "occupancy")
    elif lp.get("end") and lp["end"] != p.end.isoformat():
        ctx.note("warning", f"The Lease Trade-Out report covers {lp.get('start')} to {lp.get('end')}, which is not the reporting period", "occupancy")
    for key, label in (("occupancy_narrative", "Occupancy commentary"), ("new_lease_narrative", "New lease commentary"), ("renewal_narrative", "Renewal commentary")):
        f[key] = M(label, "longtext")
    return s


def _status(ctx: Ctx, data: ReportData) -> Section:
    sel, p = ctx.sel, ctx.period
    s = Section(key="status", title="Status Update & Next Quarter Goals", page=10)
    f = s.fields
    b = sel.budget
    lines = b.data["lines"] if b else []
    col = match_lines(lines, [r"former resident collections", r"collections? recover", r"bad debt recover", r"^collections"])
    wo = match_lines(lines, [r"write.?off bad debt", r"bad debt write", r"^bad debt"])
    f["collections_recovered"] = F(f"{p.quarter_label} collections recovered", "money", col[0]["values"].get("ptd_actual") if col else None,
                                   b.source(f"row {col[0]['row'] + 1}", col[0]["label"]) if col else None)
    f["bad_debt_writeoff"] = F(f"{p.quarter_label} bad debt write-offs", "money", wo[0]["values"].get("ptd_actual") if wo else None,
                               b.source(f"row {wo[0]['row'] + 1}", wo[0]["label"]) if wo else None)
    f["next_quarter_label"] = D("Next quarter", "text")
    for i in (1, 2, 3):
        f[f"status{i}_title"] = M(f"Status item {i}: title", "text")
        f[f"status{i}_subtitle"] = M(f"Status item {i}: headline", "text")
        f[f"status{i}_body"] = M(f"Status item {i}: body", "longtext")
    for i in (1, 2, 3):
        f[f"goal{i}_title"] = M(f"Goal {i}: title", "text")
        f[f"goal{i}_subtitle"] = M(f"Goal {i}: headline", "text")
        f[f"goal{i}_body"] = M(f"Goal {i}: body", "longtext")
    return s


SECTION_BUILDERS = (_property, _in_place_rent, _capital, _underwriting, _rent_trend, _financing, _financials, _commentary, _capex, _submarket, _occupancy, _status)


def build(project: dict, files: list[dict]) -> tuple[ReportData, list[dict]]:
    """Consolidate processed files into ReportData. Returns (data, notes) where notes are selection/period issues."""
    sel = select(collect(files))
    period, period_notes = _period(sel)
    ctx = Ctx(sel=sel, period=period, notes=list(sel.notes) + period_notes)
    data = ReportData(meta={
        "project_id": project.get("id"), "project_name": project.get("name"),
        "period": {"start": period.start.isoformat(), "end": period.end.isoformat(), "quarter_label": period.quarter_label},
        "sources": _sources_used(sel),
    })
    for fn in SECTION_BUILDERS:
        sec = fn(ctx, data)
        data.sections[sec.key] = sec
    data.meta["property_name"] = ctx.property_name
    calc.recompute(data)
    return data, ctx.notes


def apply_overrides(data: ReportData, overrides: dict) -> list[str]:
    """Apply AI drafts, manual rows, row deletions and field overrides. Returns paths that no longer exist."""
    stale: list[str] = []
    for path, text in (overrides.get("ai_drafts") or {}).items():
        f = data.field(path)
        if f is None:
            stale.append(path)
            continue
        if f.value in (None, "") or f.status in ("missing", "ai_draft"):
            f.value, f.status = text, "ai_draft"
            f.source = Source(text="Drafted by AI from the section's structured data; review before publishing")
    for tpath, rows in (overrides.get("rows") or {}).items():
        t = data.table(tpath)
        if t is None:
            stale.append(tpath)
            continue
        for rkey, cells in rows.items():
            label = next((str(v) for v in cells.values() if isinstance(v, str) and v), rkey)
            row = t.rows.get(rkey) or t.new_row(rkey, label=label, manual=True)
            t.row_meta.setdefault(rkey, {})["manual"] = True
            for ckey, val in cells.items():
                if ckey in row and row[ckey].status != "derived":
                    row[ckey].value, row[ckey].status = val, "manual"
    for tpath, keys in (overrides.get("deleted_rows") or {}).items():
        t = data.table(tpath)
        if t is None:
            continue
        for k in keys:
            t.rows.pop(k, None)
            t.row_meta.pop(k, None)
    for path, val in (overrides.get("fields") or {}).items():
        f = data.field(path)
        if f is None:
            stale.append(path)
            continue
        f.override = val
    return stale
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_builder.py -v`
Expected: 3 PASS. If `test_build_end_to_end` fails on a single value, print `data.field(path)` for that path: the `source.locator` tells you which line was matched.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: builder consolidating extractions into ReportData with overrides"
```

---

### Task 19: Validation

**Files:**
- Create: `backend/app/consolidate/validate.py`, `backend/tests/test_validate.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_validate.py
from app.consolidate.builder import build
from app.consolidate.calc import recompute
from app.consolidate.validate import run, summary
from tests.test_builder import sample_files


def test_validate_reports_conflicts_missing_and_file_problems():
    data, notes = build({"id": "p", "name": "P"}, sample_files())
    files = [{"original_filename": "bad.docx", "status": "unsupported", "error": "Unsupported file type '.docx'", "parts": []},
             {"original_filename": "odd.xlsx", "status": "processed", "parts": [{"doc_type": "unknown", "locator": "sheet 'S'", "warnings": []}]},
             {"original_filename": "warn.xlsx", "status": "processed", "parts": [{"doc_type": "yardi_rent_roll", "locator": "sheet 'R'", "warnings": ["'As Of' date not found"]}]}]
    issues = run(data, notes, files)
    msgs = [i.message for i in issues]
    assert any(i.path == "capital.fields.purchase_price" and i.severity == "warning" and "sources disagree" in i.message for i in issues)
    assert any(i.path == "financing.fields.lender" and i.message == "Missing: Lender" for i in issues)
    assert any(m.startswith("bad.docx") for m in msgs) and any("odd.xlsx" in m and "not used" in m for m in msgs)
    assert any("warn.xlsx (sheet 'R'): 'As Of' date not found" == m for m in msgs)
    assert not any("does not equal" in m for m in msgs)
    s = summary(data, issues)
    assert s["conflicts"] == 1 and s["missing"] > 10 and s["errors"] == 0 and s["warnings"] > 0


def test_validate_reconciliation_warnings_after_edit():
    data, notes = build({"id": "p", "name": "P"}, sample_files())
    data.field("financials.tables.lines.rows.total_revenue.ptd_actual").override = 2000
    data.field("occupancy.fields.current_occupied").override = 200
    recompute(data)
    issues = run(data, notes, [])
    assert any(i.path == "financials.tables.lines.rows.total_revenue.ptd_actual" and "does not equal the sum" in i.message for i in issues)
    assert any(i.path == "financials.tables.lines.rows.noi.ptd_actual" and "revenue minus opex" in i.message for i in issues)
    assert any(i.path == "occupancy.fields.current_pct" and "occupied / total" in i.message for i in issues)


def test_required_fields_are_errors_when_missing():
    data, notes = build({"id": "p", "name": "P"}, sample_files()[:1])
    issues = run(data, notes, [])
    assert any(i.path == "property.fields.units" and i.severity == "error" for i in issues)
    assert any(i.path == "occupancy.fields.current_pct" and i.severity == "error" for i in issues)
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_validate.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `backend/app/consolidate/validate.py`**

```python
"""Completeness and consistency checks over the effective (override-applied, recomputed) ReportData."""
from __future__ import annotations

from ..models import Issue, ReportData

REQUIRED: dict[str, str] = {
    "property.fields.name": "error",
    "property.fields.units": "error",
    "financials.tables.lines.rows.total_revenue.ptd_actual": "error",
    "financials.tables.lines.rows.total_opex.ptd_actual": "error",
    "financials.tables.lines.rows.noi.ptd_actual": "error",
    "occupancy.fields.current_pct": "error",
    "capital.fields.purchase_price": "warning",
    "capital.fields.equity_invested": "warning",
    "financing.fields.loan_amount": "warning",
    "submarket.fields.vacancy": "warning",
    "property.fields.year_built": "warning",
    "property.fields.acquired_date": "warning",
}
TOLERANCE = 2.0
FIN = "financials.tables.lines.rows"
OPEX_ROWS = ("payroll", "g_and_a", "marketing", "r_and_m", "utilities", "management_fees", "property_taxes", "insurance")
REVENUE_ROWS = ("net_rental_income", "utility_income", "other_income")


def _fmt(v) -> str:
    return f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)


def _sum(data: ReportData, paths: list[str]) -> float | None:
    vals = [data.value(p) for p in paths]
    present = [v for v in vals if v is not None]
    return sum(present) if present else None


def _file_issues(files: list[dict]) -> list[Issue]:
    out: list[Issue] = []
    for f in files:
        name = f.get("original_filename", "?")
        status = f.get("status")
        if status in ("failed", "unsupported"):
            out.append(Issue(severity="warning", message=f"{name}: {f.get('error') or status}"))
        elif status == "processed" and f.get("parts") and all(p.get("doc_type") == "unknown" for p in f["parts"]):
            out.append(Issue(severity="info", message=f"{name}: no recognised report found; the file is not used"))
        for p in f.get("parts") or []:
            for w in p.get("warnings") or []:
                out.append(Issue(severity="warning", message=f"{name} ({p.get('locator')}): {w}"))
    return out


def _field_issues(data: ReportData) -> list[Issue]:
    out: list[Issue] = []
    for path, fld in data.iter_fields():
        if fld.status == "conflict" and fld.override is None:
            alts = ", ".join(_fmt(a.value) for a in fld.alternatives)
            out.append(Issue(path=path, severity="warning", message=f"{fld.label}: sources disagree (using {_fmt(fld.value)}; alternatives: {alts})"))
        elif fld.effective in (None, "") and fld.status in ("missing", "extracted"):
            if path in REQUIRED:
                out.append(Issue(path=path, severity=REQUIRED[path], message=f"Missing: {fld.label}"))
            elif fld.kind == "longtext":
                out.append(Issue(path=path, severity="info", message=f"Narrative not written: {fld.label}"))
            else:
                out.append(Issue(path=path, severity="warning" if ".fields." in path else "info", message=f"Missing: {fld.label}"))
    return out


def _reconciliation_issues(data: ReportData) -> list[Issue]:
    out: list[Issue] = []
    v = data.value
    for total_key, parts, label in (("total_revenue", REVENUE_ROWS, "Total revenue"), ("total_opex", OPEX_ROWS, "Total operating expenses")):
        for col in ("ptd_actual", "ytd_actual"):
            total, s = v(f"{FIN}.{total_key}.{col}"), _sum(data, [f"{FIN}.{k}.{col}" for k in parts])
            if total is not None and s is not None and abs(total - s) > TOLERANCE:
                out.append(Issue(path=f"{FIN}.{total_key}.{col}", severity="warning",
                                 message=f"{label} ({col}) {_fmt(total)} does not equal the sum of its lines {_fmt(s)}"))
    for col in ("ptd_actual", "ytd_actual"):
        rev, opex, noi = v(f"{FIN}.total_revenue.{col}"), v(f"{FIN}.total_opex.{col}"), v(f"{FIN}.noi.{col}")
        if None not in (rev, opex, noi) and abs(rev - opex - noi) > TOLERANCE:
            out.append(Issue(path=f"{FIN}.noi.{col}", severity="warning", message=f"NOI ({col}) {_fmt(noi)} does not equal revenue minus opex {_fmt(rev - opex)}"))
        ds, ncf = v(f"{FIN}.debt_service.{col}"), v(f"{FIN}.net_cash_flow.{col}")
        if None not in (noi, ds, ncf) and abs(noi - ds - ncf) > TOLERANCE:
            out.append(Issue(path=f"{FIN}.net_cash_flow.{col}", severity="warning",
                             message=f"Net cash flow ({col}) {_fmt(ncf)} does not equal NOI minus debt service {_fmt(noi - ds)}"))
    occ, tot, pct = v("occupancy.fields.current_occupied"), v("occupancy.fields.total_units"), v("occupancy.fields.current_pct")
    if None not in (occ, tot, pct) and tot and abs(occ / tot - pct) > 0.001:
        out.append(Issue(path="occupancy.fields.current_pct", severity="warning",
                         message=f"Occupancy {pct * 100:.2f}% does not match occupied / total units ({occ:,.0f} / {tot:,.0f} = {occ / tot * 100:.2f}%)"))
    cap, src = v("capex.tables.lines.totals.ptd_actual"), v("capex.fields.source_total_ptd")
    if None not in (cap, src) and abs(cap - src) > TOLERANCE:
        out.append(Issue(path="capex.tables.lines.totals.ptd_actual", severity="warning",
                         message=f"Capital table total {_fmt(cap)} differs from Yardi's summary total {_fmt(src)}; check the sections in capex_mapping.toml"))
    return out


def run(data: ReportData, notes: list[dict], files: list[dict]) -> list[Issue]:
    issues = [Issue(path=n.get("path"), severity=n.get("severity", "info"), message=n["message"]) for n in notes]
    issues += _file_issues(files)
    issues += _field_issues(data)
    issues += _reconciliation_issues(data)
    order = {"error": 0, "warning": 1, "info": 2}
    return sorted(issues, key=lambda i: order[i.severity])


def summary(data: ReportData, issues: list[Issue]) -> dict:
    missing = conflicts = drafts = 0
    for _, fld in data.iter_fields():
        if fld.status == "conflict" and fld.override is None:
            conflicts += 1
        elif fld.status == "ai_draft" and fld.override is None:
            drafts += 1
        elif fld.effective in (None, "") and fld.status in ("missing", "extracted"):
            missing += 1
    return {"missing": missing, "conflicts": conflicts, "ai_drafts": drafts,
            "errors": sum(i.severity == "error" for i in issues), "warnings": sum(i.severity == "warning" for i in issues),
            "infos": sum(i.severity == "info" for i in issues)}
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_validate.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: validation of missing, conflicting and non-reconciling values"
```

---

### Task 20: Worker pool and jobs

Processing runs in an in-process thread pool: each file is one isolated job, a failure marks only that file, and consolidation runs automatically when the last file of a project finishes. Report rendering and AI drafting are jobs too (added in Tasks 25 and 26).

**Files:**
- Create: `backend/app/workers/__init__.py` (empty), `backend/app/workers/pool.py`, `backend/app/workers/jobs.py`, `backend/tests/test_workers.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_workers.py
import time

from app import db
from app.classify.classifier import DocType
from app.workers import jobs
from app.workers.pool import Pool
from tests.helpers import BUDGET_ROWS, LTO_ROWS, make_xlsx, rent_roll_rows


def setup_module(module):
    db.init_db()


def test_pool_runs_jobs_once_per_key_and_reports_idle():
    pool = Pool(workers=2)
    seen = []
    assert pool.submit("k1", lambda: seen.append(1)) is True
    assert pool.submit("k2", lambda: (time.sleep(0.2), seen.append(2))) is True
    assert pool.submit("k2", lambda: seen.append(3)) is False  # already running
    assert pool.wait_idle(5) and sorted(seen) == [1, 2]
    pool.submit("boom", lambda: 1 / 0)  # exceptions are logged, never raised
    assert pool.wait_idle(5)
    pool.shutdown()


def test_process_file_extracts_and_builds_report_data(tmp_path):
    p = db.create_project("W")
    good = make_xlsx(tmp_path / "fin.xlsx", {"Report1": BUDGET_ROWS, "RR": rent_roll_rows("06/30/2026", 306, 338, 90.53, 14), "LTO": LTO_ROWS})
    fid = db.new_id()
    db.add_file(p["id"], fid, "fin.xlsx", str(good), ".xlsx", good.stat().st_size)
    jobs.process_file(fid)
    f = db.get_file(fid)
    assert f["status"] == "processed" and f["error"] is None
    assert [x["doc_type"] for x in f["parts"]] == [DocType.YARDI_BUDGET_COMPARISON, DocType.YARDI_RENT_ROLL, DocType.YARDI_LEASE_TRADE_OUT]
    assert len(f["extractions"]) == 3 and f["processed_at"]
    rd = db.get_report_data(p["id"])
    assert rd["built_at"] and rd["data"]["sections"]["property"]["fields"]["units"]["value"] == 338
    data, issues, row = jobs.load_effective(p["id"])
    assert data.value("financials.tables.lines.rows.noi.ptd_actual") == 550 and any(i.severity == "warning" for i in issues)


def test_process_file_failure_modes(tmp_path):
    p = db.create_project("W2")
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not a workbook")
    fid = db.new_id()
    db.add_file(p["id"], fid, "bad.xlsx", str(bad), ".xlsx", 14)
    jobs.process_file(fid)
    assert db.get_file(fid)["status"] == "failed" and "Could not read" in db.get_file(fid)["error"]
    odd = make_xlsx(tmp_path / "odd.xlsx", {"S": [["hello"], ["world", 1]]})
    fid2 = db.new_id()
    db.add_file(p["id"], fid2, "odd.xlsx", str(odd), ".xlsx", odd.stat().st_size)
    jobs.process_file(fid2)
    f2 = db.get_file(fid2)
    assert f2["status"] == "processed" and f2["parts"][0]["doc_type"] == "unknown" and "No recognised report" in f2["error"]
    assert db.get_report_data(p["id"])["built_at"]  # consolidation still ran, with errors flagged


def test_override_doc_type_and_recover_stuck(tmp_path):
    p = db.create_project("W3")
    path = make_xlsx(tmp_path / "x.xlsx", {"Sheet": rent_roll_rows("03/31/2026", 310, 338, 91.71, 34)})
    fid = db.new_id()
    db.add_file(p["id"], fid, "x.xlsx", str(path), ".xlsx", 10)
    db.update_file(fid, doc_type_override=DocType.YARDI_LEASE_TRADE_OUT, status="processing")
    jobs.recover_stuck_files()
    assert jobs.pool.wait_idle(10)
    f = db.get_file(fid)
    assert f["status"] == "failed" and f["parts"][0]["doc_type"] == DocType.YARDI_LEASE_TRADE_OUT
    assert f["parts"][0]["warnings"] and "Extraction failed" in f["parts"][0]["warnings"][0]
    assert "extraction failed for every part" in f["error"]
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_workers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.workers'`

- [ ] **Step 3: Write `backend/app/workers/pool.py`**

```python
"""A small in-process job runner: a ThreadPoolExecutor keyed by job id so the same job is never queued twice.

# ponytail: in-process threads are enough for a single-user desktop tool; swap for RQ/Celery if
# processing ever needs to survive restarts or run on more than one machine.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

from ..config import settings

log = logging.getLogger(__name__)


class Pool:
    def __init__(self, workers: int) -> None:
        self._ex = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="job")
        self._running: dict[str, Future] = {}
        self._lock = threading.Lock()

    def submit(self, key: str, fn: Callable, *args) -> bool:
        """Queue fn(*args) under `key`. Returns False if a job with that key is still running."""
        with self._lock:
            fut = self._running.get(key)
            if fut is not None and not fut.done():
                return False
            self._running[key] = self._ex.submit(self._run, key, fn, *args)
            return True

    def _run(self, key: str, fn: Callable, *args) -> None:
        try:
            fn(*args)
        except Exception:  # noqa: BLE001 - a job must never take the pool down
            log.exception("job %s failed", key)
        finally:
            with self._lock:
                self._running.pop(key, None)

    def is_running(self, key: str) -> bool:
        with self._lock:
            fut = self._running.get(key)
            return fut is not None and not fut.done()

    def running_keys(self) -> list[str]:
        with self._lock:
            return [k for k, f in self._running.items() if not f.done()]

    def wait_idle(self, timeout: float = 30) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.running_keys():
                return True
            time.sleep(0.05)
        return False

    def shutdown(self) -> None:
        self._ex.shutdown(wait=False, cancel_futures=True)


pool = Pool(settings.workers)
```

- [ ] **Step 4: Write `backend/app/workers/jobs.py`**

```python
"""Job functions: process one file, consolidate a project, load the effective report data.

Report rendering (generate_report) is added in Task 25 and AI drafting (draft_narratives) in Task 26.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .. import db
from ..classify.classifier import DocType, classify
from ..consolidate import validate
from ..consolidate.builder import apply_overrides, build
from ..consolidate.calc import recompute
from ..extract.registry import run_extractor
from ..models import Issue, ReportData
from ..readers.registry import UnsupportedFileType, read_document
from .pool import pool

log = logging.getLogger(__name__)
ACTIVE = ("queued", "processing")


def process_file(file_id: str) -> None:
    f = db.get_file(file_id)
    if f is None:
        return
    project_id = f["project_id"]
    db.update_file(file_id, status="processing", error=None)
    try:
        doc = read_document(Path(f["stored_path"]), file_id, f["original_filename"])
    except UnsupportedFileType as e:
        db.update_file(file_id, status="unsupported", error=str(e), processed_at=db.now())
        rebuild_if_idle(project_id)
        return
    except Exception as e:  # noqa: BLE001 - corrupt or unreadable file
        log.exception("read failed for %s", f["original_filename"])
        db.update_file(file_id, status="failed", error=f"Could not read file: {e}", processed_at=db.now())
        rebuild_if_idle(project_id)
        return
    parts = classify(doc)
    if f.get("doc_type_override") and len(parts) == 1:
        parts[0].doc_type, parts[0].confidence = f["doc_type_override"], 1.0
    extractions, parts_json = [], []
    for part in parts:
        pj = {**part.to_json(), "warnings": []}
        if part.doc_type != DocType.UNKNOWN.value:
            try:
                ex = run_extractor(part)
                extractions.append(ex.model_dump())
                pj["warnings"] = list(ex.warnings)
            except Exception as e:  # noqa: BLE001 - one part failing must not fail the file
                log.warning("extraction failed for %s %s: %s", f["original_filename"], part.locator, e)
                pj["warnings"] = [f"Extraction failed: {e}"]
        parts_json.append(pj)
    recognised = [p for p in parts_json if p["doc_type"] != DocType.UNKNOWN.value]
    if not recognised:
        error = "No recognised report found in this file; it is not used. Set the document type manually if it should be."
    elif not extractions:
        error = "Recognised, but extraction failed for every part: " + "; ".join(w for p in parts_json for w in p["warnings"])
    else:
        error = None
    db.update_file(file_id, status="processed" if extractions or not recognised else "failed", error=error,
                   parts=parts_json, extractions=extractions, processed_at=db.now())
    rebuild_if_idle(project_id)


def rebuild_if_idle(project_id: str) -> None:
    if any(x["status"] in ACTIVE for x in db.list_files(project_id)):
        return
    build_report_data(project_id)


def build_report_data(project_id: str) -> ReportData:
    project = db.get_project(project_id)
    if project is None:
        raise KeyError(project_id)
    files = db.list_files(project_id)
    data, notes = build(project, files)
    db.save_report_data(project_id, data.model_dump(), notes)
    return data


def load_effective(project_id: str) -> tuple[ReportData, list[Issue], dict]:
    """Base data + overrides + recompute + validation. Cheap enough to run on every read."""
    row = db.get_report_data(project_id)
    if row is None or not row.get("data"):
        raise LookupError("Report data has not been built yet; upload and process files first")
    data = ReportData.model_validate(row["data"])
    stale = apply_overrides(data, row.get("overrides") or {})
    recompute(data)
    issues = validate.run(data, row.get("notes") or [], db.list_files(project_id))
    issues += [Issue(path=p, severity="info", message=f"An earlier edit to '{p}' no longer applies (the row or field disappeared after re-processing)") for p in stale]
    db.save_issues(project_id, [i.model_dump() for i in issues])
    return data, issues, row


def recover_stuck_files() -> None:
    """On startup, re-queue files that were mid-flight when the server last stopped."""
    for p in db.list_projects():
        for f in db.list_files(p["id"]):
            if f["status"] in ACTIVE:
                db.update_file(f["id"], status="queued")
                pool.submit(f"file:{f['id']}", process_file, f["id"])
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_workers.py -v`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: in-process worker pool with per-file processing and auto-consolidation"
```

---

### Task 21: API for projects and files, application wiring

**Files:**
- Create: `backend/app/api/__init__.py` (empty), `backend/app/api/serialize.py`, `backend/app/api/projects.py`, `backend/app/api/files.py`, `backend/tests/test_api_files.py`
- Modify: `backend/app/main.py` (replace whole file)

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_api_files.py
from fastapi.testclient import TestClient

from app.main import app
from app.workers.pool import pool
from tests.helpers import BUDGET_ROWS, LTO_ROWS, make_xlsx, rent_roll_rows


def test_project_and_file_lifecycle(tmp_path):
    xlsx = make_xlsx(tmp_path / "fin.xlsx", {"Report1": BUDGET_ROWS, "RR": rent_roll_rows("06/30/2026", 306, 338, 90.53, 14), "LTO": LTO_ROWS})
    with TestClient(app) as client:
        assert client.get("/api/doc-types").json()[0]["key"] == "yardi_budget_comparison"
        p = client.post("/api/projects", json={"name": "  Boardwalk 2Q26 "}).json()
        assert p["name"] == "Boardwalk 2Q26" and client.get("/api/projects").json()[0]["id"] == p["id"]
        assert client.get(f"/api/projects/{p['id']}").json()["stage"] == "upload"
        with xlsx.open("rb") as fh:
            r = client.post(f"/api/projects/{p['id']}/files", files=[("files", ("fin.xlsx", fh, "application/octet-stream")),
                                                                     ("files", ("notes.docx", b"hello", "application/octet-stream"))])
        assert r.status_code == 201
        recs = r.json()
        assert recs[0]["status"] in ("queued", "processing", "processed") and recs[1]["status"] == "unsupported"
        assert "extractions" not in recs[0]
        assert pool.wait_idle(20)
        detail = client.get(f"/api/projects/{p['id']}").json()
        assert detail["stage"] == "review" and detail["report_built"] is True
        good = next(f for f in detail["files"] if f["original_filename"] == "fin.xlsx")
        assert good["status"] == "processed" and [x["doc_type"] for x in good["parts"]][0] == "yardi_budget_comparison"
        ex = client.get(f"/api/projects/{p['id']}/files/{good['id']}/extraction").json()
        assert len(ex["extractions"]) == 3
        assert client.patch(f"/api/projects/{p['id']}/files/{good['id']}", json={"ignored": True}).json()["ignored"] is True
        assert client.patch(f"/api/projects/{p['id']}/files/{good['id']}", json={"ignored": False, "doc_type_override": "nope"}).status_code == 422
        r = client.post(f"/api/projects/{p['id']}/files/{good['id']}/reprocess")
        assert r.status_code == 200 and pool.wait_idle(20)
        bad = next(f for f in detail["files"] if f["original_filename"] == "notes.docx")
        assert client.post(f"/api/projects/{p['id']}/files/{bad['id']}/reprocess").status_code == 409
        assert client.delete(f"/api/projects/{p['id']}/files/{bad['id']}").status_code == 204
        assert len(client.get(f"/api/projects/{p['id']}/files").json()) == 1
        assert client.delete(f"/api/projects/{p['id']}").status_code == 204
        assert client.get(f"/api/projects/{p['id']}").status_code == 404


def test_upload_rejects_oversize(tmp_path, monkeypatch):
    from app.api import files as files_api
    monkeypatch.setattr(files_api, "_upload_limit", lambda: 5)
    with TestClient(app) as client:
        p = client.post("/api/projects", json={"name": "P"}).json()
        r = client.post(f"/api/projects/{p['id']}/files", files=[("files", ("big.xlsx", b"x" * 10, "application/octet-stream"))])
        assert r.status_code == 413
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_api_files.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.api'`

- [ ] **Step 3: Write `backend/app/api/serialize.py`**

```python
"""ReportData -> the JSON shape the review screen renders (flat lists, paths on every leaf)."""
from __future__ import annotations

from ..consolidate.validate import summary
from ..models import Field, Issue, ReportData


def field_json(path: str, key: str, f: Field) -> dict:
    return {
        "path": path, "key": key, "label": f.label, "kind": f.kind, "value": f.value, "override": f.override,
        "effective": f.effective, "status": "manual" if f.override is not None else f.status,
        "source": f.source.model_dump() if f.source else None,
        "alternatives": [a.model_dump() for a in f.alternatives], "note": f.note, "readonly": f.status == "derived",
    }


def to_ui(data: ReportData, issues: list[Issue], row: dict) -> dict:
    sections = []
    for sk, sec in data.sections.items():
        fields = [field_json(f"{sk}.fields.{k}", k, f) for k, f in sec.fields.items()]
        tables = []
        for tk, t in sec.tables.items():
            tp = f"{sk}.tables.{tk}"
            rows = []
            for rk, r in t.rows.items():
                meta = t.row_meta.get(rk, {})
                rows.append({"key": rk, "label": meta.get("label", rk), "manual": bool(meta.get("manual")), "subject": bool(meta.get("subject")),
                             "cells": [field_json(f"{tp}.rows.{rk}.{c.key}", c.key, r[c.key]) for c in t.columns if c.key in r]})
            totals = [field_json(f"{tp}.totals.{c.key}", c.key, t.totals[c.key]) for c in t.columns if c.key in t.totals]
            tables.append({"path": tp, "key": tk, "title": t.title, "columns": [c.model_dump() for c in t.columns],
                           "rows": rows, "totals": totals, "editable_rows": t.editable_rows})
        sections.append({"key": sk, "title": sec.title, "page": sec.page, "fields": fields, "tables": tables})
    return {"built_at": row.get("built_at"), "summary": summary(data, issues), "issues": [i.model_dump() for i in issues],
            "sections": sections, "meta": data.meta, "narrative_status": row.get("narrative_status"),
            "narrative_error": row.get("narrative_error")}
```

- [ ] **Step 4: Write `backend/app/api/projects.py`**

```python
from __future__ import annotations

import shutil

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field as PField

from .. import db
from ..config import settings
from ..workers.pool import pool

router = APIRouter(tags=["projects"])


class ProjectIn(BaseModel):
    name: str = PField(min_length=1, max_length=200)


def file_public(f: dict) -> dict:
    """File record without the (large) extraction payload."""
    return {k: v for k, v in f.items() if k != "extractions"}


def project_or_404(pid: str) -> dict:
    p = db.get_project(pid)
    if p is None:
        raise HTTPException(404, "Project not found")
    return p


def _stage(files: list[dict], rd: dict | None, reports: list[dict]) -> str:
    if not files:
        return "upload"
    if any(f["status"] in ("queued", "processing") for f in files):
        return "processing"
    if any(r["status"] == "done" for r in reports):
        return "generated"
    return "review" if rd and rd.get("built_at") else "processing"


def project_detail(pid: str) -> dict:
    p = project_or_404(pid)
    files = db.list_files(pid)
    rd = db.get_report_data(pid)
    reports = db.list_reports(pid)
    return {**p, "files": [file_public(f) for f in files], "reports": reports, "stage": _stage(files, rd, reports),
            "report_built": bool(rd and rd.get("built_at")),
            "processing": [f["id"] for f in files if pool.is_running(f"file:{f['id']}")]}


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn) -> dict:
    return db.create_project(body.name.strip())


@router.get("/projects")
def list_projects() -> list[dict]:
    return db.list_projects()


@router.get("/projects/{pid}")
def get_project(pid: str) -> dict:
    return project_detail(pid)


@router.delete("/projects/{pid}", status_code=204)
def delete_project(pid: str) -> None:
    project_or_404(pid)
    db.delete_project(pid)
    shutil.rmtree(settings.data_dir / "projects" / pid, ignore_errors=True)
```

- [ ] **Step 5: Write `backend/app/api/files.py`**

```python
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from .. import db
from ..classify.classifier import DOC_TYPE_LABELS, DocType
from ..config import settings
from ..readers.registry import SUPPORTED_EXTENSIONS
from ..workers import jobs
from ..workers.pool import pool
from .projects import file_public, project_or_404

router = APIRouter(tags=["files"])
CHUNK = 1024 * 1024


class FilePatch(BaseModel):
    ignored: bool | None = None
    doc_type_override: str | None = None
    clear_override: bool = False


def _upload_limit() -> int:
    return settings.max_upload_mb * 1024 * 1024


def file_or_404(pid: str, fid: str) -> dict:
    f = db.get_file(fid)
    if f is None or f["project_id"] != pid:
        raise HTTPException(404, "File not found")
    return f


@router.get("/doc-types")
def doc_types() -> list[dict]:
    return [{"key": t.value, "label": label} for t, label in DOC_TYPE_LABELS.items()]


@router.post("/projects/{pid}/files", status_code=201)
async def upload_files(pid: str, files: list[UploadFile] = File(...)) -> list[dict]:
    project_or_404(pid)
    out = []
    for uf in files:
        name = Path(uf.filename or "upload").name
        ext = Path(name).suffix.lower()
        fid = db.new_id()
        dest = settings.data_dir / "projects" / pid / "uploads" / f"{fid}{ext}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        with dest.open("wb") as fh:
            while chunk := await uf.read(CHUNK):
                size += len(chunk)
                if size > _upload_limit():
                    fh.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(413, f"{name} exceeds the {settings.max_upload_mb} MB upload limit")
                fh.write(chunk)
        db.add_file(pid, fid, name, str(dest), ext, size)
        if ext not in SUPPORTED_EXTENSIONS:
            db.update_file(fid, status="unsupported", processed_at=db.now(),
                           error=f"Unsupported file type '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}")
        else:
            pool.submit(f"file:{fid}", jobs.process_file, fid)
        out.append(file_public(db.get_file(fid)))
    return out


@router.get("/projects/{pid}/files")
def list_files(pid: str) -> list[dict]:
    project_or_404(pid)
    return [file_public(f) for f in db.list_files(pid)]


@router.get("/projects/{pid}/files/{fid}/extraction")
def file_extraction(pid: str, fid: str) -> dict:
    f = file_or_404(pid, fid)
    return {"parts": f["parts"], "extractions": f["extractions"]}


@router.patch("/projects/{pid}/files/{fid}")
def patch_file(pid: str, fid: str, body: FilePatch) -> dict:
    f = file_or_404(pid, fid)
    cols: dict = {}
    if body.ignored is not None:
        cols["ignored"] = body.ignored
    if body.clear_override:
        cols["doc_type_override"] = None
    elif body.doc_type_override is not None:
        if body.doc_type_override not in {t.value for t in DocType}:
            raise HTTPException(422, f"Unknown document type '{body.doc_type_override}'")
        cols["doc_type_override"] = body.doc_type_override
    db.update_file(fid, **cols)
    if "doc_type_override" in cols and f["status"] != "unsupported":
        db.update_file(fid, status="queued", error=None)
        pool.submit(f"file:{fid}", jobs.process_file, fid)
    else:
        jobs.rebuild_if_idle(pid)
    return file_public(db.get_file(fid))


@router.post("/projects/{pid}/files/{fid}/reprocess")
def reprocess_file(pid: str, fid: str) -> dict:
    f = file_or_404(pid, fid)
    if f["status"] == "unsupported":
        raise HTTPException(409, "Unsupported file types cannot be processed")
    db.update_file(fid, status="queued", error=None)
    pool.submit(f"file:{fid}", jobs.process_file, fid)
    return file_public(db.get_file(fid))


@router.delete("/projects/{pid}/files/{fid}", status_code=204)
def delete_file(pid: str, fid: str) -> None:
    f = file_or_404(pid, fid)
    db.delete_file(fid)
    Path(f["stored_path"]).unlink(missing_ok=True)
    jobs.rebuild_if_idle(pid)
```

- [ ] **Step 6: Replace `backend/app/main.py`**

```python
"""FastAPI application entry point."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .api import files, projects
from .config import settings
from .workers.jobs import recover_stuck_files
from .workers.pool import pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def pdf_renderer_available() -> bool:
    """True when Playwright and its Chromium build are installed. Must run in a worker thread, never on the event loop."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:  # noqa: BLE001
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    app.state.pdf_renderer = await asyncio.to_thread(pdf_renderer_available)  # sync Playwright cannot run on the loop
    recover_stuck_files()
    yield
    pool.shutdown()


app = FastAPI(title="Investor Report Generator", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"], allow_headers=["*"])
for r in (projects.router, files.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "llm_enabled": settings.llm_enabled, "pdf_renderer": bool(getattr(app.state, "pdf_renderer", False)),
            "workers": settings.workers}
```

- [ ] **Step 7: Run the tests**

Run: `pytest tests/test_api_files.py tests/test_health.py -v`
Expected: 3 PASS

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: project and file APIs with upload, reprocess, override and delete"
```

---

### Task 22: API for report data (read, patch, rows)

**Files:**
- Create: `backend/app/api/report_data.py`, `backend/tests/test_api_report_data.py`
- Modify: `backend/app/main.py` (router registration line)

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_api_report_data.py
from fastapi.testclient import TestClient

from app.main import app
from app.workers.pool import pool
from tests.helpers import (BALANCE_ROWS, BUDGET_ROWS, COMPS_ROWS, COSTAR_ROWS, LISTINGS_ROWS, LTO_ROWS, RENT_CHART_ROWS, make_xlsx,
                           rent_roll_rows, schedule_rows)

RENTS = {"BWK.A1": 1172.47, "BWK.B0": 1331.04, "BWK.B1": 1370.84, "BWK.S1": 1108.31, "TOTAL": 1250.5}


def upload_all(client, pid, tmp_path):
    xlsx = make_xlsx(tmp_path / "all.xlsx", {
        "Fin": BUDGET_ROWS, "BS": BALANCE_ROWS, "RR": rent_roll_rows("06/30/2026", 306, 338, 90.53, 14),
        "RR0": rent_roll_rows("03/31/2026", 310, 338, 91.71, 34), "Sch": schedule_rows("06/30/2026", RENTS), "LTO": LTO_ROWS,
        "HD": LISTINGS_ROWS, "Comps": COMPS_ROWS, "CoStar": COSTAR_ROWS, "Chart": RENT_CHART_ROWS})
    with xlsx.open("rb") as fh:
        assert client.post(f"/api/projects/{pid}/files", files=[("files", ("all.xlsx", fh, "application/octet-stream"))]).status_code == 201
    assert pool.wait_idle(30)


def test_report_data_read_patch_rows_and_rebuild(tmp_path):
    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "RD"}).json()["id"]
        assert client.get(f"/api/projects/{pid}/report-data").status_code == 409
        upload_all(client, pid, tmp_path)
        ui = client.get(f"/api/projects/{pid}/report-data").json()
        keys = [s["key"] for s in ui["sections"]]
        assert keys == ["property", "in_place_rent", "capital", "underwriting", "rent_trend", "financing", "financials", "commentary", "capex", "submarket", "occupancy", "status"]
        prop = next(s for s in ui["sections"] if s["key"] == "property")
        units = next(f for f in prop["fields"] if f["key"] == "units")
        assert units["effective"] == 338 and units["status"] == "extracted" and units["source"]["locator"].startswith("sheet 'RR'")
        assert ui["summary"]["missing"] > 0 and ui["built_at"]
        fin = next(t for s in ui["sections"] if s["key"] == "financials" for t in s["tables"])
        noi = next(r for r in fin["rows"] if r["key"] == "noi")
        assert next(c for c in noi["cells"] if c["key"] == "ptd_var")["readonly"] is True
        body = {"changes": [{"path": "financing.fields.lender", "value": "Fannie Mae"},
                            {"path": "financials.tables.lines.rows.total_revenue.ptd_actual", "value": 1100}],
                "add_rows": [{"table": "underwriting.tables.budget", "values": {"category": "Amenity Upkeep", "section": "value_add", "original_budget": 75000, "spent_to_date": 0}}],
                "delete_rows": [{"table": "submarket.tables.comps", "key": "the-ashlar"}]}
        ui = client.patch(f"/api/projects/{pid}/report-data", json=body).json()
        financing = next(s for s in ui["sections"] if s["key"] == "financing")
        lender = next(f for f in financing["fields"] if f["key"] == "lender")
        assert lender["effective"] == "Fannie Mae" and lender["status"] == "manual"
        fin = next(t for s in ui["sections"] if s["key"] == "financials" for t in s["tables"])
        rev = next(r for r in fin["rows"] if r["key"] == "total_revenue")
        assert next(c for c in rev["cells"] if c["key"] == "ptd_var")["effective"] == 146
        assert any("does not equal the sum" in i["message"] for i in ui["issues"])
        uw = next(t for s in ui["sections"] if s["key"] == "underwriting" for t in s["tables"])
        assert uw["rows"][0]["manual"] is True and next(c for c in uw["totals"] if c["key"] == "original_budget")["effective"] == 75000
        comps = next(t for s in ui["sections"] if s["key"] == "submarket" for t in s["tables"])
        assert [r["key"] for r in comps["rows"]] == ["the-boardwalk"]
        # clearing an override restores the extracted value; rebuild keeps the remaining overrides
        ui = client.patch(f"/api/projects/{pid}/report-data", json={"changes": [{"path": "financials.tables.lines.rows.total_revenue.ptd_actual", "value": None}]}).json()
        fin = next(t for s in ui["sections"] if s["key"] == "financials" for t in s["tables"])
        rev = next(r for r in fin["rows"] if r["key"] == "total_revenue")
        assert next(c for c in rev["cells"] if c["key"] == "ptd_actual")["effective"] == 1000
        ui = client.post(f"/api/projects/{pid}/report-data/rebuild").json()
        financing = next(s for s in ui["sections"] if s["key"] == "financing")
        assert next(f for f in financing["fields"] if f["key"] == "lender")["effective"] == "Fannie Mae"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_api_report_data.py -v`
Expected: FAIL (404 instead of 409 on the first request, since the router does not exist)

- [ ] **Step 3: Write `backend/app/api/report_data.py`**

```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field as PField

from .. import db
from ..workers import jobs
from .projects import project_or_404
from .serialize import to_ui

router = APIRouter(tags=["report-data"])


class Change(BaseModel):
    path: str
    value: Any = None


class AddRow(BaseModel):
    table: str
    key: str | None = None
    values: dict[str, Any] = PField(default_factory=dict)


class DeleteRow(BaseModel):
    table: str
    key: str


class PatchBody(BaseModel):
    changes: list[Change] = PField(default_factory=list)
    add_rows: list[AddRow] = PField(default_factory=list)
    delete_rows: list[DeleteRow] = PField(default_factory=list)


def ui_payload(pid: str) -> dict:
    try:
        data, issues, row = jobs.load_effective(pid)
    except LookupError as e:
        raise HTTPException(409, str(e)) from e
    return to_ui(data, issues, row)


@router.get("/projects/{pid}/report-data")
def get_report_data(pid: str) -> dict:
    project_or_404(pid)
    return ui_payload(pid)


@router.post("/projects/{pid}/report-data/rebuild")
def rebuild_report_data(pid: str) -> dict:
    project_or_404(pid)
    if any(f["status"] in ("queued", "processing") for f in db.list_files(pid)):
        raise HTTPException(409, "Files are still processing; wait for them to finish")
    jobs.build_report_data(pid)
    return ui_payload(pid)


@router.patch("/projects/{pid}/report-data")
def patch_report_data(pid: str, body: PatchBody) -> dict:
    project_or_404(pid)
    row = db.get_report_data(pid)
    if row is None or not row.get("data"):
        raise HTTPException(409, "Report data has not been built yet; upload and process files first")
    ov = row.get("overrides") or {}
    fields = ov.setdefault("fields", {})
    rows = ov.setdefault("rows", {})
    deleted = ov.setdefault("deleted_rows", {})
    for ch in body.changes:
        if ch.value is None or ch.value == "":
            fields.pop(ch.path, None)
        else:
            fields[ch.path] = ch.value
    for ar in body.add_rows:
        key = ar.key or f"manual-{db.new_id()[:6]}"
        rows.setdefault(ar.table, {})[key] = ar.values
        if key in deleted.get(ar.table, []):
            deleted[ar.table].remove(key)
    for dr in body.delete_rows:
        if dr.key in rows.get(dr.table, {}):
            rows[dr.table].pop(dr.key)
        else:
            deleted.setdefault(dr.table, [])
            if dr.key not in deleted[dr.table]:
                deleted[dr.table].append(dr.key)
        prefix = f"{dr.table}.rows.{dr.key}."
        for p in [p for p in fields if p.startswith(prefix)]:
            fields.pop(p)
    db.save_overrides(pid, ov)
    return ui_payload(pid)
```

- [ ] **Step 4: Register the router in `backend/app/main.py`**

Change the import line to `from .api import files, projects, report_data` and the loop to `for r in (projects.router, files.router, report_data.router):`.

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_api_report_data.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: report-data API with overrides, manual rows and rebuild"
```

---

### Task 23: Formatters and the SVG line chart

**Files:**
- Create: `backend/app/report/__init__.py` (empty), `backend/app/report/formatters.py`, `backend/app/report/chart.py`, `backend/tests/test_report_helpers.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_report_helpers.py
from app.report import formatters as fm
from app.report.chart import line_chart_svg


def test_formatters():
    assert fm.money(1346580.4) == "$1,346,580" and fm.money(-22) == "−$22" and fm.money(None) == "—"
    assert fm.money_m(48000000) == "$48.0M" and fm.money_m(48000000, 0) == "$48M"
    assert fm.num(-53131) == "(53,131)" and fm.num(9961) == "9,961"
    assert fm.signed_money(4183) == "+$4,183" and fm.signed_money(-34283) == "−$34,283"
    assert fm.signed_num(4183) == "+4,183" and fm.signed_num(-34283) == "(34,283)" and fm.signed_num(0) == "0"
    assert fm.pct(0.1916) == "19.2%" and fm.pct(-0.9729, 1, True) == "−97.3%" and fm.pct(0.1916, 1, True) == "+19.2%"
    assert fm.var_pct(0.0) == "flat" and fm.var_pct(None) == "—"
    assert fm.bps(-118) == "−118 bps" and fm.date_long("2025-07-30") == "Jul 30, 2025" and fm.date_short("2025-07-30") == "Jul ’25"
    assert fm.integer(338.0) == "338" and fm.text(None) == "—" and fm.sf(841) == "841 sf" and fm.psf(1.5) == "$1.50"


def test_line_chart_svg():
    svg = line_chart_svg(["Jul '25", "Aug '25"], [{"name": "Subject gross", "values": [1.83, 1.75], "color": "#b3261e"},
                                                    {"name": "Comp effective", "values": [1.5, None], "color": "#1b3a6b", "dash": True}])
    assert svg.startswith("<svg") and "Subject gross" in svg and "stroke-dasharray" in svg and svg.count("<circle") == 3
    assert line_chart_svg([], []) == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_report_helpers.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `backend/app/report/formatters.py`**

```python
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
```

- [ ] **Step 4: Write `backend/app/report/chart.py`**

```python
"""Dependency-free SVG line chart for the rent trend on page 3."""
from __future__ import annotations


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
            out.append(f'<text x="{x(i):.1f}" y="{height - pad_b + 18}" class="xlab">{lab}</text>')
    for s in series:
        dash = ' stroke-dasharray="5,4"' if s.get("dash") else ""
        pts = [(x(i), y(v)) for i, v in enumerate(s.get("values", [])) if v is not None]
        if not pts:
            continue
        d = " ".join(f"{'M' if j == 0 else 'L'}{px:.1f},{py:.1f}" for j, (px, py) in enumerate(pts))
        out.append(f'<path d="{d}" fill="none" stroke="{s["color"]}" stroke-width="2"{dash}/>')
        out.extend(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2.5" fill="{s["color"]}"/>' for px, py in pts)
    lx, ly = pad_l, height - 14
    for s in series:
        dash = ' stroke-dasharray="5,4"' if s.get("dash") else ""
        out.append(f'<line x1="{lx}" x2="{lx + 22}" y1="{ly}" y2="{ly}" stroke="{s["color"]}" stroke-width="2"{dash}/>')
        out.append(f'<text x="{lx + 28}" y="{ly + 4}" class="legend">{s["name"]}</text>')
        lx += 28 + int(6.2 * len(s["name"])) + 22
    out.append("</svg>")
    return "".join(out)
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_report_helpers.py -v`
Expected: 2 PASS

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: report formatters and SVG line chart"
```

---

### Task 24: HTML template, stylesheet, and HTML rendering

The page is 10in x 5.625in (16:9) to match the example. Fonts: if `Source Serif 4` and `JetBrains Mono` TTFs are dropped into `backend/app/report/static/fonts/` (both are free on Google Fonts; file names in `_fonts_css`), they are embedded; otherwise Georgia and Menlo are used.

**Files:**
- Create: `backend/app/report/render.py`, `backend/app/report/templates/report.html`, `backend/app/report/static/report.css`, `backend/app/report/static/fonts/.gitkeep`, `backend/tests/test_render_html.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_render_html.py
from app.consolidate.builder import build
from app.report.render import render_html
from tests.test_builder import sample_files


def test_render_html_contains_every_page_and_key_values():
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    data.field("financing.fields.lender").override = "Fannie Mae"
    html = render_html(data, {"name": "P"})
    assert html.count('class="page') == 10
    for s in ("The Boardwalk", "2Q26", "Fort Myers, FL", "$48.0M", "Fannie Mae", "Western Lee County", "Financial Performance",
              "Capital Projects", "Comp set average", "New Lease", "Plumbing &amp; Water Heaters", "<svg", "16.3%", "90.53%", "−118 bps"):
        assert s in html, s
    assert "Jinja" not in html and "{{" not in html
    assert "—" in html  # missing values render as an em dash, never as 'None'
    assert ">None<" not in html
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_render_html.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.report.render'`

- [ ] **Step 3: Write `backend/app/report/render.py`**

```python
"""HTML rendering of ReportData with Jinja. PDF rendering is added in Task 25."""
from __future__ import annotations

import calendar
from pathlib import Path
from typing import Callable

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..models import ReportData, Table
from .chart import line_chart_svg
from .formatters import FILTERS, MINUS

REPORT_DIR = Path(__file__).resolve().parent
env = Environment(loader=FileSystemLoader(REPORT_DIR / "templates"), autoescape=select_autoescape(["html"]),
                  trim_blocks=True, lstrip_blocks=True)
env.filters.update(FILTERS)

FONT_FACES = (
    ("Source Serif 4", "SourceSerif4-Regular.ttf", 400, "normal"), ("Source Serif 4", "SourceSerif4-Semibold.ttf", 600, "normal"),
    ("Source Serif 4", "SourceSerif4-It.ttf", 400, "italic"), ("JetBrains Mono", "JetBrainsMono-Regular.ttf", 400, "normal"),
    ("JetBrains Mono", "JetBrainsMono-Medium.ttf", 500, "normal"),
)


def _fonts_css() -> str:
    fonts = REPORT_DIR / "static" / "fonts"
    faces = [f"@font-face{{font-family:'{fam}';src:url('{(fonts / file).as_uri()}');font-weight:{w};font-style:{style};}}"
             for fam, file, w, style in FONT_FACES if (fonts / file).exists()]
    return "\n".join(faces)


def _rows(t: Table | None, sort_key: Callable | None = None) -> list[dict]:
    if t is None:
        return []
    out = []
    for key, row in t.rows.items():
        meta = t.row_meta.get(key, {})
        out.append({"key": key, "label": meta.get("label", key), "subject": bool(meta.get("subject")),
                    "c": {ck: f.effective for ck, f in row.items()}})
    if sort_key:
        out.sort(key=sort_key)
    return out


def _totals(t: Table | None) -> dict:
    return {ck: f.effective for ck, f in t.totals.items()} if t else {}


def _month_tick(ym) -> str:
    try:
        y, m = str(ym).split("-")[:2]
        return f"{calendar.month_abbr[int(m)]} '{y[2:]}"
    except (ValueError, IndexError):
        return str(ym)


def _sum(rows: list[dict], col: str) -> float | None:
    vals = [r["c"].get(col) for r in rows if r["c"].get(col) is not None]
    return sum(vals) if vals else None


def context(data: ReportData, project: dict | None = None) -> dict:
    v = data.value
    uw_rows = _rows(data.table("underwriting.tables.budget"))
    uw_groups = {"value_add": [r for r in uw_rows if str(r["c"].get("section") or "").lower().startswith("value")],
                 "recurring": [r for r in uw_rows if not str(r["c"].get("section") or "").lower().startswith("value")]}
    uw_sub = {}
    for g, rs in uw_groups.items():
        ob, sp = _sum(rs, "original_budget"), _sum(rs, "spent_to_date")
        uw_sub[g] = {"original_budget": ob, "spent_to_date": sp, "pct_spent": (sp / ob) if ob and sp is not None else None}
    trend = _rows(data.table("rent_trend.tables.monthly"))
    subject = v("rent_trend.fields.subject_name") or v("property.fields.name") or "Subject"
    comp = v("rent_trend.fields.comp_name") or "Comp Set"
    series = [
        {"name": f"{subject} gross", "values": [r["c"].get("subject_gross_psf") for r in trend], "color": "#b3261e"},
        {"name": f"{subject} effective", "values": [r["c"].get("subject_eff_psf") for r in trend], "color": "#b3261e", "dash": True},
        {"name": f"{comp} gross", "values": [r["c"].get("comp_gross_psf") for r in trend], "color": "#1b3a6b"},
        {"name": f"{comp} effective", "values": [r["c"].get("comp_eff_psf") for r in trend], "color": "#1b3a6b", "dash": True},
    ]
    chart_svg = line_chart_svg([_month_tick(r["c"].get("month")) for r in trend], series) if trend else ""
    capex_rows = _rows(data.table("capex.tables.lines"), sort_key=lambda r: (-(r["c"].get("ptd_actual") or 0), -(r["c"].get("ptd_budget") or 0)))
    fin_t = data.table("financials.tables.lines")
    return {
        "v": v, "f": data.field, "meta": data.meta, "project": project or {}, "MINUS": MINUS,
        "css": (REPORT_DIR / "static" / "report.css").read_text(), "fonts_css": _fonts_css(),
        "ipr_rows": _rows(data.table("in_place_rent.tables.by_floor_plan")), "ipr_totals": _totals(data.table("in_place_rent.tables.by_floor_plan")),
        "uw_groups": uw_groups, "uw_sub": uw_sub, "uw_totals": _totals(data.table("underwriting.tables.budget")), "chart_svg": chart_svg,
        "fin_rows": _rows(fin_t), "fin_meta": fin_t.row_meta if fin_t else {},
        "capex_rows": capex_rows, "capex_totals": _totals(data.table("capex.tables.lines")),
        "comp_rows": _rows(data.table("submarket.tables.comps")), "comp_totals": _totals(data.table("submarket.tables.comps")),
        "nl_rows": _rows(data.table("occupancy.tables.new_leases")), "nl_totals": _totals(data.table("occupancy.tables.new_leases")),
        "rn_rows": _rows(data.table("occupancy.tables.renewals")), "rn_totals": _totals(data.table("occupancy.tables.renewals")),
    }


def render_html(data: ReportData, project: dict | None = None) -> str:
    return env.get_template("report.html").render(**context(data, project))
```

- [ ] **Step 4: Write `backend/app/report/static/report.css`**

```css
:root { --navy: #1b3a6b; --red: #b3261e; --green: #1f7a4d; --ink: #1a1a1a; --mute: #6b6b6b; --line: #d9d9d9; --wash: #f4f5f7; }
@page { size: 10in 5.625in; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; color: var(--ink); font-family: "Source Serif 4", Georgia, "Times New Roman", serif; font-size: 9.5pt; line-height: 1.35; background: #fff; }
.mono { font-family: "JetBrains Mono", Menlo, Consolas, monospace; letter-spacing: 0.04em; }
.small { font-size: 7pt; color: var(--mute); }
.page { width: 10in; height: 5.625in; padding: 0.32in 0.45in 0.4in; position: relative; overflow: hidden; page-break-after: always; break-after: page; background: #fff; }
.page:last-child { page-break-after: auto; break-after: auto; }
h1, h2, h3 { margin: 0; font-weight: 600; }
.hdr { display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 1px solid var(--line); padding-bottom: 5pt; margin-bottom: 9pt; }
.hdr h1 { font-size: 17pt; }
.hdr .brand { display: block; font-size: 6.5pt; color: var(--navy); font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 2pt; }
.hdr-r { text-align: right; font-size: 6.5pt; color: var(--mute); }
.hdr-r .tag { display: block; margin-top: 2pt; color: var(--navy); }
.ftr { position: absolute; left: 0.45in; right: 0.45in; bottom: 0.2in; display: flex; justify-content: space-between; font-size: 6pt; color: var(--mute); border-top: 1px solid var(--line); padding-top: 4pt; }
.two-col { display: grid; grid-template-columns: 1fr 1.6fr; gap: 0.25in; }
.three-col { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.22in; }
.grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.15in; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0.25in; }
.lab { font-size: 6pt; color: var(--mute); text-transform: uppercase; margin-bottom: 1pt; }
.kpi { font-size: 20pt; font-weight: 600; line-height: 1.1; }
.kpi-m { font-size: 14pt; font-weight: 600; line-height: 1.1; }
.kpi-l { font-size: 6pt; color: var(--mute); margin-top: 2pt; }
.kpi .unit, .kpi-m .unit { font-size: 8pt; color: var(--mute); font-weight: 400; }
.sub { font-size: 7pt; color: var(--mute); margin-top: 2pt; }
.neg { color: var(--red); } .pos { color: var(--green); }
.body { font-size: 9pt; margin: 0 0 8pt; }
.note { font-size: 7.5pt; color: var(--ink); margin: 6pt 0 0; }
.tbl { width: 100%; border-collapse: collapse; font-size: 7.5pt; }
.tbl th { font-family: "JetBrains Mono", Menlo, monospace; font-weight: 500; font-size: 5.8pt; color: var(--mute); text-align: left; padding: 3pt 4pt; border-bottom: 1px solid var(--ink); letter-spacing: 0.05em; }
.tbl td { padding: 2.4pt 4pt; border-bottom: 1px solid var(--line); }
.tbl .r { text-align: right; font-variant-numeric: tabular-nums; }
.tbl .total td { font-weight: 600; border-top: 1px solid var(--ink); border-bottom: none; }
.tbl .group td { font-family: "JetBrains Mono", Menlo, monospace; font-size: 5.8pt; color: var(--navy); padding-top: 5pt; border-bottom: none; letter-spacing: 0.06em; }
.tbl .subject td { background: var(--wash); font-weight: 600; }
.tbl.dense td { padding: 1.6pt 3pt; } .tbl.dense { font-size: 6.8pt; }
.facts { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5pt 10pt; font-size: 7.5pt; margin: 6pt 0; }
.rent-kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10pt; margin: 6pt 0 8pt; }
.photo-ph, .cover-photo { background: linear-gradient(135deg, var(--navy), #3b5f9a); color: #fff; display: flex; align-items: flex-end; padding: 10pt; font-size: 12pt; font-weight: 600; border-radius: 3pt; height: 100%; min-height: 2.2in; }
.cover { display: grid; grid-template-columns: 1fr 1fr; gap: 0.3in; }
.cover-photo { height: 100%; }
.badge { display: inline-block; background: var(--navy); color: #fff; font-size: 7pt; padding: 3pt 7pt; margin: 6pt 0 10pt; }
.badge span { font-weight: 400; opacity: 0.85; margin-left: 6pt; }
.cover-title { font-size: 26pt; line-height: 1.05; }
.cover-sub { font-size: 16pt; font-style: italic; font-weight: 400; color: var(--navy); margin-bottom: 6pt; }
.lede { font-size: 8.5pt; margin: 0 0 12pt; }
.kpi-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10pt 20pt; border-top: 1px solid var(--line); padding-top: 10pt; }
.prepared { margin-top: 18pt; }
.card { border: 1px solid var(--line); border-radius: 3pt; padding: 8pt; }
.card h3 { font-family: "JetBrains Mono", Menlo, monospace; font-size: 6pt; color: var(--navy); letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 4pt; }
.callout { border-left: 3px solid var(--navy); padding: 4pt 8pt; background: var(--wash); font-size: 8.5pt; margin-bottom: 8pt; }
.col-h { font-family: "JetBrains Mono", Menlo, monospace; font-size: 6.5pt; color: var(--navy); letter-spacing: 0.08em; text-transform: uppercase; display: flex; justify-content: space-between; border-bottom: 1px solid var(--line); padding-bottom: 3pt; margin-bottom: 4pt; }
.col-h .v { color: var(--ink); }
.col-body { font-size: 7.6pt; }
.col-body h4 { font-family: "JetBrains Mono", Menlo, monospace; font-size: 6pt; color: var(--mute); margin: 6pt 0 2pt; letter-spacing: 0.06em; text-transform: uppercase; }
.col-body p { margin: 0 0 4pt; }
.term { display: grid; grid-template-columns: 1fr 1fr; gap: 6pt 12pt; font-size: 7.5pt; }
.term .lab { margin-bottom: 0; }
.chart { width: 100%; height: auto; }
.chart .grid { stroke: var(--line); stroke-width: 1; }
.chart .ylab { font-size: 9px; fill: var(--mute); text-anchor: end; font-family: Menlo, monospace; }
.chart .xlab { font-size: 9px; fill: var(--mute); text-anchor: middle; font-family: Menlo, monospace; }
.chart .legend { font-size: 10px; fill: var(--ink); }
.status-block { margin-bottom: 8pt; }
.status-block .t { font-family: "JetBrains Mono", Menlo, monospace; font-size: 6pt; color: var(--navy); letter-spacing: 0.08em; text-transform: uppercase; }
.status-block .s { font-weight: 600; font-size: 9pt; margin: 1pt 0 2pt; }
.status-block .b { font-size: 7.6pt; }
```

- [ ] **Step 5: Write `backend/app/report/templates/report.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ v('property.fields.name')|text }} {{ v('property.fields.quarter_label')|text }} Investor Report</title>
<style>
{{ fonts_css }}
{{ css }}
</style>
</head>
<body>
{% set name = v('property.fields.name')|text %}
{% set q = v('property.fields.quarter_label')|text %}
{% set head = name ~ ' · ' ~ q %}
{% macro header(title, tag='') %}
<div class="hdr">
  <div class="hdr-l"><span class="brand">{{ v('property.fields.prepared_by')|text }}</span><h1>{{ title }}</h1></div>
  <div class="hdr-r mono">{{ head|upper }}{% if tag %}<span class="tag">{{ tag }}</span>{% endif %}</div>
</div>
{% endmacro %}
{% macro footer(section, n) %}
<div class="ftr mono"><span>{{ name|upper }} · {{ q }} · {{ section|upper }}</span><span>{{ '%02d' % n }} / 10</span></div>
{% endmacro %}
{% macro vcls(x) %}{{ 'neg' if (x or 0) < 0 else 'pos' }}{% endmacro %}

{# ---------- 1 COVER ---------- #}
<section class="page cover">
  <div class="cover-photo"><span>{{ name }}</span></div>
  <div>
    <div class="mono small">{{ q }} · LP QUARTERLY REPORT · CONFIDENTIAL</div>
    <div class="badge mono">{{ q }}<span>QUARTERLY INVESTOR REPORT</span></div>
    <h1 class="cover-title">{{ name }}</h1>
    <h2 class="cover-sub">{{ v('property.fields.city_state')|text }}</h2>
    <p class="lede">{{ v('property.fields.units')|integer }}-unit multifamily community. Quarterly performance review for the period ending {{ v('property.fields.period_end')|date_long }}.</p>
    <div class="kpi-grid">
      <div><div class="kpi">{{ v('property.fields.units')|integer }}</div><div class="kpi-l mono">UNITS</div></div>
      <div><div class="kpi">{{ v('property.fields.year_built')|text }}</div><div class="kpi-l mono">VINTAGE</div></div>
      <div><div class="kpi">{{ v('property.fields.acquired_date')|date_short }}</div><div class="kpi-l mono">ACQUIRED</div></div>
      <div><div class="kpi">{{ v('capital.fields.purchase_price')|money_m(0) }}</div><div class="kpi-l mono">PURCHASE PRICE</div></div>
    </div>
    <div class="prepared mono small">PREPARED BY<br><strong>{{ v('property.fields.prepared_by')|text }}</strong><br>Period ending {{ v('property.fields.period_end')|date_long }}</div>
  </div>
</section>

{# ---------- 2 PROPERTY DESCRIPTION ---------- #}
<section class="page">
{{ header('Property Description', 'VINTAGE ' ~ (v('property.fields.year_built')|text) ~ ' · CLASS ' ~ (v('property.fields.building_class')|text) ~ ' · HOLD PERIOD ' ~ (v('property.fields.hold_period_years')|text) ~ ' YR') }}
<div class="two-col">
  <div class="photo-ph"><span>{{ name }}</span></div>
  <div>
    <p class="body">{{ v('property.fields.description')|text }}</p>
    <div class="facts">
      <div><div class="lab mono">Address</div>{{ v('property.fields.address')|text }}<br>{{ v('property.fields.city_state')|text }} {{ v('property.fields.zip')|text }}</div>
      <div><div class="lab mono">Submarket</div>{{ v('property.fields.submarket')|text }}</div>
      <div><div class="lab mono">MSA</div>{{ v('property.fields.msa')|text }}</div>
      <div><div class="lab mono">Year built</div>{{ v('property.fields.year_built')|text }}</div>
      <div><div class="lab mono">Building class</div>{{ v('property.fields.building_class')|text }}</div>
      <div><div class="lab mono">Site / density</div>{% if v('property.fields.site_acres') %}{{ v('property.fields.site_acres')|num(1) }} ac · {{ v('property.fields.density')|num(1) }} u/ac{% else %}{{ MINUS }}{% endif %}</div>
      <div><div class="lab mono">Acquired</div>{{ v('property.fields.acquired_date')|date_long }}</div>
      <div><div class="lab mono">Avg unit size</div>{{ v('property.fields.avg_unit_sf')|sf }}</div>
    </div>
    <div class="rent-kpis">
      <div><div class="lab mono">{{ q }} avg in-place rent</div><div class="kpi-m">{{ ipr_totals.current_rent|money }} <span class="unit">/ mo</span></div></div>
      <div><div class="lab mono">Prior qtr ({{ v('in_place_rent.fields.prior_quarter_label')|text }})</div><div class="kpi-m">{{ ipr_totals.prior_rent|money }} <span class="unit">/ mo</span></div></div>
      <div><div class="lab mono">QoQ variance</div><div class="kpi-m {{ vcls(ipr_totals.variance) }}">{{ ipr_totals.variance|signed_money }} / {{ ipr_totals.variance_pct|pct(1, true) }}</div>{% if v('in_place_rent.fields.prior_variance_note') %}<div class="sub">{{ v('in_place_rent.fields.prior_variance_note') }}</div>{% endif %}</div>
    </div>
    <table class="tbl dense">
      <thead><tr><th>Type</th><th class="r">Units</th><th class="r">Avg SF</th><th class="r">{{ v('in_place_rent.fields.prior_quarter_label')|text }} in-place rent</th><th class="r">{{ q }} in-place rent</th><th class="r">QoQ variance</th></tr></thead>
      <tbody>
      {% for r in ipr_rows %}
      <tr><td>{{ r.c.type|text }}</td><td class="r">{{ r.c.units|integer }}</td><td class="r">{{ r.c.avg_sf|integer }}</td><td class="r">{{ r.c.prior_rent|money }}</td><td class="r">{{ r.c.current_rent|money }}</td><td class="r {{ vcls(r.c.variance) }}">{{ r.c.variance|signed_money }} / {{ r.c.variance_pct|pct(1, true) }}</td></tr>
      {% endfor %}
      <tr class="total"><td>{{ ipr_totals.type|text }}</td><td class="r">{{ ipr_totals.units|integer }}</td><td class="r">{{ ipr_totals.avg_sf|integer }}</td><td class="r">{{ ipr_totals.prior_rent|money }}</td><td class="r">{{ ipr_totals.current_rent|money }}</td><td class="r {{ vcls(ipr_totals.variance) }}">{{ ipr_totals.variance|signed_money }} / {{ ipr_totals.variance_pct|pct(1, true) }}</td></tr>
      </tbody>
    </table>
    <p class="note">{{ v('in_place_rent.fields.narrative')|text }}</p>
  </div>
</div>
{{ footer('Property Description', 2) }}
</section>

{# ---------- 3 PROPERTY SUMMARY & BUSINESS PLAN ---------- #}
<section class="page">
{{ header('Property Summary & Business Plan') }}
<div class="grid-4">
  <div><div class="lab mono">Purchase price</div><div class="kpi">{{ v('capital.fields.purchase_price')|money_m(1) }}</div><div class="sub">{{ v('capital.fields.price_per_unit')|money }} / unit · {{ v('property.fields.units')|integer }} units</div></div>
  <div><div class="lab mono">Equity invested (ITD)</div><div class="kpi">{{ v('capital.fields.equity_invested')|money_m(1) }}</div></div>
  <div><div class="lab mono">{{ q }} equity contributions</div><div class="kpi">{{ v('capital.fields.quarter_contributions')|money }}</div><div class="sub">{{ v('capital.fields.contributions_note')|text }}</div></div>
  <div><div class="lab mono">Cash distributions (ITD)</div><div class="kpi">{{ v('capital.fields.distributions_itd')|money }}</div><div class="sub">{{ v('capital.fields.distributions_note')|text }}</div></div>
</div>
<div class="grid-2" style="margin-top:10pt">
  <div>
    <div class="col-h"><span>Original business plan</span></div>
    <p class="col-body">{{ v('capital.fields.business_plan_summary')|text }}</p>
    <div class="col-h"><span>Original underwriting budget</span></div>
    <table class="tbl dense">
      <thead><tr><th>Category</th><th class="r">Original UW</th><th class="r">Spent to date*</th><th class="r">% spent</th></tr></thead>
      <tbody>
      {% for gkey, gtitle in (('value_add', 'Value add projects'), ('recurring', 'Recurring capex')) %}
      <tr class="group"><td colspan="4">{{ gtitle|upper }}</td></tr>
      {% for r in uw_groups[gkey] %}
      <tr><td>{{ r.c.category|text }}</td><td class="r">{{ r.c.original_budget|money }}</td><td class="r">{{ r.c.spent_to_date|money }}</td><td class="r">{{ r.c.pct_spent|pct(0) }}</td></tr>
      {% endfor %}
      <tr class="total"><td>Total {{ gtitle|lower }}</td><td class="r">{{ uw_sub[gkey].original_budget|money }}</td><td class="r">{{ uw_sub[gkey].spent_to_date|money }}</td><td class="r">{{ uw_sub[gkey].pct_spent|pct(0) }}</td></tr>
      {% endfor %}
      <tr class="total"><td>Total underwritten capital</td><td class="r">{{ uw_totals.original_budget|money }}</td><td class="r">{{ uw_totals.spent_to_date|money }}</td><td class="r">{{ uw_totals.pct_spent|pct(0) }}</td></tr>
      </tbody>
    </table>
    <div class="small">*{{ v('underwriting.fields.spent_period_note')|text }}</div>
  </div>
  <div>
    <div class="col-h"><span>Submarket rent trends</span><span class="v">{{ v('rent_trend.fields.chart_subtitle')|text }}</span></div>
    <div class="mono small" style="text-align:center">{{ v('rent_trend.fields.chart_title')|text }}</div>
    {{ chart_svg|safe }}
    <p class="note">{{ v('rent_trend.fields.caption')|text }}</p>
  </div>
</div>
{{ footer('Property Summary', 3) }}
</section>

{# ---------- 4 FINANCING ---------- #}
<section class="page">
{{ header('Financing Overview', (v('financing.fields.lender')|text|upper) ~ ' · ' ~ (v('financing.fields.rate_type')|text|upper) ~ ' ' ~ (v('financing.fields.rate')|pct(2)) ~ ' · ' ~ (v('financing.fields.recourse')|text|upper)) }}
<div class="grid-2">
  <div>
    <div class="col-h"><span>Senior loan</span></div>
    <div class="kpi">{{ v('financing.fields.loan_amount')|money_m(2) }}</div>
    <div class="sub">Initial principal · {{ v('financing.fields.rate_type')|text }} {{ v('financing.fields.rate')|pct(2) }} · IO through {{ v('financing.fields.io_end_date')|date_long }} · matures {{ v('financing.fields.maturity_date')|date_long }}</div>
    <div class="term" style="margin-top:8pt">
      <div><div class="lab mono">Lender</div>{{ v('financing.fields.lender')|text }}{% if v('financing.fields.servicer') %} (svcd. {{ v('financing.fields.servicer') }}){% endif %}</div>
      <div><div class="lab mono">Borrower</div>{{ v('financing.fields.borrower')|text }}</div>
      <div><div class="lab mono">Effective date</div>{{ v('financing.fields.effective_date')|date_long }}</div>
      <div><div class="lab mono">Maturity date</div>{{ v('financing.fields.maturity_date')|date_long }}</div>
      <div><div class="lab mono">Loan term</div>{% if v('financing.fields.term_months') %}{{ v('financing.fields.term_months')|integer }} months{% else %}{{ MINUS }}{% endif %}</div>
      <div><div class="lab mono">Rate</div>{{ v('financing.fields.rate')|pct(2) }}{% if v('financing.fields.rate') is none and v('financing.fields.implied_rate') %} (implied {{ v('financing.fields.implied_rate')|pct(2) }}){% endif %}</div>
      <div><div class="lab mono">IO period</div>{% if v('financing.fields.io_months') %}{{ v('financing.fields.io_months')|integer }} mo to {{ v('financing.fields.io_end_date')|date_long }}{% else %}{{ MINUS }}{% endif %}</div>
      <div><div class="lab mono">Amortization</div>{% if v('financing.fields.amort_years') %}{{ v('financing.fields.amort_years')|integer }} yrs{% else %}{{ MINUS }}{% endif %}</div>
      <div><div class="lab mono">IO payment (monthly)</div>{{ v('financing.fields.interest_monthly')|money }}</div>
      <div><div class="lab mono">P&amp;I payment (monthly)</div>{{ v('financing.fields.pi_payment')|money }}</div>
      <div><div class="lab mono">Recourse</div>{{ v('financing.fields.recourse')|text }}</div>
      <div><div class="lab mono">Reserve balance</div>{{ v('financing.fields.reserve_balance')|money }}</div>
    </div>
  </div>
  <div>
    <div class="col-h"><span>Structure, prepayment &amp; reserves</span></div>
    <div class="card"><h3>Prepayment</h3>{{ v('financing.fields.prepayment')|text }}{% if v('financing.fields.yield_maintenance_through') %}<div class="sub">Yield maintenance through {{ v('financing.fields.yield_maintenance_through')|date_long }}{% if v('financing.fields.open_prepay_months') %} · open prepay last {{ v('financing.fields.open_prepay_months')|integer }} mo{% endif %}</div>{% endif %}</div>
    <div class="card" style="margin-top:6pt"><h3>Replacement reserve</h3>{{ v('financing.fields.replacement_reserve_monthly')|money }} / mo{% if v('financing.fields.replacement_reserve_annual') %} · {{ v('financing.fields.replacement_reserve_annual')|money_k }} / yr{% endif %}</div>
    <div class="card" style="margin-top:6pt"><h3>Repairs escrow</h3>{{ v('financing.fields.repairs_escrow')|money }} one-time</div>
    <p class="note">{{ v('financing.fields.narrative')|text }}</p>
  </div>
</div>
{{ footer('Financing', 4) }}
</section>

{# ---------- 5 COMMENTARY ---------- #}
<section class="page">
{{ header('Financial & Capital Commentary') }}
<div class="callout"><span class="mono small">{{ q }} TAKEAWAY</span><br>{{ v('commentary.fields.takeaway')|text }}</div>
<div class="three-col">
  <div>
    <div class="col-h"><span>01 · Revenue</span><span class="v {{ vcls(v('commentary.fields.revenue_var')) }}">{{ v('commentary.fields.revenue_var')|signed_money }} vs. budget</span></div>
    <div class="col-body">
      <p>Total revenue of {{ v('commentary.fields.revenue_actual')|money }} finished {{ v('commentary.fields.revenue_var_pct')|pct(1, true) }} against the {{ v('commentary.fields.revenue_budget')|money }} budget. Gain/loss to lease was {{ v('commentary.fields.gain_to_lease_actual')|money }} versus a {{ v('commentary.fields.gain_to_lease_budget')|money }} budget ({{ v('commentary.fields.gain_to_lease_var_pct')|pct(1, true) }}).</p>
      <p>{{ v('commentary.fields.revenue_body')|text }}</p>
      <h4>Outlook</h4><p>{{ v('commentary.fields.revenue_outlook')|text }}</p>
    </div>
  </div>
  <div>
    <div class="col-h"><span>02 · Operating expenses</span><span class="v {{ vcls(v('commentary.fields.opex_var')) }}">{{ v('commentary.fields.opex_var')|signed_money }} vs. budget</span></div>
    <div class="col-body">
      <p>Total operating expenses of {{ v('commentary.fields.opex_actual')|money }} finished {{ v('commentary.fields.opex_var_pct')|pct(1, true) }} against the {{ v('commentary.fields.opex_budget')|money }} budget. Insurance {{ v('commentary.fields.insurance_var')|signed_money }} and utilities {{ v('commentary.fields.utilities_var')|signed_money }} versus budget.</p>
      <p>{{ v('commentary.fields.opex_body')|text }}</p>
      <h4>Outlook</h4><p>{{ v('commentary.fields.opex_outlook')|text }}</p>
    </div>
  </div>
  <div>
    <div class="col-h"><span>03 · NOI &amp; cash flow</span><span class="v {{ vcls(v('commentary.fields.noi_var')) }}">{{ v('commentary.fields.noi_var')|signed_money }} vs. budget</span></div>
    <div class="col-body">
      <p>NOI of {{ v('commentary.fields.noi_actual')|money }} finished {{ v('commentary.fields.noi_var_pct')|pct(1, true) }} against the {{ v('commentary.fields.noi_budget')|money }} budget. Net cash flow after debt service was {{ v('commentary.fields.ncf_actual')|money }} versus {{ v('commentary.fields.ncf_budget')|money }} budgeted ({{ v('commentary.fields.ncf_var')|signed_money }}). Capital spend was {{ v('commentary.fields.capex_actual')|money }} against a {{ v('commentary.fields.capex_budget')|money }} quarterly budget; year to date {{ v('commentary.fields.capex_ytd_actual')|money }} of the {{ v('commentary.fields.capex_annual_budget')|money }} annual budget.</p>
      <p>{{ v('commentary.fields.noi_body')|text }}</p>
      <h4>Outlook</h4><p>{{ v('commentary.fields.noi_outlook')|text }}</p>
    </div>
  </div>
</div>
{{ footer('Financial & Capital Commentary', 5) }}
</section>

{# ---------- 6 FINANCIAL PERFORMANCE ---------- #}
<section class="page">
{{ header('Financial Performance', (v('financials.fields.period_label')|text|upper) ~ ' VS. BUDGET & YTD') }}
<table class="tbl dense">
  <thead><tr><th>$ in actuals</th><th class="r">{{ q }} actual</th><th class="r">{{ q }} budget</th><th class="r">Var %</th><th class="r">YTD actual</th><th class="r">YTD budget</th><th class="r">Var %</th></tr></thead>
  <tbody>
  {% set ns = namespace(group=none) %}
  {% for r in fin_rows %}
    {% set g = fin_meta[r.key].group if r.key in fin_meta else '' %}
    {% if g != ns.group %}{% set ns.group = g %}<tr class="group"><td colspan="7">{{ {'revenue': 'Revenue', 'opex': 'Operating expenses', 'noi': 'Net operating income'}[g] if g in ('revenue', 'opex', 'noi') else g }}</td></tr>{% endif %}
    <tr class="{{ 'total' if r.key in ('net_rental_income', 'total_revenue', 'total_opex', 'noi', 'net_cash_flow') else '' }}">
      <td>{{ r.label }}</td>
      <td class="r">{{ r.c.ptd_actual|num }}</td><td class="r">{{ r.c.ptd_budget|num }}</td>
      <td class="r {{ vcls(r.c.ptd_var) }}">{% if r.key == 'net_cash_flow' %}{{ r.c.ptd_var|num }}{% elif r.key == 'debt_service' %}{% else %}{{ r.c.ptd_var_pct|var_pct }}{% endif %}</td>
      <td class="r">{{ r.c.ytd_actual|num }}</td><td class="r">{{ r.c.ytd_budget|num }}</td>
      <td class="r {{ vcls(r.c.ytd_var) }}">{% if r.key == 'net_cash_flow' %}{{ r.c.ytd_var|num }}{% elif r.key == 'debt_service' %}{% else %}{{ r.c.ytd_var_pct|var_pct }}{% endif %}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{{ footer('Financial Performance', 6) }}
</section>

{# ---------- 7 CAPITAL PROJECTS ---------- #}
<section class="page">
{{ header('Capital Projects', (q ~ ' ACTIVITY')) }}
<table class="tbl dense">
  <thead><tr><th>Line item</th><th class="r">{{ q }} actual</th><th class="r">{{ q }} budget</th><th class="r">Var $</th><th class="r">YTD actual</th><th class="r">YTD budget</th><th class="r">Var $</th><th class="r">Annual budget</th></tr></thead>
  <tbody>
  {% for r in capex_rows %}
  <tr><td>{{ r.label }}</td><td class="r">{{ r.c.ptd_actual|num }}</td><td class="r">{{ r.c.ptd_budget|num }}</td><td class="r {{ vcls(r.c.ptd_var) }}">{{ r.c.ptd_var|signed_num }}</td><td class="r">{{ r.c.ytd_actual|num }}</td><td class="r">{{ r.c.ytd_budget|num }}</td><td class="r {{ vcls(r.c.ytd_var) }}">{{ r.c.ytd_var|signed_num }}</td><td class="r">{{ r.c.annual_budget|num }}</td></tr>
  {% endfor %}
  <tr class="total"><td>Total capital spend</td><td class="r">{{ capex_totals.ptd_actual|num }}</td><td class="r">{{ capex_totals.ptd_budget|num }}</td><td class="r {{ vcls(capex_totals.ptd_var) }}">{{ capex_totals.ptd_var|signed_num }}</td><td class="r">{{ capex_totals.ytd_actual|num }}</td><td class="r">{{ capex_totals.ytd_budget|num }}</td><td class="r {{ vcls(capex_totals.ytd_var) }}">{{ capex_totals.ytd_var|signed_num }}</td><td class="r">{{ capex_totals.annual_budget|num }}</td></tr>
  </tbody>
</table>
<p class="note">{{ v('capex.fields.narrative')|text }}</p>
{{ footer('Capital Projects', 7) }}
</section>

{# ---------- 8 SUBMARKET ---------- #}
<section class="page">
{{ header('Submarket Comparison', (v('submarket.fields.source_note')|text|upper) ~ ' · ' ~ (v('submarket.fields.submarket_name')|text|upper) ~ ' · ' ~ (v('submarket.fields.data_quarter')|text)) }}
<div class="three-col" style="margin-bottom:8pt">
  <div><div class="lab mono">Submarket vacancy</div><div class="kpi">{{ v('submarket.fields.vacancy')|pct(1) }}</div><div class="sub">CoStar {{ v('submarket.fields.submarket_name')|text }} · prior quarter {{ v('submarket.fields.prior_vacancy')|pct(1) }}</div></div>
  <div><div class="lab mono">YoY asking rent</div><div class="kpi">{{ v('submarket.fields.rent_growth_yoy')|pct(1, true) }}</div><div class="sub">{{ v('submarket.fields.avg_asking_rent')|money }}/unit avg market asking · prior quarter {{ v('submarket.fields.prior_rent_growth')|pct(1, true) }}</div></div>
  <div><div class="lab mono">Under construction</div><div class="kpi">{{ v('submarket.fields.under_construction')|integer }} units</div><div class="sub">{{ v('submarket.fields.pipeline_note')|text }}{% if v('submarket.fields.recent_deliveries') %} · recent deliveries: {{ v('submarket.fields.recent_deliveries') }}{% endif %}</div></div>
</div>
<table class="tbl dense">
  <thead><tr><th>Property name</th><th class="r">Units</th><th class="r">Vintage</th><th class="r">Leased %</th><th class="r">Asking rent</th><th class="r">Eff. rent (NER)</th><th class="r">Concession</th></tr></thead>
  <tbody>
  {% for r in comp_rows %}
  <tr class="{{ 'subject' if r.subject else '' }}"><td>{{ r.c.name|text }}{% if r.subject %} <span class="mono small">SUBJECT</span>{% endif %}</td><td class="r">{{ r.c.units|integer }}</td><td class="r">{{ r.c.vintage|text }}</td><td class="r">{{ r.c.leased_pct|pct(1) }}</td><td class="r">{{ r.c.asking_rent|money }}</td><td class="r">{{ r.c.effective_rent|money }}</td><td class="r">{% if r.c.concession %}{{ r.c.concession|money }}/mo ({{ r.c.concession_pct|pct(0) }}){% else %}{{ MINUS }}{% endif %}</td></tr>
  {% endfor %}
  <tr class="total"><td>{{ comp_totals.name|text }}</td><td class="r">{{ comp_totals.units|integer }}</td><td class="r">{{ comp_totals.vintage|text }}</td><td class="r">{{ comp_totals.leased_pct|pct(1) }}</td><td class="r">{{ comp_totals.asking_rent|money }}</td><td class="r">{{ comp_totals.effective_rent|money }}</td><td class="r">{{ comp_totals.concession|money }}</td></tr>
  </tbody>
</table>
<div class="three-col" style="margin-top:8pt">
  <div><div class="col-h"><span>Occupancy</span></div><div class="col-body">{{ v('submarket.fields.occupancy_narrative')|text }}</div></div>
  <div><div class="col-h"><span>Effective rent</span></div><div class="col-body">{{ v('submarket.fields.rent_narrative')|text }}</div></div>
  <div><div class="col-h"><span>Concessions</span></div><div class="col-body">{{ v('submarket.fields.concession_narrative')|text }}</div></div>
</div>
<div class="small" style="margin-top:6pt">{{ v('submarket.fields.footnote')|text }} Subject leased % is physical occupancy per the Yardi rent roll.</div>
{{ footer('Submarket Comparison', 8) }}
</section>

{# ---------- 9 OCCUPANCY & LEASING ---------- #}
<section class="page">
{{ header('Occupancy & Leasing', (q ~ ' EXECUTED · ' ~ (v('occupancy.fields.new_lease_count')|integer) ~ ' NEW LEASES · ' ~ (v('occupancy.fields.renewal_count')|integer) ~ ' RENEWALS')) }}
<div class="three-col" style="margin-bottom:8pt">
  <div><div class="lab mono">{{ v('occupancy.fields.prior_date')|date_long|upper }}</div><div class="kpi">{{ v('occupancy.fields.prior_pct')|pct(2) }}</div><div class="sub">{{ v('occupancy.fields.prior_occupied')|integer }} / {{ v('occupancy.fields.total_units')|integer }} occupied</div></div>
  <div><div class="lab mono">{{ v('occupancy.fields.current_date')|date_long|upper }}</div><div class="kpi">{{ v('occupancy.fields.current_pct')|pct(2) }}</div><div class="sub">{{ v('occupancy.fields.current_occupied')|integer }} / {{ v('occupancy.fields.total_units')|integer }} occupied · {{ v('occupancy.fields.future_applicants')|integer }} future / applicants</div></div>
  <div><div class="lab mono">Quarter change</div><div class="kpi {{ vcls(v('occupancy.fields.change_bps')) }}">{{ v('occupancy.fields.change_bps')|bps }}</div><div class="sub">{{ v('occupancy.fields.occupancy_narrative')|text }}</div></div>
</div>
<div class="grid-2">
  {% for title, rows, totals, narrative, pctf in (('New Leases', nl_rows, nl_totals, 'occupancy.fields.new_lease_narrative', 'occupancy.fields.new_lease_lto_pct'), ('Renewals', rn_rows, rn_totals, 'occupancy.fields.renewal_narrative', 'occupancy.fields.renewal_lto_pct')) %}
  <div>
    <div class="col-h"><span>{{ title }} · {{ q }} · by floor plan</span><span class="v {{ vcls(v(pctf)) }}">Overall {{ v(pctf)|pct(1, true) }}</span></div>
    <div class="col-body" style="margin-bottom:4pt">{{ v(narrative)|text }}</div>
    <table class="tbl dense">
      <thead><tr><th>Floor plan</th><th class="r">Count</th><th class="r">Avg prior</th><th class="r">Avg current</th><th class="r">$ LTO</th><th class="r">% LTO</th></tr></thead>
      <tbody>
      {% for r in rows %}
      <tr><td>{{ r.c.floor_plan|text }}{% if r.c.sqft %} · {{ r.c.sqft|integer }} sf{% endif %}</td><td class="r">{{ r.c.count|integer }}</td><td class="r">{{ r.c.avg_prior|money }}</td><td class="r">{{ r.c.avg_current|money }}</td><td class="r {{ vcls(r.c.lto) }}">{{ r.c.lto|signed_money }}</td><td class="r {{ vcls(r.c.lto_pct) }}">{{ r.c.lto_pct|pct(2, true) }}</td></tr>
      {% endfor %}
      <tr class="total"><td>{{ title }} total</td><td class="r">{{ totals.count|integer }}</td><td class="r">{{ totals.avg_prior|money }}</td><td class="r">{{ totals.avg_current|money }}</td><td class="r {{ vcls(totals.lto) }}">{{ totals.lto|signed_money }}</td><td class="r {{ vcls(totals.lto_pct) }}">{{ totals.lto_pct|pct(2, true) }}</td></tr>
      </tbody>
    </table>
  </div>
  {% endfor %}
</div>
<div class="small mono" style="margin-top:6pt">{{ v('occupancy.fields.lto_period_note')|text|upper }}</div>
{{ footer('Occupancy & Leasing', 9) }}
</section>

{# ---------- 10 STATUS UPDATE & GOALS ---------- #}
<section class="page">
{{ header('Status Update & ' ~ (v('status.fields.next_quarter_label')|text) ~ ' Goals') }}
<div class="grid-2">
  <div>
    <div class="col-h"><span>Status update</span></div>
    {% for i in (1, 2, 3) %}
    {% if v('status.fields.status' ~ i ~ '_title') or v('status.fields.status' ~ i ~ '_body') %}
    <div class="status-block"><div class="t">{{ v('status.fields.status' ~ i ~ '_title')|text }}</div><div class="s">{{ v('status.fields.status' ~ i ~ '_subtitle')|text }}</div><div class="b">{{ v('status.fields.status' ~ i ~ '_body')|text }}</div></div>
    {% endif %}
    {% endfor %}
    <div class="small">{{ q }} collections recovered: {{ v('status.fields.collections_recovered')|money }} · bad debt write-offs: {{ v('status.fields.bad_debt_writeoff')|money }}</div>
  </div>
  <div>
    <div class="col-h"><span>{{ v('status.fields.next_quarter_label')|text }} goals / initiatives</span></div>
    {% for i in (1, 2, 3) %}
    {% if v('status.fields.goal' ~ i ~ '_title') or v('status.fields.goal' ~ i ~ '_body') %}
    <div class="status-block"><div class="t">{{ v('status.fields.goal' ~ i ~ '_title')|text }}</div><div class="s">{{ v('status.fields.goal' ~ i ~ '_subtitle')|text }}</div><div class="b">{{ v('status.fields.goal' ~ i ~ '_body')|text }}</div></div>
    {% endif %}
    {% endfor %}
  </div>
</div>
{{ footer('Status Update & Goals', 10) }}
</section>
</body>
</html>
```

- [ ] **Step 6: Run the test**

Run: `pytest tests/test_render_html.py -v`
Expected: PASS. If a filter name is misspelled Jinja raises `TemplateSyntaxError` naming the line; fix the template rather than the test.

- [ ] **Step 7: Eyeball it once**

```bash
python -c "
from app.consolidate.builder import build
from app.report.render import render_html
from tests.test_builder import sample_files
open('/tmp/report.html','w').write(render_html(build({'id':'p','name':'P'}, sample_files())[0]))
" && open /tmp/report.html
```
Expected: ten 16:9 pages in the browser with placeholders (em dashes) where the synthetic data has no values.

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: 10-page HTML report template with stylesheet and rent trend chart"
```

---

### Task 25: PDF rendering, report versions API, and the render job

**Files:**
- Modify: `backend/app/report/render.py` (append two functions), `backend/app/workers/jobs.py` (append `generate_report`), `backend/app/main.py` (router + renderer check)
- Create: `backend/app/api/report.py`, `backend/tests/test_api_report.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_api_report.py
from fastapi.testclient import TestClient

from app.main import app
from app.workers.pool import pool
from tests.test_api_report_data import upload_all


def test_preview_generate_and_download(tmp_path):
    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "R"}).json()["id"]
        assert client.get(f"/api/projects/{pid}/report/preview").status_code == 409
        assert client.post(f"/api/projects/{pid}/reports").status_code == 409
        upload_all(client, pid, tmp_path)
        html = client.get(f"/api/projects/{pid}/report/preview")
        assert html.status_code == 200 and "The Boardwalk" in html.text and html.headers["content-type"].startswith("text/html")
        r = client.post(f"/api/projects/{pid}/reports")
        assert r.status_code == 202 and r.json()["version"] == 1 and r.json()["status"] in ("queued", "rendering", "done", "failed")
        rid = r.json()["id"]
        assert pool.wait_idle(120)
        rep = client.get(f"/api/projects/{pid}/reports/{rid}").json()
        if client.get("/api/health").json()["pdf_renderer"]:
            assert rep["status"] == "done" and rep["has_pdf"] is True, rep["error"]
            dl = client.get(f"/api/projects/{pid}/reports/{rid}/download")
            assert dl.status_code == 200 and dl.headers["content-type"] == "application/pdf" and dl.content[:4] == b"%PDF"
        else:
            assert rep["status"] == "failed" and rep["error"]
            assert client.get(f"/api/projects/{pid}/reports/{rid}/download").status_code == 409
        r2 = client.post(f"/api/projects/{pid}/reports").json()
        assert r2["version"] == 2 and [x["version"] for x in client.get(f"/api/projects/{pid}/reports").json()] == [2, 1]
        assert pool.wait_idle(120)
        assert client.get(f"/api/projects/{pid}").json()["stage"] in ("generated", "review")
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_api_report.py -v`
Expected: FAIL (404 on the preview route)

- [ ] **Step 3: Append to `backend/app/report/render.py`**

```python
def chromium_available() -> bool:
    """True when Playwright's Chromium is installed. Call from a worker thread, not the event loop."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:  # noqa: BLE001
        return False


def render_pdf(html_path: Path, pdf_path: Path) -> None:
    """Print the saved HTML file to PDF with headless Chromium (fonts and CSS are resolved from the file URL)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(html_path.resolve().as_uri(), wait_until="load")
            page.emulate_media(media="print")
            page.pdf(path=str(pdf_path), prefer_css_page_size=True, print_background=True)
        finally:
            browser.close()
```

- [ ] **Step 4: Append to `backend/app/workers/jobs.py`**

```python
def generate_report(report_id: str) -> None:
    """Render the current effective data to HTML and PDF for one report version."""
    from ..config import settings
    from ..report.render import render_html, render_pdf

    r = db.get_report(report_id)
    if r is None:
        return
    db.update_report(report_id, status="rendering", error=None)
    try:
        project = db.get_project(r["project_id"])
        data, _issues, _row = load_effective(r["project_id"])
        out_dir = settings.data_dir / "projects" / r["project_id"] / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        html_path = out_dir / f"report-v{r['version']}.html"
        pdf_path = out_dir / f"report-v{r['version']}.pdf"
        html_path.write_text(render_html(data, project))
        db.update_report(report_id, html_path=str(html_path))
        render_pdf(html_path, pdf_path)
        db.update_report(report_id, status="done", pdf_path=str(pdf_path))
    except Exception as e:  # noqa: BLE001 - surface the failure on the version row
        log.exception("report render failed for %s", report_id)
        db.update_report(report_id, status="failed",
                         error=f"{type(e).__name__}: {e}. If Chromium is missing run: python -m playwright install chromium")
```

- [ ] **Step 5: Write `backend/app/api/report.py`**

```python
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from .. import db
from ..report.render import render_html
from ..workers import jobs
from ..workers.pool import pool
from .projects import project_or_404

router = APIRouter(tags=["report"])


def report_public(r: dict) -> dict:
    return {"id": r["id"], "project_id": r["project_id"], "version": r["version"], "status": r["status"], "error": r["error"],
            "created_at": r["created_at"], "has_pdf": bool(r.get("pdf_path"))}


def report_or_404(pid: str, rid: str) -> dict:
    r = db.get_report(rid)
    if r is None or r["project_id"] != pid:
        raise HTTPException(404, "Report not found")
    return r


@router.get("/projects/{pid}/report/preview", response_class=HTMLResponse)
def preview(pid: str) -> HTMLResponse:
    project = project_or_404(pid)
    try:
        data, _issues, _row = jobs.load_effective(pid)
    except LookupError as e:
        raise HTTPException(409, str(e)) from e
    return HTMLResponse(render_html(data, project))


@router.post("/projects/{pid}/reports", status_code=202)
def create_report(pid: str) -> dict:
    project_or_404(pid)
    rd = db.get_report_data(pid)
    if rd is None or not rd.get("data"):
        raise HTTPException(409, "Report data has not been built yet; upload and process files first")
    r = db.create_report(pid)
    pool.submit(f"report:{r['id']}", jobs.generate_report, r["id"])
    return report_public(db.get_report(r["id"]))


@router.get("/projects/{pid}/reports")
def list_reports(pid: str) -> list[dict]:
    project_or_404(pid)
    return [report_public(r) for r in db.list_reports(pid)]


@router.get("/projects/{pid}/reports/{rid}")
def get_report(pid: str, rid: str) -> dict:
    return report_public(report_or_404(pid, rid))


@router.get("/projects/{pid}/reports/{rid}/download")
def download_report(pid: str, rid: str) -> FileResponse:
    r = report_or_404(pid, rid)
    if r["status"] != "done" or not r.get("pdf_path"):
        raise HTTPException(409, r.get("error") or "The PDF is not ready yet")
    project = project_or_404(pid)
    stem = re.sub(r"[^A-Za-z0-9]+", "-", project["name"]).strip("-").lower() or "report"
    return FileResponse(r["pdf_path"], media_type="application/pdf", filename=f"{stem}-v{r['version']}.pdf")
```

- [ ] **Step 6: Update `backend/app/main.py`**

Replace the import block and lifespan so the renderer check comes from `render.py` and the report router is registered:

```python
from . import db
from .api import files, projects, report, report_data
from .config import settings
from .report.render import chromium_available
from .workers.jobs import recover_stuck_files
from .workers.pool import pool
```
Remove the local `pdf_renderer_available` function, use `app.state.pdf_renderer = await asyncio.to_thread(chromium_available)` in `lifespan`, and register `for r in (projects.router, files.router, report_data.router, report.router):`.

- [ ] **Step 7: Run the tests**

Run: `pytest tests/test_api_report.py -v`
Expected: PASS (the PDF branch runs when Chromium is installed; the other branch otherwise)

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: PDF rendering with Chromium, report versions API and render job"
```

---

### Task 26: Optional AI narrative drafting (skip if behind schedule)

Drafts only the empty narrative fields, only from the structured section values (never from raw files), stores them as `ai_draft` so the user must review, and works entirely without a key (the button is simply disabled). Uses the Anthropic SDK with server-side refusal fallbacks enabled.

**Files:**
- Create: `backend/app/services/__init__.py` (empty), `backend/app/services/narrative.py`, `backend/tests/test_narrative.py`
- Modify: `backend/app/workers/jobs.py` (append `draft_narratives`), `backend/app/api/report_data.py` (append endpoint)

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_narrative.py
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.consolidate.builder import build
from app.main import app
from app.services.narrative import NARRATIVES, draft_all, section_values
from tests.test_builder import sample_files


class FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        instruction = kwargs["messages"][0]["content"].split("\n")[0]
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=f"Draft: {instruction[:20]}")])


def fake_client():
    msgs = FakeMessages()
    return SimpleNamespace(beta=SimpleNamespace(messages=msgs)), msgs


def test_draft_all_fills_only_empty_narratives_from_section_values():
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    data.field("commentary.fields.takeaway").override = "Already written."
    client, msgs = fake_client()
    drafts = draft_all(data, model="claude-opus-5", client=client)
    assert "commentary.fields.takeaway" not in drafts and "commentary.fields.revenue_body" in drafts
    assert len(drafts) == len(NARRATIVES) - 1 and all(t.startswith("Draft: ") for t in drafts.values())
    call = msgs.calls[0]
    assert call["model"] == "claude-opus-5" and call["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in call["betas"]
    assert '"total_revenue"' in call["messages"][0]["content"] and "Never invent" in call["system"]
    sv = section_values(data, "financials")
    assert sv["tables"]["lines"]["rows"]["noi"]["ptd_actual"] == 550 and "longtext" not in str(sv)


def test_refusals_and_insufficient_data_are_skipped():
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    refusing = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(stop_reason="refusal", content=[]))))
    assert draft_all(data, client=refusing) == {}
    empty = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="INSUFFICIENT DATA")]))))
    assert draft_all(data, client=empty) == {}


def test_narratives_endpoint_requires_key():
    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "N"}).json()["id"]
        assert client.post(f"/api/projects/{pid}/narratives").status_code == 503
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_narrative.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services'`

- [ ] **Step 3: Write `backend/app/services/narrative.py`**

```python
"""Optional: draft narrative paragraphs with Claude from the structured numbers only.

The prompt carries the effective values of the relevant sections as JSON, never the source files, so the
model can only phrase numbers the reviewer already sees. Drafts are stored with status `ai_draft`.
"""
from __future__ import annotations

import json
from typing import Any

from ..config import settings
from ..models import ReportData

SYSTEM = (
    "You write concise commentary for a quarterly multifamily investor report. Use only the numbers in the JSON provided. "
    "Never invent figures, names, dates or events. Write two to four plain sentences: no bullet points, no headings, "
    "no em dashes. If the data needed for the request is missing, reply with exactly: INSUFFICIENT DATA"
)

# (field path, instruction, sections whose effective values are sent)
NARRATIVES: list[tuple[str, str, list[str]]] = [
    ("commentary.fields.takeaway", "Write the quarter's headline takeaway: revenue versus budget, NOI versus budget, and net cash flow after debt service.", ["commentary"]),
    ("commentary.fields.revenue_body", "Explain the revenue variance versus budget using gross potential rent, gain or loss to lease, concessions and vacancy.", ["commentary", "financials"]),
    ("commentary.fields.opex_body", "Explain the operating expense variance versus budget, naming the largest favourable and unfavourable lines.", ["commentary", "financials"]),
    ("commentary.fields.noi_body", "Explain NOI and net cash flow after debt service versus budget, then summarise capital spend versus budget.", ["commentary", "capex"]),
    ("in_place_rent.fields.narrative", "Describe how in-place rents moved quarter over quarter by floor plan and overall.", ["in_place_rent"]),
    ("submarket.fields.occupancy_narrative", "Compare the subject's occupancy with the comp set leased percentages.", ["submarket", "occupancy"]),
    ("submarket.fields.rent_narrative", "Compare the subject's asking and effective rent with the comp set average.", ["submarket"]),
    ("submarket.fields.concession_narrative", "Compare the subject's concession level with the comp set.", ["submarket"]),
    ("occupancy.fields.new_lease_narrative", "Summarise new-lease trade-outs by floor plan and overall.", ["occupancy"]),
    ("occupancy.fields.renewal_narrative", "Summarise renewal trade-outs by floor plan and overall.", ["occupancy"]),
    ("capex.fields.narrative", "Summarise capital spend for the quarter and year to date versus budget, naming the largest items.", ["capex", "commentary"]),
]


def section_values(data: ReportData, key: str) -> dict[str, Any]:
    """Effective values of one section, without narrative fields, as plain JSON-able dicts."""
    sec = data.sections.get(key)
    if sec is None:
        return {}
    out: dict[str, Any] = {"fields": {k: f.effective for k, f in sec.fields.items() if f.effective is not None and f.kind != "longtext"}, "tables": {}}
    for tk, t in sec.tables.items():
        out["tables"][tk] = {
            "rows": {rk: {ck: c.effective for ck, c in row.items() if c.effective is not None} for rk, row in t.rows.items()},
            "totals": {ck: c.effective for ck, c in t.totals.items() if c.effective is not None},
        }
    return out


def draft_all(data: ReportData, model: str | None = None, client: Any = None) -> dict[str, str]:
    """Return {field path: draft text} for every narrative field that is still empty."""
    if client is None:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    model = model or settings.anthropic_model
    drafts: dict[str, str] = {}
    for path, instruction, sections in NARRATIVES:
        fld = data.field(path)
        if fld is None or fld.effective not in (None, ""):
            continue
        payload = {"property": data.meta.get("property_name"), "period": data.meta.get("period"),
                   **{s: section_values(data, s) for s in sections}}
        response = client.beta.messages.create(
            model=model,
            max_tokens=1024,  # deliberately short: two to four sentences
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM,
            messages=[{"role": "user", "content": f"{instruction}\n\nDATA (JSON):\n{json.dumps(payload, default=str)}"}],
        )
        if response.stop_reason == "refusal":
            continue
        text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text").strip()
        if text and "INSUFFICIENT DATA" not in text.upper():
            drafts[path] = text
    return drafts
```

- [ ] **Step 4: Append to `backend/app/workers/jobs.py`**

```python
def draft_narratives(project_id: str) -> None:
    """Draft empty narrative fields with the LLM and store them as ai_drafts in the overrides."""
    from ..services.narrative import draft_all

    db.set_narrative(project_id, "running", None)
    try:
        data, _issues, row = load_effective(project_id)
        drafts = draft_all(data)
        ov = row.get("overrides") or {}
        ov.setdefault("ai_drafts", {}).update(drafts)
        db.save_overrides(project_id, ov)
        db.set_narrative(project_id, "done", None if drafts else "Nothing to draft: every narrative field already has text, or the data was insufficient")
    except Exception as e:  # noqa: BLE001 - shown to the user on the review screen
        log.exception("narrative drafting failed")
        db.set_narrative(project_id, "failed", f"{type(e).__name__}: {e}")
```

- [ ] **Step 5: Append to `backend/app/api/report_data.py`**

```python
@router.post("/projects/{pid}/narratives", status_code=202)
def draft_narratives(pid: str) -> dict:
    from ..config import settings
    from ..workers.pool import pool

    project_or_404(pid)
    if not settings.llm_enabled:
        raise HTTPException(503, "AI drafting is not configured: set ANTHROPIC_API_KEY in .env and restart the backend")
    row = db.get_report_data(pid)
    if row is None or not row.get("data"):
        raise HTTPException(409, "Report data has not been built yet")
    queued = pool.submit(f"narratives:{pid}", jobs.draft_narratives, pid)
    return {"status": "queued" if queued else "already_running"}
```

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_narrative.py -v`
Expected: 3 PASS

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: optional AI narrative drafting from structured section values"
```

---

### Task 27: Integration test on the real dataset

Runs only when `TEST_DATASET_DIR` points at the client's `SOURCE FILES` folder (never committed). The expected numbers are the ones verified against the example report during analysis.

**Files:**
- Create: `backend/tests/test_dataset.py`

- [ ] **Step 1: Write the test**

```python
# backend/tests/test_dataset.py
import os
from pathlib import Path

import pytest

DATASET = os.getenv("TEST_DATASET_DIR")
pytestmark = pytest.mark.skipif(not DATASET, reason="set TEST_DATASET_DIR to the folder holding the real source files")


def test_real_dataset_end_to_end():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.workers.pool import pool

    paths = sorted(p for p in Path(DATASET).rglob("*") if p.suffix.lower() in (".xlsx", ".pdf") and not p.name.startswith("~$"))
    assert paths, "no source files found"
    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "dataset"}).json()["id"]
        for p in paths:
            with p.open("rb") as fh:
                assert client.post(f"/api/projects/{pid}/files", files=[("files", (p.name, fh, "application/octet-stream"))]).status_code == 201
        assert pool.wait_idle(180)
        detail = client.get(f"/api/projects/{pid}").json()
        bad = [(f["original_filename"], f["status"], f["error"]) for f in detail["files"] if f["status"] not in ("processed", "unsupported")]
        assert not bad, bad
        ui = client.get(f"/api/projects/{pid}/report-data").json()
        v = {f["path"]: f["effective"] for s in ui["sections"] for f in s["fields"]}
        cells = {c["path"]: c["effective"] for s in ui["sections"] for t in s["tables"] for r in t["rows"] for c in r["cells"]}
        cells.update({c["path"]: c["effective"] for s in ui["sections"] for t in s["tables"] for c in t["totals"]})
        assert v["property.fields.name"] == "The Boardwalk" and v["property.fields.units"] == 338
        assert v["property.fields.year_built"] == 1973 and v["property.fields.acquired_date"] == "2025-07-30"
        assert v["capital.fields.purchase_price"] == 48000000 and abs(v["capital.fields.equity_invested"] - 14259605.94) < 1
        assert abs(v["financing.fields.implied_rate"] - 0.0523) < 1e-4 and v["financing.fields.loan_amount"] == 36519000
        assert abs(cells["financials.tables.lines.rows.noi.ptd_actual"] - 636105.69) < 1
        assert abs(cells["financials.tables.lines.rows.total_revenue.ytd_actual"] - 2826719.16) < 1
        assert abs(cells["financials.tables.lines.rows.concessions.ptd_actual"] + 53131.05) < 1
        assert abs(cells["financials.tables.lines.rows.net_cash_flow.ptd_var"] + 134365.64) < 1
        assert abs(cells["capex.tables.lines.totals.ptd_actual"] - 241077.37) < 1 and abs(v["capex.fields.source_total_ptd"] - 241077.37) < 1
        assert abs(cells["capex.tables.lines.rows.plumbing_water_heaters.ptd_actual"] - 80252.75) < 1
        assert abs(cells["in_place_rent.tables.by_floor_plan.totals.current_rent"] - 1323.98) < 0.01
        assert abs(cells["in_place_rent.tables.by_floor_plan.rows.0br.current_rent"] - 1074.1) < 0.5
        assert abs(v["occupancy.fields.current_pct"] - 0.9053) < 1e-4 and v["occupancy.fields.change_bps"] == -118
        assert cells["occupancy.tables.new_leases.totals.count"] == 38 and abs(cells["occupancy.tables.new_leases.totals.lto_pct"] + 0.1762) < 1e-3
        assert cells["occupancy.tables.renewals.totals.count"] == 25
        assert abs(v["submarket.fields.vacancy"] - 0.1634) < 1e-3 and abs(v["submarket.fields.prior_vacancy"] - 0.1471) < 1e-3
        assert abs(cells["submarket.tables.comps.rows.the-ashlar.asking_rent"] - 1719) < 1
        assert abs(cells["submarket.tables.comps.rows.the-boardwalk.asking_rent"] - 1303) < 1
        assert v["submarket.fields.submarket_name"] == "Western Lee County" and v["property.fields.prepared_by"] == "ZMR Capital"
        assert not [i for i in ui["issues"] if i["severity"] == "error"], [i["message"] for i in ui["issues"] if i["severity"] == "error"]
```

- [ ] **Step 2: Run it against the real files**

Run: `TEST_DATASET_DIR="/Users/yashvibhandik/Desktop/Yash/Work/1.) The Boardwalk_2Q26 Source Files/SOURCE FILES" pytest tests/test_dataset.py -v -s`
Expected: PASS. For any failing assertion, open the review screen (or `GET /report-data`) and read the `source.locator` of the field: that tells you which line was matched, which is where the fix belongs (a mapping pattern in `config/*.toml` or a header pattern in the extractor). Do not special-case a value.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "test: end-to-end integration test against the supplied dataset (opt-in)"
```

---

### Task 28: README, developer notes, limitations

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

````markdown
# Investor Report Generator

Turns a folder of property source files (Yardi, HelloData, CoStar, Slate exports) into a quarterly LP investor report.
Upload files, review every extracted value with its source, correct what is wrong or missing, generate the PDF, edit, regenerate.

## Prerequisites

- Python 3.12 or newer
- Node.js 22 LTS and npm 10
- Chromium for PDF rendering (installed once by Playwright, see below)
- No cloud services are required. AI narrative drafting is optional and needs an Anthropic API key.

## Backend setup

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt                     # or requirements.txt without test/LLM extras
python -m playwright install chromium                   # one-time, ~150 MB, needed for PDF output
cp ../.env.example ../.env                              # edit if you want a different data folder or workers
uvicorn app.main:app --reload --port 8000
```

`GET http://localhost:8000/api/health` reports whether the PDF renderer and the LLM are available.

## Frontend setup

```bash
cd frontend
npm install
npm start                                               # Angular dev server on http://localhost:4200, proxies /api to :8000
```

## Environment variables (`.env` at the repo root)

| Variable | Default | Purpose |
|---|---|---|
| `APP_DATA_DIR` | `backend/data` | SQLite database, uploaded files, generated reports |
| `APP_WORKERS` | `3` | Parallel file-processing threads |
| `APP_MAX_UPLOAD_MB` | `50` | Per-file upload limit |
| `APP_CORS_ORIGINS` | `http://localhost:4200` | Allowed browser origins |
| `ANTHROPIC_API_KEY` | unset | Optional. Enables the "Draft narratives with AI" button |
| `ANTHROPIC_MODEL` | `claude-opus-5` | Model used for drafting |

## External services

| Service | Purpose | Variable | Credentials |
|---|---|---|---|
| Anthropic Claude API | Drafts narrative paragraphs from the structured, reviewed numbers. Optional; the app is fully functional without it. | `ANTHROPIC_API_KEY` | The user supplies their own key in `.env`. Requests are made with server-side refusal fallbacks enabled (`fallbacks: "default"`). |

Nothing else leaves the machine. Playwright's Chromium is downloaded once at setup time.

## Using the application

1. **Create a report**: Projects page, enter a name, Create.
2. **Upload source files**: Files page, drop or pick `.xlsx` / `.pdf` files (any names, any order). Each file shows a status: queued, processing, processed, failed, unsupported, and the report types detected inside it. One bad file never blocks the others.
3. **Review extracted data**: Review page. Left: report sections in page order. Every value shows a status chip (extracted, derived, manual, AI draft, missing, conflict) and a "source" button with the file, sheet or page, and row it came from. "Needs attention" filters to missing and conflicting values.
4. **Correct data**: type in any editable field or table cell and Save. Derived values recompute immediately. Conflicts show the alternatives; pick one. Tables such as the underwriting budget and the comp set accept new rows. "Reset" restores the extracted value.
5. **Generate the report**: Report page shows a live HTML preview. Generate PDF creates a new version; download it from the versions list.
6. **Regenerate**: edit on the Review page and press Generate again. Uploads are not reprocessed; edits are kept.

Generated files live under `APP_DATA_DIR/projects/<project id>/reports/report-v<N>.pdf` (and `.html`).

Setting a file's document type manually: if a file was not recognised, pick its type in the Files page dropdown and it is re-processed. "Exclude" removes a file from the report data without deleting it (useful when two exports overlap, for example two HelloData comp sets).

## Developer notes

### Architecture

```
Upload → readers (xlsx/pdf → Document) → classifier (content signatures → DocType per sheet/PDF)
      → extractors (DocType → typed JSON payload with row/page provenance)
      → builder (select sources, consolidate into ReportData: sections of Fields and Tables)
      → calc.recompute (derived values) → validate (missing / conflict / reconciliation issues)
      → review UI (edits stored as overrides, applied on every read)
      → Jinja HTML template → Chromium PDF
```

Files are processed by an in-process thread pool; each file is an isolated job. When the last file finishes, consolidation runs automatically. Per-file extraction payloads, the consolidated data, the user's overrides and the report versions are stored in SQLite (`app.db`).

### Extraction strategy

- Every document is located by **content**, never by filename: a Yardi Budget Comparison is a sheet whose header says "Budget Comparison" with Actual/Budget columns; a rent roll is a sheet with a "Summary Groups" block; HelloData listings are a sheet with Property Name / Asking Rent / Effective Rent columns, and so on (`classify/classifier.py`).
- Inside a document, values are located by **header and label text**. Multi-row headers are joined; Yardi's leading-space indentation is used to track section hierarchy so capital lines can be told apart from operating lines.
- The financial table maps canonical rows (Gross Potential Rent, Payroll, NOI ...) to source lines through regex patterns in `backend/config/pl_mapping.toml`; capital-project regrouping lives in `capex_mapping.toml`. Both are editable without touching code.
- Derived values (variances, weighted averages, per-unit figures, comp averages) are computed from inputs, so a corrected input updates everything that depends on it.
- Every extracted value keeps `{file, sheet or page, row}` provenance, shown in the UI as the "source" of the value.

### Generalization strategy

- Nothing keys on filenames, sheet names, cell coordinates, unit-type codes or GL account numbers.
- Multiple candidate sources for the same section are ranked deterministically (for example the Budget Comparison with YTD columns wins over a monthly one; a standalone HelloData export wins over the same sheet inside a full report), the alternatives are listed as issues, and the user can exclude a file to switch.
- Missing files degrade gracefully: the section's fields become `missing` and editable; the rest of the report still generates.
- Percentages are normalised to fractions regardless of how the source expresses them; dates are parsed from several formats.
- The dataset integration test (`tests/test_dataset.py`) is opt-in and asserts totals, not layout.

### Known limitations

- Loan terms, the original underwriting budget, property description facts (acreage, class, hold period) and status-update narratives are not present in any supplied source file. They are manual fields flagged as missing.
- The rent trend chart needs the pre-built rent chart workbook for a full 12-month history; without it the chart is computed from whatever months the LTO and HelloData listings cover.
- Comp unit counts and vintages come from a HelloData comp summary when one is supplied; the unit-level listings export does not contain them.
- Image-only (scanned) PDFs are reported as unsupported; no OCR is implemented.
- The optional AI drafting sends section values (not files) to the Anthropic API and requires the user's key.
- No authentication or multi-user support; single local user by design.

### Next steps (another 40 hours)

1. OCR for scanned PDFs (Tesseract) behind the same reader interface.
2. A loan-document extractor (term sheet PDF) feeding the financing page.
3. Per-sheet document type overrides for multi-sheet workbooks.
4. Side-by-side source viewer on the review screen (open the sheet at the row the value came from).
5. Property photo and logo upload slots for the cover page.
6. A mapping editor in the UI for `pl_mapping.toml` / `capex_mapping.toml`.
7. Snapshot tests of the rendered HTML per section.

## Running the tests

```bash
cd backend && pytest -q
TEST_DATASET_DIR="/path/to/SOURCE FILES" pytest tests/test_dataset.py -v   # optional, needs the real files
```
````

- [ ] **Step 2: Run the whole suite one more time**

Run: `cd backend && pytest -q`
Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "docs: README with setup, usage, architecture, limitations and next steps"
```

---

# Part B: Frontend

The frontend is a thin, generic client of the API contract in section 0.4. It has no domain logic: it renders whatever sections, fields and tables the backend sends, and posts edits back by path.

### Task 29: Angular workspace, API client, shell and stepper

**Files:**
- Create (via CLI): `frontend/` workspace
- Create: `frontend/proxy.conf.json`, `frontend/src/main.ts`, `frontend/src/app/app.config.ts`, `frontend/src/app/app.routes.ts`, `frontend/src/app/app.component.ts`, `frontend/src/app/core/models.ts`, `frontend/src/app/core/api.service.ts`, `frontend/src/app/shared/stepper.component.ts`, `frontend/src/app/shared/status-chip.component.ts`

- [ ] **Step 1: Generate the workspace**

```bash
cd investor-report-app
npx -y @angular/cli@latest new frontend --directory frontend --style=css --routing --ssr=false --skip-git --skip-tests --package-manager=npm --defaults
cd frontend && rm -f src/app/app.ts src/app/app.html src/app/app.css src/app/app.spec.ts
```
Expected: `frontend/` with `angular.json`, `package.json`, `src/`. (Older CLIs name the root component files `app.component.*`; delete those too. We write our own below.)

- [ ] **Step 2: Write `frontend/proxy.conf.json` and wire it into `angular.json`**

```json
{ "/api": { "target": "http://localhost:8000", "secure": false, "changeOrigin": true } }
```

```bash
node -e "const fs=require('fs');const j=JSON.parse(fs.readFileSync('angular.json'));const p=j.projects[Object.keys(j.projects)[0]];p.architect.serve.options=Object.assign(p.architect.serve.options||{},{proxyConfig:'proxy.conf.json'});fs.writeFileSync('angular.json',JSON.stringify(j,null,2));"
```

- [ ] **Step 3: Write `frontend/src/main.ts`**

```ts
import { bootstrapApplication } from '@angular/platform-browser';
import { AppComponent } from './app/app.component';
import { appConfig } from './app/app.config';

bootstrapApplication(AppComponent, appConfig).catch((err) => console.error(err));
```

- [ ] **Step 4: Write `frontend/src/app/app.config.ts` and `frontend/src/app/app.routes.ts`**

```ts
// app.config.ts
import { ApplicationConfig, provideZoneChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [provideZoneChangeDetection({ eventCoalescing: true }), provideRouter(routes), provideHttpClient()],
};
```

```ts
// app.routes.ts
import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'projects', pathMatch: 'full' },
  { path: 'projects', loadComponent: () => import('./pages/projects/projects.component').then((m) => m.ProjectsComponent) },
  { path: 'projects/:id/files', loadComponent: () => import('./pages/files/files.component').then((m) => m.FilesComponent) },
  { path: 'projects/:id/review', loadComponent: () => import('./pages/review/review.component').then((m) => m.ReviewComponent) },
  { path: 'projects/:id/report', loadComponent: () => import('./pages/report/report.component').then((m) => m.ReportComponent) },
  { path: '**', redirectTo: 'projects' },
];
```

- [ ] **Step 5: Write `frontend/src/app/core/models.ts`**

```ts
export type FileStatus = 'queued' | 'processing' | 'processed' | 'failed' | 'unsupported';
export type Stage = 'upload' | 'processing' | 'review' | 'generated';

export interface Project { id: string; name: string; created_at: string; updated_at: string; file_count?: number; }
export interface Part { doc_type: string; confidence: number; locator: string; warnings: string[]; }
export interface ProjectFile {
  id: string; project_id: string; original_filename: string; ext: string; size: number; status: FileStatus;
  error: string | null; parts: Part[]; doc_type_override: string | null; ignored: boolean; uploaded_at: string; processed_at: string | null;
}
export interface Report { id: string; project_id: string; version: number; status: string; error: string | null; created_at: string; has_pdf: boolean; }
export interface ProjectDetail extends Project { files: ProjectFile[]; reports: Report[]; stage: Stage; report_built: boolean; processing: string[]; }
export interface DocTypeOption { key: string; label: string; }
export interface Health { ok: boolean; llm_enabled: boolean; pdf_renderer: boolean; workers: number; }
export interface Source { file_id?: string | null; filename?: string | null; locator?: string | null; text?: string | null; }
export interface Alternative { value: unknown; source: Source | null; note: string | null; }
export type Kind = 'money' | 'number' | 'integer' | 'percent' | 'date' | 'text' | 'longtext';
export type Status = 'extracted' | 'derived' | 'manual' | 'ai_draft' | 'missing' | 'conflict';
export interface UiField {
  path: string; key: string; label: string; kind: Kind; value: unknown; override: unknown; effective: unknown; status: Status;
  source: Source | null; alternatives: Alternative[]; note: string | null; readonly: boolean;
}
export interface UiColumn { key: string; label: string; kind: Kind; derived: boolean; }
export interface UiRow { key: string; label: string; manual: boolean; subject: boolean; cells: UiField[]; }
export interface UiTable { path: string; key: string; title: string; columns: UiColumn[]; rows: UiRow[]; totals: UiField[]; editable_rows: boolean; }
export interface UiSection { key: string; title: string; page: number; fields: UiField[]; tables: UiTable[]; }
export interface Issue { path: string | null; severity: 'error' | 'warning' | 'info'; message: string; }
export interface Summary { missing: number; conflicts: number; ai_drafts: number; errors: number; warnings: number; infos: number; }
export interface ReportDataUi {
  built_at: string | null; summary: Summary; issues: Issue[]; sections: UiSection[]; meta: Record<string, unknown>;
  narrative_status: string | null; narrative_error: string | null;
}
export interface Change { path: string; value: unknown; }
export interface PatchBody { changes?: Change[]; add_rows?: { table: string; key?: string; values: Record<string, unknown> }[]; delete_rows?: { table: string; key: string }[]; }
export interface FileExtraction { parts: Part[]; extractions: { doc_type: string; locator: string; data: unknown; warnings: string[] }[]; }
```

- [ ] **Step 6: Write `frontend/src/app/core/api.service.ts`**

```ts
import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { DocTypeOption, FileExtraction, Health, PatchBody, Project, ProjectDetail, ProjectFile, Report, ReportDataUi } from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private base = '/api';

  health(): Observable<Health> { return this.http.get<Health>(`${this.base}/health`); }
  docTypes(): Observable<DocTypeOption[]> { return this.http.get<DocTypeOption[]>(`${this.base}/doc-types`); }

  listProjects(): Observable<Project[]> { return this.http.get<Project[]>(`${this.base}/projects`); }
  createProject(name: string): Observable<Project> { return this.http.post<Project>(`${this.base}/projects`, { name }); }
  getProject(id: string): Observable<ProjectDetail> { return this.http.get<ProjectDetail>(`${this.base}/projects/${id}`); }
  deleteProject(id: string): Observable<void> { return this.http.delete<void>(`${this.base}/projects/${id}`); }

  uploadFiles(pid: string, files: File[]): Observable<ProjectFile[]> {
    const fd = new FormData();
    files.forEach((f) => fd.append('files', f, f.name));
    return this.http.post<ProjectFile[]>(`${this.base}/projects/${pid}/files`, fd);
  }
  patchFile(pid: string, fid: string, body: { ignored?: boolean; doc_type_override?: string; clear_override?: boolean }): Observable<ProjectFile> {
    return this.http.patch<ProjectFile>(`${this.base}/projects/${pid}/files/${fid}`, body);
  }
  reprocessFile(pid: string, fid: string): Observable<ProjectFile> { return this.http.post<ProjectFile>(`${this.base}/projects/${pid}/files/${fid}/reprocess`, {}); }
  deleteFile(pid: string, fid: string): Observable<void> { return this.http.delete<void>(`${this.base}/projects/${pid}/files/${fid}`); }
  fileExtraction(pid: string, fid: string): Observable<FileExtraction> { return this.http.get<FileExtraction>(`${this.base}/projects/${pid}/files/${fid}/extraction`); }

  reportData(pid: string): Observable<ReportDataUi> { return this.http.get<ReportDataUi>(`${this.base}/projects/${pid}/report-data`); }
  rebuildReportData(pid: string): Observable<ReportDataUi> { return this.http.post<ReportDataUi>(`${this.base}/projects/${pid}/report-data/rebuild`, {}); }
  patchReportData(pid: string, body: PatchBody): Observable<ReportDataUi> { return this.http.patch<ReportDataUi>(`${this.base}/projects/${pid}/report-data`, body); }
  draftNarratives(pid: string): Observable<{ status: string }> { return this.http.post<{ status: string }>(`${this.base}/projects/${pid}/narratives`, {}); }

  previewUrl(pid: string): string { return `${this.base}/projects/${pid}/report/preview?t=${Date.now()}`; }
  createReport(pid: string): Observable<Report> { return this.http.post<Report>(`${this.base}/projects/${pid}/reports`, {}); }
  listReports(pid: string): Observable<Report[]> { return this.http.get<Report[]>(`${this.base}/projects/${pid}/reports`); }
  getReport(pid: string, rid: string): Observable<Report> { return this.http.get<Report>(`${this.base}/projects/${pid}/reports/${rid}`); }
  downloadUrl(pid: string, rid: string): string { return `${this.base}/projects/${pid}/reports/${rid}/download`; }
}
```

- [ ] **Step 7: Write the shared components**

```ts
// frontend/src/app/shared/stepper.component.ts
import { Component, computed, input } from '@angular/core';
import { Stage } from '../core/models';

const STEPS = ['Upload', 'Process', 'Extract', 'Review', 'Correct', 'Generate', 'Download'];
const ACTIVE: Record<Stage, number> = { upload: 0, processing: 1, review: 3, generated: 6 };

@Component({
  selector: 'app-stepper',
  standalone: true,
  template: `
    <ol class="stepper">
      @for (s of steps; track s; let i = $index) {
        <li [class.done]="i < active()" [class.active]="i === active()"><span class="n">{{ i + 1 }}</span>{{ s }}</li>
      }
    </ol>`,
})
export class StepperComponent {
  stage = input<Stage>('upload');
  steps = STEPS;
  active = computed(() => ACTIVE[this.stage()] ?? 0);
}
```

```ts
// frontend/src/app/shared/status-chip.component.ts
import { Component, input } from '@angular/core';

const LABELS: Record<string, string> = {
  extracted: 'extracted', derived: 'derived', manual: 'edited', ai_draft: 'AI draft', missing: 'missing', conflict: 'conflict',
  queued: 'queued', processing: 'processing', processed: 'processed', failed: 'failed', unsupported: 'unsupported',
  rendering: 'rendering', done: 'done',
};

@Component({
  selector: 'app-status-chip',
  standalone: true,
  template: `<span class="chip chip-{{ status() }}">{{ label }}</span>`,
})
export class StatusChipComponent {
  status = input.required<string>();
  get label(): string { return LABELS[this.status()] ?? this.status(); }
}
```

- [ ] **Step 8: Write `frontend/src/app/app.component.ts`**

```ts
import { Component, inject, signal } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';
import { ApiService } from './core/api.service';
import { Health } from './core/models';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink],
  template: `
    <header class="topbar">
      <a routerLink="/projects" class="brand">Investor Report Generator</a>
      <span class="spacer"></span>
      @if (health(); as h) {
        <span class="muted small">PDF {{ h.pdf_renderer ? 'ready' : 'unavailable' }} · AI {{ h.llm_enabled ? 'on' : 'off' }}</span>
      } @else if (offline()) {
        <span class="err small">Backend not reachable on /api. Start it with: uvicorn app.main:app --port 8000</span>
      }
    </header>
    <main class="container"><router-outlet /></main>`,
})
export class AppComponent {
  private api = inject(ApiService);
  health = signal<Health | null>(null);
  offline = signal(false);
  constructor() {
    this.api.health().subscribe({ next: (h) => this.health.set(h), error: () => this.offline.set(true) });
  }
}
```

- [ ] **Step 9: Build once to catch type errors**

Run: `npx ng build --configuration development 2>&1 | tail -20`
Expected: build fails only because `pages/*` components do not exist yet (the router imports them). That is expected; the next three tasks add them. If it fails for any other reason, fix it now.

- [ ] **Step 10: Commit**

```bash
cd .. && git add -A && git commit -m "feat(frontend): Angular workspace, API client, shell and progress stepper"
```

---

### Task 30: Projects page

**Files:**
- Create: `frontend/src/app/pages/projects/projects.component.ts`

- [ ] **Step 1: Write the component**

```ts
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { Project } from '../../core/models';

@Component({
  selector: 'app-projects',
  standalone: true,
  imports: [FormsModule, RouterLink],
  template: `
    <h1>Reports</h1>
    <form class="row" (ngSubmit)="create()">
      <input name="name" [(ngModel)]="name" placeholder="New report name, e.g. The Boardwalk 2Q26" required />
      <button type="submit" [disabled]="!name.trim() || busy()">Create</button>
    </form>
    @if (error()) { <p class="err">{{ error() }}</p> }
    <table class="grid">
      <thead><tr><th>Name</th><th>Files</th><th>Updated</th><th></th></tr></thead>
      <tbody>
        @for (p of projects(); track p.id) {
          <tr>
            <td><a [routerLink]="['/projects', p.id, 'files']">{{ p.name }}</a></td>
            <td>{{ p.file_count ?? 0 }}</td>
            <td>{{ p.updated_at | slice: 0 : 16 }}</td>
            <td class="r"><button class="link danger" (click)="remove(p)">Delete</button></td>
          </tr>
        } @empty {
          <tr><td colspan="4" class="muted">No reports yet. Create one above.</td></tr>
        }
      </tbody>
    </table>`,
})
export class ProjectsComponent {
  private api = inject(ApiService);
  private router = inject(Router);
  projects = signal<Project[]>([]);
  name = '';
  busy = signal(false);
  error = signal<string | null>(null);

  constructor() { this.load(); }

  load(): void { this.api.listProjects().subscribe({ next: (ps) => this.projects.set(ps), error: (e) => this.error.set(e.message) }); }

  create(): void {
    this.busy.set(true);
    this.api.createProject(this.name.trim()).subscribe({
      next: (p) => { this.busy.set(false); this.router.navigate(['/projects', p.id, 'files']); },
      error: (e) => { this.busy.set(false); this.error.set(e.error?.detail ?? e.message); },
    });
  }

  remove(p: Project): void {
    if (!confirm(`Delete "${p.name}" and all its files and reports?`)) return;
    this.api.deleteProject(p.id).subscribe({ next: () => this.load(), error: (e) => this.error.set(e.message) });
  }
}
```

Add `SlicePipe` to the imports: `import { SlicePipe } from '@angular/common';` and `imports: [FormsModule, RouterLink, SlicePipe]`.

- [ ] **Step 2: Commit**

```bash
git add -A && git commit -m "feat(frontend): projects list and creation"
```

---

### Task 31: Files page (upload, status polling, document type override, reprocess, exclude, delete, raw extraction)

**Files:**
- Create: `frontend/src/app/pages/files/files.component.ts`

- [ ] **Step 1: Write the component**

```ts
import { JsonPipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subscription, interval, switchMap } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { DocTypeOption, FileExtraction, ProjectDetail, ProjectFile } from '../../core/models';
import { StatusChipComponent } from '../../shared/status-chip.component';
import { StepperComponent } from '../../shared/stepper.component';

@Component({
  selector: 'app-files',
  standalone: true,
  imports: [FormsModule, RouterLink, JsonPipe, StatusChipComponent, StepperComponent],
  template: `
    @if (project(); as p) {
      <app-stepper [stage]="p.stage" />
      <div class="row between">
        <h1>{{ p.name }} <span class="muted">· source files</span></h1>
        <nav class="row">
          <a [routerLink]="['/projects', p.id, 'review']" class="btn" [class.disabled]="!p.report_built">Review data →</a>
          <a [routerLink]="['/projects', p.id, 'report']" class="btn secondary" [class.disabled]="!p.report_built">Report</a>
        </nav>
      </div>
      <label class="dropzone" [class.drag]="dragging()" (dragover)="$event.preventDefault(); dragging.set(true)" (dragleave)="dragging.set(false)" (drop)="onDrop($event)">
        <input type="file" multiple accept=".xlsx,.xlsm,.pdf" (change)="onPick($event)" hidden />
        <strong>Drop files here or click to choose</strong>
        <span class="muted small">Yardi, HelloData, CoStar and Slate exports (.xlsx, .pdf). Any names, any order.</span>
      </label>
      @if (error()) { <p class="err">{{ error() }}</p> }
      <table class="grid">
        <thead><tr><th>File</th><th>Status</th><th>Detected as</th><th>Type override</th><th>Use</th><th></th></tr></thead>
        <tbody>
          @for (f of p.files; track f.id) {
            <tr [class.muted]="f.ignored">
              <td>{{ f.original_filename }}<div class="small muted">{{ (f.size / 1024) | number: '1.0-0' }} KB</div>
                @if (f.error) { <div class="small err">{{ f.error }}</div> }</td>
              <td><app-status-chip [status]="f.status" /></td>
              <td>
                @for (part of f.parts; track part.locator) {
                  <div class="small"><code>{{ part.locator }}</code> → <strong>{{ label(part.doc_type) }}</strong>
                    @if (part.doc_type !== 'unknown') { <span class="muted">({{ part.confidence * 100 | number: '1.0-0' }}%)</span> }
                    @for (w of part.warnings; track w) { <div class="warn">{{ w }}</div> }
                  </div>
                }
              </td>
              <td>
                @if (f.parts.length <= 1 && f.status !== 'unsupported') {
                  <select [ngModel]="f.doc_type_override ?? ''" (ngModelChange)="override(f, $event)">
                    <option value="">auto-detect</option>
                    @for (t of docTypes(); track t.key) { <option [value]="t.key">{{ t.label }}</option> }
                  </select>
                } @else { <span class="muted small">per-sheet (auto)</span> }
              </td>
              <td><label class="small"><input type="checkbox" [checked]="!f.ignored" (change)="toggleIgnore(f)" /> include</label></td>
              <td class="r nowrap">
                <button class="link" (click)="reprocess(f)" [disabled]="f.status === 'unsupported' || f.status === 'processing'">Reprocess</button>
                <button class="link" (click)="showExtraction(f)">Data</button>
                <button class="link danger" (click)="remove(f)">Remove</button>
              </td>
            </tr>
          } @empty { <tr><td colspan="6" class="muted">No files yet.</td></tr> }
        </tbody>
      </table>
      @if (extraction(); as ex) {
        <details open class="panel"><summary>Extracted payload <button class="link" (click)="extraction.set(null)">close</button></summary>
          <pre class="small">{{ ex | json }}</pre></details>
      }
    }`,
})
export class FilesComponent {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private destroy = inject(DestroyRef);
  private pid = this.route.snapshot.paramMap.get('id')!;
  private poll: Subscription | null = null;
  project = signal<ProjectDetail | null>(null);
  docTypes = signal<DocTypeOption[]>([]);
  extraction = signal<FileExtraction | null>(null);
  dragging = signal(false);
  error = signal<string | null>(null);

  constructor() {
    this.api.docTypes().subscribe((t) => this.docTypes.set(t));
    this.load();
  }

  label(key: string): string { return this.docTypes().find((t) => t.key === key)?.label ?? key; }

  load(): void {
    this.api.getProject(this.pid).subscribe({ next: (p) => { this.project.set(p); this.syncPolling(p); }, error: (e) => this.error.set(e.message) });
  }

  private syncPolling(p: ProjectDetail): void {
    const active = p.files.some((f) => f.status === 'queued' || f.status === 'processing');
    if (active && !this.poll) {
      this.poll = interval(2000).pipe(switchMap(() => this.api.getProject(this.pid)), takeUntilDestroyed(this.destroy))
        .subscribe((np) => { this.project.set(np); if (!np.files.some((f) => f.status === 'queued' || f.status === 'processing')) { this.poll?.unsubscribe(); this.poll = null; } });
    }
  }

  onPick(ev: Event): void { const input = ev.target as HTMLInputElement; this.upload(Array.from(input.files ?? [])); input.value = ''; }
  onDrop(ev: DragEvent): void { ev.preventDefault(); this.dragging.set(false); this.upload(Array.from(ev.dataTransfer?.files ?? [])); }

  upload(files: File[]): void {
    if (!files.length) return;
    this.api.uploadFiles(this.pid, files).subscribe({ next: () => this.load(), error: (e) => this.error.set(e.error?.detail ?? e.message) });
  }

  override(f: ProjectFile, key: string): void {
    const body = key ? { doc_type_override: key } : { clear_override: true };
    this.api.patchFile(this.pid, f.id, body).subscribe({ next: () => this.load(), error: (e) => this.error.set(e.error?.detail ?? e.message) });
  }
  toggleIgnore(f: ProjectFile): void { this.api.patchFile(this.pid, f.id, { ignored: !f.ignored }).subscribe({ next: () => this.load(), error: (e) => this.error.set(e.message) }); }
  reprocess(f: ProjectFile): void { this.api.reprocessFile(this.pid, f.id).subscribe({ next: () => this.load(), error: (e) => this.error.set(e.error?.detail ?? e.message) }); }
  remove(f: ProjectFile): void { if (confirm(`Remove ${f.original_filename}?`)) this.api.deleteFile(this.pid, f.id).subscribe({ next: () => this.load(), error: (e) => this.error.set(e.message) }); }
  showExtraction(f: ProjectFile): void { this.api.fileExtraction(this.pid, f.id).subscribe({ next: (ex) => this.extraction.set(ex), error: (e) => this.error.set(e.message) }); }
}
```

Add `DecimalPipe` to the imports (`import { DecimalPipe, JsonPipe } from '@angular/common';` and include `DecimalPipe` in `imports`) for the `number` pipe.

- [ ] **Step 2: Try it end to end**

Run backend (`uvicorn app.main:app --port 8000` in `backend/`) and frontend (`npm start` in `frontend/`), open http://localhost:4200, create a report, drop the files from `SOURCE FILES/`.
Expected: rows appear with `queued`, flip to `processing` then `processed` within seconds; each shows the detected report types per sheet; the docx-style file shows `unsupported`; "Review data" enables once processing ends.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat(frontend): file upload with status polling, type override, exclude and reprocess"
```

---

### Task 32: Review page (generic field and table editors, sources, filters, save, rows, AI drafts)

**Files:**
- Create: `frontend/src/app/pages/review/field-editor.component.ts`, `frontend/src/app/pages/review/table-editor.component.ts`, `frontend/src/app/pages/review/review.component.ts`

- [ ] **Step 1: Write `field-editor.component.ts`**

```ts
import { Component, computed, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { UiField } from '../../core/models';
import { StatusChipComponent } from '../../shared/status-chip.component';

export interface FieldChange { path: string; value: unknown; }

@Component({
  selector: 'app-field-editor',
  standalone: true,
  imports: [FormsModule, StatusChipComponent],
  template: `
    <div class="field" [class.attention]="needsAttention()">
      <div class="field-head">
        <label [for]="id">{{ f().label }}</label>
        <app-status-chip [status]="f().status" />
        @if (f().source; as s) {
          <button type="button" class="link small" (click)="showSource.set(!showSource())" title="Where did this value come from?">source</button>
        }
        @if (f().override !== null && f().override !== undefined) {
          <button type="button" class="link small" (click)="reset()">reset</button>
        }
      </div>
      @switch (f().kind) {
        @case ('longtext') { <textarea [id]="id" rows="4" [disabled]="f().readonly" [ngModel]="text()" (ngModelChange)="edit($event)"></textarea> }
        @case ('date') { <input [id]="id" type="date" [disabled]="f().readonly" [ngModel]="text()" (ngModelChange)="edit($event)" /> }
        @case ('text') { <input [id]="id" type="text" [disabled]="f().readonly" [ngModel]="text()" (ngModelChange)="edit($event)" /> }
        @default { <input [id]="id" type="number" step="any" [disabled]="f().readonly" [ngModel]="numberText()" (ngModelChange)="editNumber($event)" />
          @if (f().kind === 'percent') { <span class="unit">%</span> } }
      }
      @if (f().alternatives.length) {
        <div class="alts small">
          <span class="muted">Sources disagree. Choose:</span>
          <label><input type="radio" [name]="id + '-alt'" [checked]="isChosen(f().value)" (change)="choose(f().value)" /> {{ fmt(f().value) }} <span class="muted">({{ f().source?.filename }})</span></label>
          @for (a of f().alternatives; track $index) {
            <label><input type="radio" [name]="id + '-alt'" [checked]="isChosen(a.value)" (change)="choose(a.value)" /> {{ fmt(a.value) }} <span class="muted">({{ a.source?.filename }}{{ a.note ? ', ' + a.note : '' }})</span></label>
          }
        </div>
      }
      @if (f().note) { <div class="small muted">{{ f().note }}</div> }
      @if (showSource() && f().source; as s) {
        <div class="source small"><strong>{{ s.filename ?? 'computed' }}</strong> {{ s.locator }} @if (s.text) { <span class="muted">· "{{ s.text }}"</span> }</div>
      }
    </div>`,
})
export class FieldEditorComponent {
  f = input.required<UiField>();
  compact = input(false);
  changed = output<FieldChange>();
  showSource = signal(false);
  private counter = Math.random().toString(36).slice(2, 8);
  get id(): string { return 'f-' + this.counter; }

  needsAttention = computed(() => (this.f().status === 'missing' && this.f().effective == null) || this.f().status === 'conflict' || this.f().status === 'ai_draft');
  text = computed(() => (this.f().effective == null ? '' : String(this.f().effective)));
  numberText = computed(() => {
    const v = this.f().effective;
    if (v == null || v === '') return '';
    return this.f().kind === 'percent' ? String(Math.round(Number(v) * 1e6) / 1e4) : String(v);
  });

  edit(value: string): void { this.changed.emit({ path: this.f().path, value: value === '' ? null : value }); }
  editNumber(value: string | number | null): void {
    if (value === '' || value === null || value === undefined) { this.changed.emit({ path: this.f().path, value: null }); return; }
    const n = Number(value);
    this.changed.emit({ path: this.f().path, value: this.f().kind === 'percent' ? n / 100 : n });
  }
  reset(): void { this.changed.emit({ path: this.f().path, value: null }); }
  choose(v: unknown): void { this.changed.emit({ path: this.f().path, value: v }); }
  isChosen(v: unknown): boolean { return this.f().effective === v; }
  fmt(v: unknown): string { return typeof v === 'number' ? v.toLocaleString() : String(v ?? '—'); }
}
```

- [ ] **Step 2: Write `table-editor.component.ts`**

```ts
import { Component, input, output } from '@angular/core';
import { UiRow, UiTable } from '../../core/models';
import { FieldChange, FieldEditorComponent } from './field-editor.component';

@Component({
  selector: 'app-table-editor',
  standalone: true,
  imports: [FieldEditorComponent],
  template: `
    <div class="table-block">
      <div class="row between"><h3>{{ t().title }}</h3>
        @if (t().editable_rows) { <button type="button" class="link" (click)="addRow.emit(t().path)">+ add row</button> }
      </div>
      <div class="scroll">
      <table class="grid cells">
        <thead><tr><th>Row</th>@for (c of t().columns; track c.key) { <th>{{ c.label }}</th> }<th></th></tr></thead>
        <tbody>
          @for (r of rows(); track r.key) {
            <tr [class.subject]="r.subject">
              <td class="rowlabel">{{ r.label }} @if (r.manual) { <span class="chip chip-manual">added</span> }</td>
              @for (cell of r.cells; track cell.path) {
                <td><app-field-editor [f]="cell" [compact]="true" (changed)="changed.emit($event)" /></td>
              }
              <td class="r">@if (t().editable_rows || r.manual) { <button type="button" class="link danger small" (click)="deleteRow.emit({ table: t().path, key: r.key })">delete</button> }</td>
            </tr>
          } @empty { <tr><td [attr.colspan]="t().columns.length + 2" class="muted">No rows extracted.@if (t().editable_rows) { Add rows manually.}</td></tr> }
          @if (t().totals.length) {
            <tr class="totals"><td class="rowlabel">Total</td>
              @for (c of t().columns; track c.key) {
                <td>@if (totalFor(c.key); as cell) { <app-field-editor [f]="cell" [compact]="true" (changed)="changed.emit($event)" /> }</td>
              }<td></td></tr>
          }
        </tbody>
      </table>
      </div>
    </div>`,
})
export class TableEditorComponent {
  t = input.required<UiTable>();
  attentionOnly = input(false);
  changed = output<FieldChange>();
  addRow = output<string>();
  deleteRow = output<{ table: string; key: string }>();

  rows(): UiRow[] {
    if (!this.attentionOnly()) return this.t().rows;
    return this.t().rows.filter((r) => r.cells.some((c) => (c.status === 'missing' && c.effective == null) || c.status === 'conflict'));
  }
  totalFor(key: string) { return this.t().totals.find((c) => c.key === key) ?? null; }
}
```

- [ ] **Step 3: Write `review.component.ts`**

```ts
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { interval, switchMap, takeWhile } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { Health, Issue, ProjectDetail, ReportDataUi, UiSection } from '../../core/models';
import { StepperComponent } from '../../shared/stepper.component';
import { FieldChange, FieldEditorComponent } from './field-editor.component';
import { TableEditorComponent } from './table-editor.component';

@Component({
  selector: 'app-review',
  standalone: true,
  imports: [RouterLink, StepperComponent, FieldEditorComponent, TableEditorComponent],
  template: `
    @if (project(); as p) {
      <app-stepper [stage]="pending().size ? 'review' : p.stage" />
      <div class="row between">
        <h1>{{ p.name }} <span class="muted">· review extracted data</span></h1>
        <nav class="row">
          <a [routerLink]="['/projects', p.id, 'files']" class="btn secondary">← Files</a>
          <a [routerLink]="['/projects', p.id, 'report']" class="btn" [class.disabled]="pending().size > 0">Report →</a>
        </nav>
      </div>
    }
    @if (error()) { <p class="err">{{ error() }}</p> }
    @if (data(); as d) {
      <div class="toolbar row between">
        <div class="row">
          <label class="small"><input type="checkbox" [checked]="attentionOnly()" (change)="attentionOnly.set(!attentionOnly())" /> needs attention only</label>
          <span class="small muted">{{ d.summary.missing }} missing · {{ d.summary.conflicts }} conflicts · {{ d.summary.ai_drafts }} AI drafts · {{ d.summary.errors }} errors · {{ d.summary.warnings }} warnings</span>
        </div>
        <div class="row">
          <button type="button" class="secondary" (click)="rebuild()" [disabled]="saving()">Rebuild from files</button>
          @if (health()?.llm_enabled) {
            <button type="button" class="secondary" (click)="draft()" [disabled]="drafting()">{{ drafting() ? 'Drafting…' : 'Draft narratives with AI' }}</button>
          }
          <button type="button" (click)="save()" [disabled]="!pending().size || saving()">{{ saving() ? 'Saving…' : 'Save ' + (pending().size ? '(' + pending().size + ')' : '') }}</button>
        </div>
      </div>
      @if (d.narrative_error) { <p class="warn small">AI drafting: {{ d.narrative_error }}</p> }
      <div class="review-layout">
        <aside class="sections">
          @for (s of d.sections; track s.key) {
            <button type="button" class="section-link" [class.active]="s.key === selected()" (click)="selected.set(s.key)">
              <span class="pg">p{{ s.page }}</span> {{ s.title }}
              @if (attentionCount(s); as n) { <span class="badge">{{ n }}</span> }
            </button>
          }
          <details class="issues"><summary>Issues ({{ d.issues.length }})</summary>
            @for (i of d.issues; track $index) { <div class="issue issue-{{ i.severity }} small" (click)="jump(i)">{{ i.message }}</div> }
          </details>
        </aside>
        <section class="editor">
          @if (section(); as s) {
            <h2>{{ s.title }} <span class="muted small">page {{ s.page }}</span></h2>
            <div class="fields">
              @for (f of visibleFields(s); track f.path) { <app-field-editor [f]="f" (changed)="onChange($event)" /> }
            </div>
            @for (t of s.tables; track t.path) {
              <app-table-editor [t]="t" [attentionOnly]="attentionOnly()" (changed)="onChange($event)" (addRow)="addRow($event)" (deleteRow)="deleteRow($event)" />
            }
          }
        </section>
      </div>
    } @else if (!error()) { <p class="muted">Loading…</p> }`,
})
export class ReviewComponent {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private destroy = inject(DestroyRef);
  private pid = this.route.snapshot.paramMap.get('id')!;
  project = signal<ProjectDetail | null>(null);
  data = signal<ReportDataUi | null>(null);
  health = signal<Health | null>(null);
  selected = signal<string>('property');
  attentionOnly = signal(false);
  pending = signal<Map<string, unknown>>(new Map());
  saving = signal(false);
  drafting = signal(false);
  error = signal<string | null>(null);
  section = computed<UiSection | null>(() => this.data()?.sections.find((s) => s.key === this.selected()) ?? null);

  constructor() {
    this.api.getProject(this.pid).subscribe({ next: (p) => this.project.set(p), error: (e) => this.error.set(e.message) });
    this.api.health().subscribe((h) => this.health.set(h));
    this.load();
  }

  load(): void {
    this.api.reportData(this.pid).subscribe({
      next: (d) => { this.data.set(d); if (d.narrative_status === 'running') this.watchNarratives(); },
      error: (e) => this.error.set(e.error?.detail ?? e.message),
    });
  }

  attention(f: { status: string; effective: unknown }): boolean { return (f.status === 'missing' && f.effective == null) || f.status === 'conflict' || f.status === 'ai_draft'; }
  attentionCount(s: UiSection): number {
    return s.fields.filter((f) => this.attention(f)).length + s.tables.reduce((n, t) => n + t.rows.reduce((m, r) => m + r.cells.filter((c) => this.attention(c)).length, 0), 0);
  }
  visibleFields(s: UiSection) { return this.attentionOnly() ? s.fields.filter((f) => this.attention(f)) : s.fields; }

  onChange(ch: FieldChange): void { const m = new Map(this.pending()); m.set(ch.path, ch.value); this.pending.set(m); }

  save(): void {
    const changes = Array.from(this.pending().entries()).map(([path, value]) => ({ path, value }));
    this.saving.set(true);
    this.api.patchReportData(this.pid, { changes }).subscribe({
      next: (d) => { this.data.set(d); this.pending.set(new Map()); this.saving.set(false); },
      error: (e) => { this.saving.set(false); this.error.set(e.error?.detail ?? e.message); },
    });
  }
  addRow(table: string): void {
    this.api.patchReportData(this.pid, { add_rows: [{ table, values: {} }] }).subscribe({ next: (d) => this.data.set(d), error: (e) => this.error.set(e.error?.detail ?? e.message) });
  }
  deleteRow(ev: { table: string; key: string }): void {
    if (!confirm('Remove this row from the report?')) return;
    this.api.patchReportData(this.pid, { delete_rows: [ev] }).subscribe({ next: (d) => this.data.set(d), error: (e) => this.error.set(e.error?.detail ?? e.message) });
  }
  rebuild(): void {
    if (this.pending().size && !confirm('Unsaved edits will be lost. Rebuild anyway?')) return;
    this.saving.set(true);
    this.api.rebuildReportData(this.pid).subscribe({ next: (d) => { this.data.set(d); this.pending.set(new Map()); this.saving.set(false); }, error: (e) => { this.saving.set(false); this.error.set(e.error?.detail ?? e.message); } });
  }
  draft(): void {
    this.drafting.set(true);
    this.api.draftNarratives(this.pid).subscribe({ next: () => this.watchNarratives(), error: (e) => { this.drafting.set(false); this.error.set(e.error?.detail ?? e.message); } });
  }
  private watchNarratives(): void {
    this.drafting.set(true);
    interval(2000).pipe(switchMap(() => this.api.reportData(this.pid)), takeWhile((d) => d.narrative_status === 'running', true), takeUntilDestroyed(this.destroy))
      .subscribe({ next: (d) => { this.data.set(d); if (d.narrative_status !== 'running') this.drafting.set(false); }, error: () => this.drafting.set(false) });
  }
  jump(i: Issue): void { if (i.path) this.selected.set(i.path.split('.')[0]); }
}
```

- [ ] **Step 4: Try it**

Open the review page for a processed project.
Expected: the section list shows attention badges; page 4 (Financing) is mostly `missing`; editing a P&L actual and saving updates its variance and the NOI reconciliation issue; "source" shows `financials.xlsx sheet 'Report1' rows 121`; the conflict on purchase price offers the CoStar alternative; "+ add row" on the underwriting table adds an editable row; AI button is hidden without a key.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(frontend): review screen with generic field/table editors, sources, conflicts and AI drafts"
```

---

### Task 33: Report page (preview, generate, versions, download)

**Files:**
- Create: `frontend/src/app/pages/report/report.component.ts`

- [ ] **Step 1: Write the component**

```ts
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { interval, switchMap, takeWhile } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { ProjectDetail, Report, ReportDataUi } from '../../core/models';
import { StatusChipComponent } from '../../shared/status-chip.component';
import { StepperComponent } from '../../shared/stepper.component';

@Component({
  selector: 'app-report',
  standalone: true,
  imports: [RouterLink, StepperComponent, StatusChipComponent],
  template: `
    @if (project(); as p) {
      <app-stepper [stage]="p.stage" />
      <div class="row between">
        <h1>{{ p.name }} <span class="muted">· report</span></h1>
        <nav class="row">
          <a [routerLink]="['/projects', p.id, 'review']" class="btn secondary">← Review</a>
          <button type="button" (click)="generate()" [disabled]="generating()">{{ generating() ? 'Rendering…' : 'Generate PDF' }}</button>
        </nav>
      </div>
      @if (summary(); as s) {
        @if (s.missing || s.conflicts || s.errors) {
          <p class="warn small">{{ s.missing }} missing values will print as "—", {{ s.conflicts }} unresolved conflicts use the primary source, {{ s.errors }} errors. You can still generate; fix them on the Review page and regenerate.</p>
        }
      }
      @if (error()) { <p class="err">{{ error() }}</p> }
      <div class="report-layout">
        <div class="preview"><iframe [src]="previewUrl()" title="Report preview"></iframe></div>
        <aside class="versions">
          <h3>Versions</h3>
          @for (r of reports(); track r.id) {
            <div class="version">
              <div><strong>v{{ r.version }}</strong> <span class="small muted">{{ r.created_at.slice(0, 16) }}</span></div>
              <div class="row"><app-status-chip [status]="r.status" />
                @if (r.status === 'done') { <a class="btn small" [href]="api.downloadUrl(pid, r.id)" target="_blank" rel="noopener">Download PDF</a> }
              </div>
              @if (r.error) { <div class="small err">{{ r.error }}</div> }
            </div>
          } @empty { <p class="muted small">No PDF generated yet.</p> }
          <button type="button" class="link small" (click)="refreshPreview()">Refresh preview</button>
        </aside>
      </div>
    }`,
})
export class ReportComponent {
  api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private sanitizer = inject(DomSanitizer);
  private destroy = inject(DestroyRef);
  pid = this.route.snapshot.paramMap.get('id')!;
  project = signal<ProjectDetail | null>(null);
  reports = signal<Report[]>([]);
  summary = signal<ReportDataUi['summary'] | null>(null);
  previewUrl = signal<SafeResourceUrl>(this.sanitizer.bypassSecurityTrustResourceUrl(this.api.previewUrl(this.pid)));
  generating = signal(false);
  error = signal<string | null>(null);

  constructor() {
    this.api.getProject(this.pid).subscribe({ next: (p) => { this.project.set(p); this.reports.set(p.reports); if (p.reports.some((r) => r.status === 'queued' || r.status === 'rendering')) this.watch(); }, error: (e) => this.error.set(e.message) });
    this.api.reportData(this.pid).subscribe({ next: (d) => this.summary.set(d.summary), error: () => this.summary.set(null) });
  }

  refreshPreview(): void { this.previewUrl.set(this.sanitizer.bypassSecurityTrustResourceUrl(this.api.previewUrl(this.pid))); }

  generate(): void {
    this.generating.set(true);
    this.api.createReport(this.pid).subscribe({ next: () => this.watch(), error: (e) => { this.generating.set(false); this.error.set(e.error?.detail ?? e.message); } });
  }

  private watch(): void {
    this.generating.set(true);
    interval(1500).pipe(switchMap(() => this.api.listReports(this.pid)), takeWhile((rs) => rs.some((r) => r.status === 'queued' || r.status === 'rendering'), true), takeUntilDestroyed(this.destroy))
      .subscribe({ next: (rs) => { this.reports.set(rs); if (!rs.some((r) => r.status === 'queued' || r.status === 'rendering')) { this.generating.set(false); this.api.getProject(this.pid).subscribe((p) => this.project.set(p)); } }, error: (e) => { this.generating.set(false); this.error.set(e.message); } });
  }
}
```

- [ ] **Step 2: Try it**

Expected: the preview iframe shows the ten pages; Generate PDF adds "v1 rendering" then "v1 done" with a Download link that opens a PDF; a second Generate after an edit produces v2.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat(frontend): report preview, PDF generation and version downloads"
```

---

### Task 34: Styles, production build, final smoke test

**Files:**
- Create: `frontend/src/styles.css` (replace generated file)

- [ ] **Step 1: Write `frontend/src/styles.css`**

```css
:root { --navy: #1b3a6b; --red: #b3261e; --amber: #9a6700; --green: #1f7a4d; --ink: #1a1a1a; --mute: #6b6b6b; --line: #d9d9d9; --wash: #f4f5f7; }
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, "Segoe UI", Roboto, sans-serif; font-size: 14px; color: var(--ink); background: #fff; }
a { color: var(--navy); }
h1 { font-size: 20px; margin: 12px 0; } h2 { font-size: 17px; margin: 8px 0; } h3 { font-size: 14px; margin: 6px 0; }
.topbar { display: flex; align-items: center; gap: 12px; padding: 10px 20px; background: var(--navy); color: #fff; }
.topbar .brand { color: #fff; text-decoration: none; font-weight: 600; } .topbar .spacer { flex: 1; } .topbar .muted { color: #cfd8e6; } .topbar .err { color: #ffd5d1; }
.container { padding: 16px 20px; max-width: 1400px; margin: 0 auto; }
.row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; } .between { justify-content: space-between; }
.muted { color: var(--mute); } .small { font-size: 12px; } .err { color: var(--red); } .warn { color: var(--amber); } .r { text-align: right; } .nowrap { white-space: nowrap; }
button, .btn { font: inherit; padding: 6px 12px; border-radius: 4px; border: 1px solid var(--navy); background: var(--navy); color: #fff; cursor: pointer; text-decoration: none; display: inline-block; }
button.secondary, .btn.secondary { background: #fff; color: var(--navy); }
button:disabled, .btn.disabled { opacity: 0.45; pointer-events: none; }
button.link { background: none; border: none; color: var(--navy); padding: 2px 6px; text-decoration: underline; } button.link.danger { color: var(--red); }
.btn.small { padding: 3px 8px; font-size: 12px; }
input, select, textarea { font: inherit; padding: 5px 7px; border: 1px solid var(--line); border-radius: 4px; width: 100%; }
input[type="checkbox"], input[type="radio"] { width: auto; }
.grid { width: 100%; border-collapse: collapse; margin-top: 10px; } .grid th { text-align: left; font-size: 12px; color: var(--mute); border-bottom: 1px solid var(--ink); padding: 6px; } .grid td { padding: 6px; border-bottom: 1px solid var(--line); vertical-align: top; }
.grid.cells td { padding: 3px 4px; min-width: 120px; } .grid.cells .rowlabel { min-width: 160px; font-weight: 600; } .grid.cells .totals td { border-top: 2px solid var(--ink); } .grid.cells tr.subject td { background: var(--wash); }
.scroll { overflow-x: auto; }
.chip { display: inline-block; font-size: 11px; padding: 1px 7px; border-radius: 10px; background: var(--wash); color: var(--mute); white-space: nowrap; }
.chip-extracted { background: #e6f0ea; color: var(--green); } .chip-derived { background: #eef1f6; color: var(--navy); } .chip-manual { background: #e9f1fb; color: #1d4ed8; }
.chip-ai_draft { background: #f3e8ff; color: #6b21a8; } .chip-missing { background: #fdecea; color: var(--red); } .chip-conflict { background: #fff4e0; color: var(--amber); }
.chip-processed, .chip-done { background: #e6f0ea; color: var(--green); } .chip-failed, .chip-unsupported { background: #fdecea; color: var(--red); } .chip-processing, .chip-rendering, .chip-queued { background: #fff4e0; color: var(--amber); }
.stepper { display: flex; gap: 6px; list-style: none; padding: 0; margin: 0 0 14px; } .stepper li { flex: 1; padding: 6px 8px; border-bottom: 3px solid var(--line); color: var(--mute); font-size: 12px; } .stepper li .n { display: inline-block; width: 18px; height: 18px; line-height: 18px; text-align: center; border-radius: 50%; background: var(--line); margin-right: 6px; font-size: 11px; }
.stepper li.done { border-color: var(--green); color: var(--ink); } .stepper li.done .n { background: var(--green); color: #fff; } .stepper li.active { border-color: var(--navy); color: var(--navy); font-weight: 600; } .stepper li.active .n { background: var(--navy); color: #fff; }
.dropzone { display: block; border: 2px dashed var(--line); border-radius: 6px; padding: 24px; text-align: center; margin: 12px 0; cursor: pointer; } .dropzone.drag { border-color: var(--navy); background: var(--wash); } .dropzone span { display: block; margin-top: 4px; }
.panel { margin-top: 12px; border: 1px solid var(--line); border-radius: 4px; padding: 8px; } .panel pre { max-height: 400px; overflow: auto; }
.toolbar { position: sticky; top: 0; background: #fff; padding: 8px 0; border-bottom: 1px solid var(--line); z-index: 2; }
.review-layout { display: grid; grid-template-columns: 260px 1fr; gap: 16px; margin-top: 12px; }
.sections { display: flex; flex-direction: column; gap: 4px; } .section-link { text-align: left; background: #fff; color: var(--ink); border: 1px solid var(--line); display: flex; gap: 8px; align-items: center; } .section-link.active { border-color: var(--navy); background: var(--wash); } .section-link .pg { color: var(--mute); font-size: 11px; width: 26px; } .section-link .badge { margin-left: auto; background: var(--red); color: #fff; border-radius: 10px; font-size: 11px; padding: 0 6px; }
.issues { margin-top: 12px; font-size: 12px; } .issue { padding: 4px 6px; border-left: 3px solid var(--line); margin: 3px 0; cursor: pointer; } .issue-error { border-color: var(--red); } .issue-warning { border-color: var(--amber); } .issue-info { border-color: var(--line); color: var(--mute); }
.fields { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; margin-bottom: 14px; }
.field { border: 1px solid var(--line); border-radius: 4px; padding: 6px 8px; } .field.attention { border-color: var(--amber); } .field-head { display: flex; gap: 6px; align-items: center; margin-bottom: 4px; font-size: 12px; } .field-head label { font-weight: 600; flex: 1; }
.field .unit { margin-left: 4px; color: var(--mute); } .alts label { display: block; margin: 2px 0; } .source { margin-top: 4px; background: var(--wash); padding: 4px 6px; border-radius: 3px; }
.grid.cells .field { border: none; padding: 0; } .grid.cells .field-head label { display: none; } .grid.cells .field-head { margin: 0; }
.table-block { margin: 14px 0; }
.report-layout { display: grid; grid-template-columns: 1fr 260px; gap: 16px; } .preview iframe { width: 100%; height: 80vh; border: 1px solid var(--line); background: #888; }
.version { border: 1px solid var(--line); border-radius: 4px; padding: 8px; margin-bottom: 8px; }
```

- [ ] **Step 2: Production build**

Run: `cd frontend && npx ng build 2>&1 | tail -5`
Expected: `Application bundle generation complete.` with no errors (warnings about bundle size are fine).

- [ ] **Step 3: Full smoke test on the real dataset**

1. `cd backend && uvicorn app.main:app --port 8000` and `cd frontend && npm start`.
2. Create a report, upload every file in `SOURCE FILES/` (including the `_Misc. FIles` ones), wait for processing.
3. Review: confirm the Financing section is flagged missing, purchase price shows the CoStar conflict, financials match the example PDF (NOI 636,106; total revenue 1,450,138), capex total 241,077, occupancy 90.53% / −118 bps, new leases 38 at −17.62%.
4. Enter a lender and rate, add the three value-add underwriting rows from the example, save, generate the PDF, open it, then change one value and regenerate as v2.
5. Delete the Rent Chart workbook from the project and rebuild: page 3 must switch to the computed trend with a warning, not fail.
6. Upload a `.docx`: it must show `unsupported` and nothing else changes.

- [ ] **Step 4: Commit and tag**

```bash
git add -A && git commit -m "feat(frontend): styles, production build, smoke-tested end to end" && git tag v0.1.0
```

---

## Self-review notes (already applied while writing this plan)

- **Spec coverage** against `Test Project Requirements - The Boardwalk.docx`: file intake with metadata and per-file failure isolation (Tasks 20, 21, 31); content-based extraction with provenance (Tasks 5 to 14); structured intermediate model separate from files and report (Task 15); review UI with missing/uncertain indication, editing, and saving (Tasks 22, 32); no silent invention (missing/conflict statuses, Tasks 18 and 19; AI drafts flagged, Task 26); report in the example's PDF format from verified data (Tasks 24 and 25); regeneration without reprocessing (overrides + versions, Tasks 22, 25, 33); persistence in SQLite (Task 2); visible error handling (statuses, issues, report errors); architecture separation (readers / classify / extract / consolidate / report / api / workers); README with setup, usage, external APIs, developer notes, limitations, next steps (Task 28); `.env.example` (Task 1).
- **Type consistency**: `Part(doc_type, confidence, locator, file_id, filename, sheet, pages)` is used identically by the classifier, the test helpers and every extractor; `Src.source(suffix, text)` returns the dict that `Field.source` accepts; `ReportData.field/value/table/set_derived/iter_fields` are the only accessors used by calc, validate, serialize, render and narrative; section, table and column keys created in Task 18 are the ones read by Task 17 (`recompute`), Task 19 (`REQUIRED`), Task 24 (template) and Task 26 (`NARRATIVES`).
- **Deliberate scope cuts** (document in README if they stay): per-sheet type overrides for multi-sheet workbooks, OCR, photo upload, mapping editor UI.
