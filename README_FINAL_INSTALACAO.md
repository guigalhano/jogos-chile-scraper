# Pacote final - Jogos Chile Scraper

Este ZIP reúne as últimas correções e melhorias do projeto `jogos-chile-scraper`.

## O que está incluído

### Página GitHub Pages
- `index.html`
- `style.css`
- `script.js`
- `estadios.js`

Inclui:
- mapa com Leaflet
- filtros por competição, time, cidade, região e data
- botão Hoje
- botão Próximos 3 dias
- botão Próximos 7 dias
- botão Jogos sem coordenadas
- botão Mostrar todos do time
- versão Português/Espanhol
- coordenadas de estádios melhoradas

### Scrapers e adicionadores
- `atualizar_jogos_chile.py`
- `adicionar_enelcamarin_tercera.py`
- `adicionar_conmebol.py`
- `corrigir_json_estadios_errados.py`
- `scrap_estadios_campeonato_chileno.py`

Inclui:
- correção de estádios errados, como Cobreloa x San Marcos de Arica no Zorros del Desierto
- CF3 / Tercera División
- En El Camarín para Tercera A/B
- CONMEBOL Libertadores/Sudamericana
- estádios e coordenadas melhoradas

### Workflow GitHub Actions
- `.github/workflows/atualizar-jogos.yml`

Roda:
1. scraper principal Chile
2. adicionador En El Camarín
3. adicionador CONMEBOL
4. correção de estádios conhecidos
5. commit automático dos arquivos em `data/`

## Como instalar no GitHub

Suba todos os arquivos deste ZIP na raiz do repositório:

`guigalhano/jogos-chile-scraper`

No GitHub:

1. Abra o repositório.
2. Clique em `Add file > Upload files`.
3. Arraste todos os arquivos e pastas deste ZIP.
4. Clique em `Commit changes`.

Atenção: a pasta `.github/workflows/` precisa ser mantida com esse caminho exato.

## Depois de subir

Vá em:

`Actions > Atualizar jogos Chile completo > Run workflow`

No log, procure mensagens como:

```text
[OK] Tercera A -> X jogos
[OK] Tercera B -> X jogos
En El Camarín adicionados/atualizados: X
```

## Arquivos gerados pelo workflow

- `data/jogos_programados.json`
- `data/jogos_programados.csv`
- `data/historico_jogos.csv`

## Observação

Se algum site estiver temporariamente fora do ar, o workflow continua tentando as outras fontes.


## Atualização Brasil incluída

Este pacote também inclui:

```text
adicionar_brasil_jogos.py
```

Fontes brasileiras tentadas:

```text
CBF
FERJ
FMF
FPF
```

No workflow, a etapa é:

```text
Adicionar Brasil CBF FERJ FMF FPF
```

Observação: nesta primeira versão a fonte mais estável é a FERJ. CBF e FPF podem depender de JavaScript/API e podem retornar 0 jogos até mapearmos a API interna.


## Atualização Brasil via PDF CBF

Incluído parser de PDFs de "Tabela Detalhada" da CBF:

```text
adicionar_brasil_jogos.py
```

A fonte principal é:

```text
https://www.cbf.com.br/futebol-brasileiro/tabelas/
```

Os PDFs baixados ficam em:

```text
data/cbf_pdfs/
```

A etapa no workflow é:

```text
Adicionar Brasil CBF PDFs FERJ FMF FPF
```


## Atualização FPF via API/Playwright

Incluído:

```text
scrap_fpf_playwright_api.py
```

Esse script abre as páginas da Federação Paulista com navegador headless, captura respostas JSON/XHR e extrai jogos com campos como:

```text
NomePopularMandante
NomePopularVisitante
Data
Horario
Estadio
Municipio
Rodada
```

Também gera arquivos de debug:

```text
data/debug_fpf_api_urls.json
data/debug_fpf_matches_raw.json
```


## Melhorias FPF e FMF

Incluído scraper dedicado para FMF e cache de endpoints para FPF.
