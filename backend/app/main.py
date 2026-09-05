"""FastAPI application entry point."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .api import files, projects, report, report_data
from .config import settings
from .report.render import chromium_available
from .workers.jobs import recover_stuck_files
from .workers.pool import pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    app.state.pdf_renderer = await asyncio.to_thread(chromium_available)  # sync Playwright cannot run on the loop
    recover_stuck_files()
    yield
    pool.shutdown()


app = FastAPI(title="Investor Report Generator", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"], allow_headers=["*"])
for r in (projects.router, files.router, report_data.router, report.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "llm_enabled": settings.llm_enabled, "llm_provider": settings.llm_provider,
            "pdf_renderer": bool(getattr(app.state, "pdf_renderer", False)), "workers": settings.workers}
