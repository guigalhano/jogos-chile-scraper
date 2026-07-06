# Adicionar Tercera A/B via En El Camarín

Este pacote adiciona os jogos da Tercera División a partir do calendário do En El Camarín.

## Fontes

- `https://enelcamarin.cl/joomsport_season/tercera-division-a-3ra-tercera-a-2026/?action=calendar`
- `https://enelcamarin.cl/joomsport_season/tercera-division-b-3ra-tercera-b-2026/?action=calendar`

## Por que é melhor

A página de calendário traz estrutura simples:

```text
Fecha 8 Tercera A 2026
29-05-2026 20:00
Municipal Puente Alto
1 - 1
Comunal Cabrero
Municipal de Puente Alto
```

Então é mais fácil capturar:
- data
- horário
- mandante
- visitante
- placar
- estádio
- fecha/rodada

## Instalação

Suba na raiz:

- `adicionar_enelcamarin_tercera.py`

Substitua o workflow:

- `.github/workflows/atualizar-jogos.yml`

pelo `atualizar-jogos.yml` deste pacote.

## Rodar

No GitHub:

`Actions > Atualizar jogos Chile + Tercera En El Camarin > Run workflow`

No log procure:

```text
[OK] Tercera A -> X jogos
[OK] Tercera B -> X jogos
```
