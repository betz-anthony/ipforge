from datetime import datetime

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CustomFieldDef(Base):
    __tablename__ = "custom_field_defs"
    __table_args__ = (
        UniqueConstraint("entity_type", "name", name="uq_custom_field_entity_name"),
    )

    id:          Mapped[int]            = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str]            = mapped_column(String(20), nullable=False)   # "subnet" | "address"
    name:        Mapped[str]            = mapped_column(String(64), nullable=False)   # machine key
    label:       Mapped[str]            = mapped_column(String(255), nullable=False)
    field_type:  Mapped[str]            = mapped_column(String(20), nullable=False)   # "text" | "select" | "date"
    options:     Mapped[str | None]     = mapped_column(Text, nullable=True)          # JSON list for select
    created_at:  Mapped[datetime]       = mapped_column(DateTime, default=datetime.utcnow)


class CustomFieldValue(Base):
    __tablename__ = "custom_field_values"
    __table_args__ = (
        UniqueConstraint("field_id", "entity_id", name="uq_custom_field_value"),
    )

    id:        Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id:  Mapped[int] = mapped_column(Integer, ForeignKey("custom_field_defs.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    value:     Mapped[str] = mapped_column(Text, nullable=False)


class Tag(Base):
    __tablename__ = "tags"

    id:   Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)


class TagAssignment(Base):
    __tablename__ = "tag_assignments"
    __table_args__ = (
        UniqueConstraint("tag_id", "entity_type", "entity_id", name="uq_tag_assignment"),
    )

    id:          Mapped[int] = mapped_column(Integer, primary_key=True)
    tag_id:      Mapped[int] = mapped_column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id:   Mapped[int] = mapped_column(Integer, nullable=False, index=True)
