#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper FMF - Federação Mineira de Futebol.

Objetivo:
- Buscar jogos da FMF em "Próximos Jogos".
- Tentar HTML direto primeiro.
- Usar Playwright/JSON/XHR como fallback.
- Atualizar o mesmo JSON/CSV do projeto.

Saídas:
- data/jogos_programados.json
- data/jogos_programados.csv
- data/historico_jogos.csv
- data/debug_fmf_api_urls.json
- data/debug_fmf_matches_raw.json
- data/fmf_endpoints.json

Uso:
    python scrap_fmf_prox_jogos.py --dias 180 --dias-atras 30
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

try:
    from playwright.async_api import async_playwright
except Exception:
    async_playwright = None


OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)
ENDPOINTS_PATH = OUT_DIR / "fmf_endpoints.json"

START_URLS = [
    "https://fmf.com.br/Competicoes/ProxJogos.aspx?d=1",
    "http://fmf.com.br/Competicoes/ProxJogos.aspx?d=1",
    "https://www.fmf.com.br/",
    "https://fmf.com.br/",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,es;q=0.8,en;q=0.7",
}

FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em",
]

DATE_RE = re.compile(r"\b(?P<dia>\d{1,2})[/-](?P<mes>\d{1,2})[/-](?P<ano>\d{2,4})\b")
TIME_RE = re.compile(r"\b(?P<hora>\d{1,2}:\d{2})h?\b")
VS_RE = re.compile(r"\s+(?:X|x|vs\.?|v/s)\s+")

MESES = {
    "jan": 1, "janeiro": 1, "fev": 2, "fevereiro": 2,
    "mar": 3, "março": 3, "marco": 3, "abr": 4, "abril": 4,
    "mai": 5, "maio": 5, "jun": 6, "junho": 6,
    "jul": 7, "julho": 7, "ago": 8, "agosto": 8,
    "set": 9, "setembro": 9, "out": 10, "outubro": 10,
    "nov": 11, "novembro": 11, "dez": 12, "dezembro": 12,
}
TEXT_MONTH_RE = re.compile(
    r"\b(?P<dia>\d{1,2})\s+"
    r"(?P<mes_txt>jan|janeiro|fev|fevereiro|mar|março|marco|abr|abril|mai|maio|jun|junho|jul|julho|ago|agosto|set|setembro|out|outubro|nov|novembro|dez|dezembro)\.?\s+"
    r"(?P<ano>\d{2,4})\b",
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
        raw = "|".join([self.fonte, self.competicao, self.data, self.hora, self.mandante, self.visitante, self.estadio, self.rodada])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def to_row(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        d["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
        return d


def clean_text(value: Any) -> str:
    value = "" if value is None else str(value)
    value = value.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", value).strip()


def norm(value: Any) -> str:
    value = unicodedata.normalize("NFD", clean_text(value))
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def parse_year(y: str) -> int:
    n = int(y)
    return 2000 + n if n < 100 else n


def parse_date(value: Any) -> str:
    txt = clean_text(value)
    if not txt:
        return ""
    m_iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})", txt)
    if m_iso:
        try:
            return date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))).isoformat()
        except Exception:
            pass
    m = DATE_RE.search(txt)
    if m:
        try:
            return date(parse_year(m.group("ano")), int(m.group("mes")), int(m.group("dia"))).isoformat()
        except Exception:
            return ""
    mt = TEXT_MONTH_RE.search(txt)
    if mt:
        try:
            return date(parse_year(mt.group("ano")), MESES[norm(mt.group("mes_txt"))], int(mt.group("dia"))).isoformat()
        except Exception:
            return ""
    return ""


def parse_time(value: Any) -> str:
    m = TIME_RE.search(clean_text(value))
    return m.group("hora") if m else ""


def first_value(obj: dict, keys: list[str]) -> str:
    if not isinstance(obj, dict):
        return ""
    for k in keys:
        if k in obj and clean_text(obj[k]):
            return clean_text(obj[k])
    normalized = {norm(k): v for k, v in obj.items()}
    for wanted in keys:
        nw = norm(wanted)
        for nk, val in normalized.items():
            if nw == nk or nw in nk:
                txt = clean_text(val)
                if txt:
                    return txt
    return ""


def infer_competicao(txt: str) -> str:
    low = txt.lower()
    if "módulo i" in low or "modulo i" in low:
        return "Brasil - FMF - Campeonato Mineiro Módulo I"
    if "módulo ii" in low or "modulo ii" in low:
        return "Brasil - FMF - Campeonato Mineiro Módulo II"
    if "mineiro" in low:
        return "Brasil - FMF - Campeonato Mineiro"
    if "sub-20" in low or "sub 20" in low:
        return "Brasil - FMF - Sub-20"
    if "sub-17" in low or "sub 17" in low:
        return "Brasil - FMF - Sub-17"
    return "Brasil - FMF"


def obj_to_partido(obj: dict, api_url: str) -> Partido | None:
    mandante = first_value(obj, ["Mandante", "NomeMandante", "ClubeMandante", "TimeMandante", "EquipeMandante", "NomePopularMandante"])
    visitante = first_value(obj, ["Visitante", "NomeVisitante", "ClubeVisitante", "TimeVisitante", "EquipeVisitante", "NomePopularVisitante"])
    data_raw = first_value(obj, ["Data", "DataJogo", "DataFormatada", "Dia"])
    hora_raw = first_value(obj, ["Horario", "Horário", "Hora", "HoraFormatada"])
    estadio = first_value(obj, ["Estadio", "Estádio", "Local", "Campo", "Arena"])
    cidade = first_value(obj, ["Cidade", "Municipio", "Município"])
    rodada = first_value(obj, ["Rodada", "Fase", "Etapa", "NumeroRodada"])
    competicao_txt = first_value(obj, ["Competicao", "Competição", "Campeonato", "Torneio", "Categoria"])

    data = parse_date(data_raw)
    hora = parse_time(hora_raw) or clean_text(hora_raw)
    if not data:
        joined = " ".join(clean_text(v) for v in obj.values() if isinstance(v, (str, int, float)))
        data = parse_date(joined)
        if not hora:
            hora = parse_time(joined)

    if not (mandante and visitante and data):
        return None
    if len(mandante) > 90 or len(visitante) > 90:
        return None

    extra = ["pais=Brasil"]
    if cidade:
        extra.append(f"cidade={cidade}")

    return Partido("FMF", infer_competicao(competicao_txt or str(obj)), data, hora, mandante, visitante, estadio, rodada, api_url, "; ".join(extra))


def walk_json(data: Any, api_url: str) -> list[Partido]:
    out = []
    if isinstance(data, dict):
        p = obj_to_partido(data, api_url)
        if p:
            out.append(p)
        for v in data.values():
            out.extend(walk_json(v, api_url))
    elif isinstance(data, list):
        for item in data:
            out.extend(walk_json(item, api_url))
    return out


def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    return r.text


def parse_html(html: str, url: str) -> list[Partido]:
    soup = BeautifulSoup(html, "html.parser")
    out = []

    # tabelas
    for table in soup.find_all("table"):
        headers = [clean_text(th.get_text(" ", strip=True)) for th in table.find_all("th")]
        for tr in table.find_all("tr"):
            cells = [clean_text(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
            if len(cells) < 3:
                continue
            row_text = " ".join(cells)
            if headers and len(headers) == len(cells):
                p = obj_to_partido(dict(zip(headers, cells)), url)
                if p:
                    out.append(p)
                    continue
            p = parse_text_match(row_text, url, "tabela_html")
            if p:
                out.append(p)

    # texto solto
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    lines = [clean_text(x) for x in soup.get_text("\n").splitlines() if clean_text(x)]
    for i in range(len(lines)):
        p = parse_text_match(" ".join(lines[i:i+4]), url, "texto_html")
        if p:
            out.append(p)

    return dedupe(out)


def parse_text_match(text: str, url: str, origem: str) -> Partido | None:
    if not parse_date(text) or not VS_RE.search(text):
        return None
    data = parse_date(text)
    hora = parse_time(text)
    parts = VS_RE.split(text, maxsplit=1)
    before = DATE_RE.sub("", parts[0])
    before = TIME_RE.sub("", before)
    mandante = " ".join(clean_text(before).split()[-5:])
    visitante = " ".join(clean_text(parts[1]).split()[:5])
    if not mandante or not visitante:
        return None
    return Partido("FMF", infer_competicao(text), data, hora, mandante, visitante, "", "", url, f"pais=Brasil; origem={origem}")


def load_cached_endpoints() -> list[str]:
    if not ENDPOINTS_PATH.exists():
        return []
    try:
        data = json.loads(ENDPOINTS_PATH.read_text(encoding="utf-8"))
        return [x["url"] if isinstance(x, dict) else str(x) for x in data]
    except Exception:
        return []


def save_cached_endpoints(urls: list[str]) -> None:
    seen = set()
    rows = []
    for u in urls:
        if not u or u in seen:
            continue
        seen.add(u)
        rows.append({"url": u, "updated_at": datetime.now().isoformat(timespec="seconds")})
    ENDPOINTS_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def try_cached_endpoints() -> tuple[list[Partido], list[dict]]:
    partidos = []
    debug = []
    for url in load_cached_endpoints():
        try:
            r = requests.get(url, headers=HEADERS, timeout=45)
            item = {"url": url, "status": r.status_code, "content_type": r.headers.get("content-type", "")}
            if "json" in item["content_type"].lower():
                found = walk_json(r.json(), url)
                partidos.extend(found)
                item["matches"] = len(found)
            debug.append(item)
        except Exception as e:
            debug.append({"url": url, "error": str(e)})
    return partidos, debug


async def collect_with_playwright(wait_ms: int) -> tuple[list[Partido], list[dict], list[str]]:
    if async_playwright is None:
        return [], [{"error": "playwright não instalado"}], []

    partidos = []
    debug = []
    endpoints = []
    seen = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=HEADERS["User-Agent"], locale="pt-BR")

        async def on_response(response):
            url = response.url
            if url in seen:
                return
            seen.add(url)
            low = url.lower()
            if "fmf.com.br" not in low:
                return
            ct = response.headers.get("content-type", "")
            interesting = "json" in ct.lower() or any(x in low for x in ["api", "handler", "ashx", "service", "competicoes", "jogos", "proxjogos", "tabela"])
            if not interesting:
                return
            item = {"url": url, "status": response.status, "content_type": ct}
            try:
                data = await response.json()
                found = walk_json(data, url)
                item["json"] = True
                item["matches"] = len(found)
                if found:
                    partidos.extend(found)
                    endpoints.append(url)
            except Exception:
                item["json"] = False
            debug.append(item)

        page.on("response", on_response)

        for url in START_URLS:
            try:
                print(f"[INFO] Abrindo FMF: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(wait_ms)
                for selector in ["select", "button", "a[href*='Competicoes']", "a[href*='ProxJogos']", ".dropdown-toggle"]:
                    try:
                        locs = page.locator(selector)
                        for i in range(min(await locs.count(), 6)):
                            try:
                                await locs.nth(i).click(timeout=1200)
                                await page.wait_for_timeout(700)
                            except Exception:
                                pass
                    except Exception:
                        pass
            except Exception as e:
                debug.append({"url": url, "error": str(e)})
        await browser.close()

    return partidos, debug, endpoints


def dedupe(rows: list[Partido]) -> list[Partido]:
    seen = set()
    out = []
    for p in rows:
        if p.id in seen:
            continue
        seen.add(p.id)
        out.append(p)
    return out


def in_window(p: Partido, desde: date, ate: date, incluir_passados: bool) -> bool:
    try:
        dt = date.fromisoformat(p.data)
    except Exception:
        return False
    return incluir_passados or (desde <= dt <= ate)


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
    raw = "|".join([row.get("fonte",""), row.get("competicao",""), row.get("data",""), row.get("hora",""), row.get("mandante",""), row.get("visitante",""), row.get("estadio",""), row.get("rodada","")])
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
    return sorted(by_id.values(), key=lambda r: (r.get("data",""), r.get("hora",""), r.get("competicao",""), r.get("mandante","")))


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


async def async_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dias", type=int, default=180)
    parser.add_argument("--dias-atras", type=int, default=30)
    parser.add_argument("--incluir-passados", action="store_true")
    parser.add_argument("--wait-ms", type=int, default=7000)
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    partidos, debug = try_cached_endpoints()

    for url in START_URLS:
        try:
            found = parse_html(fetch(url), url)
            print(f"[OK] FMF HTML {url} -> {len(found)} jogos")
            partidos.extend(found)
        except Exception as e:
            debug.append({"url": url, "error": f"html_fetch: {e}"})

    if len(partidos) < 3:
        pw_partidos, pw_debug, endpoints = await collect_with_playwright(args.wait_ms)
        partidos.extend(pw_partidos)
        debug.extend(pw_debug)
        if endpoints:
            save_cached_endpoints(endpoints)

    partidos = dedupe([p for p in partidos if in_window(p, desde, ate, args.incluir_passados)])

    (OUT_DIR / "debug_fmf_api_urls.json").write_text(json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "debug_fmf_matches_raw.json").write_text(json.dumps([p.to_row() for p in partidos], ensure_ascii=False, indent=2), encoding="utf-8")

    rows_new = [p.to_row() for p in partidos]
    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    merged_current = merge_rows(load_json_rows(current_json), rows_new)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    merged_history = merge_rows(load_csv_rows(history_csv), rows_new)
    write_csv(history_csv, merged_history)

    print(f"\nFMF adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
