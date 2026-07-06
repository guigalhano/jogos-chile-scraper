# Pacote melhorado - FPF e FMF

Este ZIP melhora o scraping das federações Paulista e Mineira.

## Inclui

```text
scrap_fpf_playwright_api.py
scrap_fmf_prox_jogos.py
requirements.txt
.github/workflows/atualizar-jogos.yml
README_FPF_FMF_MELHORIAS.md
```

## FPF

O scraper da Federação Paulista continua usando Playwright/JSON, mas agora adiciona:

```text
data/fpf_endpoints.json
```

para reutilizar endpoints encontrados em execuções futuras. Também filtra respostas fora do domínio `futebolpaulista.com.br`.

## FMF

Novo arquivo:

```text
scrap_fmf_prox_jogos.py
```

Estratégia:

```text
1. Lê a página ProxJogos.aspx?d=1 com requests/BeautifulSoup
2. Procura tabelas HTML
3. Procura linhas com data/hora/confronto
4. Se não funcionar, usa Playwright para capturar JSON/XHR
5. Salva endpoints em data/fmf_endpoints.json
```

## Arquivos de debug

```text
data/debug_fpf_api_urls.json
data/debug_fpf_matches_raw.json
data/debug_fmf_api_urls.json
data/debug_fmf_matches_raw.json
data/fpf_endpoints.json
data/fmf_endpoints.json
```

## Instalação

Suba todos os arquivos na raiz do repositório:

```text
guigalhano/jogos-chile-scraper
```

Depois rode:

```text
Actions > Atualizar jogos Chile Brasil completo > Run workflow
```
