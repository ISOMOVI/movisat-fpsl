"""Rotas do painel de demandas — PÚBLICAS, abertas por link.

🚨 Este router não usa `get_usuario_painel`. É de propósito: o quadro é
compartilhado por link, sem conta. Por isso:

  - o token da URL é a única credencial, e é conferido em TODA rota;
  - nenhuma rota daqui toca tabela do FPSL — só as quatro `demanda_*`;
  - todo campo tem teto de tamanho, porque quem escreve não tem conta.

Fica montado em `/demandas` para não se misturar com `/painel`, que exige
login.
"""
import logging
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from ... import demandas

log = logging.getLogger(__name__)

router = APIRouter(prefix="/demandas", tags=["demandas"])

FRONT = Path(__file__).resolve().parents[3] / "frontend"
PAGINAS = {"esteira": FRONT / "demandas.html", "planilha": FRONT / "planilha.html"}

# Limite simples por IP: rota pública sem conta. Em memória basta -- o FPSL
# roda com 1 worker, e o pior caso de perder a contagem num restart é alguém
# escrever demais por um minuto.
_escritas: dict[str, list[float]] = {}
JANELA, TETO = 60.0, 60


def _pode_escrever(ip: str) -> bool:
    import time
    agora = time.time()
    marcas = [t for t in _escritas.get(ip, []) if agora - t < JANELA]
    marcas.append(agora)
    _escritas[ip] = marcas
    return len(marcas) <= TETO


def _ip(request: Request) -> str:
    """Atrás do nginx, `request.client.host` é sempre 127.0.0.1."""
    conexao = request.client.host if request.client else "?"
    if conexao in ("127.0.0.1", "::1"):
        return (request.headers.get("x-real-ip")
                or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
                or conexao)
    return conexao


def _guardar(request: Request) -> None:
    if not _pode_escrever(_ip(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Muitas alterações seguidas. Espere um minuto.")


def _exigir_texto(valor: str, campo: str) -> str:
    """Pydantic aceita "   " -- tem 3 caracteres. Depois do strip vira vazio.

    Sem isto o quadro devolvia 404 para nome em branco, dizendo "não
    encontrado" quando o problema era o campo. Mensagem errada manda quem
    está usando procurar no lugar errado.
    """
    limpo = (valor or "").strip()
    if not limpo:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"{campo} não pode ficar em branco.")
    return limpo


# Faixa de ano aceita num prazo. Larga o bastante para qualquer planejamento
# real, estreita o bastante para pegar o ano digitado errado -- que é o erro
# que de fato acontece (ver o validador abaixo).
ANO_MIN, ANO_MAX = 2020, 2100


class ItemIn(BaseModel):
    prazo: str | None = Field(default=None, max_length=10)
    sem_prazo: bool = False

    @field_validator("prazo")
    @classmethod
    def _prazo_e_data_de_verdade(cls, v: str | None) -> str | None:
        """🚨 O PRAZO PRECISA SER `AAAA-MM-DD` DE VERDADE.

        Antes só havia limite de tamanho, e `atualizar_item` gravava o que
        chegasse. Como a comparação de atraso é de TEXTO (`prazo < hoje`),
        formato errado erra em silêncio, nos dois sentidos:

            '07/08/2026'  ->  '0' < '2'  ->  atrasado PARA SEMPRE
            'amanha'      ->  'a' > '2'  ->  NUNCA atrasado

        Pela tela não acontecia -- o campo é `input type="date"`, que só manda
        ISO. Mas **este quadro é público por link e a API aceita POST direto**:
        quem tem o endereço manda o que quiser. Validação de tela nunca foi
        validação.

        ⚠️ `date.fromisoformat` também recusa data impossível (`2026-13-45`),
        que o formato sozinho aceitaria.

        🚨 E A FAIXA DE ANO NÃO É PRECIOSISMO. Encontrado no quadro real em
        07/08: o card "Liberação para uso" estava com prazo `0002-08-11` --
        ano 2. O `input type="date"` produz isso sozinho quando alguém digita
        o ano no teclado e sai do campo antes de terminar. `date.fromisoformat`
        aceita numa boa, porque ano 2 EXISTE.

        O efeito é o pior possível: `'0002-08-11' < hoje` é verdadeiro, então o
        card fica **atrasado para sempre**, e nada indica por quê. O irmão
        desse erro é o ano 9999, que fica **eternamente no prazo**.
        """
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        try:
            if len(v) != 10:
                raise ValueError
            d = date.fromisoformat(v)
        except ValueError:
            raise ValueError("Prazo precisa ser uma data no formato AAAA-MM-DD.")
        if not (ANO_MIN <= d.year <= ANO_MAX):
            raise ValueError(
                f"Ano {d.year} não faz sentido para um prazo "
                f"(esperado entre {ANO_MIN} e {ANO_MAX}). Confira a data digitada.")
        return v
    obs: str | None = Field(default=None, max_length=500)
    quem: str | None = Field(default=None, max_length=60)


class EtapaIn(BaseModel):
    concluida: bool
    quem: str | None = Field(default=None, max_length=60)


class FrenteNova(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    contato: str | None = Field(default=None, max_length=120)


class ItemNovo(BaseModel):
    frente_id: int
    titulo: str = Field(min_length=1, max_length=120)
    # 🆕 escolhida da lista, não digitada: nome digitado cria pessoa nova a
    # cada erro de grafia, e cada uma ganharia uma cor
    pessoa_id: int


class EtapaNova(BaseModel):
    item_id: int
    descricao: str = Field(min_length=1, max_length=120)
    pessoa_id: int


class PessoaNova(BaseModel):
    nome: str = Field(min_length=1, max_length=60)
    cor: str = Field(min_length=4, max_length=9)


# ------------------------------------------------------------------ leitura

@router.get("/api/{token}")
async def ler(token: str):
    q = demandas.quadro(token)
    if not q:
        raise HTTPException(404, "Quadro não encontrado.")
    return q


# ------------------------------------------------------------------ escrita

@router.post("/api/{token}/item/{item_id}")
async def salvar_item(token: str, item_id: int, dados: ItemIn, request: Request):
    _guardar(request)
    if not demandas.atualizar_item(token, item_id, dados.prazo, dados.sem_prazo,
                                   dados.obs, dados.quem):
        # 409, não 403: não é falta de permissão, é a fila
        raise HTTPException(409, "Item inexistente ou aguardando a tarefa acima.")
    return {"ok": True}


@router.post("/api/{token}/etapa/{etapa_id}")
async def marcar(token: str, etapa_id: int, dados: EtapaIn, request: Request):
    _guardar(request)
    if not demandas.marcar_etapa(token, etapa_id, dados.concluida, dados.quem):
        raise HTTPException(409, "Etapa inexistente ou aguardando a tarefa acima.")
    return {"ok": True}


@router.post("/api/{token}/frente")
async def nova_frente(token: str, dados: FrenteNova, request: Request):
    _guardar(request)
    r = demandas.criar_frente(token, _exigir_texto(dados.nome, "Nome do assunto"),
                              dados.contato)
    if not r:
        raise HTTPException(404, "Quadro não encontrado.")
    return r


@router.post("/api/{token}/item")
async def novo_item(token: str, dados: ItemNovo, request: Request):
    _guardar(request)
    r = demandas.criar_item(token, dados.frente_id,
                            _exigir_texto(dados.titulo, "Título do card"),
                            dados.pessoa_id)
    if not r:
        raise HTTPException(404, "Assunto ou responsável não encontrado.")
    return r


@router.post("/api/{token}/etapa")
async def nova_etapa(token: str, dados: EtapaNova, request: Request):
    _guardar(request)
    r = demandas.criar_etapa(token, dados.item_id,
                             _exigir_texto(dados.descricao, "Descrição da etapa"),
                             dados.pessoa_id)
    if not r:
        raise HTTPException(404, "Card ou responsável não encontrado.")
    return r


MOTIVOS = {
    "nome_vazio": (422, "O nome não pode ficar em branco."),
    "cor_invalida": (422, "Essa cor não está na paleta."),
    "nome_repetido": (409, "Já existe alguém com esse nome no quadro."),
    "cor_em_uso": (409, "Essa cor já é de outra pessoa. Escolha outra."),
}


@router.post("/api/{token}/pessoa")
async def nova_pessoa(token: str, dados: PessoaNova, request: Request):
    """🚨 Recusa com MOTIVO. 'não deu' faz a pessoa tentar de novo igual."""
    _guardar(request)
    r = demandas.criar_pessoa(token, dados.nome, dados.cor)
    if r is None:
        raise HTTPException(404, "Quadro não encontrado.")
    if "erro" in r:
        status_code, texto = MOTIVOS.get(r["erro"], (422, "Não foi possível cadastrar."))
        raise HTTPException(status_code, texto)
    return r


class TituloIn(BaseModel):
    titulo: str = Field(min_length=1, max_length=120)
    quem: str | None = Field(default=None, max_length=60)


class RespIn(BaseModel):
    pessoa_id: int
    quem: str | None = Field(default=None, max_length=60)


class CancelarIn(BaseModel):
    cancelado: bool


@router.post("/api/{token}/item/{item_id}/titulo")
async def renomear(token: str, item_id: int, dados: TituloIn, request: Request):
    _guardar(request)
    if not demandas.renomear_item(token, item_id,
                                  _exigir_texto(dados.titulo, "Tarefa"), dados.quem):
        raise HTTPException(409, "Tarefa inexistente ou aguardando a de cima.")
    return {"ok": True}


@router.post("/api/{token}/item/{item_id}/responsavel")
async def trocar_resp(token: str, item_id: int, dados: RespIn, request: Request):
    _guardar(request)
    if not demandas.trocar_responsavel(token, item_id, dados.pessoa_id, dados.quem):
        raise HTTPException(404, "Tarefa ou responsável não encontrado.")
    return {"ok": True}


@router.post("/api/{token}/item/{item_id}/cancelar")
async def cancelar(token: str, item_id: int, dados: CancelarIn, request: Request):
    """🚨 Cancelado NÃO libera a de baixo: a tarefa não aconteceu."""
    _guardar(request)
    if not demandas.cancelar_item(token, item_id, dados.cancelado):
        raise HTTPException(404, "Tarefa não encontrada.")
    return {"ok": True}


@router.post("/api/{token}/item/{item_id}/apagar")
async def apagar_item(token: str, item_id: int, request: Request):
    _guardar(request)
    if not demandas.apagar_item(token, item_id):
        raise HTTPException(404, "Card não encontrado.")
    return {"ok": True}


@router.post("/api/{token}/frente/{frente_id}/apagar")
async def apagar_frente(token: str, frente_id: int, request: Request):
    _guardar(request)
    if not demandas.apagar_frente(token, frente_id):
        raise HTTPException(404, "Assunto não encontrado.")
    return {"ok": True}


# ------------------------------------------------------------------ página

@router.get("/{token}", include_in_schema=False)
async def pagina(token: str):
    """A vista sai do `modo` do quadro: esteira (cards) ou planilha (tabela).

    ⚠️ Token inválido cai na esteira, sem 404. A página sozinha não entrega
    nada, e responder 404 aqui diria a quem tenta adivinhar que aquele token
    não existe.
    """
    q = demandas.quadro(token)
    modo = (q or {}).get("modo", "esteira")
    return FileResponse(PAGINAS.get(modo, PAGINAS["esteira"]))
