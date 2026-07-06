# Correção do scraper: estádios errados

## Erro identificado

Exemplo enviado:

- Página oficial:
  - Cobreloa x San Marcos de Arica
  - 31 de agosto, 20:00
  - Estádio: Zorros del Desierto

- Página gerada:
  - Cobreloa x San Marcos de Arica
  - Estádio: Elías Figueroa Brander

## Causa

O scraper não reconhecia `Zorros del Desierto` como estádio. Então ele pulava essa linha
e seguia procurando até o próximo jogo, onde encontrava `Elías Figueroa Brander`.

## Correções

1. Adicionado `Zorros del Desierto` e vários outros estádios/aliases à função `is_probably_stadium`.
2. A função `find_stadium_after` agora para quando encontra:
   - nova data
   - nova hora
   - nova `Fecha XX`

Assim o parser não atravessa para o jogo seguinte.

## Arquivos

Substituir no GitHub:

- `atualizar_jogos_chile.py`

Opcional:

- subir `corrigir_json_estadios_errados.py`
- substituir `.github/workflows/atualizar-jogos.yml` pelo `atualizar-jogos.yml`

## Depois

Rode:

`Actions > Atualizar jogos Chile > Run workflow`

O jogo Cobreloa x San Marcos deve passar a aparecer com:

`Zorros del Desierto`
