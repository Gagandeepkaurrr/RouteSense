"""Compatibility import for the former standalone posts demo.

The old file embedded a PostgreSQL username/password and connected to an
unrelated ``posts`` table. RouteSense now has one application entry point:
``uvicorn app.main:app``. This module intentionally delegates to it so the
legacy ``main:app`` import no longer contains credentials or a second DB pool.
"""
from app.main import app

__all__ = ["app"]
