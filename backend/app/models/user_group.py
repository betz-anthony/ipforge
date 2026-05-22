from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

user_group_members = Table(
    "user_group_members",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", Integer, ForeignKey("user_groups.id", ondelete="CASCADE"), primary_key=True),
)


class UserGroup(Base):
    __tablename__ = "user_groups"

    id:          Mapped[int] = mapped_column(Integer, primary_key=True)
    name:        Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
