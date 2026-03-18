"""
PostgreSQL client using SQLAlchemy + Redis caching layer.
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from app.core.config import settings
from typing import Any, Optional
import logging
import redis
import json
import os

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# PostgreSQL Engine
# ─────────────────────────────────────────────
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


# ─────────────────────────────────────────────
# Redis Cache Client
# ─────────────────────────────────────────────
_redis_client = None

def get_redis() -> Optional[redis.Redis]:
    global _redis_client
    if _redis_client is None:
        redis_url = os.environ.get("REDIS_URL")
        if not redis_url:
            return None
        try:
            _redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            _redis_client.ping()
            logger.info("✅ Redis connected")
        except Exception as e:
            logger.warning(f"⚠️ Redis unavailable, running without cache: {e}")
            _redis_client = None
    return _redis_client


def cache_get(key: str) -> Optional[Any]:
    """Get value from Redis cache. Returns None if not found or Redis unavailable."""
    try:
        r = get_redis()
        if not r:
            return None
        val = r.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    """Set value in Redis cache with TTL in seconds. Silently fails if Redis unavailable."""
    try:
        r = get_redis()
        if not r:
            return
        r.setex(key, ttl, json.dumps(value, default=str))
    except Exception:
        pass


def cache_delete(key: str) -> None:
    """Delete a single key from Redis cache."""
    try:
        r = get_redis()
        if r:
            r.delete(key)
    except Exception:
        pass


def cache_delete_pattern(pattern: str) -> None:
    """Delete all keys matching a pattern (e.g. 'employees:*')."""
    try:
        r = get_redis()
        if not r:
            return
        keys = r.keys(pattern)
        if keys:
            r.delete(*keys)
    except Exception:
        pass


# ─────────────────────────────────────────────
# DBResult — mimics supabase response
# ─────────────────────────────────────────────
class DBResult:
    def __init__(self, data: list):
        self.data = data


# ─────────────────────────────────────────────
# DB Helpers
# ─────────────────────────────────────────────
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
    """For INSERT/UPDATE/DELETE — returns rows if RETURNING used."""
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        conn.commit()
        try:
            rows = [dict(row._mapping) for row in result]
        except Exception:
            rows = []
    return DBResult(rows)