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

## O nginx: 90s, e por que o login continua em 35s

🚨 **ESTE TRECHO ESTEVE ERRADO DE 14/08 A 21/08, E ELE FOI A FONTE DO ENGANO.**
Ele afirmava que o `location /` tinha ido para **180s**. **Nunca foi.** O
arquivo em `/etc/nginx/sites-enabled/fpsl.conf` era de 12/08 — anterior à
decisão — e estava em **35s nos dois blocos**. A decisão ficou sete dias no
papel, e quem foi conferir conferiu este texto e a cópia de 32 linhas do
repositório, não o arquivo no ar.

⚠️ **A LIÇÃO É MAIOR QUE O NÚMERO: decisão registrada não é decisão aplicada.**
Ao mexer no nginx, ler `/etc`, aplicar lá, e ressincronizar `nginx_fpsl.conf`
na mesma passada — ele agora tem cabeçalho dizendo que é espelho, não fonte.

**Aplicado de verdade em 21/08**, com autorização: `proxy_read_timeout` e
`proxy_send_timeout` do `location /` a **90s**, **nos dois blocos server** (443
e 8005). Conferido com `nginx -T`, que mostra o que o nginx CARREGOU e não o
que está no disco.
Backup em `fpsl.conf.bak_2026-08-14`, `nginx -t` **antes** do reload.

| Rota | Timeout | Por quê |
|---|---|---|
| `location /` | **90s** | depende da WESO, que oscila. Acomoda o cliente de 60s com folga |
| `/weso/onboarding` | 120s | cadeia de cadastro, já era longa |
| `/painel/api/login` | **35s** | de propósito: login não fala com a WESO, e limite curto ali é proteção |

⚠️ **Timeout maior não conserta lentidão, só evita que ela vire erro mudo.** As
correções acima é que trouxeram o caminho normal para 2 a 9s; os 90s são
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

---

# A OS 16775 — quando o tempo da WESO vira OS errada, em silêncio (2026-08-19)

Tudo acima trata de tempo que **derruba a tela**. Este trecho trata do caso
pior: tempo que **não derruba nada** e entrega uma OS errada com cara de OS
certa.

## O que aconteceu

Em 17/08 às 15:39 a **OS 16775** foi gerada sem o rastreador e sem o chip. O
operador só percebeu conferindo no Harmonit, e corrigiu na mão. A tela não
mostrou erro nenhum, o serviço ficou `active`, e o log de acesso registrou
`200 OK`.

A causa estava no journal do serviço, no minuto exato:

```
Aug 17 15:39:29 srv786604 uvicorn[3683780]:
    equipamentos: base de veiculos indisponivel: 502: WESO indisponível (timeout)
```

`_rastreador_id_por_placa` chamava `/Veiculos/Consultar`, tomava exceção,
escrevia um `log.warning` e devolvia `{}`. Para o resto do fluxo, `{}` é
indistinguível de **"a WESO respondeu, e nenhuma dessas placas tem
rastreador"**. Sem rastreador não há modelo; sem modelo, `_material_do_equipamento`
devolve `None` e a OS sai sem o equipamento e sem o chip.

🚨 **A HIPÓTESE REGISTRADA ERA OUTRA, E ERA FALSA.** O `Proximos_Passos.md`
dizia que a causa era um modelo faltando no de-para (`produto_do_modelo`). Foi
conferido em 19/08: o de-para tem 24 modelos, a WESO tem 29 distintos, e os 5
de fora (`ST500`, `NT2x`, `ST4945S`, `NT11`, `Concox GT06`) somam 84 veículos —
nenhum na 16775. **O de-para estava íntegro.** A hipótese era plausível e
custou a apuração; o que a resolveu foi o journal, não o raciocínio.

## A correção: a falha vira aviso na tela

`equipamentos.py` ganhou `_anotar(falhas, texto)` e uma **lista opcional**
`falhas` nas funções que engoliam a exceção — `_rastreador_id_por_placa`,
`buscar_seriais`, `_base_inteira`, `_veiculos_ao_vivo` e `dados_das_placas`. O
`os_router` passa a lista nas duas chamadas da geração e despeja o resultado em
`avisos`, que a tela já renderiza escapado no passo do resumo, **antes** do
botão Gerar.

| Decisão | Por quê |
|---|---|
| **Não bloqueia** | continua valendo "lacuna é melhor que apagar". A OS sai; o que muda é que a pessoa vê |
| **Lista opcional, não retorno em tupla** | tupla quebraria `buscar_recipientes` e o `teste_upgrade_8820` |
| **Lista opcional, não variável de módulo** | variável de módulo mistura requisições concorrentes |
| **WESO respondendo ⇒ nenhum aviso** | aviso falso treina a equipe a ignorar aviso. É verificação explícita no teste |

Teste: `tests/teste_aviso_weso.py`, 20 verificações. Os itens 6 e 7 leem os
**consumidores** — o fonte do `os_router` e o `gerar_os.html` — porque um aviso
que a tela não mostra é o defeito de 18/08 outra vez.

## O teto do cliente WESO: 60s desde 21/08

🚨 **ERA 30s ATÉ 21/08, E ESTE TRECHO DIZIA QUE ESTAVA BOM.** Estava errado no
mérito: o teto foi calibrado quando a base levava 2,3s, e a documentação da
própria WESO registra **30 a 90s** como resposta normal no `UltimaPosicao`.
Medido em 18/08: base inteira de 6,0s a 30,7s, mediana 23,8s. **Foi ele que
gerou a OS 16775 sem equipamento.** O usuário autorizou **60s** em 21/08.

🚨 **A ORDEM DOS DOIS TETOS É O DESENHO, não coincidência: 60s no cliente < 90s
no nginx.** O nosso dispara PRIMEIRO, então o operador recebe erro nosso em
JSON, com explicação. Invertido, quem corta é o nginx, com uma **página HTML de
504** que a tela lê como JSON — que foi exatamente o "erro json" de 14/08.

E a espera passou a ter relógio na aba Operações: nada até 3s, contador de 3s a
15s, **barra de progresso a partir de 15s** (pedido do usuário, 21/08), com o
recado de não clicar de novo — repetir uma escrita depois de timeout duplica.

### O texto abaixo é de antes, e a conclusão dele estava errada

O teto do cliente WESO (`client.py`) não era uma preocupação
teórica: **ele já produziu uma OS errada em produção**. A documentação da WESO
descreve 30 a 90s como tempo normal de resposta. O teto continuava em 30s —
mexer nele é decisão do usuário, e nada foi alterado.

## 🚨 O timeout da WESO pode MENTIR na direção contrária

Medido em 19/08 apagando placas de teste: `/Veiculos/Excluir` estourou os 30s e
levantou `502: WESO indisponível (timeout)`. A releitura imediata da base
mostrou o veículo **ainda existindo**. Na execução seguinte, minutos depois, o
veículo **tinha sumido** e a base caiu de 1972 para 1971.

Ou seja: **o pedido foi processado depois de o cliente desistir**, e a
releitura imediata também mentiu, porque ainda era cedo demais.

Consequências práticas:

- em operação **idempotente** (excluir), repetir depois do timeout é seguro — a
  segunda tentativa apenas informa "já não existe";
- em operação **que cria**, repetir depois do timeout **duplica**. O registro
  de 17/08 no `cadastro_placas_log` mostra exatamente isso: uma linha
  `weso | falhou | nao consegui conferir na WESO: WESO indisponível (timeout)`
  para o `9BD281AJPTYBM7701`, e o veículo criado assim mesmo (`88368`);
- **"reler o estado" continua sendo a regra, mas uma releitura só não basta**
  quando o timeout foi do lado da escrita. Reler de novo, mais tarde.

