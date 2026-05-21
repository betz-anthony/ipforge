from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.database import Base


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id:           Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id:      Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name:         Mapped[str] = mapped_column(String(64), nullable=False)
    token_hash:   Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    read_only:    Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at:   Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at:   Mapped[datetime] = mapped_column(DateTime, default=utcnow)
