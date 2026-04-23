from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://ipam:ipam@localhost:5432/ipam"

    dns_provider: str = "msdns"
    dhcp_provider: str = "msdhcp"

    # MS (WinRM)
    ms_winrm_host: str = ""
    ms_winrm_user: str = ""
    ms_winrm_password: str = ""
    ms_winrm_port: int = 5985
    ms_winrm_transport: str = "ntlm"
    ms_dns_server: str = ""
    ms_dhcp_server: str = ""

    # Pi-hole v6
    pihole_url: str = ""       # e.g. http://192.168.1.1
    pihole_password: str = ""

    # BIND (dnspython AXFR + RFC 2136)
    bind_host: str = ""
    bind_port: int = 53
    bind_tsig_key_name: str = ""
    bind_tsig_key_secret: str = ""  # base64-encoded
    bind_tsig_algorithm: str = "hmac-sha256"
    bind_zones: str = ""        # comma-separated zone list

    # ISC Kea Control Agent
    kea_url: str = ""           # e.g. http://kea-host:8000
    kea_secret: str = ""        # API key (if auth enabled)

    # Deployment mode: "background" (docker-compose) or "disabled" (K8s CronJob handles sync)
    sync_mode: str = "background"

    class Config:
        env_file = ".env"


settings = Settings()
