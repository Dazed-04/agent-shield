import datetime

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text

from app.database import Base


class SecurityAuditLog(Base):
    __tablename__ = "security_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(String(64), index=True, default="default_session")
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    prompt = Column(Text, nullable=False)
    risk_score = Column(Float, nullable=False)
    decision = Column(String(20), nullable=False)
    justification = Column(Text, nullable=False)
    triggered_detectors = Column(JSON, default={})
    tool_calls_attempted = Column(JSON, default=[])
    final_response = Column(Text, nullable=True)
    status = Column(String(20), default="COMPLETED")
