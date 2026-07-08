#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Futebol Peruano - Scraper diagnóstico (futbolperuano.com)

Páginas:
    https://www.futbolperuano.com/liga-1/
    https://www.futbolperuano.com/liga-2/
    https://www.futbolperuano.com/liga-3/
    https://www.futbolperuano.com/copa-de-la-liga/
    https://www.futbolperuano.com/copa-peru/
    https://www.futbolperuano.com/futbol-femenino/resultados

Essas páginas trazem um widget de resultados/fixture (aparenta ser
"Score24", indicado no rodapé "Powered by Score24") já renderizado no
servidor, com data, hora e placar em texto puro.

Esta é a VERSÃO DIAGNÓSTICA: salva o HTML bruto e uma amostra da
estrutura de cada card de partida pra escrever o parser de verdade com
base na estrutura CSS real (mesmo método já usado com sucesso para
FFERJ e CONMEBOL neste projeto).

Uso:
    python scrap_futbolperuano.py --debug-html
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
HTML_DIR = OUT_DIR / "debug_futbolperuano_html"

URLS = [
    ("Peru - Liga 1", "https://www.futbolperuano.com/liga-1/"),
    ("Peru - Liga 2", "https://www.futbolperuano.com/liga-2/"),
    ("Peru - Liga 3", "https://www.futbolperuano.com/liga-3/"),
    ("Peru - Copa de la Liga", "https://www.futbolperuano.com/copa-de-la-liga/"),
    ("Peru - Copa Peru", "https://www.futbolperuano.com/copa-peru/"),
    ("Peru - Futbol Femenino", "https://www.futbolperuano.com/futbol-femenino/resultados"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "es-PE,es;q=0.9,pt;q=0.8,en;q=0.7",
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
                (HTML_DIR / f"fp_{slug}.html").write_text(html, encoding="utf-8")

            soup = BeautifulSoup(html, "html.parser")

            # Procura o bloco de resultados: geralmente tem "vs" nos links de
            # partida ou algum id/classe característica do widget Score24.
            candidatos = set()
            for tag in soup.find_all(True, id=True):
                if re.search(r"resultado|score24|fixture|partido", tag.get("id", ""), re.I):
                    candidatos.add(tag.get("id"))
            for tag in soup.find_all(True, class_=True):
                classes = " ".join(tag.get("class", []))
                if re.search(r"resultado|score24|fixture|partido|match", classes, re.I):
                    candidatos.add(classes)

            info["ids_classes_candidatos"] = sorted(candidatos)[:30]

            # Salva um trecho ao redor do texto "Fecha" (cabeçalho de rodada)
            # pra ver a estrutura completa de um bloco de partidas.
            idx = html.find(">Fecha ")
            if idx == -1:
                idx = html.lower().find("por jugar")
            if idx != -1:
                (OUT_DIR / f"debug_futbolperuano_{slug}_snippet.json").write_text(
                    json.dumps({"snippet": html[max(0, idx - 4000):idx + 4000]}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

        except Exception as e:
            info["erro"] = str(e)

        debug_info.append(info)
        print(f"[INFO] {label}: status={info.get('status')} bytes={info.get('bytes')} erro={info.get('erro')}")

    (OUT_DIR / "debug_futbolperuano_pages.json").write_text(
        json.dumps(debug_info, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
