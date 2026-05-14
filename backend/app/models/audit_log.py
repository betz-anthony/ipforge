from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id            = Column(Integer, primary_key=True)
    timestamp     = Column(DateTime, nullable=False)
    username      = Column(String(64), nullable=False)
    action        = Column(String(16), nullable=False)   # create | update | delete
    resource_type = Column(String(32), nullable=False)   # subnet | address | dns_record | dhcp_reservation
    resource_id   = Column(String(128), nullable=False)
    summary       = Column(Text, nullable=True)
    before_state  = Column(Text, nullable=True)          # JSON string
    after_state   = Column(Text, nullable=True)          # JSON string


Index("ix_audit_log_timestamp",     AuditLog.timestamp.desc())
Index("ix_audit_log_resource_type", AuditLog.resource_type)
Index("ix_audit_log_username",      AuditLog.username)
