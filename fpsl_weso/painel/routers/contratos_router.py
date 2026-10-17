"""Router da Gestão de Contratos (`CTR_1.1`).

Prefixo: /painel/api/contratos
Protegido por requer_aba("contratos") — permissão de OWNER (decisão dele, 13/10:
*"somente eu, como padrão owner inicial para FPSL"*).

🚨 ETAPA C2: LÊ E CONFERE, NÃO GRAVA NADA. Nenhuma rota aqui escreve no banco,
no Harmonit, na WESO ou em disco. A gravação é a C3, e separar as duas é o que
permite o operador ver o efeito antes de assumi-lo.

🚨 A LEITURA NÃO CRUZA CLIENTE, e isto é cópia deliberada da aba Operações. Lá,
a tela velha (`/placas/extrair`) lia o PDF e batia nos dois sistemas na mesma
requisição — e a consulta ao Harmonit e à WESO é justamente a parte que
oscila. Quando ela demorava, a leitura do PDF, que é local e instantânea,
demorava junto, e a tela não dizia nada. Aqui a leitura responde na hora.
"""
import io
import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from fastapi.responses import FileResponse, PlainTextResponse

from ..auth import requer_aba
from .. import contratos_eventos as motor
from .. import contratos_grid as grid
from .. import contratos_leitura as leitura
from .. import contratos_registro as registro

log = logging.getLogger("fpsl.contratos_router")

router = APIRouter(
    prefix="/painel/api/contratos",
    tags=["contratos"],
    dependencies=[Depends(requer_aba("contratos"))],
)


@router.get("/perfis")
async def perfis():
    """Os perfis que a aba aceita, e os que ela recusa COM O MOTIVO.

    ⚠️ Os recusados vão na resposta de propósito (`M12`): a tela mostra por que
    manutenção não tem termo para subir, em vez de simplesmente não oferecer e
    deixar o operador procurando.
    """
    return {
        "aceitos": [{"id": k, "label": v["label"], "acao": v["acao"]} for k, v in leitura.PERFIS.items()],
        "recusados": [{"id": k, "motivo": m} for k, m in leitura.PERFIS_FORA.items()],
    }


@router.post("/extrair")
async def extrair(perfil: str = Query(...),
                  arquivo: UploadFile = File(...),
                  arquivo_harmonit: UploadFile | None = File(None)):
    """Lê o termo ASSINADO e, se vier, a versão do Harmonit do mesmo termo.

    🚨 DUAS VERSÕES, PORQUE É A DIFERENÇA ENTRE ELAS QUE REVELA A TROCA. Regra
    dele (13/10): *"se o termo X está assinado e o cliente pediu a troca e está
    registrado no Harmonit, está certo"*. O caso é a Maxi Confort 8872 — o
    assinado traz `DVS 2992`, e o PDF do Harmonit do MESMO termo acrescenta
    `FAC 5H30` com a anotação do pedido, sem tirar a antiga. Sem a segunda
    versão, a placa que está de fato em uso fica sem contrato na tela.

    ⚠️ A versão do Harmonit é OPCIONAL. Termo sem troca não precisa dela, e
    exigir as duas sempre travaria o caso comum por causa do raro.
    """
    if perfil in leitura.PERFIS_FORA:
        raise HTTPException(400, f"{perfil}: {leitura.PERFIS_FORA[perfil]}")
    if perfil not in leitura.PERFIS:
        raise HTTPException(400, f"Tipo de termo desconhecido: {perfil}")

    try:
        assinado = leitura.ler(io.BytesIO(await arquivo.read()), perfil)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:                                   # pragma: no cover
        log.exception("falha lendo termo assinado")
        raise HTTPException(400, f"Não foi possível ler o documento: {e}")

    resposta = dict(assinado, arquivo=arquivo.filename, troca_registrada=None,
                    eventos_do_harmonit=[], avisos_harmonit=[])

    if arquivo_harmonit is not None:
        bruto = await arquivo_harmonit.read()
        try:
            do_harmonit = leitura.ler(io.BytesIO(bruto), perfil, fonte_evento=motor.HARMONIT)
            anotacao = leitura.troca_registrada(io.BytesIO(bruto))
        except Exception as e:                               # pragma: no cover
            log.exception("falha lendo versao do Harmonit")
            raise HTTPException(400, f"Não foi possível ler a versão do Harmonit: {e}")

        resposta["arquivo_harmonit"] = arquivo_harmonit.filename
        resposta["troca_registrada"] = anotacao
        resposta["avisos_harmonit"] = do_harmonit["avisos"]

        if do_harmonit["numero"] and assinado["numero"] and do_harmonit["numero"] != assinado["numero"]:
            # 🚨 VERSÕES DE TERMOS DIFERENTES NÃO SE COMPARAM. A regra da troca
            # vale no MESMO termo; cruzar números diferentes transformaria
            # documento de outro contrato em prova de troca.
            raise HTTPException(400,
                f"Os dois arquivos são de termos diferentes: assinado {assinado['numero']}, "
                f"Harmonit {do_harmonit['numero']}. A troca só vale dentro do mesmo termo.")

        ja = {motor.chave(e["placa"]) for e in assinado["eventos"]}
        extras = [e for e in do_harmonit["eventos"] if motor.chave(e["placa"]) not in ja]
        resposta["eventos_do_harmonit"] = extras

        if extras and not anotacao and not assinado["a_definir"]:
            # Placa que apareceu depois da assinatura, sem anotação e sem vaga
            # "a definir": era assim que 256 termos "ganhavam" placa. Entra na
            # tela como aviso, e o motor não a trata como assinada.
            resposta["avisos_harmonit"].append(
                "a versão do Harmonit tem placa que não está no documento assinado e NÃO há anotação de troca: "
                + ", ".join(e["placa"] for e in extras[:5]))

    return resposta


@router.post("/conferir")
async def conferir(perfil: str = Query(...),
                   arquivo: UploadFile = File(...),
                   arquivo_harmonit: UploadFile | None = File(None)):
    """O que este termo faria com cada placa. **Não grava.**

    ⚠️ CONFERÊNCIA DO TERMO ISOLADO. Esta etapa ainda não consulta os termos
    que o cliente já tem — isso é a C3, quando houver o que consultar. Então a
    resposta diz `base_de_comparacao: "somente este termo"`, e a tela repete a
    frase: prometer "situação final do cliente" aqui seria tela que mente
    (`M12`), e foi assim que duas telas prometeram o que não faziam.
    """
    lido = await extrair(perfil=perfil, arquivo=arquivo, arquivo_harmonit=arquivo_harmonit)

    # 🚨 A TROCA DIZ QUEM ENTRA, NUNCA QUEM SAI -- E ISSO NÃO SE ADIVINHA.
    # A anotação da Maxi Confort 8872 é *"FAC 5H30 - Cliente pediu alteração da
    # placa"*: nomeia só a placa nova. No PDF do Harmonit as DUAS ficam na
    # tabela, no mesmo item, e o extrator não devolve a posição -- então não há
    # dado que diga que a `DVS 2992` é a que sai. Inferir por ausência também
    # não serve: ela está presente nas duas versões.
    #
    # Regra 13 da casa: **não se inventa identificador**. Placa inventada é
    # pior que placa faltando (`RFD 2447`), e tirar a placa errada do contrato
    # cancelaria a cobrança de um veículo que está rodando. Então a conferência
    # mostra a anotação, lista as candidatas e PEDE a confirmação; enquanto ela
    # não vem, as duas placas seguem sustentadas e isso é dito na tela.
    troca_confirmar = None
    entram = [e["placa"] for e in (lido.get("eventos_do_harmonit") or [])]
    if lido.get("troca_registrada") and entram:
        troca_confirmar = {
            "anotacao": lido["troca_registrada"],
            "entram": entram,
            "candidatas_saida": [e["placa"] for e in lido["eventos"]],
        }
        lido["avisos"].append(
            "troca registrada no Harmonit: confirme qual placa SAI. Até a confirmação, "
            f"{', '.join(entram)} entra e nenhuma sai — o termo fica com uma placa a mais.")

    termo = {
        "numero": lido["numero"],
        "empresa": "MOVISAT",
        "tipo": lido["perfil"],
        # Veio da Clicksign/assinatura em mão: nesta etapa quem afirma é o
        # operador, e a tela deixa explícito. A verificação automática na
        # Clicksign é tarefa própria, depois.
        "assinado": True,
        "assinado_em": None,
        "troca_registrada": lido.get("troca_registrada"),
        "a_definir": lido.get("a_definir"),
        "eventos": list(lido["eventos"]) + list(lido.get("eventos_do_harmonit") or []),
    }
    situacoes = motor.situacao_das_placas([termo])

    return {
        "base_de_comparacao": "somente este termo",
        "numero": lido["numero"],
        "cnpj": lido["cnpj"],
        "cliente_nome_sugerido": lido["cliente_nome_sugerido"],
        "tipo": lido["tipo"],
        "troca_registrada": lido.get("troca_registrada"),
        "troca_confirmar": troca_confirmar,
        "a_definir": lido.get("a_definir"),
        # 🆕 G4: o que o termo diz de valor, e para quais placas isso pôde ser
        # ligado. ⚠️ O valor do documento é por ITEM DE SERVIÇO, não por placa:
        # a tela mostra o que leu e diz quantas placas ficaram sem valor, em vez
        # de ratear o total -- número inventado em cobrança é pior que faltando.
        "valores": lido.get("valores") or {},
        "vagas": lido.get("vagas") or [],
        "placas": [
            {"placa": v.get("placa"), "chave": k, "situacao": v["situacao"], "base": v.get("base"),
             "aviso_ate": v.get("aviso_ate"), "obs": v.get("obs")}
            for k, v in sorted(situacoes.items())
        ],
        "sustentadas": motor.ativas(situacoes),
        "avisos": list(lido["avisos"]) + list(lido.get("avisos_harmonit") or []),
        "veiculos_sem_placa": lido.get("veiculos_sem_placa") or [],
    }


@router.post("/gravar")
async def gravar(perfil: str = Query(...),
                 cnpj: str = Form(...),
                 assinado_em: str | None = Form(None),
                 saida_confirmada: str | None = Form(None),
                 revisar_motivo: str | None = Form(None),
                 termo_id: int | None = Form(None),
                 cliente_nome: str | None = Form(None),
                 arquivo: UploadFile = File(...),
                 arquivo_harmonit: UploadFile | None = File(None),
                 usuario: dict = Depends(requer_aba("contratos"))):
    """Grava o termo e seus eventos, e recalcula a situação do cliente.

    🚨 O CNPJ VEM DO FORMULÁRIO, NÃO DO PDF. O documento sugere; quem confirma
    é o operador na tela. A rescisão não traz CNPJ nenhum (medido nos termos
    8788 e 8842), e a auditoria achou 33 documentos cujo CNPJ divergia do
    cliente que o Harmonit aponta -- gravar evento no contrato da empresa
    errada cancela ou cria cobrança no lugar errado.

    `saida_confirmada` é JSON com as placas que o operador disse que saem na
    troca. A anotação do Harmonit nomeia só quem entra, e **não se inventa
    identificador** (regra 13).

    🚨 `termo_id` É O MODO ANEXAR, E EXISTE PARA NÃO DUPLICAR TERMO. A carga
    gravou 4.599 termos **sem hash de PDF** (ela não guarda documento), e a
    única defesa deste endpoint contra repetição é o `UNIQUE(hash)`. Sem o modo
    anexar, subir o PDF assinado do 2649 da 2HM criaria um **segundo** termo
    2649, com os eventos repetidos, enquanto o primeiro seguiria contado em
    "sem assinatura" -- a tela mostraria o cliente pior por causa do conserto.
    Com `termo_id`, o termo que já existe passa a assinado e recebe só o evento
    que falta.
    """
    cnpj_limpo = "".join(c for c in (cnpj or "") if c.isdigit())
    if len(cnpj_limpo) not in (11, 14):
        raise HTTPException(400, "Informe o CNPJ (14 dígitos) ou CPF (11) do cliente.")

    conteudo = await arquivo.read()
    try:
        lido = leitura.ler(io.BytesIO(conteudo), perfil)
    except ValueError as e:
        raise HTTPException(400, str(e))

    extras, troca = [], None
    if arquivo_harmonit is not None:
        bruto = await arquivo_harmonit.read()
        do_harmonit = leitura.ler(io.BytesIO(bruto), perfil, fonte_evento=motor.HARMONIT)
        if do_harmonit["numero"] and lido["numero"] and do_harmonit["numero"] != lido["numero"]:
            raise HTTPException(400,
                f"Os dois arquivos são de termos diferentes: assinado {lido['numero']}, "
                f"Harmonit {do_harmonit['numero']}.")
        troca = leitura.troca_registrada(io.BytesIO(bruto))
        ja = {motor.chave(e["placa"]) for e in lido["eventos"]}
        extras = [e for e in do_harmonit["eventos"] if motor.chave(e["placa"]) not in ja]

    try:
        saidas = json.loads(saida_confirmada) if saida_confirmada else []
        if not isinstance(saidas, list):
            raise ValueError
    except ValueError:
        raise HTTPException(400, "saida_confirmada deve ser uma lista JSON de placas.")

    # ⚠️ TROCA SEM SAÍDA CONFIRMADA GRAVA, E FICA MARCADA "A REVISAR". Travar a
    # gravação faria o operador perder a leitura por causa de uma decisão que
    # ele talvez precise checar com o cliente; e gravar calado deixaria uma
    # placa a mais no contrato sem ninguém saber. O meio é gravar com o motivo.
    motivo = revisar_motivo
    if troca and extras and not saidas:
        motivo = ((motivo + "; ") if motivo else "") + \
            "troca registrada no Harmonit sem confirmação de qual placa sai"

    # O nome só entra se o cliente ainda não tem nome gravado -- `fonte=pdf`
    # nunca sobrescreve a correção à mão.
    sugerido = (cliente_nome or lido.get("cliente_nome_sugerido") or "").strip()
    if sugerido:
        try:
            await registro._exec(registro.definir_nome, cnpj_limpo, sugerido,
                                 usuario.get("login") or "?", "pdf")
        except ValueError:
            pass

    try:
        if termo_id:
            r = await registro.anexar_pdf(
                termo_id, cnpj_limpo, lido, assinado_em=assinado_em or None,
                enviado_por=usuario.get("login") or "?", conteudo=conteudo,
                eventos_do_harmonit=extras, troca_registrada=troca,
                saida_confirmada=saidas)
            motivo = r.get("revisar_motivo") or motivo
        else:
            r = await registro.gravar_termo(
                cnpj_limpo, lido, assinado=True, assinado_em=assinado_em or None,
                origem="upload", enviado_por=usuario.get("login") or "?",
                conteudo=conteudo, eventos_do_harmonit=extras, troca_registrada=troca,
                saida_confirmada=saidas, revisar_motivo=motivo)
    except registro.TermoJaGravado as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))

    ficha = await registro.ficha_do_cliente(cnpj_limpo)
    return {"gravado": r, "modo": "anexado" if termo_id else "novo",
            "a_revisar": bool(motivo), "revisar_motivo": motivo, "ficha": ficha}


# ── Grid (G3/G5): a tela abre numa LISTA, não num formulário ─────────────────

@router.get("/clientes")
async def clientes(q: str | None = Query(None),
                   estado: str | None = Query(None),
                   empresa: str | None = Query(None)):
    """Uma linha por cliente, com contagens, estado e as ações possíveis.

    🚨 NÃO CHAMA A FICHA. A ficha recalcula o cliente na hora; chamá-la 731
    vezes para desenhar a primeira tela era o caminho natural e errado. Aqui
    são 3 agregações sobre o cache derivado, e o recálculo em lote acontece no
    máximo uma vez por dia (o aviso prévio vence pelo calendário, sem evento).

    ⚠️ As `acoes` de cada linha vêm daqui, com o motivo quando a ação não cabe:
    botão que existe e não faz nada é defeito, e botão escondido sem explicação
    manda o operador procurar.
    """
    return await grid.listar_clientes(q=q, estado=estado, empresa=empresa)


@router.get("/clientes.csv", response_class=PlainTextResponse)
async def clientes_csv(q: str | None = Query(None),
                       estado: str | None = Query(None),
                       empresa: str | None = Query(None)):
    """O mesmo grid, com o mesmo filtro, em CSV."""
    dados = await grid.listar_clientes(q=q, estado=estado, empresa=empresa)
    return PlainTextResponse(grid.para_csv(dados), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=contratos.csv"})


@router.get("/cliente/{cnpj}/aderencia")
async def aderencia_do_cliente(cnpj: str):
    """Placa por placa: está em uso na WESO, saiu, ou nunca foi instalada.

    🚨 É O DESEMPATE DELE, por placa: *"placas sem assiantura mas placa ativa,
    placa vence, pois se existe na weos foi feita, o erro é não ter
    assinatura"*. A tela mostra o motivo de cada uma em vez de só a situação --
    "ativa" não distingue a placa que está rodando da que nunca foi instalada.

    ⚠️ Responde com a **idade do cache**: número da WESO sem dizer de quando é
    seria tela que mente por omissão.
    """
    cnpj_limpo = "".join(c for c in (cnpj or "") if c.isdigit())
    if len(cnpj_limpo) not in (11, 14):
        raise HTTPException(400, "CNPJ/CPF inválido.")
    return await grid.aderencia(cnpj_limpo)


@router.get("/carga/fila")
async def carga_fila(cnpj: str | None = Query(None), limite: int = Query(500, le=2000)):
    """Os documentos assinados que a carga (C7) não conseguiu encaixar.

    🚨 CADA LINHA É DECISÃO ESPERANDO GENTE, e é por isso que ela aparece na
    tela em vez de ficar só no log: leitura que veio descritiva, CNPJ do PDF
    divergente do cliente da pasta, número que existe no Instituto E na Movisat.
    Forçar qualquer um anexaria o documento assinado ao contrato errado.
    """
    cnpj_limpo = "".join(c for c in (cnpj or "") if c.isdigit()) or None
    return await grid.fila(cnpj_limpo, limite)


@router.get("/cliente/{cnpj}/candidatos")
async def candidatos(cnpj: str, numero: str = Query(...), empresa: str | None = Query(None)):
    """Termos deste cliente com este número e **sem PDF guardado**.

    🚨 É O QUE O MODAL PRECISA PARA NÃO DUPLICAR TERMO. A carga gravou 4.599
    termos sem hash, e `/gravar` só deduplica por hash -- sem esta consulta,
    subir o assinado do 2649 criaria um segundo 2649.

    ⚠️ Devolve lista, nunca um escolhido: a 2HM tem **dois** aditivos nº 2 na
    Clicksign, assinados em dias diferentes. Com mais de um candidato, quem
    decide é quem está na tela.
    """
    cnpj_limpo = "".join(c for c in (cnpj or "") if c.isdigit())
    return {"candidatos": await registro.listar_candidatos(cnpj_limpo, numero, empresa)}


@router.put("/cliente/{cnpj}/nome")
async def nomear(cnpj: str, corpo: dict, usuario: dict = Depends(requer_aba("contratos"))):
    """Corrige o nome do cliente. A correção à mão nunca é desfeita pela carga."""
    cnpj_limpo = "".join(c for c in (cnpj or "") if c.isdigit())
    if len(cnpj_limpo) not in (11, 14):
        raise HTTPException(400, "CNPJ/CPF inválido.")
    try:
        return await registro.nomear_cliente(cnpj_limpo, corpo.get("nome") or "",
                                             usuario.get("login") or "?")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/termo/{termo_id}/saida")
async def saida(termo_id: int, corpo: dict, usuario: dict = Depends(requer_aba("contratos"))):
    """Grava quem SAI numa troca registrada no Harmonit. Só inserção.

    🚨 A anotação do Harmonit nomeia só a placa que ENTRA (Maxi Confort 8872),
    e as duas ficam no mesmo item da tabela, sem posição. Então a saída vem de
    gente e fica gravada com a autoria -- não se inventa identificador.
    """
    try:
        return await registro.confirmar_saida_do_termo(
            termo_id, corpo.get("placa") or "", usuario.get("login") or "?")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/termo/{termo_id}/revisado")
async def revisado(termo_id: int, corpo: dict, usuario: dict = Depends(requer_aba("contratos"))):
    """Baixa o flag `revisar` e registra quem olhou. O motivo **não se apaga**."""
    try:
        return await registro.revisado(termo_id, usuario.get("login") or "?", corpo.get("nota"))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/termo/{termo_id}/pdf")
async def pdf_do_termo(termo_id: int):
    """O PDF guardado do termo.

    ⚠️ 404 **com o motivo**: os 4.599 termos da carga não têm PDF (a auditoria
    leu os documentos, a carga não os guardou), e "não encontrado" seco faria o
    operador pensar em arquivo perdido.
    """
    import asyncio

    def _ler():
        with registro._connect() as conn:
            return conn.execute(
                "SELECT arquivo, numero, origem FROM contrato_termo WHERE id = ?",
                (termo_id,)).fetchone()
    linha = await asyncio.get_running_loop().run_in_executor(None, _ler)
    if not linha:
        raise HTTPException(404, f"Termo {termo_id} não existe.")
    arquivo, numero, origem = linha
    if not arquivo:
        raise HTTPException(404, f"O termo {numero} não tem PDF guardado "
                                 f"(origem: {origem}). Suba o documento assinado pela tela.")
    caminho = registro.pasta_pdf() / arquivo
    if not caminho.exists():
        raise HTTPException(404, f"O PDF do termo {numero} está registrado como {arquivo}, "
                                 "mas não está na pasta de documentos.")
    return FileResponse(str(caminho), media_type="application/pdf", filename=arquivo)


@router.get("/cliente/{cnpj}")
async def cliente(cnpj: str):
    """Ficha do cliente: placas com situação derivada e a linha do tempo dos termos.

    ⚠️ RECALCULA NA HORA. Ler o cache sem recalcular devolveria aviso prévio
    vencido como se ainda valesse: o prazo de 90 dias passa sozinho, sem nenhum
    evento novo para disparar a conta.
    """
    cnpj_limpo = "".join(c for c in (cnpj or "") if c.isdigit())
    if len(cnpj_limpo) not in (11, 14):
        raise HTTPException(400, "CNPJ/CPF inválido.")
    return await registro.ficha_do_cliente(cnpj_limpo)


# ── Rotina de auditoria (C6) ─────────────────────────────────────────────────

@router.get("/auditoria/interruptor")
async def ler_interruptor():
    """Estado da rotina. Quem tem a aba LÊ; mudar é do dono (ver o PUT).

    🚨 DEVOLVE TAMBÉM A ÚLTIMA PASSADA (16/10), pelo mesmo motivo da `FIN_1.1`:
    "ligada" nunca foi "rodou", e esta rotina nasce desligada -- o carimbo é o
    que mostra que o laço está vivo mesmo com a flag em `false`.
    """
    from ... import rotinas, storage
    from ...services import contratos_auditoria as aud
    passada = await rotinas.ultima("contratos_auditoria")
    return {"ativa": await storage.get_config(aud.FLAG, "false") == "true",
            "intervalo_h": aud.INTERVALO_ROTINA // 3600,
            "idade_maxima_cache_h": aud.IDADE_MAXIMA_H,
            "ultima_em": passada["ultima_em"],
            "ultimo_resultado": passada["resultado"],
            "atrasada": passada["atrasada"],
            "sem_registro": passada["sem_registro"]}


@router.put("/auditoria/interruptor")
async def mudar_interruptor(corpo: dict, _=Depends(requer_aba("config"))):
    """Liga/desliga a rotina.

    🚨 A TRANCA É `requer_aba("config")`, igual à da `FIN_1.1`, e pelo mesmo
    motivo: ela barra quem não é dono E dá o recado certo. `get_owner_painel`
    responderia "só o proprietário gerencia usuários", que é mentira para quem
    tentou ligar uma rotina.

    ⚠️ LIGAR NÃO FAZ RODAR NA HORA: o laço relê a flag a cada 6 h. Para rodar
    já existe o "Rodar agora", e a tela diz isso.
    """
    from ... import storage
    from ...services import contratos_auditoria as aud
    await storage.set_config(aud.FLAG, "true" if corpo.get("ativa") else "false")
    # A prova é RELER, nunca o que acabamos de mandar gravar.
    return {"ativa": await storage.get_config(aud.FLAG, "false") == "true",
            "intervalo_h": aud.INTERVALO_ROTINA // 3600}


@router.post("/auditoria/rodar-agora")
async def rodar_agora(_=Depends(requer_aba("config"))):
    """Roda a auditoria na hora, independente do interruptor."""
    from ...services import contratos_auditoria as aud
    return await aud.run_auditoria()


@router.get("/auditoria/achados")
async def achados(tipo: str | None = Query(None), limite: int = Query(200, le=2000)):
    """Os achados da última rodada, agrupados por tipo.

    ⚠️ A TABELA É REFEITA A CADA RODADA, de propósito: achado é retrato de um
    instante. Mostrar achado velho como atual seria tela que mente.
    """
    from ...services import contratos_auditoria as aud
    from .. import contratos_registro as reg

    def _ler(conn):
        quando = conn.execute("SELECT MAX(rodada_em) FROM contrato_achado").fetchone()[0]
        resumo = [{"tipo": t, "o_que_e": aud.TIPOS.get(t, ""), "quantos": n}
                  for t, n in conn.execute(
                      "SELECT tipo, COUNT(*) FROM contrato_achado GROUP BY tipo ORDER BY 2 DESC")]
        sql = "SELECT tipo, cnpj, placa_texto, detalhe FROM contrato_achado"
        p = ()
        if tipo:
            sql += " WHERE tipo = ?"
            p = (tipo,)
        sql += " ORDER BY tipo, cnpj LIMIT ?"
        linhas = [{"tipo": a, "cnpj": b, "placa": c, "detalhe": d}
                  for a, b, c, d in conn.execute(sql, p + (limite,))]
        return {"rodada_em": quando, "resumo": resumo, "achados": linhas}

    import asyncio
    def _run():
        with reg._connect() as conn:
            return _ler(conn)
    return await asyncio.get_running_loop().run_in_executor(None, _run)
