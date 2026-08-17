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

    # Entrada pelo Google (17/08). SO LOGIN -- escopo `openid email profile`,
    # nada de Gmail nem Calendar.
    # 🚨 PROJETO/CLIENTE PROPRIO, nao o do MoviZap: compartilhar o client
    # secret entre dois sistemas significa que rotacionar um derruba o outro,
    # e a tela de consentimento mostraria o nome do outro aplicativo.
    # Sem credencial, `google_auth.configurado()` devolve False e a tela nem
    # mostra o botao -- o painel segue 100% funcional por senha.
    google_client_id:     str = ""
    google_client_secret: str = ""
    google_redirect:      str = "https://fpsl.movisat.com.br/painel/api/auth/google/callback"
    google_dominio:       str = "movisat.com.br"

    class Config:
        env_file = ".env"


settings = Settings()
