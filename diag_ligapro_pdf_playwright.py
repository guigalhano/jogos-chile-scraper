#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostico Playwright: acha a URL real do PDF por tras do
visualizador "Loading Viewer..." nas paginas de "acta de programacion"
da LigaPro, interceptando requisicoes de rede e inspecionando o DOM
final apos o JS rodar."""
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

URL = "https://ligapro.ec/acta-de-programacion-fecha-18-fase-inicial-de-la-liga-ecuabet/"

HEADERS_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
)

info = {"pdf_requests": [], "erro": ""}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(user_agent=HEADERS_UA, locale="es-EC")
    page = context.new_page()

    def on_request(request):
        if ".pdf" in request.url.lower():
            info["pdf_requests"].append(request.url)

    page.on("request", on_request)

    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)

        html = page.content()
        m_div = re.search(r'<div[^>]*class="[^"]*pdfp_wrapper[^"]*"[^>]*>.*?</div>\s*</div>\s*</div>', html, re.S)
        if m_div:
            info["dom_pdfp_snippet"] = m_div.group(0)[:4000]
        else:
            idx = html.find("pdfp_wrapper")
            info["dom_pdfp_snippet"] = html[max(0, idx - 200):idx + 3000] if idx != -1 else "nao encontrado no DOM final"

        # procura tambem qualquer atributo com .pdf no DOM renderizado
        achados = set(re.findall(r'["\']([^"\']+\.pdf[^"\']*)["\']', html))
        info["pdf_urls_no_dom"] = sorted(achados)

    except Exception as e:
        info["erro"] = str(e)

    browser.close()

(OUT_DIR / "debug_ligapro_pdf_playwright.json").write_text(
    json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps({k: v for k, v in info.items() if k != "dom_pdfp_snippet"}, ensure_ascii=False, indent=2))
