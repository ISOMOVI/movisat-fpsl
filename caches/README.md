# `caches/` — os espelhos diários das duas bases externas

Aqui moram **só os scripts**. Os bancos ficam fora do repositório, e isso é
deliberado.

| | WESO | Harmonit |
|---|---|---|
| Script | `weso_atualizar.py` | `harmonit_atualizar.py` |
| Chamado pelo cron via | `weso_rodar.sh` | `harmonit_rodar.sh` |
| Horário | **04:15** | **04:50** |
| Banco (fora do git) | `/home/claude/weso_cache/weso.db` | `/home/claude/harmonit_cache/harmonit.db` |
| Log (fora do git) | `/home/claude/weso_cache/atualizar.log` | `/home/claude/harmonit_cache/atualizar.log` |
| Tamanho | 1.955 veículos, 3.765 rastreadores, 4.070 chips, 300 clientes | 9.116 veículos, 653 clientes |
| Custo | ~19 s | ~2 s |

## Por que o banco não entra no git

É **dado gerado**: refeito inteiro todo dia, pesa MB e não responde nenhuma
pergunta que o histórico do repositório devesse responder. O que precisa
sobreviver é o script que sabe refazê-lo. `.gitignore` na raiz cobre `*.db`.

## Por que os dados ficam nesses caminhos, e não aqui

O `weso.db` **não se muda de lugar**: `fpsl_weso/painel/equipamentos.py` e
`painel/routers/placas_router.py` apontam para `/home/claude/weso_cache` numa
constante absoluta (`CACHE_DIR`), e o `cache.py` que os dois importam vive lá.
Mover o dado custaria mexer em código de produção para não ganhar nada.

O `harmonit.db` seguiu o mesmo caminho por simetria — quem o lê é
`operacoes_router.CACHE_HARMONIT`.

## A estratégia é a mesma nos dois, e ela tem motivo

1. **Monta um banco NOVO num arquivo temporário e só troca no fim,
   atomicamente.** Cache pela metade é pior que cache velho, porque parece
   completo. O leitor nunca vê meio caminho.
2. **Piso de sanidade.** Resposta muito menor que a base conhecida é problema
   do outro lado, não a base tendo encolhido. Sem o piso, um dia ruim do
   fornecedor trocaria o cache bom por um quase vazio — e a tela passaria a
   dizer "este cliente não tem veículo", mentira indistinguível da verdade.
3. **`integrity_check` antes de promover.**
4. **Carimbo em `meta.atualizado_em`**, para quem lê poder dizer de quando é o
   dado.
5. **Reusa o `venv` e o `.env` do FPSL.** Nenhuma credencial é duplicada aqui.

## 🚨 Por que o cache do Harmonit existe (24/08)

A lista de placas da etapa 3 dos perfis **sem termo** saía da tabela
`harmonit_veiculos`, dentro do banco do app, e **nada a atualizava** — nenhum
cron, nenhum caminho no código. Ela andava quando alguém lembrava de rodar um
script à mão, e não havia como perceber que tinha parado: lista velha e lista
nova têm a mesma cara.

Medido no dia: Harmonit ao vivo **9.116** × espelho **9.114**. Uma das duas
ausentes, `FWB 0E36`, tinha sido criada **pelo próprio painel três horas
antes**.

A regra da operação é que manutenção só acontece em placa que já está na WESO
há pelo menos um dia. A regra é boa — mas só se sustenta se a base for refeita
todo dia. A placa criada hoje não é elegível hoje; amanhã, quando passa a ser,
continuava fora da lista. Para sempre. **Não era a placa que era nova demais:
era o espelho que nunca deixava de ser velho.**

## O que ainda depende de gente

- **`weso_cache/cache.py` continua fora do git.** É biblioteca importada em
  produção pelo caminho absoluto; trazê-la para cá é mudar duas constantes de
  código de produção, e isso é uma decisão à parte.
- **Os dois diretórios de dados não entram no `backup_projetos.sh`.** Perder
  um deles custa uma rodada do cron, não trabalho — mas o log de execução se
  perde junto.
