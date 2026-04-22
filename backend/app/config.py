from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://ipam:ipam@localhost:5432/ipam"

    dns_provider: str = "msdns"
    dhcp_provider: str = "msdhcp"

    ms_winrm_host: str = ""
    ms_winrm_user: str = ""
    ms_winrm_password: str = ""
    ms_winrm_port: int = 5985
    ms_winrm_transport: str = "ntlm"
    ms_dns_server: str = ""
    ms_dhcp_server: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
