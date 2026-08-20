"""Na coluna de veículo, o que vem depois do traço é a placa. 2026-08-20.

Decisão do usuário, nascida do termo 8846: o campo se chama "Veículo e Placa ou
Chassis do veículo", e o que vem depois do `-` é o identificador — **inclusive
fora do padrão brasileiro**.

O caso real: o 8846 traz `NISSAN, 2022, DIESEL - RZL H405`. `RZL H405` não casa
com nenhum padrão brasileiro (o antigo é 3 letras + 4 dígitos; o Mercosul é
3 letras + dígito + letra + 2 dígitos), mas **existe na WESO com rastreador
vinculado**. O painel recusava gerar a OS com `400 Nenhuma placa informada`, e a
Erika tentou seis vezes sem entender por quê.

🚨 A GUARDA NÃO É ZELO EXCESSIVO, E ESTE ARQUIVO EXISTE POR CAUSA DELA. Medido
nos 14 fixtures antes de escrever a regra: sem guarda, duas linhas de texto
corrido que caem na tabela de veículos do `transferencia_novo.pdf` virariam a
placa `la também no contrato principal de`. Isso é o `RFD 2447` renascendo.

E a regra roda DEPOIS do reconhecimento normal: 4 linhas dos fixtures têm placa
E traço na descrição, inclusive `SEMI- REBOQUE`.

Roda na VPS: venv/bin/python tests/teste_placa_pos_traco.py
🚨 NÃO FAZ REDE. Lê PDF do disco e chama função pura.
"""
import io
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fpsl_weso.painel import pdf_extractor as ex  # noqa: E402

ok, falhas = 0, []
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


def extrair(arquivo, perfil):
    dados = (FIXTURES / arquivo).read_bytes()
    return ex.extrair_campos(io.BytesIO(dados), perfil)


# ── 1. o caso real ───────────────────────────────────────────────────────────

def teste_8846():
    print("\n1. O termo 8846 — o caso que travou a geração")
    c = extrair("contrato_novo_8846.pdf", "contrato_novo")
    placas = c.get("placas") or []
    checar("agora lê 1 veículo, e não zero", len(placas) == 1, str(placas))
    checar("nenhuma linha sobra para revisão humana",
           not (c.get("veiculos_sem_placa") or []),
           str(c.get("veiculos_sem_placa")))
    if not placas:
        return
    p = placas[0]
    checar("a placa é a do termo, como está escrita",
           p["placa"] == "RZL H405", repr(p["placa"]))
    checar("a descrição do veículo fica sem a placa",
           p["veiculo"] == "NISSAN, 2022, DIESEL", repr(p["veiculo"]))
    # ⚠️ Marcada como não convencional para a tela destacar — é rótulo de
    # conferência visual, não tratamento diferente. Chassi e série já são assim.
    checar("vem marcada como NÃO convencional, para a tela destacar",
           p.get("placa_convencional") is False, str(p))
    checar("o número do termo continua sendo lido", c.get("termo") == "8846")
    checar("e os 12 itens do contrato continuam vindo",
           len(c.get("itens") or []) == 12, str(len(c.get("itens") or [])))


# ── 2. a guarda: texto corrido NÃO vira placa ───────────────────────────────

def teste_nao_inventa():
    print("\n2. A guarda — texto corrido continua indo para revisão humana")
    c = extrair("transferencia_novo.pdf", "transferencia_novo_titular")
    sem = c.get("veiculos_sem_placa") or []
    checar("as duas linhas de texto corrido seguem em revisão",
           len(sem) == 2, str(sem))
    textos = " | ".join(s["texto"] for s in sem)
    checar("inclusive a que termina com frase depois do traço",
           "contrato principal de" in textos, textos[:160])
    placas = [p["placa"] for p in (c.get("placas") or [])]
    checar("e NENHUMA placa nasceu de frase",
           not any("contrato" in p.lower() for p in placas), str(placas[:5]))
    checar("as 28 placas de verdade continuam lá", len(placas) == 28,
           str(len(placas)))


# ── 3. quem já tinha placa não é afetado ────────────────────────────────────

def teste_nao_rouba():
    print("\n3. Linha que já tem placa não é tocada — a regra vem DEPOIS")
    casos = [
        ("cliente_novo.pdf", "contrato_novo", "TEW 6B41"),
        ("upgrade_8820.pdf", "upgrade", "OOM 3895"),
        ("transferencia_existente.pdf", "transferencia_antigo_titular",
         "PGT 6726"),
    ]
    for arquivo, perfil, esperada in casos:
        c = extrair(arquivo, perfil)
        placas = [p["placa"] for p in (c.get("placas") or [])]
        checar(f"{arquivo}: {esperada} continua sendo lida",
               esperada in placas, str(placas[:6]))


# ── 4. os limites da guarda, cada um com o seu caso ─────────────────────────

def teste_limites():
    print("\n4. Cada limite da guarda, com o caso que o justifica")
    # 🚨 PLACA ESTRANGEIRA É O MOTIVO DA REGRA. A do 8846 é CHILENA — 4 letras
    # + 2 dígitos, escrita `RZ.LH40.5` — e foi adaptada à força ao Mercosul por
    # quem escreveu o termo. Exigir formato brasileiro, ou mesmo alfanumérico
    # puro, reprovaria a grafia original.
    aceita = [
        ("NISSAN, 2022, DIESEL - RZ.LH40.5", "RZ.LH40.5",
         "a chilena com pontos, a grafia de verdade"),
        ("NISSAN, 2022, DIESEL - RZL H405", "RZL H405",
         "a mesma, adaptada ao Mercosul no termo"),
        ("VEICULO - BCDF.12", "BCDF.12", "chilena atual, 4 letras + 2 dígitos"),
        ("VEICULO - AB-123-CD", "AB-123-CD", "estrangeira com hífen interno"),
        ("FORD CARGO - ABC1D23", "ABC1D23", "Mercosul colado"),
    ]
    for celula, esperado, porque in aceita:
        ident, _ = ex._placa_pos_traco(celula)
        checar(f"aceita — {porque}", ident == esperado,
               f"{celula!r} -> {ident!r}")

    recusa = [
        ("...registrá-la também no contrato principal de", "6 blocos: frase"),
        ("VEICULO - de", "curto demais e sem dígito"),
        ("VEICULO - SEMI REBOQUE", "sem dígito nenhum"),
        ("VEICULO - também", "palavra: não tem dígito"),
        ("VEICULO - 1BM6115JJMD002601", "17 caracteres: chassi tem via própria"),
        ("VEICULO - (Veiculo transferido do contrato 8665)",
         "parênteses são marca de prosa"),
        ("SEM TRACO NENHUM", "não há traço"),
        ("VEICULO -", "nada depois do traço"),
        ("VEICULO - 12345678", "só dígitos, sem letra"),
    ]
    for celula, porque in recusa:
        ident, _ = ex._placa_pos_traco(celula)
        checar(f"recusa — {porque}", ident is None, f"{celula!r} -> {ident!r}")


# ── 5. o separador é o traço COM ESPAÇO dos dois lados ──────────────────────

def teste_separador():
    print("\n5. O separador é ` - `, não qualquer traço")
    # Achado ao testar placa com hífen interno: cortando no último traço,
    # `AB-123-CD` virava `CD`.
    ident, veic = ex._placa_pos_traco("VEICULO IMPORTADO - AB-123-CD")
    checar("hífen DENTRO da placa não parte a placa",
           ident == "AB-123-CD", repr(ident))
    checar("e a descrição do veículo fica inteira",
           veic == "VEICULO IMPORTADO", repr(veic))

    # `SR/FACCHINI SEMI- REBOQUE` tem traço de palavra quebrada, com espaço só
    # de um lado. Não é separador.
    ident, _ = ex._placa_pos_traco("SR/FACCHINI SEMI- REBOQUE, DIESEL, 2015")
    checar("traço de palavra quebrada não é separador", ident is None,
           repr(ident))

    # ⚠️ CASO PERMISSIVO CONHECIDO, e é assim de propósito. A sua regra é
    # "depois do veículo e do traço, é placa, não importa o que tiver ali".
    # Então `- Aditivo 8782` numa linha SEM placa reconhecida entra como
    # identificador. Na prática essa linha já tem placa e nunca chega aqui; e o
    # que entra vem marcado como não convencional, para a tela destacar e
    # alguém confirmar — que é o que a regra 13 pede.
    ident, _ = ex._placa_pos_traco("SCANIA/P 340 - Aditivo 8782")
    checar("permissivo assumido: aceita o que vier depois do separador",
           ident == "ADITIVO 8782", repr(ident))

    # 🚨 A que mais importa, escrita por extenso: sem esta linha o `RFD 2447`
    # volta por outra porta.
    frase = ("Contudo, como a placa permanecia vinculada ao contrato da "
             "Slotran, foi necessário registrá-la também no contrato principal "
             "de")
    ident, _ = ex._placa_pos_traco(frase)
    checar("a frase exata do fixture NÃO vira placa", ident is None,
           repr(ident))


def main():
    for t in (teste_8846, teste_nao_inventa, teste_nao_rouba, teste_limites,
              teste_separador):
        t()
    print(f"\n{'=' * 62}")
    print(f"{ok} verificações OK, {len(falhas)} falhas")
    if falhas:
        for f in falhas:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
