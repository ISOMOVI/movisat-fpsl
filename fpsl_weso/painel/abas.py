"""Compatibilidade: o vocabulário antigo de "abas", agora derivado do registro.

🚨 ESTE ARQUIVO DEIXOU DE SER FONTE EM 2026-08-17. A fonte é `telas.py`, com
código imutável por tela. Aqui ficou só a tradução para o vocabulário que o
resto do sistema já fala -- `requer_aba("gerar_os")`, `painel_usuarios.abas`,
o modal de perfil.

Por que traduzir em vez de migrar tudo de uma vez: mudar os ids exigiria migrar
a coluna `abas` de todas as contas E reescrever 25 chamadas de `requer_aba`, e
nenhuma das duas coisas melhora nada. O que faltava era o CÓDIGO, e é isso que
o registro acrescenta.

⚠️ NÃO ACRESCENTE TELA AQUI. Tela nova entra em `telas.py` e aparece aqui
sozinha. Duas listas seria exatamente o problema que o registro resolve.
"""
from . import telas as registro

# Reexporta o que o resto do sistema importa daqui.
CodigoDeTelaInvalido = registro.CodigoDeTelaInvalido
por_codigo = registro.por_codigo
normalizar = registro.normalizar
para_frontend = registro.para_frontend

IDS_VALIDOS = set(registro.PERMISSOES_VALIDAS)
IDS_CONCEDIVEIS = set(registro.PERMISSOES_CONCEDIVEIS)


def _uma_por_permissao() -> list[dict]:
    """Uma entrada por permissão, no formato antigo de `ABAS`.

    A permissão herda título e ícone da PRIMEIRA tela que a usa -- que é a
    principal dela: `cadastro_placas` fica com o Cadastro de Placas, não com o
    Histórico de Cadastros, porque TELAS está na ordem do trabalho real.
    """
    fora, vistos = [], set()
    for t in registro.TELAS:
        p = t["permissao"]
        if not p or p in vistos:
            continue
        vistos.add(p)
        fora.append({
            "id": p,
            "nome": t["titulo"],
            "rota": t["rota"],
            "icone": t["icone"],
            "descricao": t["descricao"],
            "sensivel": p in registro.PERMISSOES_SO_OWNER,
            "somente_owner": p in registro.PERMISSOES_SO_OWNER,
            "codigo": t["codigo"],
            "fase": t["fase"],
        })
    return fora


ABAS = _uma_por_permissao()


def permissoes_do_usuario(usuario: dict) -> list[str]:
    """Toda permissão acessível, inclusive fora do menu. Ver o registro."""
    return registro.permissoes_do_usuario(usuario)


def do_usuario(usuario: dict) -> list[dict]:
    """As telas que ESTE usuário vê na sidebar. Owner vê tudo que está ativo."""
    return registro.do_usuario(usuario)


def pode_acessar(usuario: dict, aba_id: str) -> bool:
    """Recebe PERMISSÃO (o vocabulário antigo), não código.

    ⚠️ As 25 chamadas de `requer_aba` passam permissão, e é assim que fica.
    Para perguntar por código existe `telas.pode_acessar`.
    """
    if usuario.get("owner"):
        return True
    if aba_id not in registro.PERMISSOES_CONCEDIVEIS:
        return False
    return aba_id in set(usuario.get("abas") or [])
