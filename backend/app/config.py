from urllib.parse import quote

from pydantic import model_validator
from pydantic_settings import BaseSettings

# Built-in placeholder JWT key. The server refuses to start while this value
# is still in use — a predictable signing key allows token forgery.
DEFAULT_JWT_SECRET_KEY = "change-me-in-production-use-a-long-random-string"


class Settings(BaseSettings):
    # Set DATABASE_URL to use a connection string verbatim (tests, external
    # databases, non-PostgreSQL backends). When it is empty the URL is built
    # from the DB_* parts below, with the credentials percent-encoded — a
    # password containing "@", ":", "/" or "?" corrupts a hand-built URL.
    database_url: str = ""

    db_user: str = "ipam"
    db_password: str = "ipam"
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "ipam"

    # Credential encryption: Fernet key (base64-urlsafe, 32 bytes).
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # If empty, secrets stored as plaintext (backward-compatible).
    secret_key: str = ""

    # Auth
    jwt_secret_key: str = DEFAULT_JWT_SECRET_KEY
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480      # 8 hours
    auth_backend: str = "local"        # "local" | "ldap" (planned)
    default_admin_password: str = "admin"

    # LDAP / Active Directory
    ldap_enabled:        bool = False
    ldap_host:           str  = ""
    ldap_port:           int  = 389
    ldap_use_ssl:        bool = False
    ldap_bind_dn:        str  = ""
    ldap_bind_password:  str  = ""
    ldap_base_dn:        str  = ""
    ldap_user_filter:    str  = "(sAMAccountName={username})"
    ldap_group_admin:    str  = ""
    ldap_group_operator: str  = ""
    ldap_group_readonly: str  = ""
    ldap_default_role:   str  = "readonly"

    # Utilization thresholds
    util_warn_threshold: int = 80
    util_critical_threshold: int = 95
    util_dashboard_top_n: int = 5

    # Scan interval (minutes); per-subnet override takes precedence
    scan_interval_minutes: int = 30

    # Deployment mode: "background" (docker-compose) or "disabled" (K8s CronJob handles sync)
    sync_mode: str = "background"

    # Stale IP reclamation: number of days without activity before an IP is considered stale
    stale_reclaim_days: int = 30

    # Alert dispatcher: seconds between dispatcher ticks
    alert_dispatch_interval: int = 30

    @model_validator(mode="after")
    def _assemble_database_url(self):
        if not self.database_url:
            # safe="" so "@", ":" and "/" in the password are encoded rather
            # than being read as URL structure. quote(), not quote_plus():
            # "+" is not a space in the userinfo section.
            user = quote(self.db_user, safe="")
            password = quote(self.db_password, safe="")
            self.database_url = (
                f"postgresql://{user}:{password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        return self

    class Config:
        env_file = ".env"


settings = Settings()
