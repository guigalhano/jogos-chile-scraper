#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adiciona jogos do Brasil ao mesmo JSON do projeto jogos-chile-scraper.

COMO FUNCIONA (v2):
CBF (Série A/B/C/D) bloqueia scraping direto: robots.txt proíbe crawling das
páginas de tabelas, e o WAF do site retorna 403 para requests simples (mesmo
com navegador headless, testado). Só que os PDFs de "Tabela Detalhada" em si
(hospedados em stcbfsiteprdimgbrs.blob.core.windows.net, um CDN Azure) NÃO
têm essa proteção quando acessados diretamente.

Então, em vez de abrir a página de tabelas da CBF (bloqueada), este script:
1. Faz buscas de texto (DuckDuckGo HTML, com fallback Bing HTML) por PDFs de
   "Tabela Detalhada" da Série A/B/C/D mais recentes -- já que o Google/Bing
   indexam esses PDFs diretamente.
2. Baixa o PDF encontrado direto do CDN (sem passar pelo cbf.com.br).
3. Extrai o texto com pdfplumber e faz o parsing linha a linha no formato
   conhecido: "REF ROD DATA-DIA HORA MANDANTE UF x VISITANTE UF ESTADIO CIDADE UF [transmissao]"

Mantém, como complemento best-effort, o scraping simples de FERJ/FMF/FPF
(páginas HTML mais simples, sem robots.txt restritivo conhecido) -- mas isso
pode continuar retornando 0 jogos se esses sites também bloquearem; isso é
tratado com try/except e não interrompe o restante do script.

Saídas atualizadas:
- data/jogos_programados.json
- data/jogos_programados.csv
- data/historico_jogos.csv

Uso:
    python adicionar_brasil_jogos.py --dias 180 --dias-atras 30
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, asdict
from datetime import datetime, date, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, parse_qs, urlparse, unquote

import requests
from bs4 import BeautifulSoup

try:
    import pdfplumber
except Exception:
    pdfplumber = None


OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,es;q=0.8,en;q=0.7",
}

# Fontes complementares simples (best-effort; podem falhar sem quebrar o script)
EXTRA_HTML_SOURCES = [
    ("FERJ", "https://www.fferj.com.br/partidas"),
    ("FMF", "https://www.fmf.com.br/"),
    # FPF Paulista removida daqui: agora é coberta exclusivamente pelo scraper
    # dedicado scrap_fpf_paulista_api.py (API .ashx oficial). Manter esta fonte
    # genérica reintroduziria duplicatas ("Brasil - FPF" sem competição resolvida).
]

# Buscas para localizar os PDFs de Tabela Detalhada mais recentes de cada série.
CBF_SEARCH_QUERIES = [
    ("Brasil - Série A", 'site:stcbfsiteprdimgbrs.blob.core.windows.net filetype:pdf "Tabela_Detalhada" "Serie_A_2026"'),
    ("Brasil - Série B", 'site:stcbfsiteprdimgbrs.blob.core.windows.net filetype:pdf "Tabela_Detalhada" "Serie_B_2026"'),
    ("Brasil - Série C", 'site:stcbfsiteprdimgbrs.blob.core.windows.net filetype:pdf "Tabela_Detalhada" "Serie_C_2026"'),
    ("Brasil - Série D", 'site:stcbfsiteprdimgbrs.blob.core.windows.net filetype:pdf "Tabela_Detalhada" "Serie_D_2026"'),
    ("Brasil - Copa do Brasil", 'site:stcbfsiteprdimgbrs.blob.core.windows.net filetype:pdf "Tabela_Detalhada" "Copa_do_Brasil_2026"'),
    ("Brasil - Copa do Brasil Feminina", 'site:stcbfsiteprdimgbrs.blob.core.windows.net filetype:pdf "Copa_do_Brasil_Feminina_2026"'),
    ("Brasil - Série A Sub-20", 'site:stcbfsiteprdimgbrs.blob.core.windows.net filetype:pdf "Serie_A_Sub_20_2026"'),
    ("Brasil - Série B Sub-20", 'site:stcbfsiteprdimgbrs.blob.core.windows.net filetype:pdf "Serie_B_Sub_20_2026"'),
    ("Brasil - Sub-17", 'site:stcbfsiteprdimgbrs.blob.core.windows.net filetype:pdf "Sub_17_2026"'),
    ("Brasil - Feminino Sub-20", 'site:stcbfsiteprdimgbrs.blob.core.windows.net filetype:pdf "Feminino" "Sub_20_2026"'),
    ("Brasil - Feminino Sub-17", 'site:stcbfsiteprdimgbrs.blob.core.windows.net filetype:pdf "Feminino" "Sub_17_2026"'),
    ("Brasil - Feminino A1", 'site:stcbfsiteprdimgbrs.blob.core.windows.net filetype:pdf "Feminino_A1_2026"'),
]

# Fallback manual: como buscadores (DuckDuckGo/Bing) podem bloquear scripts
# automatizados com uma página de desafio anti-bot (confirmado em teste real
# no GitHub Actions), mantemos aqui uma lista "semente" dos PDFs mais recentes
# conhecidos. Atualize esta lista manualmente de tempos em tempos (mesma
# lógica de manutenção do estadios.js) até que a busca automática funcione
# de forma confiável, ou até que uma API de busca paga seja configurada.
SEED_PDF_URLS = [
    ("Brasil - Série A", "https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/Tabela_Detalhada_Brasileiro_Serie_A_2026_19_a_24_rodada_82505dee72.pdf"),
    ("Brasil - Série B", ""),  # antes: espelho não-oficial ne45.com.br (jul/2026),
    # removido porque ficou obsoleto e produzia linhas duplicadas malformadas
    # do mesmo jogo (nome de time cortado errado) assim que a busca
    # automática já encontra a URL oficial da CBF em stcbfsiteprdimgbrs.blob.
    # A busca automática (CBF_SEARCH_QUERIES) é a fonte primária; isto é
    # só o fallback usado quando ela falhar.
    ("Brasil - Série C", "https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/Tabela_Detalhada_1_Fase_16_a_19_Rodada_Brasileiro_Serie_C_2026_ff29c2b37c.pdf"),
    ("Brasil - Série D", "https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/Tabela_Detalhada_Brasileiro_Serie_D_2026_06_07_fb69bfb072.pdf"),
    ("Brasil - Copa do Brasil", "https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/Tabela_Detalhada_Copa_do_Brasil_2026_24_06_7dfa8d4cf5.pdf"),
    ("Brasil - Copa do Brasil Feminina", "https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/Tabela_Detalhada_Copa_do_Brasil_Feminina_2026_0d8d5d0448.pdf"),
    ("Brasil - Série B Sub-20", "https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/TABELA_DETALHADA_BRASILEIRO_MASCULINO_SERIE_B_SUB_20_10_04_v2_1683d773ce.pdf"),
    ("Brasil - Feminino A1", "https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/Tabela_Detalhada_Brasileiro_Feminino_A1_2026_04a2a21b30.pdf"),
    # Seed URLs para categorias adicionadas (fallback enquanto a descoberta v2 é estabelecida)
    # TODO: Atualizar esses URLs conforme os PDFs forem encontrados pela descoberta automática
    ("Brasil - Série A Sub-20", ""),
    ("Brasil - Sub-17", ""),
    ("Brasil - Feminino Sub-20", ""),
    ("Brasil - Feminino Sub-17", ""),
]

UF_CODES = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}

# Cidades-sede mais comuns do circuito Série A/B/C -- usado para separar
# "estadio cidade UF" quando o nome do estádio também tem várias palavras.
CIDADES_BR = sorted([
    "Rio de Janeiro", "Belo Horizonte", "Porto Alegre", "Presidente Prudente",
    "Novo Hamburgo", "Bragança Paulista", "São Paulo", "Caxias do Sul",
    "Criciúma", "São Bernardo do Campo",
    "Juiz de Fora", "Volta Redonda", "Ribeirão Preto", "Santa Maria",
    "Chapecó", "Curitiba", "Salvador", "Fortaleza", "Recife", "Brasília",
    "Belém", "Goiânia", "Cuiabá", "Vitória", "Florianópolis", "Mirassol",
    "Santos", "Sorocaba", "Natal", "Maceió", "Manaus", "Campinas",
    "Pelotas", "Niterói", "Londrina", "Maringá", "Uberlândia",
    "João Pessoa", "Teresina", "Aracaju", "Macapá", "Palmas", "Boa Vista",
    "Porto Velho", "Rio Branco", "Saquarema", "Cariacica", "Anápolis",
    "Betim", "Erechim", "Rio do Sul", "Itajaí", "Marabá", "Castanhal",
    "São Lourenço da Mata", "Ponta Grossa", "São João Del Rei", "Tombos",
    "Ivinhema", "Ji-Paraná", "Imperatriz", "Ceilândia", "Arapiraca",
    "Juazeiro", "Novo Horizonte", "Rio Claro", "Gama", "Alagoinhas",
    "Lucas do Rio Verde", "Arapongas", "Ijuí", "Iguatu", "Goiatuba",
    "Campina Grande", "Uberlândia",
], key=lambda c: -len(c.split()))

CBF_ROW_RE = re.compile(
    r"^(?P<ref>\d{2,4})\s+"
    r"(?:(?P<iv>[IV])\s+)?"
    r"(?:(?P<rod>\d{1,2})ª?\s+)?"
    r"(?:(?P<dia>\d{2}/\d{2})|A\s?def(?:inir)?\.?)\s*"
    r"(?:(?P<diasem>seg|ter|qua|qui|sex|s[aá]b|dom)\s+)?"
    r"(?:(?P<hora>\d{2}:\d{2})\s+)?"
    r"(?P<resto>.+)$",
    re.IGNORECASE,
)
CBF_VS_RE = re.compile(r"\s+[xX]\s+")
EDICAO_RE = re.compile(r"EDI[ÇC][ÃA]O\s+(\d{4})", re.IGNORECASE)

DATE_RE = re.compile(r"\b(?P<dia>\d{1,2})[/-](?P<mes>\d{1,2})[/-](?P<ano>\d{2,4})\b")
TIME_RE = re.compile(r"\b(?P<hora>\d{1,2}:\d{2})h?\b")
GENERIC_TEXT_MONTH_RE = re.compile(
    r"\b(?P<dia>\d{1,2})\s+"
    r"(?P<mes_txt>jan|janeiro|fev|fevereiro|mar|março|marco|abr|abril|mai|maio|jun|junho|jul|julho|ago|agosto|set|setembro|out|outubro|nov|novembro|dez|dezembro)\.?\s+"
    r"(?P<ano>\d{2,4})\s+"
    r"(?P<hora>\d{1,2}:\d{2})h?\s+"
    r"(?P<resto>.+?)$",
    re.IGNORECASE,
)
MESES = {
    "jan": 1, "janeiro": 1, "fev": 2, "fevereiro": 2, "mar": 3, "março": 3, "marco": 3,
    "abr": 4, "abril": 4, "mai": 5, "maio": 5, "jun": 6, "junho": 6, "jul": 7, "julho": 7,
    "ago": 8, "agosto": 8, "set": 9, "setembro": 9, "out": 10, "outubro": 10,
    "nov": 11, "novembro": 11, "dez": 12, "dezembro": 12,
}
DIAS_SEMANA = "SEG|TER|QUA|QUI|SEX|SAB|SÁB|DOM"
GENERIC_NUMERIC_RE = re.compile(
    r"\b(?P<dia>\d{1,2})[/-](?P<mes>\d{1,2})[/-](?P<ano>\d{2,4})\s+"
    r"(?P<hora>\d{1,2}:\d{2})h?\s+"
    r"(?P<resto>.+?)$",
    re.IGNORECASE,
)
VS_RE = re.compile(r"\s+(?:X|x|vs\.?|v/s)\s+")
PLACAR_RE = re.compile(r"\b\d+\s*[-xX]\s*\d+\b")


@dataclass
class Partido:
    fonte: str
    competicao: str
    data: str
    hora: str
    mandante: str
    visitante: str
    estadio: str = ""
    cidade: str = ""
    rodada: str = ""
    url: str = ""
    extra: str = ""

    @property
    def id(self) -> str:
        raw = "|".join([
            self.fonte, self.competicao, self.data, self.hora,
            self.mandante, self.visitante,
        ])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def to_row(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        d["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
        return d


def clean_text(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    value = re.sub(r"^Image:\s*", "", value, flags=re.I).strip()
    return value


def norm(value: str) -> str:
    value = unicodedata.normalize("NFD", str(value or ""))
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def parse_year(y: str) -> int:
    n = int(y)
    return 2000 + n if n < 100 else n


def dedupe(rows: list[Partido]) -> list[Partido]:
    seen = set()
    out = []
    for p in rows:
        if p.id in seen:
            continue
        seen.add(p.id)
        out.append(p)
    return out


def load_json_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def load_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def row_id(row: dict) -> str:
    # Não inclui estadio/cidade/rodada: a CBF costuma corrigir/preencher
    # esses campos numa versão posterior do PDF (ex.: "Rodada 10" virando
    # "Ida"), e se entrassem no hash o mesmo jogo ganharia um ID novo
    # (virando linha duplicada) a cada correção.
    raw = "|".join([
        row.get("fonte", ""), row.get("competicao", ""), row.get("data", ""),
        row.get("hora", ""), row.get("mandante", ""), row.get("visitante", ""),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def merge_rows(existing: list[dict], new_rows: list[dict]) -> list[dict]:
    by_id = {}
    for r in existing:
        rid = row_id(r)
        r["id"] = rid
        by_id[rid] = r
    for r in new_rows:
        rid = row_id(r)
        r["id"] = rid
        by_id[rid] = r
    return sorted(by_id.values(), key=lambda r: (r.get("data", ""), r.get("hora", ""), r.get("competicao", ""), r.get("mandante", "")))


# Palavras que não ajudam a identificar o clube (siglas de personalidade
# jurídica) e por isso são ignoradas na comparação "é o mesmo time?" abaixo.
_SUFIXOS_CLUBE_IGNORADOS = {
    "fc", "ec", "ac", "sc", "ca", "afc", "saf", "esporte", "clube", "futebol",
}


def _tokens_time(nome: str) -> set[str]:
    return {t for t in norm(nome).split() if t not in _SUFIXOS_CLUBE_IGNORADOS}


def colapsar_duplicados_mesmo_confronto(rows: list[dict]) -> list[dict]:
    """Rede de segurança para quando duas fontes (ou uma fonte semente
    obsoleta) descrevem o MESMO jogo com formatação de nome diferente
    (ex.: "São Bernardo (FC)" vs "São Bernardo FC (SP)"), o que faz o hash
    de row_id() divergir e as duas linhas sobreviverem ao merge normal.

    Agrupa por (competicao, data, hora, rodada) -- times diferentes jogando
    no mesmo horário da mesma rodada continuam distintos porque exigimos
    também sobreposição de palavras nos nomes de mandante E de visitante --
    e mantém só a linha mais recente (atualizado_em) de cada grupo."""
    grupos: dict[tuple, list[dict]] = {}
    for r in rows:
        chave = (r.get("competicao", ""), r.get("data", ""), r.get("hora", ""), r.get("rodada", ""))
        grupos.setdefault(chave, []).append(r)

    resultado: list[dict] = []
    for linhas in grupos.values():
        if len(linhas) == 1:
            resultado.append(linhas[0])
            continue
        usados = [False] * len(linhas)
        for i in range(len(linhas)):
            if usados[i]:
                continue
            grupo_dup = [linhas[i]]
            usados[i] = True
            tm_i = _tokens_time(linhas[i].get("mandante", ""))
            tv_i = _tokens_time(linhas[i].get("visitante", ""))
            for j in range(i + 1, len(linhas)):
                if usados[j]:
                    continue
                tm_j = _tokens_time(linhas[j].get("mandante", ""))
                tv_j = _tokens_time(linhas[j].get("visitante", ""))
                if (tm_i & tm_j) and (tv_i & tv_j):
                    grupo_dup.append(linhas[j])
                    usados[j] = True
            melhor = max(grupo_dup, key=lambda r: r.get("atualizado_em", ""))
            resultado.append(melhor)
    return resultado


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "id", "fonte", "competicao", "data", "hora",
        "mandante", "visitante", "estadio", "rodada",
        "url", "extra", "atualizado_em", "pais", "cidade",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


# --------------------------------------------------------------------------
# Busca por PDFs de Tabela Detalhada (DuckDuckGo HTML, com fallback Bing)
# --------------------------------------------------------------------------

def _extract_ddg_redirect(href: str) -> str:
    """DuckDuckGo's HTML endpoint wraps result links as //duckduckgo.com/l/?uddg=<encoded>."""
    if "uddg=" in href:
        try:
            qs = parse_qs(urlparse(href).query)
            if "uddg" in qs:
                return unquote(qs["uddg"][0])
        except Exception:
            pass
    return href


PDF_URL_RE = re.compile(
    r"""(?P<url>https?://[^"' <>()]+?\.pdf(?:\?[^"' <>()]*)?)""",
    re.I,
)


def _extract_links_generic(html: str, base_url: str) -> list[str]:
    """Extração resiliente: em vez de depender de uma classe CSS específica
    do resultado de busca (que quebra sempre que o buscador muda o HTML),
    varre TODOS os links <a href> da página e complementa com uma busca por
    regex de qualquer URL .pdf cru no texto (funciona mesmo se o link estiver
    dentro de um <script> ou atributo que o parser de tags não pegou)."""
    urls: list[str] = []
    soup = BeautifulSoup(html or "", "html.parser")
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if not href:
            continue
        target = _extract_ddg_redirect(href)
        target = urljoin(base_url, target)
        urls.append(target)

    for m in PDF_URL_RE.finditer(html or ""):
        urls.append(m.group("url"))

    return urls


def search_web(query: str, max_results: int = 15) -> list[str]:
    """Retorna uma lista de URLs de resultados de busca. Tenta DuckDuckGo HTML
    primeiro, cai para Bing HTML se a primeira falhar ou não retornar nada.

    Usa extração genérica (todos os <a href> + regex de URLs .pdf cru no
    HTML) em vez de depender de uma classe CSS específica do resultado de
    busca — essa era a causa real de vir vazio: os seletores anteriores
    (a.result__a, li.b_algo h2 a) não batiam mais com o HTML atual dos
    buscadores, então a chamada "funcionava" (HTTP 200, conteúdo real) mas a
    extração silenciosamente não achava nada."""
    urls: list[str] = []

    try:
        r = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=HEADERS,
            timeout=20,
        )
        r.raise_for_status()
        urls.extend(_extract_links_generic(r.text, "https://duckduckgo.com/"))
    except Exception as e:
        print(f"[WARN] Busca DuckDuckGo falhou para '{query}': {e}", file=sys.stderr)

    try:
        r = requests.get(
            "https://www.bing.com/search",
            params={"q": query},
            headers=HEADERS,
            timeout=20,
        )
        r.raise_for_status()
        urls.extend(_extract_links_generic(r.text, "https://www.bing.com/"))
    except Exception as e:
        print(f"[WARN] Busca Bing falhou para '{query}': {e}", file=sys.stderr)

    # remove duplicatas mantendo ordem
    seen = set()
    unique = []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            unique.append(u)

    return unique[:max_results]


# Palavras-chave para casar cada competição com URLs descobertas pelo
# atualizar_pdfs_cbf_pagina_v2.py (rodado como um passo separado, best-effort,
# antes deste script no workflow diário).
_PALAVRAS_COMPETICAO = {
    "Brasil - Série A": ["serie a", "bsa 2026"],
    "Brasil - Série B": ["serie_b", "serie b"],
    "Brasil - Série C": ["serie_c", "serie c"],
    "Brasil - Série D": ["serie_d", "serie d"],
    "Brasil - Copa do Brasil": ["copa_do_brasil", "copa do brasil"],
    "Brasil - Copa do Brasil Feminina": ["copa_do_brasil_feminina", "feminina"],
    "Brasil - Série A Sub-20": ["serie_a_sub_20", "serie a sub-20", "sub_20"],
    "Brasil - Série B Sub-20": ["serie_b_sub_20", "serie b sub-20"],
    "Brasil - Sub-17": ["sub_17", "sub-17"],
    "Brasil - Feminino Sub-20": ["feminino_sub_20", "feminino sub-20"],
    "Brasil - Feminino Sub-17": ["feminino_sub_17", "feminino sub-17"],
    "Brasil - Feminino A1": ["feminino_a1", "feminino a1"],
}


def find_urls_from_v2_discovery() -> dict[str, str]:
    """Lê data/debug_cbf_pdf_links.json (gerado pelo passo separado do
    atualizar_pdfs_cbf_pagina_v2.py no workflow diário, se ele rodou e achou
    algo). Retorna {competicao_label: pdf_url} para as 'tabela_detalhada'
    encontradas hoje. Se o arquivo não existir ou estiver vazio, retorna {}."""
    path = OUT_DIR / "debug_cbf_pdf_links.json"
    if not path.exists():
        return {}
    try:
        candidatos = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    achados: dict[str, str] = {}
    for c in candidatos:
        if c.get("tipo") != "tabela_detalhada":
            continue
        url = c.get("url", "")
        if not url.lower().endswith(".pdf"):
            continue
        url_norm = norm(url)
        for competicao, palavras in _PALAVRAS_COMPETICAO.items():
            if competicao in achados:
                continue
            if any(norm(p) in url_norm for p in palavras):
                achados[competicao] = url
    return achados


def find_cbf_pdf_urls() -> list[tuple[str, str]]:
    """Retorna lista de (competicao_label, pdf_url) para as tabelas detalhadas
    mais recentes encontradas via busca de texto (não via crawling do site da CBF)."""
    found: list[tuple[str, str]] = []
    search_debug: list[dict] = []
    v2_achados = find_urls_from_v2_discovery()
    for competicao, query in CBF_SEARCH_QUERIES:
        if competicao in v2_achados:
            found.append((competicao, v2_achados[competicao]))
            print(f"[OK] PDF encontrado via descoberta diária (v2/Playwright) para {competicao}: {v2_achados[competicao]}")
            continue
        try:
            results = search_web(query)
        except Exception as e:
            print(f"[WARN] Busca falhou para {competicao}: {e}", file=sys.stderr)
            search_debug.append({"competicao": competicao, "query": query, "erro": str(e)})
            continue

        pdf_candidates = [
            u for u in results
            if u.lower().endswith(".pdf") and "tabela" in u.lower() and "detalhada" in u.lower()
        ]
        if not pdf_candidates:
            # aceita qualquer pdf do CDN conhecido da CBF, mesmo sem "detalhada" no nome do arquivo
            pdf_candidates = [
                u for u in results
                if u.lower().endswith(".pdf") and "blob.core.windows.net" in u.lower()
            ]

        search_debug.append({
            "competicao": competicao,
            "query": query,
            "resultados_brutos": len(results),
            "primeiros_resultados": results[:5],
            "pdf_candidatos": len(pdf_candidates),
        })

        if pdf_candidates:
            found.append((competicao, pdf_candidates[0]))
            print(f"[OK] PDF encontrado via busca para {competicao}: {pdf_candidates[0]}")
        else:
            seed = next((url for comp, url in SEED_PDF_URLS if comp == competicao), None)
            if seed:
                found.append((competicao, seed))
                print(f"[INFO] Busca não retornou resultado para {competicao}; usando URL semente conhecida: {seed}")
            else:
                print(f"[WARN] Nenhum PDF encontrado (busca ou semente) para {competicao}", file=sys.stderr)

    (OUT_DIR / "debug_cbf_search.json").write_text(
        json.dumps(search_debug, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return found


def fetch_bytes(url: str) -> bytes:
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.content


# --------------------------------------------------------------------------
# Parsing do PDF "Tabela Detalhada" da CBF
# --------------------------------------------------------------------------

def strip_trailing_tv_codes(tokens: list[str]) -> list[str]:
    while tokens and tokens[-1].isdigit():
        tokens.pop()
    return tokens


def split_team_uf(tokens: list[str]) -> tuple[str, str]:
    if len(tokens) >= 2 and tokens[-1] in UF_CODES:
        return " ".join(tokens[:-1]), tokens[-1]
    return " ".join(tokens), ""


def split_estadio_cidade_uf(tail_text: str) -> tuple[str, str, str]:
    tokens = tail_text.split()
    tokens = strip_trailing_tv_codes(tokens)
    if not tokens:
        return "", "", ""
    uf = ""
    if tokens[-1] in UF_CODES:
        uf = tokens.pop()
    remainder = " ".join(tokens)

    for cidade in CIDADES_BR:
        if remainder == cidade or remainder.endswith(" " + cidade):
            estadio = remainder[: -len(cidade)].strip()
            return estadio, cidade, uf

    if len(tokens) >= 2:
        cidade = " ".join(tokens[-2:])
        estadio = " ".join(tokens[:-2])
        return estadio, cidade, uf
    return remainder, "", uf


CBF_SCORE_TAIL_RE = re.compile(r"\s*(?:\(\d+\)\s*)?\d+$")
CBF_SCORE_HEAD_RE = re.compile(r"^\d+\s*(?:\(\d+\)\s*)?")


def parse_cbf_line(line: str, year: int, last_rod: list[str]) -> dict | None:
    m = CBF_ROW_RE.match(line.strip())
    if not m:
        return None

    resto = m.group("resto")
    resto = re.sub(r"^[A-Z]?\d+\s+", "", resto)
    parts = CBF_VS_RE.split(resto, maxsplit=1)
    if len(parts) != 2:
        return None

    left, right = parts
    left = CBF_SCORE_TAIL_RE.sub("", left)
    right = CBF_SCORE_HEAD_RE.sub("", right)
    mandante, mandante_uf = split_team_uf(left.split())
    if not mandante:
        return None

    right_tokens = right.split()
    visitante_tokens = []
    uf_idx = None
    for i, tok in enumerate(right_tokens):
        visitante_tokens.append(tok)
        if tok in UF_CODES:
            uf_idx = i
            break
    if uf_idx is None:
        return None
    visitante = " ".join(visitante_tokens[:-1])
    visitante_uf = visitante_tokens[-1]
    if not visitante:
        return None

    tail = " ".join(right_tokens[uf_idx + 1:])
    # Remove marcador de rodapé (ex.: "Carlos Zamith*" = estádio sujeito a
    # confirmação na tabela da CBF) para não gerar duas linhas do mesmo jogo
    # (uma com "*" e outra sem, cada uma com um id de hash diferente).
    tail = tail.rstrip("*").strip()
    if norm(tail).startswith("a definir") or not tail.strip():
        estadio, cidade = "A definir", ""
    else:
        estadio, cidade, _uf2 = split_estadio_cidade_uf(tail)

    rod = m.group("rod")
    if rod:
        last_rod[0] = rod
    rodada = f"Rodada {last_rod[0]}" if last_rod[0] else ""
    iv = m.group("iv")
    if iv:
        rodada = "Ida" if iv.upper() == "I" else "Volta"

    dia_mes = m.group("dia")
    data_iso = ""
    if dia_mes:
        try:
            dd, mm = dia_mes.split("/")
            data_iso = date(year, int(mm), int(dd)).isoformat()
        except Exception:
            data_iso = ""

    return {
        "data": data_iso,
        "hora": m.group("hora") or "",
        "mandante": f"{mandante} ({mandante_uf})" if mandante_uf else mandante,
        "visitante": f"{visitante} ({visitante_uf})" if visitante_uf else visitante,
        "estadio": estadio,
        "cidade": cidade,
        "rodada": rodada,
    }


def parse_cbf_pdf(pdf_bytes: bytes, competicao: str, pdf_url: str) -> list[Partido]:
    if pdfplumber is None:
        print("[ERRO] pdfplumber não instalado. Adicione pdfplumber ao requirements.txt", file=sys.stderr)
        return []

    out: list[Partido] = []
    last_rod = [""]

    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            full_text_parts = []
            for page in pdf.pages:
                try:
                    text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                except Exception:
                    text = ""
                full_text_parts.append(text)

            full_text = "\n".join(full_text_parts)
            year_match = EDICAO_RE.search(full_text)
            year = int(year_match.group(1)) if year_match else date.today().year

            for line in full_text.splitlines():
                row = parse_cbf_line(line, year, last_rod)
                if not row:
                    continue
                out.append(Partido(
                    fonte="CBF",
                    competicao=competicao,
                    data=row["data"],
                    hora=row["hora"],
                    mandante=row["mandante"],
                    visitante=row["visitante"],
                    estadio=row["estadio"],
                    cidade=row["cidade"],
                    rodada=row["rodada"],
                    url=pdf_url,
                    # cidade continua também em extra por compatibilidade com
                    # front-ends antigos que ainda leem extractCidadeFromExtra,
                    # mas agora o campo estruturado "cidade" é a fonte confiável.
                    extra=f"pais=Brasil; cidade={row['cidade']}" if row["cidade"] else "pais=Brasil",
                ))
    except Exception as e:
        print(f"[WARN] Erro lendo PDF {pdf_url}: {e}", file=sys.stderr)

    return dedupe(out)


# --------------------------------------------------------------------------
# "Tabela Básica" da CBF (todas as rodadas da temporada, divulgada em
# dezembro/janeiro) -- usada só como PREENCHIMENTO PROVISÓRIO para rodadas
# que a "Tabela Detalhada" (parse_cbf_pdf acima) ainda não cobre.
#
# Diferença de formato: a Tabela Básica não tem hora nem estádio -- só um
# intervalo de até 3 datas possíveis por rodada (ex.: "29/08 (sáb), 30/08
# (dom) ou 31/08 (seg)"), porque o dia exato de cada jogo só é definido perto
# da rodada (direitos de TV). Confirmado com o PDF real (26/07/2026): essa
# tabela NUNCA é atualizada com a data confirmada -- até a rodada 1 (já
# jogada em janeiro) continua mostrando o range original de datas. Por isso,
# jogos daqui são sempre marcados extra="status=Provisorio" e nunca devem
# sobrepor um jogo já confirmado pela Tabela Detalhada (ver filtro em main()
# e a limpeza automática que remove a linha provisória assim que a Tabela
# Detalhada trouxer a versão confirmada da mesma rodada).
#
# Layout real extraído (pdfplumber, x_tolerance=1/y_tolerance=3), um
# fragmento de data por linha, intercalado com as linhas de jogo -- às vezes
# a 2ª/3ª data vem em linha própria, às vezes embutida na frente da linha do
# próprio jogo, e às vezes é só o dia da semana entre parênteses sem data
# (continuação) ou uma única data sem "ou" alternativo (rodadas de meio de
# semana, ex. a última rodada da temporada):
#   29/08 (sáb),
#   241 25ª Flamengo RJ x Botafogo RJ
#   30/08 (dom)
#   242 25 ou 31/08 Vasco da Gama RJ x Cruzeiro MG
#   (seg)
#   243 25 São Paulo SP x Red Bull Bragantino SP
# Quando a rodada atravessa uma quebra de página, o PDF repete o fragmento
# de data na continuação (mesma rodada) -- por isso os fragmentos são
# deduplicados antes de montar o texto final.
SEED_TABELA_BASICA_URLS = [
    ("Brasil - Série A", "https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/Tabela_BA_sica_Brasileiro_SA_rie_A_2026_d64996b4d8.pdf"),
]

_MES_DIA_RE = r"\d{1,2}/\d{1,2}"
_DOW_RE = r"[A-Za-zÀ-Úà-ú]{3}"
TABELA_BASICA_FRAG_DATA_RE = re.compile(rf"^(?:ou\s+)?{_MES_DIA_RE}(?:\s*\({_DOW_RE}\))?\,?$", re.IGNORECASE)
TABELA_BASICA_FRAG_DIA_RE = re.compile(rf"^\(?{_DOW_RE}\)?$", re.IGNORECASE)
TABELA_BASICA_ROW_RE = re.compile(
    rf"^(?P<ref>\d{{2,4}})\s+(?P<rod>\d{{1,3}})(?P<marca>ª)?\s+"
    # Fragmento de data embutido na própria linha do jogo, em 3 variações
    # confirmadas no PDF real: "ou 31/08" / "ou 31/08 (seg)" (rodada 25),
    # "(dom)" sozinho -- dia da semana sem data, continuando um fragmento
    # anterior (rodada 37) -- ou "02/12 (qua)" sem "ou" -- rodada que só tem
    # 1 dia possível, sem alternativa (rodada 38, última do ano).
    rf"(?:(?P<frag_embutido>(?:ou\s+)?{_MES_DIA_RE}(?:\s*\({_DOW_RE}\))?|\({_DOW_RE}\))\s+)?"
    rf"(?P<resto>.+)$"
)
TABELA_BASICA_DATA_EXTRAI_RE = re.compile(r"(\d{1,2})/(\d{1,2})")


def parse_tabela_basica_pdf(pdf_bytes: bytes, competicao: str, pdf_url: str) -> list[Partido]:
    if pdfplumber is None:
        return []

    out: list[Partido] = []
    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            full_text_parts = []
            for page in pdf.pages:
                try:
                    text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                except Exception:
                    text = ""
                full_text_parts.append(text)
            full_text = "\n".join(full_text_parts)

        year_match = EDICAO_RE.search(full_text)
        year = int(year_match.group(1)) if year_match else date.today().year

        # Passo 1: percorre tudo e agrupa os fragmentos de data por rodada,
        # e coleta as linhas de jogo (rodada + texto restante "Time UF x Time UF").
        frags_por_rodada: dict[str, list[str]] = {}
        frags_pendentes: list[str] = []
        rodada_atual: str | None = None
        linhas_jogo: list[tuple[str, str]] = []

        for raw_line in full_text.splitlines():
            line = clean_text(raw_line)
            if not line:
                continue
            if TABELA_BASICA_FRAG_DATA_RE.match(line) or TABELA_BASICA_FRAG_DIA_RE.match(line):
                # Um fragmento de data solto sempre pertence à rodada da
                # PRÓXIMA linha de jogo que aparecer (seja ela continuação da
                # rodada atual, ex. "30/08 (dom)" entre as linhas 241 e 242,
                # ou já a primeira linha da rodada seguinte, ex. "05/09
                # (sáb)," depois da última linha da rodada 25 e antes da
                # primeira da 26) -- nunca da rodada que já está terminando.
                # Por isso só entra no dicionário quando a PRÓXIMA linha de
                # jogo for lida (flush abaixo), nunca direto aqui.
                frags_pendentes.append(line)
                continue
            m = TABELA_BASICA_ROW_RE.match(line)
            if not m:
                continue  # cabeçalho/rodapé (EMISSAO, DATA ATUALIZAÇÃO, etc.)
            rod = m.group("rod")
            if rod != rodada_atual:
                rodada_atual = rod
                frags_por_rodada.setdefault(rod, [])
            frags_por_rodada[rod].extend(frags_pendentes)
            frags_pendentes = []
            if m.group("frag_embutido"):
                frags_por_rodada[rod].append(m.group("frag_embutido"))
            linhas_jogo.append((rod, m.group("resto")))

        # Passo 2: monta os jogos usando o conjunto COMPLETO de fragmentos de
        # cada rodada (só fecha depois de ler o texto inteiro, porque um
        # fragmento pode aparecer embutido numa linha de jogo posterior da
        # mesma rodada, como "ou 31/08" na linha 242 acima).
        for rod, resto in linhas_jogo:
            parts = CBF_VS_RE.split(resto, maxsplit=1)
            if len(parts) != 2:
                continue
            mandante, mandante_uf = split_team_uf(parts[0].split())
            visitante, visitante_uf = split_team_uf(parts[1].split())
            if not (mandante and visitante):
                continue

            # Quando uma rodada atravessa uma quebra de página, o PDF repete
            # o fragmento de data na continuação (mesma rodada, nova página)
            # -- dedup preservando a ordem pra não duplicar no texto final.
            frags = list(dict.fromkeys(frags_por_rodada.get(rod, [])))
            datas_dd_mm = TABELA_BASICA_DATA_EXTRAI_RE.findall(" ".join(frags))
            datas_iso = []
            for dd, mm in datas_dd_mm:
                try:
                    datas_iso.append(date(year, int(mm), int(dd)).isoformat())
                except Exception:
                    continue
            if not datas_iso:
                continue
            data_provisoria = min(datas_iso)
            texto_range = clean_text(" ".join(frags))

            extra = [
                "status=Provisorio",
                f"data_provisoria={texto_range}" if texto_range else "",
                "fonte_dados=tabela_basica",
                "pais=Brasil",
            ]
            extra = "; ".join(e for e in extra if e)

            out.append(Partido(
                fonte="CBF",
                competicao=competicao,
                data=data_provisoria,
                hora="",
                mandante=f"{mandante} ({mandante_uf})" if mandante_uf else mandante,
                visitante=f"{visitante} ({visitante_uf})" if visitante_uf else visitante,
                estadio="",
                cidade="",
                rodada=f"Rodada {rod}",
                url=pdf_url,
                extra=extra,
            ))
    except Exception as e:
        print(f"[WARN] Erro lendo Tabela Básica {pdf_url}: {e}", file=sys.stderr)

    return dedupe(out)


def chave_confronto(mandante: str, visitante: str, competicao: str) -> tuple[str, str, str]:
    """Identidade de um confronto sem depender de data/hora (que na Tabela
    Básica é só uma estimativa) -- usada tanto pra evitar adicionar um jogo
    provisório quando já existe um confirmado, quanto pra limpar o
    provisório depois que o confirmado chegar."""
    return (norm(mandante), norm(visitante), competicao)


# --------------------------------------------------------------------------
# Fallback simples para federações estaduais (best-effort)
# --------------------------------------------------------------------------

FERJ_RE = re.compile(
    rf"\b(?:{DIAS_SEMANA})\s+"
    r"(?P<dia>\d{2})/(?P<mes>\d{2})/(?P<ano>\d{2,4})\s+"
    r"(?P<hora>\d{1,2}:\d{2})h?\s+"
    r"(?P<resto>.+?)$",
    re.IGNORECASE,
)


def get_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    lines = []
    for raw in soup.get_text("\n").splitlines():
        line = clean_text(raw)
        if not line or line in {"*", "* * *", "Home", "Contato"}:
            continue
        lines.append(line)
    return lines


def infer_competicao_estadual(resto: str, fonte: str) -> str:
    low = resto.lower()
    if "carioca" in low or "ferj" in low:
        return "Brasil - FERJ"
    if "mineiro" in low or "fmf" in low:
        return "Brasil - FMF"
    if "paulista" in low or "fpf" in low:
        return "Brasil - FPF"
    return f"Brasil - {fonte}"


def split_visitante_comp(txt: str) -> tuple[str, str]:
    words = txt.split()
    if len(words) <= 3:
        return clean_text(txt), ""
    return " ".join(words[:3]), " ".join(words[3:])


def parse_estadual_line(line: str, fonte: str) -> Partido | None:
    m = FERJ_RE.search(line) or GENERIC_NUMERIC_RE.search(line) or GENERIC_TEXT_MONTH_RE.search(line)
    if not m:
        return None
    gd = m.groupdict()
    try:
        if "mes_txt" in gd and gd.get("mes_txt"):
            dt = date(parse_year(gd["ano"]), MESES[norm(gd["mes_txt"])], int(gd["dia"]))
        else:
            dt = date(parse_year(gd["ano"]), int(gd["mes"]), int(gd["dia"]))
    except Exception:
        return None

    hora = gd.get("hora", "")
    resto = gd.get("resto", "")
    placar = ""
    if PLACAR_RE.search(resto):
        placar = PLACAR_RE.search(resto).group(0)
        resto = PLACAR_RE.sub(" X ", resto, count=1)

    parts = VS_RE.split(resto, maxsplit=1)
    if len(parts) != 2:
        return None
    mandante = clean_text(parts[0])
    visitante, comp_txt = split_visitante_comp(parts[1])
    if not mandante or not visitante or len(mandante) > 80 or len(visitante) > 80:
        return None

    extra_parts = ["pais=Brasil"]
    if placar:
        extra_parts.append(f"placar={placar}")

    return Partido(
        fonte=fonte,
        competicao=infer_competicao_estadual(comp_txt or resto, fonte),
        data=dt.isoformat(),
        hora=hora,
        mandante=mandante,
        visitante=visitante,
        estadio="",
        rodada="",
        url="",
        extra="; ".join(extra_parts),
    )


def parse_extra_html_sources(desde: date, ate: date, incluir_passados: bool) -> list[Partido]:
    out = []
    for fonte, url in EXTRA_HTML_SOURCES:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            count = 0
            for line in get_lines(r.text):
                p = parse_estadual_line(line, fonte)
                if not p:
                    continue
                try:
                    dt = date.fromisoformat(p.data)
                except Exception:
                    continue
                if incluir_passados or (desde <= dt <= ate):
                    out.append(p)
                    count += 1
            print(f"[OK] {fonte} HTML -> {count} jogos")
        except Exception as e:
            print(f"[WARN] Fonte HTML {fonte} falhou (esperado se o site bloquear bots): {e}", file=sys.stderr)
    return dedupe(out)


def in_window(p: Partido, desde: date, ate: date, incluir_passados: bool) -> bool:
    if not p.data:
        return True  # jogos "a definir" ficam, o front-end já trata isso
    try:
        dt = date.fromisoformat(p.data)
    except Exception:
        return False
    return incluir_passados or (desde <= dt <= ate)


# Quantos dias de cobertura futura consideramos aceitaveis antes de soar o
# alarme. O gatilho do bug original (Serie B travada nas rodadas 12-18 por
# semanas, sem ninguem perceber) foi a cobertura se esgotar silenciosamente:
# so um log [INFO] discreto avisava que a busca automatica tinha falhado e
# caido pro fallback "semente", e ninguem olha esse log todo dia.
DIAS_AVISO_COBERTURA = 10  # cobertura menor que isso -> "atencao", ja e hora de atualizar
DIAS_CRITICO_COBERTURA = 2  # cobertura menor que isso (ou zero jogos futuros) -> "critico"


def checar_cobertura(competicao: str, pdf_url: str, matches_raw: list[Partido], today: date) -> dict:
    """Calcula ate quando essa competicao tem jogos agendados (futuros) na
    tabela que acabamos de baixar/parsear, e classifica isso.

    Retorna um dict pronto pra virar linha do relatorio de cobertura, e
    tambem imprime um aviso no formato de annotation do GitHub Actions
    (`::warning::`) quando o status nao e "ok" -- isso faz o aviso aparecer
    destacado no resumo do workflow run, em vez de se perder no meio de
    milhares de linhas de log.
    """
    datas_futuras = []
    for m in matches_raw:
        if not m.data:
            continue
        try:
            dt = date.fromisoformat(m.data)
        except Exception:
            continue
        if dt >= today:
            datas_futuras.append(dt)

    if not datas_futuras:
        status = "atencao"
        cobertura_ate = None
        dias_restantes = 0
        msg = (
            f"'{competicao}' nao tem NENHUM jogo futuro nesta tabela "
            f"(pdf: {pdf_url}). Competicao pode ter acabado/estar em pausa."
        )
    else:
        cobertura_ate = max(datas_futuras)
        dias_restantes = (cobertura_ate - today).days
        if dias_restantes < DIAS_CRITICO_COBERTURA:
            status = "critico"
            msg = (
                f"'{competicao}' so tem jogos futuros ate {cobertura_ate.isoformat()} "
                f"({dias_restantes} dia(s)) -- cobertura prestes a se esgotar. "
                f"Atualize o link/seed para o proximo lote de rodadas."
            )
        elif dias_restantes < DIAS_AVISO_COBERTURA:
            status = "atencao"
            msg = (
                f"'{competicao}' cobre jogos futuros so ate {cobertura_ate.isoformat()} "
                f"({dias_restantes} dias) -- vale planejar a atualizacao do link/seed em breve."
            )
        else:
            status = "ok"
            msg = f"'{competicao}' cobre jogos futuros ate {cobertura_ate.isoformat()} ({dias_restantes} dias)."

    if status != "ok":
        # Formato de annotation do GitHub Actions: aparece destacado no
        # resumo do workflow run (aba "Summary"), nao so no log bruto.
        nivel_gh = "error" if status == "critico" else "warning"
        print(f"::{nivel_gh}::[COBERTURA CBF] {msg}")
    else:
        print(f"[COBERTURA CBF] OK - {msg}")

    return {
        "competicao": competicao,
        "pdf_url": pdf_url,
        "jogos_futuros_na_tabela": len(datas_futuras),
        "cobertura_ate": cobertura_ate.isoformat() if cobertura_ate else None,
        "dias_restantes": dias_restantes,
        "status": status,
        "mensagem": msg,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dias", type=int, default=180)
    parser.add_argument("--dias-atras", type=int, default=30)
    parser.add_argument("--incluir-passados", action="store_true")
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    all_new: list[Partido] = []
    debug_info: list[dict] = []
    cobertura_report: list[dict] = []

    print("[INFO] Buscando PDFs de Tabela Detalhada da CBF via busca de texto...")
    pdf_targets = find_cbf_pdf_urls()
    print(f"[INFO] PDFs encontrados: {len(pdf_targets)}")

    for competicao, pdf_url in pdf_targets:
        entry = {"competicao": competicao, "pdf_url": pdf_url}
        try:
            pdf_bytes = fetch_bytes(pdf_url)
            entry["bytes_baixados"] = len(pdf_bytes)
            matches_raw = parse_cbf_pdf(pdf_bytes, competicao, pdf_url)
            entry["jogos_extraidos_total"] = len(matches_raw)
            matches = [m for m in matches_raw if in_window(m, desde, ate, args.incluir_passados)]
            entry["jogos_na_janela_de_datas"] = len(matches)
            print(f"[OK] {competicao} -> {len(matches)} jogos | {pdf_url}")
            all_new.extend(matches)
            cobertura_report.append(checar_cobertura(competicao, pdf_url, matches_raw, today))
        except Exception as e:
            entry["erro"] = str(e)
            print(f"[ERRO] Falha ao baixar/processar PDF {pdf_url}: {e}", file=sys.stderr)
            cobertura_report.append({
                "competicao": competicao, "pdf_url": pdf_url, "status": "erro",
                "mensagem": f"Falha ao baixar/processar o PDF: {e}",
            })
            print(f"::error::[COBERTURA CBF] '{competicao}' falhou ao baixar/processar ({e}); jogos futuros dessa competicao NAO foram atualizados nesta rodada do script.")
        debug_info.append(entry)

    for competicao, _query in CBF_SEARCH_QUERIES:
        if not any(d["competicao"] == competicao for d in debug_info):
            debug_info.append({"competicao": competicao, "pdf_url": None, "erro": "nenhum PDF encontrado (busca nem seed)"})
            cobertura_report.append({
                "competicao": competicao, "pdf_url": None, "status": "erro",
                "mensagem": "Nenhum PDF encontrado (nem busca, nem seed) -- competicao ficou sem nenhuma fonte de dados nesta rodada.",
            })
            print(f"::error::[COBERTURA CBF] '{competicao}' sem PDF algum (busca e seed falharam) -- confira CBF_SEARCH_QUERIES/SEED_PDF_URLS.")

    (OUT_DIR / "debug_cbf_pdf_discovery.json").write_text(
        json.dumps(debug_info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "debug_cbf_cobertura.json").write_text(
        json.dumps(cobertura_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    problematicos = [c for c in cobertura_report if c["status"] != "ok"]
    print("\n" + "=" * 70)
    print(f"RESUMO DE COBERTURA CBF ({len(cobertura_report)} competições verificadas)")
    if problematicos:
        print(f"{len(problematicos)} precisam de atenção:")
        for c in problematicos:
            print(f"  [{c['status'].upper()}] {c['competicao']}: {c['mensagem']}")
    else:
        print("Todas as competições com cobertura futura saudável.")
    print("=" * 70)

    # Complemento best-effort: federações estaduais (pode retornar 0 se bloquearem bots)
    all_new.extend(parse_extra_html_sources(desde, ate, args.incluir_passados))

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"
    current_existing = load_json_rows(current_json)

    # Tabela Básica: só preenche rodadas que a Tabela Detalhada ainda não
    # cobre (ver docstring de parse_tabela_basica_pdf). Confrontos que já têm
    # uma linha confirmada (existente ou vinda da Tabela Detalhada nesta
    # mesma rodada do script) não recebem a versão provisória.
    confrontos_confirmados = {
        chave_confronto(r.get("mandante", ""), r.get("visitante", ""), r.get("competicao", ""))
        for r in current_existing
        if "status=Provisorio" not in (r.get("extra") or "")
    }
    confrontos_confirmados |= {chave_confronto(m.mandante, m.visitante, m.competicao) for m in all_new}

    print("[INFO] Buscando Tabela Básica da CBF (preenchimento provisório de rodadas futuras)...")
    for competicao, pdf_url in SEED_TABELA_BASICA_URLS:
        try:
            pdf_bytes = fetch_bytes(pdf_url)
            provisorios = parse_tabela_basica_pdf(pdf_bytes, competicao, pdf_url)
            provisorios = [
                m for m in provisorios
                if chave_confronto(m.mandante, m.visitante, m.competicao) not in confrontos_confirmados
                and in_window(m, desde, ate, args.incluir_passados)
            ]
            print(f"[OK] {competicao} (Tabela Básica) -> {len(provisorios)} jogos provisórios novos | {pdf_url}")
            all_new.extend(provisorios)
        except Exception as e:
            print(f"[WARN] Falha ao baixar/processar Tabela Básica {pdf_url}: {e}", file=sys.stderr)

    rows_new = [m.to_row() for m in dedupe(all_new)]

    merged_current = merge_rows(current_existing, rows_new)
    history_existing = load_csv_rows(history_csv)
    merged_history = merge_rows(history_existing, rows_new)

    # Limpeza automática: remove qualquer linha "Provisorio" (Tabela Básica)
    # cujo confronto já tenha uma versão confirmada no mesmo conjunto -- é
    # assim que uma rodada provisória "vira" a confirmada quando a Tabela
    # Detalhada finalmente publica a data exata (evita ficar com as duas
    # linhas do mesmo jogo lado a lado pra sempre).
    def limpar_provisorios_confirmados(rows: list[dict]) -> list[dict]:
        confirmados = {
            chave_confronto(r.get("mandante", ""), r.get("visitante", ""), r.get("competicao", ""))
            for r in rows
            if "status=Provisorio" not in (r.get("extra") or "")
        }
        return [
            r for r in rows
            if "status=Provisorio" not in (r.get("extra") or "")
            or chave_confronto(r.get("mandante", ""), r.get("visitante", ""), r.get("competicao", "")) not in confirmados
        ]

    merged_current = limpar_provisorios_confirmados(merged_current)
    merged_history = limpar_provisorios_confirmados(merged_history)

    # Rede de segurança final: colapsa o mesmo confronto descrito com nomes
    # de time formatados de forma diferente por fontes diferentes (ex.:
    # PDFs alternativos/espelhos), que escapariam do row_id() normal.
    merged_current = colapsar_duplicados_mesmo_confronto(merged_current)
    merged_history = colapsar_duplicados_mesmo_confronto(merged_history)

    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)
    write_csv(history_csv, merged_history)

    print(f"\nBrasil adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")


if __name__ == "__main__":
    main()
