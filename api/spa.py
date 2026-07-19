"""Serve the built Angular SPA from the API's own origin (ADR-0018).

One container hosts both the API and the UI, so the frontend calls relative
URLs and CORS stays closed in production. Kept out of main.py so that file
stays routes-only.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist" / "frontend" / "browser"


class SpaStaticFiles(StaticFiles):
    """Static files with an index.html fallback so SPA routes survive a refresh."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # Starlette raises its own HTTPException here, not FastAPI's subclass.
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


def mount_spa(app: FastAPI) -> None:
    """Mount the built SPA at /, if a build exists. Call after all API routes:
    routes win, only unmatched paths fall through to the SPA."""
    if DIST.is_dir():
        app.mount("/", SpaStaticFiles(directory=DIST, html=True), name="spa")
