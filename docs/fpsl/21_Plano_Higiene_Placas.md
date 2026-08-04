# 21 — Higiene de placas na WESO

> Aberto e EXECUTADO em 2026-07-29. Motivo: ao buscar o equipamento da placa
> `TTX 0H91` do termo 8788, a consulta voltou **zero**. A placa existia — estava
> gravada como `' TTX 0H91'`, com espaço à esquerda.
> `/Veiculos/Consultar?placa=` compara por **igualdade exata**, então o registro
> ficava invisível para qualquer rotina que consultasse por placa. Falha
> silenciosa: não dá erro, devolve vazio.

## Estado: etapas 1, 2, 3 e 4 concluídas

---

## Escopo medido (antes)

```
base WESO ......................... 1.962 veículos
espaço à ESQUERDA .................    48
espaço à DIREITA ..................    41
espaço DUPLO no meio ..............     1
com letra minúscula ...............    22
                                   ------
registros afetados ................   110  (5,6%)
```

## Etapa 1 — parar de produzir novos casos ✅

`fpsl_weso/routers/veiculos.py` passou a aplicar `placas.formatar()` antes de
enviar à WESO. Antes ia o texto cru.

⚠️ Ao aplicar, o import de `placas` **não entrou** — a âncora do patch tinha os
nomes em ordem invertida (`weso_get, weso_post` × `weso_post, weso_get`).
`py_compile` passa nisso; quebraria com `NameError` no primeiro cadastro real.
Só apareceu porque o namespace do módulo foi conferido em vez de confiar na
compilação. **Lição: py_compile não substitui verificar o símbolo.**

Confirmado que `placas.formatar` preserva não-convencional intacta
(`DZCACCDBBAHB` sai igual) e não trata `RDM` como marcador de redundância.

## Etapa 2 — leitura tolerante ✅

Novo `fpsl_weso/weso_lookup.py`, dois níveis:
1. consulta direta com a placa **formatada** (rápido, resolve a maioria);
2. se vier vazio, baixa a base completa (~2,3s) e casa por
   `placas.normalizar()`.

`routers/os.py` já usa. Testado com 7 grafias — limpa, espaço nas pontas,
minúscula, sem espaço, com hífen, não-convencional, inexistente. Todas
resolvem em 0,2–0,3s; a inexistente devolve `None` sem explodir.

**É esta etapa que torna o sistema imune, não a etapa 3.** A WESO recebe
cadastro por fora do FPSL — normalizar a base é faxina, não vacina.

## Etapa 3 — limpeza dos registros ✅

`normalizar_espacos_placas.py` (irmão do `corrigir_placas_espaco.py` de 27/07,
que tratava outro caso: placa convencional SEM espaço).

```
108 de 110 normalizados · 0 falhas
espaço à esquerda   48 → 0
espaço à direita    41 → 0
espaço duplo         1 → 0
com minúscula       22 → 2
```

Cada registro foi gravado, **relido para confirmar**, e o `rastreador_id`
comparado antes/depois — nenhum mudou. Cada linha do log traz o comando de
reversão individual.

**2 deixados de propósito:** `'Móvel 1'` duplicado (ids 6752 e 48022). Aparar
espaço de duas placas que colidem transformaria duplicata escondida em conflito
ativo. Sai junto da **decisão 3** do usuário.

## Etapa 4 — impedir a reincidência ✅

`tests/teste_higiene_placas_weso.py` — teste de integração, somente leitura.
Varre a base e falha se aparecer espaço nas pontas, espaço duplo, minúscula ou
**colisão nova**. Também verifica que a leitura tolerante da etapa 2 continua
funcionando.

**Na primeira execução ele já pegou dois casos**, o que justifica a própria
existência:

1. **`'TEO 2H51 '`, id 87765, cadastrada em 2026-07-29T16:49 UTC** — ou seja,
   *durante* a sessão que estava limpando a base. Prova ao vivo de que o
   problema reincide sozinho. Normalizada na hora.
2. **`OBD 3` × `OBD 3*`** — não é colisão na base: os dois são diferentes lá.
   Quem os funde é a **nossa** `placas.normalizar()`, que descarta o `*`. Como
   `weso_lookup` usa essa mesma chave, a ambiguidade é real do nosso lado —
   buscar `OBD 3` pode devolver qualquer um. Catalogado, não silenciado.

## Colisões conhecidas (catalogadas no teste)

| Normalizada | ids | Natureza |
|---|---|---|
| `GFI3G42` | 55976, 74120 | duplicata real — **decisão 3** |
| `SVS6J23` | 58186, 73330 | duplicata real — **decisão 3** |
| `EBU1968` | 34177, 34178 | duplicata real — **decisão 3** |
| `MVEL1` | 6752, 48022 | `Móvel 1` ×2, não-convencional reusado |
| `OBD2` | 58462, 80704 | não-convencional reusado |
| `OBD3` | 58464, 80703 | ambiguidade criada pela nossa normalização |
| `TERMO8396` | 79214, 79216, 79834, 79924 | placeholder de placa a definir |

⚠️ **`TERMO:8396` aparece 4×, e há também `'TERMO 8222 '`.** É convenção de
fato já em produção para placa indefinida. Insumo direto para a **decisão 1**
(formato do `A DEFINIR` + nº do termo). O usuário sinalizou em 29/07 que o ideal
seria `Adefinir8396_1` com apelido "termo 8396" — deixado para outra conversa.

## Como reproduzir a medição

```bash
venv/bin/python tests/teste_higiene_placas_weso.py      # trava, roda sempre
venv/bin/python normalizar_espacos_placas.py            # dry-run da limpeza
```

## O que ficou de fora

- As 2 placas em colisão, aguardando a decisão 3.
- Rodar o teste da etapa 4 **automaticamente**. Hoje é manual. Ele bate na WESO
  (~2,3s) e é só leitura, então cabe num agendamento diário — mas isso não foi
  montado.
