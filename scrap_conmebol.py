#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CONMEBOL - Scraper diagnóstico (Libertadores + Sudamericana)

Páginas:
    https://gol.conmebol.com/libertadores/es
    https://gol.conmebol.com/sudamericana/es

Essas páginas (Drupal 11) trazem, já na home, um widget "carrossel" de
jogos (2026) totalmente renderizado no servidor: data, hora (com UTC),
estádio e placar aparecem em texto puro no HTML, sem precisar de
JavaScript. A página dedicada "/tournament/{id}" (Calendario y
Resultados) já é client-side (carrega via API própria) — por isso
usamos a home, que já basta.

Esta é a VERSÃO DIAGNÓSTICA: salva o HTML bruto e uma amostra de cards
de partida para escrever o parser de verdade com base na estrutura CSS
real (mesmo método já usado com sucesso para FFERJ neste projeto).

Uso:
    python scrap_conmebol.py --debug-html
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)
HTML_DIR = OUT_DIR / "debug_conmebol_html"

URLS = [
    ("CONMEBOL Libertadores", "https://gol.conmebol.com/libertadores/es"),
    ("CONMEBOL Sudamericana", "https://gol.conmebol.com/sudamericana/es"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "es-PY,es;q=0.9,pt;q=0.8,en;q=0.7",
}


def slugify(txt: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", txt.lower()).strip("_")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug-html", action="store_true")
    args = parser.parse_args()

    debug_info = []

    for label, url in URLS:
        slug = slugify(label)
        info = {"label": label, "url": url, "status": None, "erro": ""}
        try:
            r = requests.get(url, headers=HEADERS, timeout=45)
            info["status"] = r.status_code
            html = r.text
            info["bytes"] = len(html.encode("utf-8"))

            if args.debug_html:
                HTML_DIR.mkdir(exist_ok=True)
                (HTML_DIR / f"conmebol_{slug}.html").write_text(html, encoding="utf-8")

            soup = BeautifulSoup(html, "html.parser")

            # Encontra os links de partida "/fixture/view/NUMERO" e salva o
            # outerHTML de alguns exemplos pra entender a estrutura real.
            fixture_links = [
                a for a in soup.find_all("a", href=True)
                if re.search(r"/fixture/view/\d+", a["href"])
            ]
            info["n_fixture_links"] = len(fixture_links)

            amostras = []
            vistos = set()
            for a in fixture_links:
                href = a["href"]
                if href in vistos:
                    continue
                vistos.add(href)
                # sobe até um ancestral razoável (provavel container do card)
                container = a
                for _ in range(4):
                    if container.parent:
                        container = container.parent
                    else:
                        break
                amostras.append(str(container)[:3000])
                if len(amostras) >= 3:
                    break

            (OUT_DIR / f"debug_conmebol_{slug}_amostras.json").write_text(
                json.dumps(amostras, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        except Exception as e:
            info["erro"] = str(e)

        debug_info.append(info)
        print(f"[INFO] {label}: {info}")

    (OUT_DIR / "debug_conmebol_pages.json").write_text(
        json.dumps(debug_info, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
