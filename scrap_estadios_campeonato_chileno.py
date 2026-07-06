#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extrai nomes de estádios do campeonatochileno.cl e cruza com uma base manual
de coordenadas.

O site publica nomes e páginas de estádio, mas normalmente não traz latitude/longitude
no HTML público. Por isso:
1) O script extrai nomes/URLs de estádios.
2) Cruza com a base manual abaixo.
3) Gera:
   - data/estadios_extraidos.csv
   - data/estadios_com_coordenadas.csv
   - data/estadios_pendentes.csv
   - estadios.js

Uso:
    pip install requests beautifulsoup4 lxml
    python scrap_estadios_campeonato_chileno.py
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE = "https://www.campeonatochileno.cl/"
OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; estadios-chile-scraper/1.0)",
    "Accept-Language": "es-CL,es;q=0.9,pt-BR;q=0.8,en;q=0.6",
}

# Cole aqui a lista window.ESTADIOS_CHILE do estadios.js, se quiser manter uma só base.
# Para simplificar, o script tenta carregar estadios.js primeiro.
STADIUM_PAGE_RE = re.compile(r"/estadio/([^/]+)/?", re.I)
POSSIBLE_STADIUM_RE = re.compile(
    r"\b(Estadio|Municipal|Bicentenario|Sausalito|Claro Arena|El Cobre|La Portada|El Teniente|Monumental|Ester Roa|Huachipato|Nicolás Chahuán|Nicolas Chahuan|Lucio Fariña|Lucio Farina|Nelson Oyarzún|Nelson Oyarzun)\b",
    re.I,
)


LIGA_URLS = [
    "https://www.campeonatochileno.cl/ligas/liga-de-primera-mercado-libre/",
    "https://www.campeonatochileno.cl/ligas/liga-de-ascenso-caixun/",
    "https://www.campeonatochileno.cl/ligas/segunda-la-liga-2d/",
    "https://www.campeonatochileno.cl/ligas/copa-chile-coca-cola-zero-azucar/",
    "https://www.campeonatochileno.cl/ligas/copa-de-la-liga/",
    "https://www.campeonatochileno.cl/ligas/campeonato-femenino/",
    "https://www.campeonatochileno.cl/ligas/ascenso-femenino/",
]


def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=35)
    r.raise_for_status()
    return r.text


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def norm(value: str) -> str:
    import unicodedata
    value = unicodedata.normalize("NFD", value or "")
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    value = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return value


def title_from_slug(slug: str) -> str:
    return slug.replace("-", " ").title()


def discover_stadium_pages() -> dict[str, dict]:
    found: dict[str, dict] = {}

    urls = set(LIGA_URLS + [BASE])
    # Tenta descobrir mais ligas pela home.
    try:
        soup = BeautifulSoup(fetch(BASE), "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(BASE, a["href"]).split("?")[0]
            if "/ligas/" in href:
                urls.add(href)
    except Exception:
        pass

    for url in sorted(urls):
        try:
            html = fetch(url)
        except Exception as e:
            print(f"[ERRO] {url}: {e}")
            continue

        soup = BeautifulSoup(html, "html.parser")

        # Links /estadio/<slug>/
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"]).split("?")[0]
            m = STADIUM_PAGE_RE.search(href)
            if not m:
                continue
            name = clean_text(a.get_text(" ", strip=True)) or title_from_slug(m.group(1))
            key = norm(name or m.group(1))
            found[key] = {
                "nome_extraido": name,
                "url": href,
                "origem": url,
            }

        # Textos soltos que parecem estádios dentro dos fixtures
        for line in soup.get_text("\n").splitlines():
            line = clean_text(line)
            if not line or len(line) > 80:
                continue
            if POSSIBLE_STADIUM_RE.search(line):
                key = norm(line)
                found.setdefault(key, {
                    "nome_extraido": line,
                    "url": "",
                    "origem": url,
                })

    return found


def load_manual_from_estadios_js(path: Path = Path("estadios.js")) -> list[dict]:
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    m = re.search(r"window\.ESTADIOS_CHILE\s*=\s*(\[.*?\]);", text, re.S)
    if not m:
        return []

    # Converte JS-ish para JSON-ish. Funciona porque o arquivo gerado usa chaves sem aspas,
    # então aplicamos substituições leves. Se falhar, use a lista manual Python abaixo.
    js = m.group(1)
    try:
        # Não é JSON puro, então usamos eval seguro com contexto vazio após trocar null.
        return eval(js, {"__builtins__": {}}, {})
    except Exception:
        return []


def match_manual(name: str, manual: list[dict]) -> dict | None:
    n = norm(name)
    for item in manual:
        names = [item.get("nome", "")] + item.get("aliases", [])
        for candidate in names:
            cn = norm(candidate)
            if not cn:
                continue
            if n == cn or n in cn or cn in n:
                return item
    return None


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = ["nome_extraido", "nome", "cidade", "regiao", "lat", "lng", "url", "origem", "status"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def build_estadios_js(manual: list[dict]) -> str:
    dumped = json.dumps(manual, ensure_ascii=False, indent=2)
    return "window.ESTADIOS_CHILE = " + dumped + ";\n"


def main() -> None:
    extracted = discover_stadium_pages()
    manual = load_manual_from_estadios_js()

    rows_all = []
    rows_ok = []
    rows_pending = []

    for item in sorted(extracted.values(), key=lambda x: x["nome_extraido"]):
        manual_match = match_manual(item["nome_extraido"], manual)
        row = {
            "nome_extraido": item["nome_extraido"],
            "url": item.get("url", ""),
            "origem": item.get("origem", ""),
        }
        if manual_match:
            row.update({
                "nome": manual_match.get("nome", ""),
                "cidade": manual_match.get("cidade", ""),
                "regiao": manual_match.get("regiao", ""),
                "lat": manual_match.get("lat", ""),
                "lng": manual_match.get("lng", ""),
                "status": "ok",
            })
            rows_ok.append(row)
        else:
            row.update({"status": "pendente"})
            rows_pending.append(row)

        rows_all.append(row)

    write_csv(OUT_DIR / "estadios_extraidos.csv", rows_all)
    write_csv(OUT_DIR / "estadios_com_coordenadas.csv", rows_ok)
    write_csv(OUT_DIR / "estadios_pendentes.csv", rows_pending)

    # Regrava estadios.js com a base manual carregada.
    if manual:
        Path("estadios.js").write_text(build_estadios_js(manual), encoding="utf-8")

    print(f"Extraídos: {len(rows_all)}")
    print(f"Com coordenadas: {len(rows_ok)}")
    print(f"Pendentes: {len(rows_pending)}")
    print("Arquivos gerados em data/")


if __name__ == "__main__":
    main()
