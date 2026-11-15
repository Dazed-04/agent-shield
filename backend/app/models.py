import datetime

from sqlalchemy import JSON, Column, DateTime, Float, Index, Integer, String, Text

from app.database import Base


def utcnow() -> datetime.datetime:
    """Naive UTC timestamp (datetime.utcnow() is deprecated)."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


class SecurityAuditLog(Base):
    __tablename__ = "security_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(String(64), index=True, default="default_session")
    user_id = Column(String(128), index=True, nullable=True)
    role = Column(String(64), nullable=True)
    timestamp = Column(DateTime, default=utcnow, index=True)
    prompt = Column(Text, nullable=False)
    risk_score = Column(Float, nullable=False)
    decision = Column(String(20), nullable=False, index=True)
    justification = Column(Text, nullable=False)
    triggered_detectors = Column(JSON, default=dict)
    tool_calls_attempted = Column(JSON, default=list)
    final_response = Column(Text, nullable=True)
    status = Column(String(20), default="COMPLETED", index=True)
    resolved_by = Column(String(128), nullable=True)
    latency_ms = Column(Float, nullable=True)

    __table_args__ = (Index("ix_audit_thread_id_id", "thread_id", "id"),)
