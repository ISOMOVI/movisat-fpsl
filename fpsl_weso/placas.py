"""Regra ÚNICA de placa — termo, espelho, consulta e cadastro usam esta.

Padrão definido pelo usuário em 2026-07-27, depois de padronizar a base da WESO:

    convencional antiga .... 'ABC 1234'      (espaço após as 3 letras)
    convencional Mercosul .. 'ABC 1D23'      (idem)
    redundância ............ '(RD) ABC 1234' (marcador ANTES, entre parênteses)
    não convencional ....... como veio       (chassi/série de máquina: NÃO normalizar)

Por que existe um módulo só pra isso: o campo `placa` da WESO é texto livre, e a
base tinha 5 grafias de redundância, placa sem espaço, com espaço nas bordas e em
minúscula. Se cada ponto do código reinventar a regra, o de-para diverge — e
divergência de placa não dá erro, só deixa de casar em silêncio.

ARMADILHA que este módulo existe pra evitar (ver docs/fpsl/10_Inconsistencias.md, B9):
'RDM', 'RDQ', 'RDS', 'DRD', 'QRD', 'RRD' são PREFIXOS LEGÍTIMOS de placa. Um
`replace("RD", "")` ingênuo destrói 16 placas reais. O único critério seguro é
remover o marcador e verificar se o que sobra CONTINUA sendo placa válida.
"""
import re

# 3 letras + 4 posições (antiga: 4 dígitos; Mercosul: dígito, letra, 2 dígitos)
_PLACA_RE = re.compile(r"^([A-Z]{3})[\s\-]?(\d{4}|\d[A-Z]\d{2})$")

# ordem importa: do mais específico (com parênteses) pro mais frouxo (colado)
_REMOCOES_RD = (
    re.compile(r"\s*\(\s*RD\s*\)\s*", re.I),   # (RD) em qualquer posição
    re.compile(r"\s+RD\s*$", re.I),            # RD solto no fim
    re.compile(r"^\s*RD\s+", re.I),            # RD solto no início
    re.compile(r"^RD", re.I),                  # RD colado no início
    re.compile(r"RD$", re.I),                  # RD colado no fim
)

MARCADOR_RD = "(RD)"


def _limpar(valor) -> str:
    """Caixa alta, espaços colapsados, bordas aparadas.

    O `strip()` não é preciosismo: 3 placas da WESO têm espaço nas BORDAS e 11 têm
    espaço no fim -- contar/comparar sem aparar erra a conta.
    """
    return re.sub(r"\s+", " ", str(valor or "").strip().upper())


def _canonizar(p: str) -> str | None:
    """'abc1234' / 'ABC 1234' -> 'ABC 1234'. None se não for placa convencional."""
    m = _PLACA_RE.match(p.replace(" ", "")) or _PLACA_RE.match(p)
    return f"{m.group(1)} {m.group(2)}" if m else None


def _partes(valor) -> tuple[str | None, bool]:
    """(base canônica, tem_rd). Núcleo do módulo — todo o resto chama isto.

    O marcador só é reconhecido quando, ao removê-lo, o resto CONTINUA sendo placa
    válida — é o que separa redundância de prefixo legítimo:

        'rdRCJ 0D65' -> ('RCJ 0D65', True)    o resto é placa  -> era marcador
        'RDM 0G81'   -> ('RDM 0G81', False)   'M 0G81' não é   -> RDM é prefixo

    Não convencional (chassi) volta (None, False).
    """
    s = _limpar(valor)
    if not s:
        return None, False
    for rx in _REMOCOES_RD:
        candidato = rx.sub(" ", s) if rx.pattern.startswith(r"\s*\(") else rx.sub("", s)
        if candidato == s:
            continue  # esta regex não removeu nada -- não serve de prova
        base = _canonizar(_limpar(candidato))
        if base:
            return base, True
    return _canonizar(s), False


def eh_convencional(valor) -> bool:
    """É placa brasileira (antiga ou Mercosul)? Chassi/série de máquina -> False.

    O marcador de redundância NÃO desqualifica: '(RD) ABC 1234' é tão convencional
    quanto 'ABC 1234'. Se respondesse False aqui, um chamador poderia tratá-la como
    chassi e deixar de normalizar.

    60 registros da WESO têm chassi no campo placa ('CAT0318DLSGB30031'). Esses sim
    NÃO se normalizam: vão como vieram do contrato.
    """
    return _partes(valor)[0] is not None


def separar_rd(valor) -> tuple[str | None, bool]:
    """(placa_base_formatada, tem_marcador_rd). Não convencional -> (None, False)."""
    return _partes(valor)


def formatar(valor) -> str:
    """Forma canônica de gravação/exibição. Não convencional volta como veio."""
    s = _limpar(valor)
    if not s:
        return ""
    base, rd = _partes(s)
    if base is None:
        return s  # chassi/série: preserva o que o contrato trouxe
    return f"{MARCADOR_RD} {base}" if rd else base


def montar(base: str, tem_rd: bool = False) -> str:
    """Placa base + marcador -> forma canônica. '(RD) ABC 1234'."""
    b = formatar(base)
    if not tem_rd:
        return b
    return b if b.startswith(MARCADOR_RD) else f"{MARCADOR_RD} {b}"


def normalizar(valor) -> str:
    """Chave de COMPARAÇÃO (só A-Z0-9), pra casar grafias diferentes.

    Não serve pra gravar -- só pra indexar/comparar. Note que a chave inclui o RD:
    use `chave()` quando quiser comparar base e marcador separadamente.
    """
    return re.sub(r"[^A-Z0-9]", "", _limpar(valor))


def chave(valor) -> tuple[str, bool]:
    """(base_normalizada, tem_rd) -- a chave certa pra de-para e detecção de duplicata.

    Comparar a string crua faria 'CUB 0764 (RD)' e '(RD) CUB 0764' parecerem
    registros diferentes, quando são o mesmo veículo/marcador.
    """
    base, rd = separar_rd(valor)
    return (normalizar(base) if base else normalizar(valor)), rd
