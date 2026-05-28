from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SubnetRange(Base):
    __tablename__ = "subnet_ranges"

    id:         Mapped[int]        = mapped_column(Integer, primary_key=True)
    subnet_id:  Mapped[int]        = mapped_column(Integer, ForeignKey("subnets.id", ondelete="CASCADE"), nullable=False, index=True)
    start_ip:   Mapped[str]        = mapped_column(String(50), nullable=False)
    end_ip:     Mapped[str]        = mapped_column(String(50), nullable=False)
    kind:       Mapped[str]        = mapped_column(String(20), nullable=False)  # gateway/dhcp_pool/static/reserved
    label:      Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime]   = mapped_column(DateTime, default=datetime.utcnow)
