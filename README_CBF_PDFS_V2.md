# Atualizar PDFs da CBF - versão filtrada

A primeira versão achou muitos PDFs, mas misturou:

- documentos da competição;
- súmulas de jogos;
- páginas de jogos;
- resultados de buscadores.

Esta versão filtra por padrão apenas:

```text
Manual de Competições
PGA
REC / Regulamento
Tabela Detalhada
IMT
```

## Instalação

```bat
py -m pip install requests beautifulsoup4 playwright
py -m playwright install chromium
```

## Listar documentos aceitos

```bat
py atualizar_pdfs_cbf_pagina_v2.py --playwright --buscar-web --somente-listar
```

## Baixar documentos da competição

```bat
py atualizar_pdfs_cbf_pagina_v2.py --playwright --buscar-web
```

## Se aparecer erro SSL

```bat
py atualizar_pdfs_cbf_pagina_v2.py --playwright --buscar-web --insecure
```

## Forçar baixar de novo

```bat
py atualizar_pdfs_cbf_pagina_v2.py --playwright --buscar-web --forcar
```

## Incluir também súmulas

```bat
py atualizar_pdfs_cbf_pagina_v2.py --playwright --incluir-sumulas
```

## Saídas

```text
data/cbf_pdfs/serie-a-2026/
data/cbf_pdfs_manifest.json
data/cbf_pdfs_manifest.csv
data/debug_cbf_pdf_links.json
data/debug_cbf_page_resources.json
```
