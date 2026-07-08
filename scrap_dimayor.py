#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DIMAYOR (Colômbia) - Scraper diagnóstico

Páginas:
    https://dimayor.com.co/liga-betplay-dimayor/
    https://dimayor.com.co/torneo-betplay-dimayor/
    https://dimayor.com.co/liga-femenina-betplay-dimayor/
    https://dimayor.com.co/copa-betplay-dimayor/

Essas páginas mostram um widget "Partidos / Posiciones / Filtros" com
"Cargando..." (carregamento via JS) — indício de API JSON própria.
Os PDFs de programação oficial (ex.: fixture completo por fecha) têm
estádio/data/hora em texto selecionável, mas os NOMES DOS TIMES vêm
como imagem/escudo (sem texto), então não dá pra extrair só do PDF.

Esta é a VERSÃO DIAGNÓSTICA: abre as páginas com Playwright, intercepta
respostas de rede que parecem JSON e salva tudo em arquivos de debug
pra escrever o parser de verdade depois.

Uso:
    python scrap_dimayor.py --debug-html --wait-ms 15000
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)
HTML_DIR = OUT_DIR / "debug_dimayor_html"

URLS = [
    ("Liga BetPlay", "https://dimayor.com.co/liga-betplay-dimayor/"),
]
# Nota: visitar as outras 3 paginas (Torneo/Feminina/Copa) na MESMA sessao
# de navegador disparou um bloqueio Cloudflare (403 + desafio Turnstile).
# Por ora, testamos uma pagina por vez, isoladamente.

HEADERS_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
)


def slugify(txt: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", txt.lower()).strip("_")


def collect(urls: list[tuple[str, str]], wait_ms: int, debug_html: bool):
    json_payloads: list[dict] = []
    all_responses: list[dict] = []
    seen = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=HEADERS_UA, locale="es-CO")
        page = context.new_page()

        def on_response(response):
            u = response.url
            key = (u, response.status)
            if key in seen:
                return
            seen.add(key)

            ct = ""
            try:
                ct = response.headers.get("content-type", "")
            except Exception:
                pass

            low = u.lower()
            is_static = any(low.split("?")[0].endswith(ext) for ext in [
                ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2",
                ".css", ".ico", ".webp", ".js", ".pdf",
            ])
            is_thirdparty = any(x in low for x in [
                "googletagmanager", "google-analytics", "doubleclick",
                "facebook.net", "gstatic.com", "hotjar", "clarity.ms",
            ])

            row = {"url": u, "status": response.status, "content_type": ct}
            is_json_ct = "json" in ct.lower()

            if is_json_ct and not is_thirdparty:
                try:
                    data = response.json()
                    row["json"] = True
                    json_payloads.append({"url": u, "status": response.status, "data": data})
                except Exception as e:
                    row["json"] = False
                    row["json_error"] = str(e)
            else:
                row["json"] = False

            if not is_static or is_json_ct:
                all_responses.append(row)

        page.on("response", on_response)

        for label, url in urls:
            try:
                print(f"[INFO] Abrindo DIMAYOR: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(wait_ms)

                # Tenta clicar na aba "Partidos" e no filtro "2026" pra
                # garantir que a chamada de dados correta é disparada.
                try:
                    locs = page.get_by_text("Partidos", exact=False)
                    if locs.count() > 0:
                        locs.first.click(timeout=1500)
                        page.wait_for_timeout(1500)
                except Exception:
                    pass

                # Rola a página pra forçar lazy-loading de mais jogos.
                try:
                    for _ in range(6):
                        page.mouse.wheel(0, 1600)
                        page.wait_for_timeout(500)
                except Exception:
                    pass

                if debug_html:
                    HTML_DIR.mkdir(exist_ok=True)
                    slug = slugify(label)
                    (HTML_DIR / f"dimayor_{slug}.html").write_text(page.content(), encoding="utf-8")

                # Salva um recorte do HTML renderizado com os cards de
                # partida (pra inspecionar a estrutura CSS real e escrever
                # o parser depois) e o texto puro renderizado.
                html_full = page.content()
                slug = slugify(label)
                idx = html_full.find("VIERNES") if "VIERNES" in html_full else html_full.upper().find("VIERNES")
                if idx == -1:
                    idx = html_full.lower().find("estadio")
                if idx != -1:
                    (Path("data") / f"debug_dimayor_{slug}_snippet.json").write_text(
                        json.dumps({"snippet": html_full[max(0, idx - 2000):idx + 20000]}, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    print(f"[INFO] Snippet de {label} salvo para depuracao")
                else:
                    print(f"[WARN] Nao achei marcador de jogos no HTML de {label} (bloqueio? pagina vazia?)")

            except Exception as e:
                print(f"[WARN] Erro abrindo {url}: {e}")

        browser.close()

    return json_payloads, all_responses


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-ms", type=int, default=12000)
    parser.add_argument("--debug-html", action="store_true")
    args = parser.parse_args()

    payloads, responses = collect(URLS, wait_ms=args.wait_ms, debug_html=args.debug_html)

    (OUT_DIR / "debug_dimayor_responses.json").write_text(
        json.dumps(responses, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "debug_dimayor_json_payloads.json").write_text(
        json.dumps(payloads, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n[INFO] Respostas relevantes: {len(responses)}")
    print(f"[INFO] Payloads JSON: {len(payloads)}")
    for p in payloads:
        print(f"  - {p['url']} (status {p['status']})")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        (OUT_DIR / "debug_dimayor_erro_fatal.json").write_text(
            json.dumps({"erro": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        raise
