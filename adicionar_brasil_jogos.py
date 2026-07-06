#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adiciona jogos do Brasil usando principalmente os PDFs de "Tabela Detalhada" da CBF.

Fonte principal:
- https://www.cbf.com.br/futebol-brasileiro/tabelas/

O script:
1. Abre a página de tabelas da CBF.
2. Descobre links internos de competições.
3. Procura links PDF, especialmente "Tabela Detalhada".
4. Baixa os PDFs em data/cbf_pdfs/.
5. Extrai tabelas/texto dos PDFs com pdfplumber.
6. Atualiza:
   - data/jogos_programados.json
   - data/jogos_programados.csv
   - data/historico_jogos.csv

Também mantém uma tentativa simples de FERJ/FMF/FPF como complemento.

Uso:
    python adicionar_brasil_jogos.py --dias 180 --dias-atras 30

Debug:
    python adicionar_brasil_jogos.py --dias 365 --dias-atras 30 --salvar-debug
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, date, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup

try:
    import pdfplumber
except Exception:
    pdfplumber = None


OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)
PDF_DIR = OUT_DIR / "cbf_pdfs"
PDF_DIR.mkdir(exist_ok=True)

CBF_TABELAS_URL = "https://www.cbf.com.br/futebol-brasileiro/tabelas/"

CBF_TABLE_URLS = [
    CBF_TABELAS_URL,
    "https://www.cbf.com.br/futebol-brasileiro/tabelas/campeonato-brasileiro/serie-a",
    "https://www.cbf.com.br/futebol-brasileiro/tabelas/campeonato-brasileiro/serie-b",
    "https://www.cbf.com.br/futebol-brasileiro/tabelas/campeonato-brasileiro/serie-c",
    "https://www.cbf.com.br/futebol-brasileiro/tabelas/campeonato-brasileiro/serie-d",
    "https://www.cbf.com.br/futebol-brasileiro/tabelas/copa-brasil",
    "https://www.cbf.com.br/futebol-brasileiro/tabelas/copa-do-brasil",
    "https://www.cbf.com.br/futebol-brasileiro/tabelas/brasileiro-feminino-a1",
    "https://www.cbf.com.br/futebol-brasileiro/tabelas/brasileiro-feminino-a2",
    "https://www.cbf.com.br/futebol-brasileiro/tabelas/brasileiro-feminino-a3",
]

EXTRA_HTML_SOURCES = [
    ("FERJ", "https://www.fferj.com.br/partidas"),
    ("FMF", "https://www.fmf.com.br/"),
    ("FPF", "https://www.futebolpaulista.com.br/Home/"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,es;q=0.8,en;q=0.7",
}

MESES = {
    "jan": 1, "janeiro": 1,
    "fev": 2, "fevereiro": 2,
    "mar": 3, "março": 3, "marco": 3,
    "abr": 4, "abril": 4,
    "mai": 5, "maio": 5,
    "jun": 6, "junho": 6,
    "jul": 7, "julho": 7,
    "ago": 8, "agosto": 8,
    "set": 9, "setembro": 9,
    "out": 10, "outubro": 10,
    "nov": 11, "novembro": 11,
    "dez": 12, "dezembro": 12,
}

DATE_RE = re.compile(r"\b(?P<dia>\d{1,2})[/-](?P<mes>\d{1,2})[/-](?P<ano>\d{2,4})\b")
TIME_RE = re.compile(r"\b(?P<hora>\d{1,2}:\d{2})h?\b")
VS_RE = re.compile(r"\s+(?:X|x|vs\.?|v/s)\s+")
PLACAR_RE = re.compile(r"\b\d+\s*[-xX]\s*\d+\b")
DIAS_SEMANA = "SEG|TER|QUA|QUI|SEX|SAB|SÁB|DOM"

FERJ_RE = re.compile(
    rf"\b(?:{DIAS_SEMANA})\s+"
    r"(?P<dia>\d{2})/(?P<mes>\d{2})/(?P<ano>\d{2,4})\s+"
    r"(?P<hora>\d{1,2}:\d{2})h?\s+"
    r"(?P<resto>.+?)$",
    re.I,
)
GENERIC_NUMERIC_RE = re.compile(
    r"\b(?P<dia>\d{1,2})[/-](?P<mes>\d{1,2})[/-](?P<ano>\d{2,4})\s+"
    r"(?P<hora>\d{1,2}:\d{2})h?\s+"
    r"(?P<resto>.+?)$",
    re.I,
)


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
    value = value.replace("\u00a0", " ").strip()
    return re.sub(r"\s+", " ", value).strip()


def norm(value: str) -> str:
    import unicodedata
    value = unicodedata.normalize("NFD", str(value or ""))
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def parse_year(y: str) -> int:
    n = int(y)
    return 2000 + n if n < 100 else n


def parse_date(value: str) -> str:
    m = DATE_RE.search(clean_text(value))
    if not m:
        return ""
    return date(parse_year(m.group("ano")), int(m.group("mes")), int(m.group("dia"))).isoformat()


def parse_time(value: str) -> str:
    m = TIME_RE.search(clean_text(value))
    return m.group("hora") if m else ""


def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text


def fetch_bytes(url: str) -> bytes:
    r = requests.get(url, headers=HEADERS, timeout=90)
    r.raise_for_status()
    return r.content


def safe_filename(url: str, prefix: str = "cbf") -> str:
    parsed = urlparse(url)
    name = Path(unquote(parsed.path)).name or "arquivo.pdf"
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    if not name.lower().startswith(prefix):
        name = f"{prefix}_{name}"
    return name


def discover_cbf_pages(start_urls: list[str], max_pages: int = 80) -> list[str]:
    """
    Descobre páginas internas da CBF que parecem conter tabelas/documentos.
    """
    seen = set()
    queue = list(dict.fromkeys(start_urls))
    out = []

    while queue and len(out) < max_pages:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        out.append(url)

        try:
            html = fetch(url)
        except Exception as e:
            print(f"[WARN] Não abriu página CBF {url}: {e}", file=sys.stderr)
            continue

        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"]).split("#")[0]
            low = href.lower() + " " + clean_text(a.get_text(" ", strip=True)).lower()

            if "cbf.com.br" not in href and "conteudo.cbf.com.br" not in href:
                continue

            if href.lower().endswith(".pdf"):
                continue

            wanted = ["tabela", "tabelas", "campeonato", "brasileiro", "copa", "feminino", "serie", "série"]
            if any(w in low for w in wanted):
                if href not in seen and href not in queue:
                    queue.append(href)

    return out


def discover_pdf_links_from_page(url: str) -> list[tuple[str, str]]:
    """
    Retorna lista de (pdf_url, texto_do_link).
    """
    try:
        html = fetch(url)
    except Exception as e:
        print(f"[WARN] Não abriu {url}: {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"]).split("#")[0]
        text = clean_text(a.get_text(" ", strip=True))
        low = (href + " " + text).lower()

        if ".pdf" in low or "download" in low:
            # Prioriza PDF de tabela detalhada, mas aceita PDF de tabela.
            if any(k in low for k in ["tabela", "detalhada", "brasileiro", "copa", "serie", "série", "feminino"]):
                links.append((href, text))

    # PDFs às vezes aparecem em atributos data-url/data-href
    for tag in soup.find_all(True):
        for attr in ["data-url", "data-href", "data-file", "onclick"]:
            val = tag.get(attr)
            if not val:
                continue
            found = re.findall(r'https?://[^"\']+?\.pdf|/[^"\']+?\.pdf', val, flags=re.I)
            for raw in found:
                href = urljoin(url, raw)
                links.append((href, clean_text(tag.get_text(" ", strip=True))))

    # Dedup
    seen = set()
    out = []
    for href, text in links:
        key = href
        if key in seen:
            continue
        seen.add(key)
        out.append((href, text))
    return out


def download_pdfs(pdf_links: list[tuple[str, str]]) -> list[tuple[Path, str, str]]:
    """
    Baixa PDFs e retorna (path, url, link_text).
    """
    files = []
    for url, text in pdf_links:
        try:
            content = fetch_bytes(url)
            if not content.startswith(b"%PDF") and b"%PDF" not in content[:1000]:
                print(f"[WARN] Ignorado, não parece PDF: {url}", file=sys.stderr)
                continue
            path = PDF_DIR / safe_filename(url)
            path.write_bytes(content)
            files.append((path, url, text))
            print(f"[OK] PDF baixado: {path.name}")
        except Exception as e:
            print(f"[WARN] Falha ao baixar PDF {url}: {e}", file=sys.stderr)
    return files


def infer_competicao_from_text(txt: str, url: str = "") -> str:
    low = (txt + " " + url).lower()
    if "série a1" in low or "serie a1" in low or "feminino a1" in low:
        return "Brasil - Feminino A1"
    if "série a2" in low or "serie a2" in low or "feminino a2" in low:
        return "Brasil - Feminino A2"
    if "série a3" in low or "serie a3" in low or "feminino a3" in low:
        return "Brasil - Feminino A3"
    if "feminino" in low:
        return "Brasil - Feminino"
    if "série a" in low or "serie a" in low or "serie-a" in low:
        return "Brasil - Série A"
    if "série b" in low or "serie b" in low or "serie-b" in low:
        return "Brasil - Série B"
    if "série c" in low or "serie c" in low or "serie-c" in low:
        return "Brasil - Série C"
    if "série d" in low or "serie d" in low or "serie-d" in low:
        return "Brasil - Série D"
    if "copa do brasil" in low or "copa-brasil" in low:
        return "Brasil - Copa do Brasil"
    if "supercopa" in low:
        return "Brasil - Supercopa"
    return "Brasil - CBF"


def choose_col(row: dict, names: list[str]) -> str:
    """
    Busca valor por nomes normalizados de colunas.
    """
    for k, v in row.items():
        nk = norm(k)
        for name in names:
            if name in nk:
                val = clean_text(v)
                if val:
                    return val
    return ""


def row_from_pdf_table(row: dict, comp: str, pdf_url: str, pdf_name: str) -> Partido | None:
    data = choose_col(row, ["data"])
    hora = choose_col(row, ["hora", "horario", "horario de brasilia"])
    mandante = choose_col(row, ["mandante", "clube mandante", "equipe mandante", "time mandante", "principal"])
    visitante = choose_col(row, ["visitante", "clube visitante", "equipe visitante", "time visitante"])
    estadio = choose_col(row, ["estadio", "estádio", "arena", "local"])
    rodada = choose_col(row, ["rodada", "fase", "jogo"])

    if not data:
        # às vezes "Data/Hora" vem junto
        dh = choose_col(row, ["data hora", "data/hora", "dia hora"])
        data = parse_date(dh)
        hora = hora or parse_time(dh)
    else:
        data = parse_date(data)
    hora = parse_time(hora) or hora

    # Algumas tabelas extraídas viram colunas sem nome. Faz fallback concatenando a linha.
    joined = " ".join(clean_text(v) for v in row.values() if clean_text(v))
    if not data:
        data = parse_date(joined)
    if not hora:
        hora = parse_time(joined)

    if not mandante or not visitante:
        # Tenta achar "Time A x Time B" no texto da linha.
        parts = VS_RE.split(joined, maxsplit=1)
        if len(parts) == 2:
            left = parts[0]
            right = parts[1]
            # remove data/hora do lado esquerdo
            left = DATE_RE.sub("", left)
            left = TIME_RE.sub("", left).strip(" -|")
            mandante = mandante or clean_text(left.split()[-5:]) if False else mandante
            # Heurística: pega texto final antes do X como mandante e inicial depois do X como visitante.
            left_words = clean_text(left).split()
            if left_words:
                mandante = mandante or " ".join(left_words[-4:])
            right_words = clean_text(right).split()
            if right_words:
                visitante = visitante or " ".join(right_words[:4])

    if not (data and mandante and visitante):
        return None

    return Partido(
        fonte="CBF PDF",
        competicao=comp,
        data=data,
        hora=hora,
        mandante=mandante,
        visitante=visitante,
        estadio=estadio,
        rodada=rodada,
        url=pdf_url,
        extra=f"pdf={pdf_name}",
    )


def extract_tables_from_pdf(path: Path, pdf_url: str, link_text: str) -> list[Partido]:
    if pdfplumber is None:
        print("[ERRO] pdfplumber não instalado. Adicione pdfplumber ao requirements.txt", file=sys.stderr)
        return []

    comp = infer_competicao_from_text(link_text + " " + path.name, pdf_url)
    out: list[Partido] = []

    try:
        with pdfplumber.open(path) as pdf:
            full_text_parts = []
            for page in pdf.pages:
                try:
                    text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                    full_text_parts.append(text)
                except Exception:
                    pass

                try:
                    tables = page.extract_tables()
                except Exception:
                    tables = []

                for table in tables or []:
                    if not table or len(table) < 2:
                        continue

                    # acha header: primeira linha com palavras de colunas.
                    header_idx = 0
                    for idx, raw in enumerate(table[:5]):
                        line = " ".join(clean_text(c) for c in raw if clean_text(c))
                        low = norm(line)
                        if any(k in low for k in ["data", "mandante", "visitante", "estadio", "hora"]):
                            header_idx = idx
                            break

                    header = [clean_text(c) or f"col_{i}" for i, c in enumerate(table[header_idx])]
                    for raw in table[header_idx + 1:]:
                        vals = [clean_text(c) for c in raw]
                        if not any(vals):
                            continue
                        row = {header[i] if i < len(header) else f"col_{i}": vals[i] for i in range(len(vals))}
                        p = row_from_pdf_table(row, comp, pdf_url, path.name)
                        if p:
                            out.append(p)

            # Fallback por texto completo
            full_text = "\n".join(full_text_parts)
            out.extend(parse_cbf_text_fallback(full_text, comp, pdf_url, path.name))

    except Exception as e:
        print(f"[WARN] Erro lendo PDF {path}: {e}", file=sys.stderr)

    return dedupe(out)


def parse_cbf_text_fallback(text: str, comp: str, pdf_url: str, pdf_name: str) -> list[Partido]:
    """
    Fallback flexível para quando pdfplumber não extrai tabela.
    Procura linhas com data/hora e confronto.
    """
    out = []
    lines = [clean_text(l) for l in text.splitlines() if clean_text(l)]
    for i, line in enumerate(lines):
        if not DATE_RE.search(line):
            continue

        data = parse_date(line)
        hora = parse_time(line)

        # Junta linha atual + próximas duas, porque PDFs quebram as linhas.
        block = clean_text(" ".join(lines[i:i+4]))
        if not hora:
            hora = parse_time(block)

        if PLACAR_RE.search(block):
            block = PLACAR_RE.sub(" X ", block, count=1)

        parts = VS_RE.split(block, maxsplit=1)
        if len(parts) != 2:
            continue

        before, after = parts
        before = DATE_RE.sub("", before)
        before = TIME_RE.sub("", before)
        before = re.sub(r"\b\d{1,3}\b", " ", before)  # jogo/rodada soltos
        left_words = clean_text(before).split()
        right_words = clean_text(after).split()

        if not left_words or not right_words:
            continue

        mandante = " ".join(left_words[-5:])
        visitante = " ".join(right_words[:5])

        if len(mandante) > 80 or len(visitante) > 80:
            continue

        out.append(Partido(
            fonte="CBF PDF",
            competicao=comp,
            data=data,
            hora=hora,
            mandante=mandante,
            visitante=visitante,
            estadio="",
            rodada="",
            url=pdf_url,
            extra=f"pdf={pdf_name}; fallback_text=1",
        ))

    return out


def get_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return [clean_text(raw) for raw in soup.get_text("\n").splitlines() if clean_text(raw)]


def split_visitante_comp(txt: str) -> tuple[str, str]:
    txt = clean_text(txt)
    keys = [
        " BRASILEIRO ", " COPA DO BRASIL ", " COPA RIO ", " Estadual ",
        " Torneio ", " Amador ", " Paulista ", " Carioca ", " Mineiro ",
        " Sub-20 ", " Sub-17 ", " Sub-16 ", " Sub-15 ", " Profissional ",
        " CBF ", " FERJ ", " FMF ", " FPF "
    ]
    padded = " " + txt + " "
    best = None
    for key in keys:
        pos = padded.lower().find(key.lower())
        if pos > 0:
            if best is None or pos < best:
                best = pos
    if best is not None:
        return txt[:best].strip(), txt[best:].strip()
    words = txt.split()
    if len(words) > 6:
        return " ".join(words[:5]).strip(), " ".join(words[5:]).strip()
    return txt, ""


def split_match_parts(resto: str) -> tuple[str, str, str, str]:
    resto = clean_text(resto)
    estadio = ""
    if re.match(r"^(ESTÁDIO|ESTADIO|ARENA|CAMPO|CT)\b", resto, flags=re.I):
        parts = VS_RE.split(resto, maxsplit=1)
        if len(parts) == 2:
            before_x, after_x = parts
            pos = before_x.rfind(")")
            if pos > 0 and pos + 1 < len(before_x):
                estadio = before_x[:pos + 1].strip()
                mandante = before_x[pos + 1:].strip()
            else:
                words = before_x.split()
                mandante = " ".join(words[-4:]).strip()
                estadio = " ".join(words[:-4]).strip()
            visitante, comp = split_visitante_comp(after_x)
            return mandante, visitante, estadio, comp

    parts = VS_RE.split(resto, maxsplit=1)
    if len(parts) != 2:
        return "", "", "", ""
    mandante = clean_text(parts[0])
    visitante, comp = split_visitante_comp(parts[1])
    return mandante, visitante, estadio, comp


def infer_competicao_html(resto: str, fonte: str) -> str:
    low = resto.lower()
    if "copa do brasil" in low:
        return "Brasil - Copa do Brasil"
    if "brasileiro" in low or "série" in low or "serie" in low:
        if "série a" in low or "serie a" in low:
            return "Brasil - Série A"
        if "série b" in low or "serie b" in low:
            return "Brasil - Série B"
        if "série c" in low or "serie c" in low:
            return "Brasil - Série C"
        if "série d" in low or "serie d" in low:
            return "Brasil - Série D"
        return "Brasil - CBF"
    if "carioca" in low or "ferj" in low:
        return "Brasil - FERJ"
    if "mineiro" in low or "fmf" in low:
        return "Brasil - FMF"
    if "paulista" in low or "fpf" in low:
        return "Brasil - FPF"
    return f"Brasil - {fonte}"


def parse_html_line(line: str, fonte: str, url: str) -> Partido | None:
    m = FERJ_RE.search(line) or GENERIC_NUMERIC_RE.search(line)
    if not m:
        return None
    data = date(parse_year(m.group("ano")), int(m.group("mes")), int(m.group("dia"))).isoformat()
    hora = m.group("hora")
    resto = m.group("resto")

    placar = ""
    if PLACAR_RE.search(resto):
        placar = PLACAR_RE.search(resto).group(0)
        resto = PLACAR_RE.sub(" X ", resto, count=1)

    mandante, visitante, estadio, comp_txt = split_match_parts(resto)
    if not mandante or not visitante:
        return None

    return Partido(
        fonte=fonte,
        competicao=infer_competicao_html(comp_txt or resto, fonte),
        data=data,
        hora=hora,
        mandante=mandante,
        visitante=visitante,
        estadio=estadio,
        rodada="",
        url=url,
        extra="; ".join(x for x in [f"competicao_original={comp_txt}" if comp_txt else "", f"placar={placar}" if placar else "", "pais=Brasil"] if x),
    )


def parse_extra_html_sources(desde: date, ate: date, incluir_passados: bool) -> list[Partido]:
    out = []
    for fonte, url in EXTRA_HTML_SOURCES:
        try:
            html = fetch(url)
            count = 0
            for line in get_lines(html):
                p = parse_html_line(line, fonte, url)
                if not p:
                    continue
                dt = date.fromisoformat(p.data)
                if incluir_passados or (desde <= dt <= ate):
                    out.append(p)
                    count += 1
            print(f"[OK] {fonte} HTML -> {count} jogos")
        except Exception as e:
            print(f"[WARN] Fonte HTML {fonte} falhou: {e}", file=sys.stderr)
    return dedupe(out)


def in_window(p: Partido, desde: date, ate: date, incluir_passados: bool) -> bool:
    try:
        dt = date.fromisoformat(p.data)
    except Exception:
        return False
    return incluir_passados or (desde <= dt <= ate)


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
        row.get("fonte", ""),
        row.get("competicao", ""),
        row.get("data", ""),
        row.get("hora", ""),
        row.get("mandante", ""),
        row.get("visitante", ""),
        row.get("estadio", ""),
        row.get("rodada", ""),
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dias", type=int, default=180)
    parser.add_argument("--dias-atras", type=int, default=30)
    parser.add_argument("--incluir-passados", action="store_true")
    parser.add_argument("--max-pages", type=int, default=80)
    parser.add_argument("--salvar-debug", action="store_true")
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    print("[INFO] Descobrindo páginas CBF...")
    pages = discover_cbf_pages(CBF_TABLE_URLS, max_pages=args.max_pages)
    print(f"[INFO] Páginas CBF descobertas: {len(pages)}")

    pdf_links = []
    for page_url in pages:
        found = discover_pdf_links_from_page(page_url)
        if found:
            print(f"[OK] PDFs encontrados em {page_url}: {len(found)}")
        pdf_links.extend(found)

    # Dedup PDFs
    seen_pdf = set()
    clean_pdf_links = []
    for href, text in pdf_links:
        if href in seen_pdf:
            continue
        seen_pdf.add(href)
        clean_pdf_links.append((href, text))

    print(f"[INFO] PDFs CBF únicos: {len(clean_pdf_links)}")
    if args.salvar_debug:
        (OUT_DIR / "debug_cbf_pdf_links.csv").write_text(
            "url,texto\n" + "\n".join(f'"{u}","{t.replace(chr(34), chr(34)+chr(34))}"' for u, t in clean_pdf_links),
            encoding="utf-8"
        )

    pdf_files = download_pdfs(clean_pdf_links)

    all_new: list[Partido] = []
    for path, pdf_url, link_text in pdf_files:
        matches = extract_tables_from_pdf(path, pdf_url, link_text)
        matches = [m for m in matches if in_window(m, desde, ate, args.incluir_passados)]
        print(f"[OK] CBF PDF {path.name} -> {len(matches)} jogos")
        all_new.extend(matches)

    # Complemento: estaduais e páginas simples
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

    print(f"\nBrasil CBF/PDF adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")


if __name__ == "__main__":
    main()
