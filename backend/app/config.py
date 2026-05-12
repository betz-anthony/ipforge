from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://ipam:ipam@localhost:5432/ipam"

    # Utilization thresholds
    util_warn_threshold: int = 80
    util_critical_threshold: int = 95
    util_dashboard_top_n: int = 5

    # Deployment mode: "background" (docker-compose) or "disabled" (K8s CronJob handles sync)
    sync_mode: str = "background"

    class Config:
        env_file = ".env"


settings = Settings()
