"""
KnowledgeHub API entrypoint.

Wires together authentication, document management, full-text search and
collaboration into a single FastAPI application. Tables are created on startup;
in production you would manage the schema with Alembic migrations instead.
"""

import logging
import pathlib

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.cache import _client
from app.database import Base, engine
from app.routers import auth as auth_router
from app.routers import collaboration as collab_router
from app.routers import documents as documents_router
from app.routers import search as search_router
from app.search import search_engine

logging.basicConfig(level=logging.INFO)

# Import side effect: ensure all models are registered before create_all.
from app import models  # noqa: E402,F401

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="KnowledgeHub",
    version=__version__,
    description="Enterprise knowledge management platform — documents, search, collaboration.",
)

app.include_router(auth_router.router)
app.include_router(documents_router.router)
app.include_router(collab_router.router)
app.include_router(search_router.router)

# Single-page web UI (the "Web App" client in the architecture). Served by the
# same FastAPI app, so it talks to the API on the same origin (no CORS needed).
_STATIC_DIR = pathlib.Path(__file__).parent / "static"
app.mount("/app", StaticFiles(directory=_STATIC_DIR, html=True), name="webapp")


@app.get("/", tags=["system"], include_in_schema=False)
def root():
    """Redirect the root URL to the web UI."""
    return FileResponse(_STATIC_DIR / "index.html")


@app.get("/api", tags=["system"])
def api_info():
    return {
        "service": "KnowledgeHub",
        "version": __version__,
        "web_app": "/app",
        "docs": "/docs",
    }


@app.get("/health", tags=["system"])
def health():
    """Liveness + dependency status for monitoring / load balancers."""
    return {
        "status": "ok",
        "search_backend": search_engine.backend,
        "cache_backend": type(_client).__name__,
    }
