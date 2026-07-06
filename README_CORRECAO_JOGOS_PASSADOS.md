# Correção: ocultar/remover jogos passados

## Por que apareciam jogos no passado?

1. O workflow usava `--dias-atras` para capturar jogos recentes/finalizados.
2. O `data/jogos_programados.json` acumulava jogos antigos.
3. A página mostrava todos os jogos do JSON por padrão.

## O que foi corrigido

### Página

O `script.js` agora mostra por padrão somente jogos com data de hoje em diante.

Jogos passados só aparecem quando:
- você escolhe uma data específica;
- usa "Mostrar todos do time";
- ou usa filtros específicos.

### JSON atual

Foi adicionado:

```text
limpar_jogos_passados_programados.py
```

Esse script remove jogos passados de:

```text
data/jogos_programados.json
data/jogos_programados.csv
```

Mas mantém o histórico completo em:

```text
data/historico_jogos.csv
```

### Workflow

O workflow agora roda a limpeza antes do commit final.

## Arquivos principais para substituir

- `script.js`
- `limpar_jogos_passados_programados.py`
- `.github/workflows/atualizar-jogos.yml`

Ou suba o ZIP completo na raiz do repositório.
