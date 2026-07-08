#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Liga 1 Peru - Scraper diagnóstico (Fixture)

Página:
    https://liga1.pe/fixture/

Site WordPress (gerador "WordPress 7.0") cujo conteúdo de fixture é
carregado via JavaScript (a página estática só mostra um loader/spinner
e "Fecha 01" como placeholder). Prováveis fontes de dados: REST API do
WordPress (/wp-json/...) ou uma chamada AJAX (admin-ajax.php) para um
plugin de fixture/calendário.

Esta é a VERSÃO DIAGNÓSTICA: abre a página com Playwright, intercepta
todas as respostas de rede que parecem JSON e salva tudo em arquivos de
debug para depois escrever o parser de verdade com base em dados reais
(mesmo método já usado com sucesso para FFERJ, AUF e APF neste
projeto).

Uso:
    python scrap_liga1_peru.py --debug-html --wait-ms 15000
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)
HTML_DIR = OUT_DIR / "debug_liga1_html"

URL = "https://liga1.pe/fixture/"

HEADERS_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
)


def collect(url: str, wait_ms: int, debug_html: bool) -> tuple[list[dict], list[dict]]:
    json_payloads: list[dict] = []
    all_responses: list[dict] = []
    seen = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=HEADERS_UA, locale="es-PE")
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
                ".css", ".ico", ".webp", ".js",
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

        print(f"[INFO] Abrindo Liga 1: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(wait_ms)

        # Os filtros são <select> nativos escondidos, com uma UI fake por
        # cima: clicar em ".select-selected" abre ".select-items", cujos
        # filhos "[data-id]" são os que de fato disparam a troca (o site
        # escuta clique nesses divs, não o evento "change" do <select>).
        # Seleciona especificamente Ano=2026 e Fase=Clausura (torneio em
        # andamento em julho/2026) e por fim uma Fecha, nessa ordem, pra
        # garantir que a chamada de listagem final já saia com os filtros
        # certos.
        seletores_alvo = [
            ("anioList", "3"),      # 2026
            ("aperturtaList", "2"),  # Liga 1 Clausura
            ("fechaList", "1"),     # FECHA 01
        ]
        for select_id, data_id in seletores_alvo:
            try:
                cs = page.locator(f".custom-select:has(#{select_id})")
                if cs.count() == 0:
                    continue
                cs.first.locator(".select-selected").click(timeout=1500)
                page.wait_for_timeout(600)
                opcao = cs.first.locator(f".select-items [data-id='{data_id}']")
                if opcao.count() > 0:
                    opcao.first.click(timeout=1500)
                    page.wait_for_timeout(2500)
            except Exception as e:
                print(f"[WARN] Falha ao selecionar {select_id}={data_id}: {e}")

        page.wait_for_timeout(3000)

        if debug_html:
            HTML_DIR.mkdir(exist_ok=True)
            (HTML_DIR / "liga1_fixture.html").write_text(page.content(), encoding="utf-8")
            try:
                text = page.evaluate("() => document.body ? document.body.innerText : ''")
                (HTML_DIR / "liga1_fixture_texto.txt").write_text(text, encoding="utf-8")
            except Exception:
                pass

        # Extrai também dados embutidos no HTML (WordPress costuma
        # exportar configs/dados via wp_localize_script em variáveis
        # window.XXX = {...}; ou blocos <script type="application/json">).
        html_full = page.content()
        embedded = []
        for m in re.finditer(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', html_full, re.S):
            embedded.append(m.group(1)[:100000])
        for m in re.finditer(r'var\s+(\w+)\s*=\s*(\{.*?\});', html_full):
            if len(m.group(2)) > 200:
                embedded.append(f"{m.group(1)} = {m.group(2)[:100000]}")
        if embedded:
            (OUT_DIR / "debug_liga1_embedded.json").write_text(
                json.dumps(embedded, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"[INFO] {len(embedded)} blocos de dados embutidos no HTML encontrados")

        idx = html_full.find("Fecha 01")
        if idx == -1:
            idx = html_full.lower().find("fixture")
        if idx != -1:
            (OUT_DIR / "debug_liga1_widget_html.json").write_text(
                json.dumps({"snippet": html_full[max(0, idx - 5000):idx + 3000]}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print("[INFO] Trecho do HTML do widget salvo para depuracao")

        browser.close()

    return json_payloads, all_responses


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-ms", type=int, default=12000)
    parser.add_argument("--debug-html", action="store_true")
    args = parser.parse_args()

    payloads, responses = collect(URL, wait_ms=args.wait_ms, debug_html=args.debug_html)

    (OUT_DIR / "debug_liga1_responses.json").write_text(
        json.dumps(responses, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "debug_liga1_json_payloads.json").write_text(
        json.dumps(payloads, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n[INFO] Respostas relevantes: {len(responses)}")
    print(f"[INFO] Payloads JSON: {len(payloads)}")
    for p in payloads:
        print(f"  - {p['url']} (status {p['status']})")


if __name__ == "__main__":
    main()
