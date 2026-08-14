# 24 — Desempenho, orçamento de tempo e o 504 que não parecia timeout

> Escrito em 2026-08-14, depois de a geração de manutenção falhar em produção
> para a Erika **sem nenhuma mensagem de erro**. A causa não era o fluxo: era
> tempo. Este documento existe para que ninguém precise redescobrir isso.

---

## O sintoma, e por que ele engana

A operadora clicava em gerar e a tela morria. Nas duas tentativas registradas
(18:43 e 18:44) o **backend chegou ao fim** — as chamadas estão no log. O que
faltou foi o navegador dela continuar esperando.

Na segunda vez, numa placa diferente, apareceu **"erro json"**. Não havia nada
de errado com JSON: o nginx devolveu a própria **página HTML de 504** e a tela
chamou `res.json()` naquilo, produzindo `Unexpected token '<'`.

🚨 **Mensagem de erro de parse quase nunca é sobre parse.** É sobre alguém ter
devolvido uma coisa no lugar de outra — aqui, o proxy respondendo no lugar da
aplicação.

---

## A causa raiz: uma medição que envelheceu e inverteu

O módulo de equipamentos foi escrito em **29/07** sobre estes números, que
estavam certos naquele dia:

| Consulta na WESO | Medido 29/07 | Medido 14/08 |
|---|---|---|
| Base inteira (`/Veiculos/Consultar` sem filtro) | **2,3s** | **16,65s**, chegando a **33s** |
| Uma placa filtrada (`?placa=`) | **~6s** | **0,67s** |

A relação **virou ao contrário**. Como o código tinha sido construído sobre "a
base inteira é barata, o filtro é caro", a geração de manutenção varria a base
completa **três vezes**: a placa real, o recipiente, e o recipiente **de novo**
dentro de `buscar_seriais` (porque recipiente criado no mesmo dia não está no
cache das 04:15).

Resultado: **43 segundos**. O `proxy_read_timeout` do nginx era **35s**.

🚨 **MEDIÇÃO NÃO TEM TESTE, ENTÃO NINGUÉM REMEDE.** Um número de desempenho
anotado em comentário ou doc é uma afirmação sobre o mundo que continua sendo
lida como verdade depois de deixar de ser. Este apodreceu em **16 dias** e
derrubou produção. Todo número de tempo neste projeto agora carrega a data em
que foi medido — se estiver sem data, trate como suspeito.

---

## O que foi feito

| Correção | Efeito |
|---|---|
| Consulta placa a placa quando são poucas (`LIMIAR_PLACA_A_PLACA = 6`) | 0,67s por placa em vez de 16s pela base |
| Uma leitura só para a placa real e o recipiente | corta uma varredura inteira |
| Recipiente sai do `buscar_seriais` na manutenção | corta a terceira |
| **Orçamento total de 18s** (`TETO_LEITURA_AO_VIVO`), com teto de 6s por chamada | o limite segura mesmo com a WESO lenta |

🚨 **O ORÇAMENTO É DO CONJUNTO, NÃO DE CADA CHAMADA.** Teto só por chamada não
resolve nada: quando a WESO está carregada, até a consulta de UMA placa passa de
5s, e 10 tentativas de 4s somam 40s sem nenhuma delas ter estourado o teto
individual. O relógio tem de correr para o conjunto.

**Se o orçamento estourar, falha para o lado seguro:** o recipiente é dado como
não encontrado, a OS sai com `ENTRARÁ: NUMERO DE SERIE`, sem material e com
aviso na tela. **Nunca sai equipamento errado** — só falta, e com recado.

⚠️ **Grafias conhecidas antes de desistir.** `?placa=` compara por igualdade
exata e devolve **vazio, não erro**: existe registro real gravado com espaço na
frente (` OOM3895-UPGRADE`). O que não aparecer na consulta individual é
procurado na base inteira, que casa por chave normalizada.

⚠️ **Deduplicar por id ao juntar as leituras.** O caminho novo podia trazer o
mesmo veículo duas vezes, e o código trata chave repetida como **ambiguidade** —
descartaria o recipiente dizendo que há dois. Falsa ambiguidade tira o
equipamento da OS, o que é pior que lentidão.

---

## Tempos depois da correção (medidos 14/08, 3 rodadas)

```
recipiente existe .........  1,2s a  9,0s   (era ~40s)
manutenção no local .......  1,1s a  4,9s
recipiente NÃO existe ..... 17,3s a 24,8s   (era 43s)
```

O caso lento continua sendo **"o setor ainda não criou o recipiente"**: ali é
preciso varrer a base para ter certeza de que não existe. Fica em ~22s.

⚠️ A WESO **oscila muito**: a mesma consulta já variou de 7s a 33s no mesmo
minuto. Qualquer teto colado no tempo típico volta a quebrar.

---

## O nginx: 180s, e por que o login continua em 35s

`proxy_read_timeout` e `proxy_send_timeout` do `location /` foram de **35s para
180s**, **nos dois blocos server** (443 e 8005), com autorização do usuário.
Backup em `fpsl.conf.bak_2026-08-14`, `nginx -t` **antes** do reload.

| Rota | Timeout | Por quê |
|---|---|---|
| `location /` | **180s** | depende da WESO, que oscila |
| `/weso/onboarding` | 120s | cadeia de cadastro, já era longa |
| `/painel/api/login` | **35s** | de propósito: login não fala com a WESO, e limite curto ali é proteção |

⚠️ **Timeout maior não conserta lentidão, só evita que ela vire erro mudo.** As
correções acima é que trouxeram o caminho normal para 2 a 9s; os 180s são
folga para quando a WESO piorar.

---

## O que o usuário vê enquanto espera

A caixa de progresso **redesenha a cada segundo**. A partir de 3s aparece o
contador e o recado: *"a WESO às vezes demora; não feche nem clique de novo"*.

🚨 **Segundo que anda é a diferença entre "está trabalhando" e "morreu".** Foi
por não haver isso que se clicou de novo — e clicar de novo numa geração de OS
é a pior coisa que pode acontecer nesta tela.

E a resposta HTTP passou a ser lida como **texto**, e só então convertida:

| Situação | O que aparece |
|---|---|
| 504 / 502 | "o servidor passou do tempo… **Nenhuma OS foi criada**" |
| 401 | "sua sessão expirou" |
| 403 | "sem permissão para esta aba" |
| 409 de vínculo | a mensagem do backend, como antes |

⚠️ `gerarOs()` não conferia `res.ok`: num erro, o `res.json()` estourava e o
operador ficava sem saber **se alguma OS foi criada** — a pergunta mais cara
desta tela. Agora confere.

---

## Como medir de novo (e quando)

```bash
cd /home/claude/fpsl_weso
venv/bin/python - <<'EOF'
import asyncio, time
from fpsl_weso.painel import equipamentos as e
async def main():
    t=time.monotonic(); await e._veiculos_ao_vivo(["JKO 1484"], {"JKO1484"}); print("1 placa", round(time.monotonic()-t,2))
asyncio.run(main())
EOF
```

**Remedir quando:** a geração passar de ~10s no caso normal · a WESO mudar de
versão · alguém for mexer em `LIMIAR_PLACA_A_PLACA` ou `TETO_LEITURA_AO_VIVO`.

Ver também: `12_Nginx.md` (config real) · `23_Manutencao.md` (perfis sem termo)
· `18_Testes.md` (o exercício da tela em node).
