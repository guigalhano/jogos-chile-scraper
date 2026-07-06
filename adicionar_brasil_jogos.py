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
    "Accept-Language": "pt-BR,pt;q=0.9,es;q=0.8,en;q=0.7",
}

# Fontes complementares simples (best-effort; podem falhar sem quebrar o script)
EXTRA_HTML_SOURCES = [
    ("FERJ", "https://www.fferj.com.br/partidas"),
    ("FMF", "https://www.fmf.com.br/"),
    ("FPF", "https://www.futebolpaulista.com.br/Home/"),
]

# Buscas para localizar os PDFs de Tabela Detalhada mais recentes de cada série.
CBF_SEARCH_QUERIES = [
    ("Brasil - Série A", "CBF \"tabela detalhada\" brasileirão \"série a\" 2026 rodada pdf"),
    ("Brasil - Série B", "CBF \"tabela detalhada\" brasileirão \"série b\" 2026 rodada pdf"),
    ("Brasil - Série C", "CBF \"tabela detalhada\" brasileirão \"série c\" 2026 rodada pdf"),
    ("Brasil - Série D", "CBF \"tabela detalhada\" brasileirão \"série d\" 2026 fase pdf"),
    ("Brasil - Copa do Brasil", "CBF \"tabela detalhada\" \"copa do brasil\" 2026 fase pdf"),
    ("Brasil - Copa do Brasil Feminina", "CBF \"tabela detalhada\" \"copa do brasil feminina\" 2026 pdf"),
    ("Brasil - Série A Sub-20", "CBF \"tabela detalhada\" brasileirão \"série a\" \"sub-20\" 2026 pdf"),
    ("Brasil - Série B Sub-20", "CBF \"tabela detalhada\" brasileirão \"série b\" \"sub-20\" 2026 pdf"),
    ("Brasil - Sub-17", "CBF \"tabela detalhada\" brasileirão \"sub-17\" 2026 rodada pdf"),
    ("Brasil - Feminino Sub-20", "CBF \"tabela detalhada\" brasileirão feminino \"sub 20\" 2026 pdf"),
    ("Brasil - Feminino Sub-17", "CBF \"tabela detalhada\" brasileirão feminino \"sub 17\" 2026 pdf"),
    ("Brasil - Feminino A1", "CBF \"tabela detalhada\" \"brasileiro feminino a1\" 2026 pdf"),
]

# Fallback manual: como buscadores (DuckDuckGo/Bing) podem bloquear scripts
# automatizados com uma página de desafio anti-bot (confirmado em teste real
# no GitHub Actions), mantemos aqui uma lista "semente" dos PDFs mais recentes
# conhecidos. Atualize esta lista manualmente de tempos em tempos (mesma
# lógica de manutenção do estadios.js) até que a busca automática funcione
# de forma confiável, ou até que uma API de busca paga seja configurada.
SEED_PDF_URLS = [
    ("Brasil - Série A", "https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/Tabela_Detalhada_Brasileiro_Serie_A_2026_19_a_24_rodada_82505dee72.pdf"),
    ("Brasil - Série B", "https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/Tabela_Detalhada_12_a_18_rodada_Brasileiro_Serie_B_2026_ea9e84afde.pdf"),
    ("Brasil - Série C", "https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/Tabela_Detalhada_Brasileiro_Serie_C_2026_23_05_d384914c53.pdf"),
    ("Brasil - Série D", "https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/Tabela_Detalhada_Brasileiro_Serie_D_2026_06_07_fb69bfb072.pdf"),
    ("Brasil - Copa do Brasil", "https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/Tabela_Detalhada_Copa_do_Brasil_2026_24_06_7dfa8d4cf5.pdf"),
    ("Brasil - Copa do Brasil Feminina", "https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/Tabela_Detalhada_Copa_do_Brasil_Feminina_2026_0d8d5d0448.pdf"),
    ("Brasil - Série B Sub-20", "https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/TABELA_DETALHADA_BRASILEIRO_MASCULINO_SERIE_B_SUB_20_10_04_v2_1683d773ce.pdf"),
    ("Brasil - Feminino A1", "https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/Tabela_Detalhada_Brasileiro_Feminino_A1_2026_04a2a21b30.pdf"),
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
    rodada: str = ""
    url: str = ""
    extra: str = ""

    @property
    def id(self) -> str:
        raw = "|".join([
            self.fonte, self.competicao, self.data, self.hora,
            self.mandante, self.visitante, self.estadio, self.rodada
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
    if row.get("id"):
        return row["id"]
    raw = "|".join([
        row.get("fonte", ""), row.get("competicao", ""), row.get("data", ""),
        row.get("hora", ""), row.get("mandante", ""), row.get("visitante", ""),
        row.get("estadio", ""), row.get("rodada", ""),
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


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "id", "fonte", "competicao", "data", "hora",
        "mandante", "visitante", "estadio", "rodada",
        "url", "extra", "atualizado_em",
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


def search_web(query: str, max_results: int = 15) -> list[str]:
    """Retorna uma lista de URLs de resultados de busca. Tenta DuckDuckGo HTML
    primeiro, cai para Bing HTML se a primeira falhar ou não retornar nada.

    NOTA: ambos os buscadores podem servir uma página de desafio anti-bot em
    vez de resultados reais quando acessados por scripts automatizados (comum
    em ambientes de CI/cloud). Quando isso acontece, o find_cbf_pdf_urls() cai
    para SEED_PDF_URLS (lista mantida manualmente). Atualize essa lista de
    tempos em tempos buscando "CBF tabela detalhada <competição> <ano>"."""
    urls: list[str] = []

    try:
        r = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=HEADERS,
            timeout=20,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a.result__a, a.result__url"):
            href = a.get("href", "")
            target = _extract_ddg_redirect(href)
            if target:
                urls.append(target)
    except Exception as e:
        print(f"[WARN] Busca DuckDuckGo falhou para '{query}': {e}", file=sys.stderr)

    if not urls:
        try:
            r = requests.get(
                "https://www.bing.com/search",
                params={"q": query},
                headers=HEADERS,
                timeout=20,
            )
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for li in soup.select("li.b_algo h2 a"):
                href = li.get("href", "")
                if href:
                    urls.append(href)
        except Exception as e:
            print(f"[WARN] Busca Bing falhou para '{query}': {e}", file=sys.stderr)

    return urls[:max_results]


def find_cbf_pdf_urls() -> list[tuple[str, str]]:
    """Retorna lista de (competicao_label, pdf_url) para as tabelas detalhadas
    mais recentes encontradas via busca de texto (não via crawling do site da CBF)."""
    found: list[tuple[str, str]] = []
    search_debug: list[dict] = []
    for competicao, query in CBF_SEARCH_QUERIES:
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
    if norm(tail).startswith("a definir") or not tail.strip():
        estadio, cidade = "A definir", ""
    else:
        estadio, cidade, _uf2 = split_estadio_cidade_uf(tail)

    rod = m.group("rod")
    if rod:
        last_rod[0] = rod
    rodada = f"Rodada {last_rod[0]}" if last_rod[0] else ""

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
                    rodada=row["rodada"],
                    url=pdf_url,
                    extra=f"pais=Brasil; cidade={row['cidade']}" if row["cidade"] else "pais=Brasil",
                ))
    except Exception as e:
        print(f"[WARN] Erro lendo PDF {pdf_url}: {e}", file=sys.stderr)

    return dedupe(out)


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
        except Exception as e:
            entry["erro"] = str(e)
            print(f"[ERRO] Falha ao baixar/processar PDF {pdf_url}: {e}", file=sys.stderr)
        debug_info.append(entry)

    for competicao, _query in CBF_SEARCH_QUERIES:
        if not any(d["competicao"] == competicao for d in debug_info):
            debug_info.append({"competicao": competicao, "pdf_url": None, "erro": "nenhum PDF encontrado (busca nem seed)"})

    (OUT_DIR / "debug_cbf_pdf_discovery.json").write_text(
        json.dumps(debug_info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Complemento best-effort: federações estaduais (pode retornar 0 se bloquearem bots)
    all_new.extend(parse_extra_html_sources(desde, ate, args.incluir_passados))

    rows_new = [m.to_row() for m in dedupe(all_new)]

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    current_existing = load_json_rows(current_json)
    merged_current = merge_rows(current_existing, rows_new)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    history_existing = load_csv_rows(history_csv)
    merged_history = merge_rows(history_existing, rows_new)
    write_csv(history_csv, merged_history)

    print(f"\nBrasil adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")


if __name__ == "__main__":
    main()
