"""Backward-compatible imports for the canonical database session.

Older planner modules import SessionLocal from this module. Keeping these
aliases avoids changing working call sites while ensuring the application
uses exactly one SQLAlchemy engine and connection pool.
"""
from app.database.connection import SessionLocal, engine, get_db

__all__ = ["SessionLocal", "engine", "get_db"]
