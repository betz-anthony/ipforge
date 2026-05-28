from sqlalchemy import Column, Integer, String, Boolean, Text
from app.database import Base


SECRET_FIELDS: dict[str, list[str]] = {
    "msdns":    ["winrm_password"],
    "msdhcp":   ["winrm_password"],
    "bind":     ["tsig_key_secret"],
    "pihole":   ["password"],
    "keadhcp":  ["secret"],
    "cloudflare": ["api_token"],
    "route53":    ["aws_secret_access_key"],
    "azure_dns":  ["client_secret"],
    "gcp_dns":    ["service_account_json"],
}


class ProviderConfig(Base):
    __tablename__ = "provider_configs"

    id            = Column(Integer, primary_key=True, index=True)
    category      = Column(String(16), nullable=False)   # "dns" | "dhcp"
    provider_type = Column(String(32), nullable=False)   # "msdns" | "bind" | ...
    name          = Column(String(64), nullable=False, unique=True)  # slug; used as source ID
    config        = Column(Text, nullable=False, default="{}")       # JSON
    enabled       = Column(Boolean, nullable=False, default=True)
    sort_order    = Column(Integer, nullable=False, default=0)
