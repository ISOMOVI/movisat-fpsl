# 18 — Testes do FPSL

**Criado em 2026-07-27.** Antes disso o projeto não tinha teste automatizado nenhum:
o que existia era `test_extracao.py`, um script de 21 linhas que **imprimia JSON e não
afirmava nada** — apontando para `/tmp/testes_pdf/`, que qualquer reboot apaga. Foi
removido nesta data.

Tudo aqui é **só leitura**: nenhum teste escreve na WESO, no Harmonit, nem em produção.

---

## `tests/teste_regressao_extracao.py` — extração de termos

**45 asserções sobre os 9 documentos REAIS**, versionados em `tests/fixtures/`.

```bash
cd /home/claude/fpsl_weso && venv/bin/python tests/teste_regressao_extracao.py
```

### Por que existe

O extrator já quebrou **em silêncio** — nenhum erro, nenhum log, dado sumindo:

| Bug histórico | O que acontecia | Guarda no teste |
|---|---|---|
| Transferência roteada pro parser errado (16/07) | 14 de 28 placas sumiam; cliente nunca capturado | `[9] placas == 28` |
| Tabela em 2 colunas (16/07) | `next()` pegava só a 1ª coluna | `[2] placas == 28` |
| Continuação de página (23/07) | Rescisão lia só a 1ª página: 12 em vez de 26 | `[5] veiculos == 26` |
| Comodato × cobrar (20/07) | Item sem indicação de origem do custo | `[1] todo item tem comodato_ou_aquisicao` |
| Acessório com bullet `▶` (23/07) | Acessório não virava item de OS | `[6] acessório do bullet virou item` |
| Termo errado (rescisão que é transferência) | Gerava OS do tipo errado | `[7] alerta_transferencia` |

**Cada número travado é um bug que já aconteceu.** Não são valores arbitrários.

### Baseline (conferido a mão em 2026-07-27, não só "o que saiu")

| fixture | perfil | termo | placas | itens | observação |
|---|---|---|---|---|---|
| `cliente_novo.pdf` | cliente_novo | 8768 | 2 | 13 | FAG |
| `cliente_novo2.pdf` | cliente_novo | 8771 | 28 | 5 | 2 colunas |
| `aditivo2.pdf` | aditivo | 8782 | 1 | 8 | |
| `trz_8790_aditivo.pdf` | aditivo | 8790 | 1 | 7 | |
| `rescisao.pdf` | rescisao | 8788 | **19** | 4 | `veiculos`=26 |
| `substituicao.pdf` | substituicao | 8786 | 0 | 1 | usa `pares` |
| `termo_errado.pdf` | rescisao | 8787 | 1 | 0 | dispara alerta |
| `transferencia_existente.pdf` | transferencia | 8785 | 1 | 7 | |
| `transferencia_novo.pdf` | transferencia | 8771 | 28 | 5 | |

### Duas armadilhas de leitura (investigadas em 27/07, não são bug)

1. **Rescisão: `veiculos`=26 mas `placas`=19.** `veiculos` é a lista crua da tabela e
   inclui **7 linhas sem placa**; `placas` só as que têm (26−7=19). O teste trava os
   **dois** de propósito: se um mudar sem o outro, algo regrediu. (Ainda há 3 placas
   repetidas dentro de `veiculos` — `TTW 4C85`, `TTW 3B64`, `TUU 2I29` — que é o caso
   tratado pelo dedup na geração de OS, não erro de extração.)
2. **Substituição tem `placas`=0 e isso está certo.** Esse parser não usa `placas`: usa
   **`pares`** (`placa_saida`/`placa_entrada`/`acessorios_entrada`), porque substituição
   é sempre veículo que sai × veículo que entra.

### Quando um número mudar

**Não atualize o número para fazer passar.** Descubra primeiro se o documento mudou ou
se o extrator regrediu. `tests/dump_extracao.py` imprime o que o extrator devolve hoje,
para comparar antes de decidir.

---

## `tests/teste_perfis.py` — perfis de acesso do painel

**22 asserções** (2026-07-29: entrou a aba `placas`, e o número de abas é
travado de propósito — aba nova sem pensar em permissão faz o teste falhar).
Owner enxerga tudo; operador só as abas marcadas; aba não concedida
dá 403; aba removida vira 403 na hora; owner não pode ser desativado. Gera o token
internamente — **nunca passa senha por linha de comando**. Cria um operador de teste e
o remove no fim. Detalhe em `17_Perfis_Acesso.md`.

```bash
cd /home/claude/fpsl_weso && venv/bin/python tests/teste_perfis.py
```

---

## `analisar_placas_weso.py` (raiz) — diagnóstico, não teste

Só leitura, sobre a base real da WESO: formato das placas (com/sem espaço × convencional
/ Mercosul / chassi), campos que o `Consultar` devolve, placas repetidas. Foi o que
fechou o **W1** e produziu o **B8** em `10_Inconsistencias.md`.

---

---

## `tests/teste_demandas.py` — o painel de demandas (14/08)

**43 verificações. TESTE DE INTEGRAÇÃO: fala HTTP com o serviço local.** Não
toca Harmonit nem WESO.

🚨 **Por que ele existe.** O painel de demandas está em uso de verdade,
compartilhado por link e **sem login**, e até 14/08 tinha zero teste. Os três
defeitos de 07/08 só apareceram porque alguém usou. Agora cada um está travado:

| Defeito de 07/08 | Guarda no teste |
|---|---|
| `pessoa_id` nulo → 422 em todo card | `[3]` card sem responsável é recusado, com código claro |
| `datetime('now')` em UTC, 3h à frente | `[5]` compara o carimbo com a hora LOCAL, e confere que local ≠ UTC |
| prazo no ano 0002, atrasado para sempre | `[4]` ano 0002 e ano 9999 recusados; a comparação de atraso é de texto |

Cobre ainda: a **esteira** (card de baixo preso até o de cima concluir), o
`CHECK` de etapa concluída sem data, o isolamento entre quadros (token de um
não alcança item de outro) e o **limitador de escrita**.

⚠️ **CRIA O PRÓPRIO QUADRO E APAGA NO FIM.** Nunca toca nos dois quadros reais.
A prova de que limpou é reler a tabela, não o retorno do `DELETE`.

🚨 **DUAS DESCOBERTAS ESCREVENDO ESTE TESTE:**

**1. Todo card nasce com uma etapa.** `criar_item` já insere uma etapa junto.
Eu tinha suposto que nascia vazio, e o teste da esteira reprovava — a esteira
estava certa, minha expectativa é que estava errada.

**2. O limitador é 60 escritas por minuto POR IP, e o teste faz ~30.** Duas
execuções seguidas no mesmo minuto estouravam o teto: o 429 na criação do card
deixava o id nulo e as chamadas seguintes viravam 422 em `/item/None` — o que
*parece* defeito de prazo e não é. O teste passou a mandar `X-Real-IP` na faixa
`203.0.113.0/24` (TEST-NET-3, RFC 5737: reservada para documentação, nunca é
gente de verdade), então não rouba a cota de ninguém nem herda a de ninguém. E
o limitador ganhou seção própria, com IP separado.

```bash
cd /home/claude/fpsl_weso && venv/bin/python tests/teste_demandas.py
```

---

## `tests/teste_roteadores_painel.py` — contrato de acesso (14/08)

**81 verificações** sobre **24 rotas** dos 8 roteadores restantes.

🚨 **Por que ele existe.** A trava de acesso é declarativa (`requer_aba(...)` no
decorador), e trava declarativa é fácil de esquecer numa rota nova: ninguém
percebe, porque a rota simplesmente funciona — para todo mundo. O teste afirma,
rota por rota: sem token → **401**; token sem a aba → **403**; token do owner →
nem um nem outro.

⚠️ **NÃO EXERCITA ROTA DE ESCRITA.** `clientes/criar`, `placas/criar` e
`oficina/resync` gravam na WESO; `os-scan/varrer` varre o Harmonit inteiro.
Dessas só se testa a tranca — abrir a porta para ver se abre estragaria dado
real. As de leitura são chamadas de verdade e têm o formato conferido.

🚨 **ACHADO: a aba `placas` não é exigida por rota nenhuma.** Ela existe no
catálogo, aparece na barra lateral e pode ser concedida — mas o `placas_router`
pede `gerar_os`. Na prática: quem recebe só "Placas" vê a aba e **não consegue
usar**; e quem tem "Gerar OS" **cria placa na WESO sem ter recebido "Placas"**.
Não foi corrigido por conta própria — mudar quem pode o quê é decisão do
usuário. Está travado no teste como órfã conhecida, e o teste reprova se
aparecer outra órfã **ou** se esta for resolvida.

⚠️ Registra também que o login devolve **`access_token`**, não `token`.

```bash
cd /home/claude/fpsl_weso && venv/bin/python tests/teste_roteadores_painel.py
```

---

## `tests/teste_manutencao.py` — perfis sem termo (14/08)

**65 verificações.** Os dois perfis de manutenção, a chave do recipiente
`-MANUT` tolerante a espaço, o acento dobrado, os quatro motivos de descarte do
recipiente, a cópia `nas_duas` e as três provas da liberação da série.

Inclui um verificador que **varre o JavaScript das telas e reprova se alguma
função chamada não existir**. Ele nasceu de um defeito real: `extrair()` chamava
`renderPlacas()` e `validarEtapa2()`, que nunca existiram — clicar em "Gerar OS"
lançava `ReferenceError` e o fluxo parava antes de trocar de etapa. **`node
--check` não pega**: valida sintaxe, e a sintaxe estava correta.

---

---

## `tests/teste_higiene_placas_weso.py` — higiene da base WESO

**25 verificações. TESTE DE INTEGRAÇÃO: bate na WESO de verdade (~2,3s),
somente leitura.** Criado em 2026-07-29 como etapa 4 do plano 21.

Falha se aparecer placa com espaço nas pontas, espaço duplo ou **colisão nova**.
Também verifica que a leitura tolerante (`weso_lookup`) continua achando a mesma
placa em 4 grafias diferentes.

⚠️ **Na primeira execução ele já pegou dois casos reais** — uma placa cadastrada
com espaço *durante* a sessão que limpava a base, e uma ambiguidade que a nossa
própria normalização cria (`OBD 3` × `OBD 3*`). Ver `21_Plano_Higiene_Placas.md`.

### Mudança de 14/08 — a regra de minúscula ficou restrita

🚨 **MINÚSCULA SÓ É COBRADA NOS NOSSOS PADRÕES**: placa convencional (com ou sem
o marcador `(RD)`), chassi rotulado (`CHASSI: ` + 17) e placa-recipiente
(`<PLACA>-UPGRADE` / `<PLACA>-MANUT`). Decisão do usuário: a base tem
identificadores que não são placa e nunca vão ser — `Móvel 1`, `TAG
identificação`, `OBD 4G - 17`, `ISCA DE CARGA` — e cobrar caixa alta neles é
cobrar uma regra que não existe. Reprovar por causa deles treinava a ignorar a
suíte inteira.

⚠️ **O espaço continua valendo para TODOS.** Minúscula é convenção; espaço é
falha silenciosa — foi ele que tornou `' TTX 0H91'` invisível para
`/Veiculos/Consultar?placa=` no termo 8788, que é o motivo desta suíte existir.

🚨 **O filtro reusa `placas.eh_convencional`, e não um regex próprio.** O regex
que eu tinha escrito deixava **47 placas `(RD) EDF 5724` fora do escopo** — ou
seja, sem a proteção que a suíte existe para dar. A regra de "o que é placa"
mora em `fpsl_weso/placas.py` e só lá; duas definições da mesma coisa divergem.

---

## O que ainda NÃO tem teste

- **Geração real de OS** (`confirmar:true`) — o dry-run está coberto ponta a
  ponta; a escrita real só foi validada à mão, com OS reais criadas e apagadas
- **A tela num navegador** — há verificação de referência do JS, mas ninguém
  clicou. Verificado ≠ exercitado
- Varredura de OS (`os_scan_router`) — só a tranca de acesso
- Escrita na WESO (`/weso/os/adicionar`) — a Fase 2 vai precisar de teste próprio
- Os 12 testes de Oficina, que validavam o fluxo descartado e precisam ser reescritos

---

## Contagem atual (2026-08-14)

**431 verificações em 10 arquivos**, todas verdes.

| Arquivo | Verificações |
|---|---|
| `tests/teste_roteadores_painel.py` | 81 |
| `tests/teste_placas.py` | 72 |
| `tests/teste_manutencao.py` | 65 |
| `tests/teste_regressao_extracao.py` | 57 |
| `tests/teste_upgrade_8820.py` | 53 |
| `tests/teste_demandas.py` | 43 |
| `tests/teste_higiene_placas_weso.py` | 25 |
| `tests/teste_perfis.py` | 22 |
| `tests/teste_continuacao_pagina.py` | 11 |
| `tests/teste_disjuntor_harmonit.py` | 2 |

🚨 **NÃO SÃO `assert`.** Os testes usam uma função `checar()` própria — um
`grep assert` no projeto devolve **zero** e engana quem for medir cobertura.

🚨 **NÃO HÁ PYTEST** instalado nem configurado. Cada arquivo roda como script
solto:

```bash
cd /home/claude/fpsl_weso
for t in tests/*.py; do echo "== $t"; venv/bin/python "$t" | tail -1; done
```

⚠️ **Os 3 testes soltos na raiz saíram em 14/08.** Dois eram exploratórios de
27/07 que **escreviam na WESO** e cujas perguntas já estão documentadas —
apagados. O `teste_perfis.py` foi para `tests/` porque a trava que ele exercita
está em uso real; ao mudar de pasta precisou do `sys.path` que os outros já
tinham.

---

## Lições que os testes deixaram
🚨 **`py_compile` NÃO substitui rodar os testes — isso aconteceu QUATRO
vezes em um dia (2026-07-29):** import faltando (`placas`), chamada na
função errada (`NameError: veiculos`), `timedelta` sem import, e
`_conectar` em vez de `_connect`. Os quatro compilaram.
Sempre conferir o **símbolo no namespace do módulo**, não só compilar.

🚨 **Resultado absurdo é sinal, não ruído.** A prévia de cliente dizia
que um CPF inventado já existia. Foi isso que revelou que o Harmonit
responde "não encontrado" em formato diferente de "encontrado".

**Nota original:** Em 2026-07-29, duas mudanças
compilaram e quebrariam em produção: um `placas.formatar()` sem o import (a
âncora do patch tinha os nomes em ordem invertida) e uma chamada inserida na
função errada (`NameError: veiculos`). Nos dois casos só o teste pegou.
