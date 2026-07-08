#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APF Paraguai - Scraper diagnóstico (Copa de Primera + División Intermedia)

Páginas:
    https://www.apf.org.py/copa-de-primera
    https://www.apf.org.py/intermedia

O site é um SPA (Next.js) com um "match center" no estilo Opta/Stats
Perform (estatísticas avançadíssimas por jogo, alinhações, eventos minuto
a minuto). Isso é forte indício de que os dados de jogos (incluindo
data/hora agendada) vêm de uma API JSON separada, carregada via
JavaScript, e não do HTML estático — mesmo padrão já visto em
FMF/FPF/AUF neste projeto.

Esta é a VERSÃO DIAGNÓSTICA: em vez de tentar adivinhar o parser,
ela abre as páginas com Playwright, intercepta TODAS as respostas de
rede que parecem JSON e salva tudo em arquivos de debug, além de
capturar o texto renderizado da página. Depois de rodar isso uma vez
via GitHub Actions (rede liberada) e inspecionar os arquivos gerados,
o parser de verdade é escrito com base em dados reais.

Uso (diagnóstico):
    python scrap_apf_paraguay.py --debug-html --wait-ms 15000
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)
HTML_DIR = OUT_DIR / "debug_apf_html"

START_URLS = [
    ("Paraguay - Copa de Primera", "https://www.apf.org.py/copa-de-primera"),
    ("Paraguay - Division Intermedia", "https://www.apf.org.py/intermedia"),
]

HEADERS_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
)


def slugify(txt: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", txt.lower()).strip("_")


def collect(start_urls: list[tuple[str, str]], wait_ms: int, debug_html: bool) -> tuple[list[dict], list[dict]]:
    json_payloads: list[dict] = []
    all_responses: list[dict] = []
    seen_urls = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=HEADERS_UA, locale="es-PY")
        page = context.new_page()

        def on_response(response):
            url = response.url
            key = (url, response.status)
            if key in seen_urls:
                return
            seen_urls.add(key)

            ct = ""
            try:
                ct = response.headers.get("content-type", "")
            except Exception:
                pass

            row = {"url": url, "status": response.status, "content_type": ct}

            is_json_ct = "json" in ct.lower()
            # Ignora recursos obviamente estáticos (imagens, fontes, css, js
            # de terceiros como GTM/Google) para não poluir o dump.
            low = url.lower()
            is_static = any(low.endswith(ext) for ext in [
                ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2",
                ".css", ".ico", ".webp",
            ])
            is_thirdparty = any(x in low for x in [
                "googletagmanager", "google-analytics", "doubleclick",
                "facebook.net", "gstatic.com",
            ])

            if is_json_ct and not is_thirdparty:
                try:
                    data = response.json()
                    row["json"] = True
                    json_payloads.append({"url": url, "status": response.status, "data": data})
                except Exception as e:
                    row["json"] = False
                    row["json_error"] = str(e)
            else:
                row["json"] = False

            if not is_static or is_json_ct:
                all_responses.append(row)

        page.on("response", on_response)

        for competicao, url in start_urls:
            try:
                print(f"[INFO] Abrindo APF: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(wait_ms)

                # Tenta rolar a página para acionar lazy-loading de mais
                # rodadas/conteúdo dinâmico.
                try:
                    for _ in range(4):
                        page.mouse.wheel(0, 1800)
                        page.wait_for_timeout(600)
                except Exception:
                    pass

                if debug_html:
                    HTML_DIR.mkdir(exist_ok=True)
                    html = page.content()
                    slug = slugify(competicao)
                    (HTML_DIR / f"apf_{slug}.html").write_text(html, encoding="utf-8")
                    try:
                        text = page.evaluate("() => document.body ? document.body.innerText : ''")
                        (HTML_DIR / f"apf_{slug}_texto.txt").write_text(text, encoding="utf-8")
                    except Exception:
                        pass

                # Clica em elementos que pareçam abrir fixture/calendário/
                # próxima jornada, para tentar acionar mais chamadas de API.
                for selector in ["a", "button"]:
                    try:
                        locs = page.locator(selector)
                        count = min(locs.count(), 25)
                        for i in range(count):
                            try:
                                txt = (locs.nth(i).inner_text(timeout=300) or "").strip().lower()
                                if any(k in txt for k in ["fixture", "calendario", "próxima", "proxima", "jornada", "partidos"]):
                                    locs.nth(i).click(timeout=1000)
                                    page.wait_for_timeout(1000)
                            except Exception:
                                pass
                    except Exception:
                        pass

            except Exception as e:
                print(f"[WARN] Erro abrindo {url}: {e}")

        # Também visita uma página de detalhe de partida para ver a API do
        # "match center" (é onde data/hora/estádio provavelmente aparecem
        # de forma estruturada).
        detail_url = "https://www.apf.org.py/partidos/temporada-2026-paraguay-primera-division-apertura-22-2-de-mayo-vs-san-lorenzo-813"
        try:
            print(f"[INFO] Abrindo página de detalhe: {detail_url}")
            page.goto(detail_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(wait_ms)
            if debug_html:
                HTML_DIR.mkdir(exist_ok=True)
                (HTML_DIR / "apf_detalhe_partida.html").write_text(page.content(), encoding="utf-8")
        except Exception as e:
            print(f"[WARN] Erro abrindo página de detalhe: {e}")

        browser.close()

    return json_payloads, all_responses


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-ms", type=int, default=12000)
    parser.add_argument("--debug-html", action="store_true")
    args = parser.parse_args()

    payloads, responses = collect(START_URLS, wait_ms=args.wait_ms, debug_html=args.debug_html)

    (OUT_DIR / "debug_apf_responses.json").write_text(
        json.dumps(responses, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "debug_apf_json_payloads.json").write_text(
        json.dumps(payloads, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n[INFO] Respostas de rede relevantes capturadas: {len(responses)}")
    print(f"[INFO] Payloads JSON capturados: {len(payloads)}")
    for p in payloads:
        print(f"  - {p['url']} (status {p['status']})")


if __name__ == "__main__":
    main()
