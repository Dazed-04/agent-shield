import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL

logger = logging.getLogger(__name__)

_is_sqlite = DATABASE_URL.startswith("sqlite")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=not _is_sqlite,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# column name -> DDL type, for upgrading databases created by older versions
_ADDED_COLUMNS = {
    "thread_id": "VARCHAR(64)",
    "user_id": "VARCHAR(128)",
    "role": "VARCHAR(64)",
    "resolved_by": "VARCHAR(128)",
    "latency_ms": "FLOAT",
    "status": "VARCHAR(20) DEFAULT 'COMPLETED'",
    "final_response": "TEXT",
    "triggered_detectors": "JSON",
    "tool_calls_attempted": "JSON",
}


def init_db() -> None:
    """Create tables and add any columns missing from an older schema."""
    from app import models  # noqa: F401  (registers the tables on Base.metadata)

    Base.metadata.create_all(bind=engine)
    insp = inspect(engine)
    if "security_audit_logs" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("security_audit_logs")}
    with engine.begin() as conn:
        for name, ddl in _ADDED_COLUMNS.items():
            if name not in existing:
                logger.info("Migrating: adding column %s", name)
                conn.execute(
                    text(f"ALTER TABLE security_audit_logs ADD COLUMN {name} {ddl}")
                )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
