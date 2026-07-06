# Atualização FPF via Playwright/API

## Melhor forma de buscar jogos da FPF

A página da Federação Paulista de Futebol não entrega os jogos completos diretamente no HTML inicial. Ela usa templates JavaScript/Angular como:

```text
{{item.NomePopularMandante}}
{{item.NomePopularVisitante}}
{{item.Estadio}}
{{ item.Horario}}
{{ item.Data }}
```

Por isso, a melhor estratégia é:

1. Abrir a página com navegador headless.
2. Capturar as respostas JSON/XHR que o site carrega.
3. Procurar objetos com campos de jogo.
4. Salvar no mesmo `data/jogos_programados.json`.

## Arquivo adicionado

```text
scrap_fpf_playwright_api.py
```

## Dependência adicionada

```text
playwright>=1.45.0
```

No workflow, também foi adicionado:

```text
python -m playwright install chromium
```

## Arquivos de debug

O script cria:

```text
data/debug_fpf_api_urls.json
data/debug_fpf_matches_raw.json
```

Esses arquivos ajudam a identificar exatamente qual endpoint/API da FPF está entregando os jogos.

## Logs esperados

No GitHub Actions, procure:

```text
[INFO] Abrindo FPF: https://www.futebolpaulista.com.br/Home/
[INFO] Abrindo FPF: https://www.futebolpaulista.com.br/Jogos/
[INFO] Abrindo FPF: https://www.futebolpaulista.com.br/Competicoes/Tabela.aspx
[OK] FPF JSON ... -> X jogos
FPF adicionados/atualizados: X
```

Se vier `0 jogos`, baixe ou abra:

```text
data/debug_fpf_api_urls.json
```

e envie o conteúdo/log para ajustar o endpoint específico.
