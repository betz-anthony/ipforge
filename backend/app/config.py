from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://ipam:ipam@localhost:5432/ipam"

    # Auth
    jwt_secret_key: str = "change-me-in-production-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480      # 8 hours
    auth_backend: str = "local"        # "local" | "ldap" (planned)
    default_admin_password: str = "admin"

    # Utilization thresholds
    util_warn_threshold: int = 80
    util_critical_threshold: int = 95
    util_dashboard_top_n: int = 5

    # Scan interval (minutes); per-subnet override takes precedence
    scan_interval_minutes: int = 30

    # Deployment mode: "background" (docker-compose) or "disabled" (K8s CronJob handles sync)
    sync_mode: str = "background"

    class Config:
        env_file = ".env"


settings = Settings()
