from sqlalchemy import Column, Integer, String, Boolean
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    username        = Column(String(64), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role            = Column(String(16), nullable=False, default="readonly")  # readonly | operator | admin
    enabled         = Column(Boolean, nullable=False, default=True)
    auth_source     = Column(String(16), nullable=False, server_default="local")
