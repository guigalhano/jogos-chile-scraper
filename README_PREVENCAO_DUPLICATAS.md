# Como evitar jogos duplicados (leia antes de criar um scraper novo)

## O bug que já aconteceu

Em julho de 2026, o mesmo jogo (Caracas x Santa Fe, CONMEBOL Sudamericana)
apareceu duas vezes na página, com estádios diferentes. A causa se repetiu
em várias outras fontes (CBF, FES, FFERJ, FMF, ESPN):

**A identidade de um jogo (o ID usado pro merge) incluía campos que a
própria fonte corrige ou preenche depois da primeira coleta** — estádio,
cidade, rótulo de rodada ("Rodada 10" virando "Ida" no PDF da CBF, uma zona
sendo preenchida depois pela AFA, etc.). Quando esse campo mudava entre duas
coletas, o hash do ID mudava junto, e o merge achava que era um jogo novo
em vez de uma atualização do jogo já existente. Resultado: duas linhas para
o mesmo confronto.

O ponto que mais demorou pra ser encontrado: não bastava corrigir o `id` de
cada scraper individual. Quem faz o merge de verdade em produção é o
**`merge_apos_reset.py`**, chamado por quase todo workflow do GitHub Actions
depois do `git reset --hard origin/main` (pra evitar condição de corrida
entre workflows rodando ao mesmo tempo). Ele tinha sua própria lógica de ID,
separada da de cada scraper — corrigir só o scraper não tinha efeito
nenhum na base real.

## Regra ao criar/editar um scraper

1. **A identidade de um jogo nunca pode depender de campos que a fonte pode
   corrigir depois.** Isso inclui, no mínimo: `estadio`, `cidade`, `rodada`,
   placar. Só entram na identidade os campos que definem *o que é o jogo*:
   as duas equipes, a data, o horário e a competição.

2. **Se a fonte fornece algum código de partida estável, use-o.** Procure
   por algo como `fixture-id`, `match_id`, `event_id`, `game_id` no
   HTML/JSON da fonte antes de escrever o parser. Se achar, salve no campo
   `extra` como `codigo_<fonte>=<valor>` (padrão já usado no projeto:
   `codigo_espn`, `codigo_conmebol`, `codigo_fbf`, `codigo_fferj`) e use
   esse código pra gerar o ID. Ele é a fonte da verdade — não muda mesmo
   que todo o resto do registro seja reescrito depois.

   Cuidado: se o código só identifica um grupo maior (ex.: `codigo_fmf` é
   a fase/divisão inteira, não o confronto), ele sozinho não é suficiente
   — precisa combinar com outro campo que identifique o jogo dentro do
   grupo. E se esse campo adicional pode falhar/faltar na extração às
   vezes, é mais seguro **não** depender dele: prefira cair direto no
   fallback natural (item 3) a arriscar duas chaves diferentes pro mesmo
   jogo.

3. **Sem código estável disponível**, use como ID:
   `fonte + competicao + data + hora + mandante + visitante`
   (duas equipes não jogam duas vezes na mesma competição, no mesmo dia e
   horário — isso já é único o suficiente na prática).

4. **O merge tem que ser "atualiza se já existe", nunca "adiciona sempre".**
   Ao colidir dois registros com a mesma identidade, fique sempre com o
   mais recente por `atualizado_em` — nunca com o que aparecer por último
   na lista por acaso (ordem de iteração não é garantia de nada).

5. **Se você mexer no merge, lembre que `merge_apos_reset.py` é quem
   manda em produção.** Ele tem sua própria cópia de `row_id`/`merge_key`
   (não importa dos scrapers individuais, de propósito, pra rodar sozinho
   isolado num workflow). Qualquer mudança na lógica de identidade de jogo
   precisa ir pra lá também, ou não terá efeito nenhum na base real — só
   nos testes locais de cada scraper.

## Teste rápido antes de subir um scraper novo

Rode a coleta duas vezes seguidas simulando um campo secundário mudando
entre elas (por exemplo, um teste local passando `estadio=""` na primeira
rodada e `estadio="Nome real"` na segunda, mantendo times/data/hora/
competição iguais) e confirme que o merge final tem **1 linha**, não 2.

```python
from merge_apos_reset import merge_rows

rodada_1 = [{"fonte": "X", "competicao": "Y", "data": "2026-01-01",
             "hora": "20:00", "mandante": "A", "visitante": "B",
             "estadio": "", "extra": "", "atualizado_em": "2026-01-01T00:00:00"}]
rodada_2 = [{"fonte": "X", "competicao": "Y", "data": "2026-01-01",
             "hora": "20:00", "mandante": "A", "visitante": "B",
             "estadio": "Estádio Real", "extra": "", "atualizado_em": "2026-01-02T00:00:00"}]

resultado = merge_rows(rodada_1, rodada_2)
assert len(resultado) == 1, "duplicou! revise a chave de identidade"
```

## Fontes já corrigidas (referência)

| Fonte | Chave usada |
|---|---|
| CONMEBOL | `codigo_conmebol` |
| ESPN (Bolívia/Colômbia/Equador/Peru/Venezuela) | `codigo_espn` |
| Baianão (FBF) | `codigo_fbf` |
| FFERJ (Rio) | `codigo_fferj` |
| FMF (Minas), FMF-MT, CBF (PDF), FES | sem código estável — hash natural (fonte+competicao+data+hora+mandante+visitante) |
