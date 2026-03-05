"""
PostgreSQL client using SQLAlchemy (replaces Supabase DB calls).
Usage: from app.core.db_client import get_db, db_fetch_one, db_fetch_all, db_execute
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from app.core.config import settings
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────
# Helper wrappers — drop-in replacements for supabase.table()
# These mirror the simple select/insert/update/delete patterns.
# ─────────────────────────────────────────────────────────────

class DBResult:
    """Mimics supabase response object with .data attribute"""
    def __init__(self, data: list):
        self.data = data


def db_fetch_all(sql: str, params: dict = None) -> DBResult:
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        rows = [dict(row._mapping) for row in result]
    return DBResult(rows)


def db_fetch_one(sql: str, params: dict = None) -> DBResult:
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        row = result.fetchone()
        data = [dict(row._mapping)] if row else []
    return DBResult(data)


def db_execute(sql: str, params: dict = None) -> DBResult:
    """For INSERT/UPDATE/DELETE — returns inserted/updated rows if RETURNING used"""
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        conn.commit()
        try:
            rows = [dict(row._mapping) for row in result]
        except Exception:
            rows = []
    return DBResult(rows)