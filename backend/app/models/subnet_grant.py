from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SubnetGrant(Base):
    __tablename__ = "subnet_grants"

    id:         Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id:    Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    group_id:   Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user_groups.id", ondelete="CASCADE"), nullable=True, index=True
    )
    subnet_id:  Mapped[int] = mapped_column(
        Integer, ForeignKey("subnets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    permission: Mapped[str] = mapped_column(String(16), nullable=False)   # "view" | "manage"
