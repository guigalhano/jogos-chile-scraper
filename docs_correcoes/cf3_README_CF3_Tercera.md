# Atualização CF3 / Tercera División

Substitua no repositório:

- `atualizar_jogos_chile.py`

Opcionalmente substitua também:

- `.github/workflows/atualizar-jogos.yml`

## O que mudou

Adicionada fonte CF3:

- `https://cf3.cl/torneo/tercera-a/fecha/13`
- `https://cf3.cl/torneo/tercera-b/grupo-norte/fecha/13`
- `https://cf3.cl/torneo/tercera-b/grupo-sur/fecha/13`

O scraper usa essas páginas para descobrir automaticamente as demais Jornadas.

## Importante

As páginas CF3 muitas vezes mostram partidas finalizadas sem horário. Nesses casos:

- `hora` fica vazio
- `extra` recebe `placar=...; status=Finalizado`

## Workflow recomendado

```bash
python atualizar_jogos_chile.py --once --dias 180 --dias-atras 14
```

O `--dias-atras 14` é importante porque a Tercera pode ter partidas recentes já finalizadas, como a Jornada 13.
