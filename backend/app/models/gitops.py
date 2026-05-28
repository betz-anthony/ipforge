from sqlalchemy import String, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GitopsManaged(Base):
    __tablename__ = "gitops_managed"
    __table_args__ = (
        UniqueConstraint("resource_type", "resource_id", name="uq_gitops_managed_resource"),
    )

    id:            Mapped[int] = mapped_column(Integer, primary_key=True)
    source:        Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False)  # vlan/subnet/subnet_range/address
    resource_id:   Mapped[int] = mapped_column(Integer, nullable=False)
