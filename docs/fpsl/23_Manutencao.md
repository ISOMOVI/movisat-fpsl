# Perfis de Manutenção — os dois primeiros sem termo

**Criado 2026-08-14.** Os 7 perfis anteriores nascem de um PDF assinado. Estes
dois nascem de um chamado: não há documento, não há número de termo e não há
item de contrato — o que existe é uma placa e um defeito.

| | Manutenção no local | Manutenção com troca |
|---|---|---|
| O que acontece | técnico resolve com o equipamento que já está no veículo | o equipamento sai e entra outro, **no mesmo veículo** |
| Placa lida | a própria | `<PLACA>-MANUT` (recipiente) |
| OS por placa | 1 | 1 |
| Materiais | serviço + equipamento + ENTREGA OS | idem, com o equipamento **que entra** |
| Financeira | nenhuma | nenhuma |

## Por que 1 OS e não 2

Substituição gera 2 OS porque os veículos são **diferentes** — o equipamento
muda de carro. Na manutenção o veículo é o mesmo, que é exatamente o caso já
decidido em 13/08 para o Upgrade: *"o upgrade troca o EQUIPAMENTO, não o
veículo"*, 1 OS com SAIRÁ e ENTRARÁ.

## O recipiente `-MANUT`

O setor de configuração cria na WESO uma placa derivada e vincula nela o
equipamento novo antes de ele ir a campo — o mesmo desenho do `-UPGRADE`.
Medido em 14/08: 5 recipientes existiam, todos com a descrição `MANUTENCAO`.

🚨 **A trava aqui é mais fraca que a do Upgrade, e é de propósito.** O upgrade
compara a descrição com `TERMO {termo}`, que identifica a rodada. A manutenção
não tem termo e todo recipiente se chama `MANUTENCAO` — então a comparação
prova que é *um* recipiente de manutenção, não que é o *desta* manutenção. O
que fecha o resto é liberar a série no fim: recipiente usado deixa de existir.

🚨 **O acento quase derrubou tudo.** Os 5 recipientes estão gravados
`MANUTENCAO`, sem cedilha e sem til; a padronização humana escreve
`MANUTENÇÃO`. Por isso `_norm_desc` passou a dobrar acento — sem isso, **toda**
geração de manutenção morreria em HTTP 400, com uma mensagem falando de upgrade
anterior.

🚨 **O espaço pode estar em qualquer lugar.** `GJN8689 - MANUT`,
`GJN 8689-MANUT` e ` GJN8689-MANUT` (esta última já existe na WESO) são a mesma
coisa. A comparação normaliza os dois lados tirando **todo** espaço. A trava é
a placa original inteira: `GJN868-MANUT`, com um dígito a menos, simplesmente
não casa — não há margem para "parecido o bastante".

## Leitura ao vivo — requisito, não luxo

`modelo_da_placa` lê só o cache local, que atualiza às 04:15. O recipiente da
manutenção é criado minutos antes da OS. Ler do cache devolveria `modelo não
localizado` para um equipamento que existe — e sem modelo não há produto no
de-para, então a OS nasceria **sem a linha do equipamento**. É exatamente o
defeito achado auditando o termo 8820.

Por isso os perfis `sem_termo` usam `dados_das_placas`, que vai à WESO ao vivo.
Custo medido: a base inteira de veículos custa **2,3s**; filtrar uma placa custa
**~6s** (a API é mais lenta com filtro que sem). Uma chamada para a base toda,
sempre.

## Sem "entrará" plausível

Decisão de 14/08: recipiente ausente, ambíguo, de outra rodada ou sem
rastreador é **descartado**. A OS sai com `ENTRARÁ: NUMERO DE SERIE` e **sem** o
equipamento nos materiais, sempre com aviso na tela.

Isso **substituiu o HTTP 400** que o upgrade dava. O efeito é o mesmo — nenhum
dado errado entra — sem travar quem está tentando trabalhar.

⚠️ São dois marcadores com sentidos diferentes: `série não localizada` é o
SAIRÁ ("não sei o que está no veículo"); `NUMERO DE SERIE` é o ENTRARÁ ("o
técnico preenche na instalação").

## Cabeçalho: tipo e problema por NOME

🚨 **ID fixo em código apodrece em silêncio.** Das 14 OS de manutenção que a
casa já abriu na mão, 7 usam `tipo = 55`, que **não está mais** na lista do
Harmonit. Os perfis guardam `"Solicitação de Cliente"` e `"MANUTENÇÃO"` como
texto e resolvem contra a lista viva na geração.

Política: nome sumiu da lista → **recusa** (é apodrecimento, precisa de decisão
humana). Lista não respondeu → usa o último id conhecido e **avisa** (é
transiente; travar por rede seria pior).

Valores medidos em 14/08: Tipo `Solicitação de Cliente` = 1783 · Problema
`MANUTENÇÃO` = 7384 · Serviço `MANUTENÇÃO` = 6966 · Situação `Nova
sollicitação` = 38 · Prioridade Normal = 382.

## Manutenção não flega nada

Decisão do usuário, 14/08: **nenhum item de OS de manutenção marca cobrar ou
comodato.** O equipamento aparece como material para o técnico saber com o que
vai lidar — não é patrimônio saindo nem cobrança entrando. Marcar comodato numa
manutenção emitiria patrimônio que já está com o cliente.

## Liberar a série

🚨 **Excluir o veículo NÃO libera o rastreador.** Medido na Pastelaria Velasco
em 14/08: criei `OVG7C78-MANUT` com o rastreador 50171 (que estava em Estoque),
ele virou Instalado, apaguei o veículo com `/Veiculos/Excluir` — e o rastreador
**continuou Instalado**, agora sem veículo nenhum. São duas chamadas.

🚨 **`situacao` é objeto, não texto.** `{"situacao": "Estoque"}` devolve "JSON
inválido"; o certo é `{"situacao": {"descricao": "Estoque"}}`.

🚨 **A ordem é liberar primeiro, apagar depois.** Se a segunda falhar sobra um
recipiente vazio — visível e inofensivo. Na ordem contrária sobraria série presa
sem dono, que é invisível.

⚠️ **A WESO mente no código de retorno nos dois sentidos.** No mesmo teste, o
cadastro do recipiente devolveu **erro HTML e gravou o registro**. Cada passo é
conferido relendo o estado.

Três provas antes de liberar, e as três precisam valer: a OS foi criada, a série
está na descrição, e o material do equipamento foi aceito pelo Harmonit. Falhou
uma, o recipiente fica onde está.

Deu erro no meio: desfaz (devolve a situação para Instalado) e **os números
ficam na tela final** — `veiculo_id` e `rastreador_id` são o que uma pessoa
precisa para resolver na mão.

## Item nas duas OS

Nasceu do termo 8839: "Central 24 horas" vem como CONTRATADO com R$ 10,00, cai
em cobrança e **some da OS que o técnico lê**. A coluna `nas_duas` em
`painel_vinculos_itens` marca o item para aparecer também na operacional, sem
flag e com **valor zero** — o preço já está contado na financeira, e valor
repetido nas duas vira soma dobrada no primeiro relatório que alguém montar.

Vale para **todos** os perfis. Aditivo de 100 placas: 100 cópias operacionais (a
alocação distribui 1 por veículo) e 1 linha na financeira com a quantidade do
contrato.

⚠️ Havia **dois vínculos** para a mesma coisa — `CENTRAL 24 HORAS` (visível) e
`CENTRAL 24H` (oculto). Um termo escrito na segunda grafia sumia das duas OS em
silêncio. Unificados em 14/08, os dois apontando para o serviço 6976.

## Testes

`tests/teste_manutencao.py` — 54 verificações, só leitura, não toca Harmonit e
não escreve na WESO. Trava os dois perfis, a chave do recipiente, o acento, os
quatro motivos de descarte, a cópia `nas_duas` e as três provas da liberação.
`tests/teste_upgrade_8820.py` continua verde (44), agora incluindo a garantia de
que sem recipiente o modelo é o marcador, não um modelo plausível.
