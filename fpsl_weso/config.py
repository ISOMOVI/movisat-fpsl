from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    weso_base_url:       str = "http://apirota.wesotecnologia.com.br"
    weso_api_key:        str
    fpsl_secret_key:     str
    harmonit_base_url:   str = "https://api-hc.harmonit.com.br:8086"
    harmonit_client_id:  str = ""
    harmonit_secret_id:  str = ""

    # Painel de geração de OS por contrato — login básico até o Google OAuth
    # entrar em produção (previsto ~20/07). Trocar/desligar quando isso acontecer.
    painel_admin_login: str = "admin"
    painel_admin_senha: str = ""
    painel_jwt_secret:  str = ""

    class Config:
        env_file = ".env"


settings = Settings()
