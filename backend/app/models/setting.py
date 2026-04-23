from sqlalchemy import Column, String
from app.database import Base


class AppSetting(Base):
    __tablename__ = "app_settings"
    key = Column(String, primary_key=True)
    value = Column(String, nullable=False, default="")
