_SITUACAO: dict[str, str] = {
    "ativo":          "Adimplente",
    "normal":         "Adimplente",
    "adimplente":     "Adimplente",
    "inadimplente":   "Inadimplente",
    "bloqueado":      "Bloqueado",
    "teste":          "Teste",
    "trial":          "Teste",
    "em negociacao":  "Negociacao",
    "em negociação":  "Negociacao",
    "negociacao":     "Negociacao",
    "negociação":     "Negociacao",
    "cortesia":       "Cortesia",
    "demo":           "Cortesia",
}

# Códigos confirmados na tabela tipoEqp da API WESO (/Veiculos/Cadastro):
# 1=Automóvel/Camioneta até 3.500kg, 2=Caminhão, 3=Caminhonete,
# 4=Ônibus, 5=Motocicleta, 6=Trator, 7=Barco, 8=Carreta, 9=Reboque
_TIPO_VEICULO: dict[str, int] = {
    "automovel":    1,
    "automóvel":    1,
    "carro":        1,
    "caminhao":     2,
    "caminhão":     2,
    "caminhonete":  3,
    "onibus":       4,
    "ônibus":       4,
    "motocicleta":  5,
    "moto":         5,
    "trator":       6,
    "barco":        7,
    "embarcacao":   7,
    "embarcação":   7,
    "carreta":      8,
    "reboque":      9,
}


def situacao_cliente(harmonit_desc: str | None, bloqueado: bool = False) -> str | None:
    if bloqueado:
        return "Bloqueado"
    if not harmonit_desc:
        return None
    return _SITUACAO.get(harmonit_desc.lower().strip())


def tipo_veiculo(harmonit_tipo: str | None) -> int | None:
    if not harmonit_tipo:
        return None
    return _TIPO_VEICULO.get(harmonit_tipo.lower().strip())
