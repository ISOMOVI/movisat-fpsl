"""A aba Operações comparada com a tela que já existe. 2026-08-21.

🚨 A REGRA QUE FALTOU EM 17/08, agora como teste. Naquele dia a tela de placas
nasceu sem nenhum `escapeHtml` enquanto o `gerar_os.html` tinha 26 desde 15/07,
e a lição registrada foi: **tela nova se compara com a tela que já existe.** Um
`grep -c escapeHtml frontend/*.html` mostrava em um segundo, e ninguém rodou.

Em 21/08 aconteceu de novo, de outro jeito, e quem viu foi o usuário usando:

  1. a busca de serviço era um `<input>` repovoando um `<select>` a cada tecla.
     Ninguém SELECIONAVA nada -- o valor era o que calhasse de ficar em
     primeiro, o id não aparecia, e a lista mudava sob o dedo de quem digitava.
     No Gerar OS é modal, clique e campo mostrando `descrição (#id)`;
  2. a etapa 2 mostrava o cruzamento e não deixava TROCAR o cliente. No Gerar
     OS há campo, botão e modal desde sempre;
  3. 57 `style="` inline contra 26 do Gerar OS e 13 do Cadastro de Placas --
     "está tudo torto", nas palavras dele.

⚠️ ISTO NÃO É `grep` DE PALAVRA. As três verificações do meio abrem as DUAS
telas e comparam: o que a velha tem e a nova não tem é o achado. Trava que mede
palavra reprova código certo -- foi o erro de 19/08, três vezes no mesmo dia.

Roda na VPS: venv/bin/python tests/teste_tela_clonada.py
🚨 NÃO FAZ REDE.
"""
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
NOVA = RAIZ / "frontend" / "operacoes.html"
VELHA = RAIZ / "frontend" / "gerar_os.html"

ok, falhas = 0, []


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  OK   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}" + (f"\n       {detalhe}" if detalhe else ""))


nova = NOVA.read_text(encoding="utf-8")
velha = VELHA.read_text(encoding="utf-8")

print("== o que a tela velha tem, a nova tem ==")

# 1. o modal de cliente: marcação, campo e resultado
for peca, oque in (("modalCliente", "modal de cliente"),
                   ("buscaCliente", "campo de busca de cliente"),
                   ("clientesResultado", "lista de resultados"),
                   ("modalServico", "modal de serviço"),
                   ("buscaServico", "campo de busca de serviço"),
                   ("servicosResultado", "lista de serviços")):
    checar(f"a nova tem o {oque}", peca in nova,
           f"a velha tem: {peca in velha}")

checar("as duas usam as mesmas classes de modal",
       all(c in nova and c in velha
           for c in ("modal-bg", "modal-item", "modal-lista")))

print()
print("== o campo mostra o que foi ESCOLHIDO, e o id ==")
# 🚨 O id na tela não é enfeite: dois serviços do Harmonit têm o nome IDÊNTICO
# (6967 e 54845). Sem o número, o operador não tem como saber qual pegou.
checar("o serviço escolhido vai para um campo somente-leitura",
       re.search(r'id="servicoCampo"[^>]*readonly', nova) is not None)
checar("e o campo mostra o id junto do nome",
       "(#${s.id})" in nova, "o Gerar OS mostra `(#${s.id})`")
checar("o cliente escolhido também tem campo somente-leitura",
       re.search(r'id="clienteCampo"[^>]*readonly', nova) is not None)

print()
print("== a busca espera o operador terminar de digitar ==")
# Sem os 400 ms, cada tecla vira uma ida ao Harmonit.
checar("a busca de cliente tem os 400 ms do Gerar OS",
       "buscarCliente(e.target.value), 400" in nova)
checar("a busca de serviço tem os 400 ms",
       "buscarServico(e.target.value), 400" in nova)
checar("cliente exige 3 caracteres, como no Gerar OS",
       "length < 3" in nova and "mín. 3 caracteres" in nova)

print()
print("== o `<select>` que ninguém selecionava não voltou ==")
checar("não existe mais `servicoId` como seletor",
       'id="servicoId"' not in nova,
       "era o select repovoado a cada tecla")
checar("o corpo da OS lê o serviço SELECIONADO",
       "servicoSelecionado && servicoSelecionado.id" in nova)

print()
print("== escapeHtml: a lição de 17/08 ==")
n_nova = nova.count("escapeHtml(")
n_velha = velha.count("escapeHtml(")
checar(f"a nova escapa em {n_nova} lugares (a velha, {n_velha})",
       n_nova >= 20, f"nova={n_nova} velha={n_velha}")

print()
print("== geometria: o que o usuário chamou de torto ==")
inline = re.findall(r'style="[^"]*"', nova)


def e_estado(s):
    """O que pode continuar inline.

    Duas famílias, e as duas são o CONTRÁRIO de geometria estática:

      - `display` e `visibility`, que o JS liga e desliga -- é estado, e o
        `gerar_os.html` faz igual;
      - qualquer valor calculado em tempo de execução (`${...}`), como a
        largura da barra de progresso. Não dá para pôr `width:47%` num arquivo
        CSS: o número é o tempo decorrido contra o teto.

    ⚠️ A segunda família entrou em 21/08 e é o M7 de novo, do lado da trava:
    a primeira versão desta verificação reprovou a barra de progresso, que está
    certa. Trava que reprova o caminho certo ensina a ignorar a trava.
    """
    if "${" in s:
        return True
    return re.fullmatch(r'style="(display:(none|block)|visibility:hidden)"', s) is not None


estado = [s for s in inline if e_estado(s)]
estaticos = sorted(set(inline) - set(estado))
# ⚠️ display/visibility inline FICAM: são estado que o JS liga e desliga, e o
# `gerar_os.html` faz igual. O que não pode voltar é geometria -- largura,
# margem, flex, tamanho de fonte -- escrita linha a linha no HTML.
checar("nenhuma geometria estática inline no HTML",
       not estaticos, f"{len(estaticos)} sobraram: {estaticos[:4]}")
checar("e o que ficou inline é só estado",
       len(estado) == len(inline), f"{len(inline)} inline, {len(estado)} de estado")

print()
print(f"== {ok} verificações OK, {len(falhas)} falha(s) ==")
if falhas:
    for f in falhas:
        print(f"   - {f}")
    sys.exit(1)
