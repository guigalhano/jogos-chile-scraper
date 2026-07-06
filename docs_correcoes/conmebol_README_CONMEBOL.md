# Adicionar jogos CONMEBOL

Este pacote adiciona jogos oficiais da CONMEBOL ao mesmo JSON usado pela página.

## Arquivos

- `adicionar_conmebol.py`
- `atualizar-jogos.yml`

## Fontes usadas

- `https://gol.conmebol.com/libertadores/es`
- `https://gol.conmebol.com/sudamericana/es`

Essas páginas trazem jogos com data, horário UTC-3, estádio e equipes.

## Como instalar no repositório

1. Suba `adicionar_conmebol.py` na raiz do repositório.

2. Substitua o workflow:

`.github/workflows/atualizar-jogos.yml`

pelo `atualizar-jogos.yml` deste pacote.

3. Rode manualmente:

`Actions > Atualizar jogos Chile + CONMEBOL > Run workflow`

## Como funciona

O workflow roda primeiro:

```bash
python atualizar_jogos_chile.py --once --dias 180 --dias-atras 14
```

Depois adiciona CONMEBOL:

```bash
python adicionar_conmebol.py --dias 180 --dias-atras 30
```

O script preserva os jogos já existentes e adiciona/atualiza os jogos CONMEBOL no mesmo:

- `data/jogos_programados.json`
- `data/jogos_programados.csv`
- `data/historico_jogos.csv`
