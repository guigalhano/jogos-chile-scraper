# Atualização Brasil usando PDFs de Tabela Detalhada da CBF

Este pacote atualiza o scraper do Brasil para usar os PDFs oficiais de tabela detalhada da CBF.

Fonte principal:

```text
https://www.cbf.com.br/futebol-brasileiro/tabelas/
```

## Como funciona

O arquivo:

```text
adicionar_brasil_jogos.py
```

agora faz:

1. Abre a página de tabelas da CBF.
2. Descobre links internos de competições.
3. Procura PDFs com `tabela`, `detalhada`, `brasileiro`, `copa`, `série`, `feminino`.
4. Baixa PDFs em:

```text
data/cbf_pdfs/
```

5. Extrai tabelas e texto com `pdfplumber`.
6. Atualiza:

```text
data/jogos_programados.json
data/jogos_programados.csv
data/historico_jogos.csv
```

## Dependências adicionadas

```text
pdfplumber>=0.11.0
pypdfium2>=4.30.0
```

## Workflow

O workflow contém a etapa:

```text
Adicionar Brasil CBF PDFs FERJ FMF FPF
```

## Logs esperados

No GitHub Actions, procure:

```text
[INFO] Páginas CBF descobertas: X
[OK] PDFs encontrados em ...: X
[INFO] PDFs CBF únicos: X
[OK] PDF baixado: ...
[OK] CBF PDF ... -> X jogos
Brasil CBF/PDF adicionados/atualizados: X
```

## Observação

A estrutura dos PDFs da CBF pode variar por competição. O script tenta primeiro extrair tabelas; se não conseguir, usa fallback por texto. Se algum PDF der 0 jogos, envie o log e ajustamos o parser para esse layout.
