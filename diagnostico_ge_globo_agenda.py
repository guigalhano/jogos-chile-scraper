#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnóstico: https://ge.globo.com/agenda/#/futebol

Objetivo: descobrir se dá pra fazer scraping do calendário de futebol
dessa página, e como. Passos:

1. Baixa e salva o robots.txt de ge.globo.com (e globo.com, por garantia)
   pra checar se a seção /agenda/ está bloqueada pra bots.
2. Abre a página com Playwright (o "#/" na URL indica rota client-side -
   o conteúdo é montado via JS, não vem pronto no HTML), espera carregar
   e captura TODAS as respostas de rede (principalmente JSON) que a
   página dispara, pra achar a API por trás do calendário.
3. Salva o HTML renderizado final e o texto visível da página.
4. Salva um resumo com as URLs de rede mais promissoras (JSON, contendo
   palavras como "agenda", "jogo", "partida", "match", "event").

Não grava nada em jogos_programados.json - é só investigação.

Uso:
    python diagnostico_ge_globo_agenda.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

OUT_DIR = Path("data/diagnostico_ge_globo")
OUT_DIR.mkdir(parents=True, exist_ok=True)

URL_AGENDA = "https://ge.globo.com/agenda/#/futebol"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
}

PALAVRAS_INTERESSANTES = [
    "agenda", "jogo", "partida", "match", "event", "calend",
    "futebol", "schedule", "fixture",
]


def checar_robots() -> dict:
    resultado = {}
    for dominio in ["https://ge.globo.com", "https://globo.com", "https://www.globo.com"]:
        url = f"{dominio}/robots.txt"
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            resultado[url] = {"status": r.status_code, "texto": r.text[:5000]}
        except Exception as e:
            resultado[url] = {"erro": str(e)}
    return resultado


def main() -> None:
    print("=== 1. Checando robots.txt ===")
    robots = checar_robots()
    (OUT_DIR / "robots.json").write_text(json.dumps(robots, ensure_ascii=False, indent=2), encoding="utf-8")
    for url, info in robots.items():
        print(f"{url}: status={info.get('status')} erro={info.get('erro')}")
        if info.get("texto"):
            print(info["texto"][:2000])
        print("---")

    print("\n=== 2. Abrindo pagina com Playwright e capturando rede ===")
    network_hits = []
    network_all_urls = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="pt-BR",
        )
        page = context.new_page()

        def on_response(response):
            rurl = response.url
            network_all_urls.append(rurl)
            ct = response.headers.get("content-type", "")
            if "json" not in ct.lower():
                return
            lower = rurl.lower()
            if not any(p in lower for p in PALAVRAS_INTERESSANTES):
                return
            row = {"url": rurl, "status": response.status, "content_type": ct}
            try:
                txt = response.text()
                row["sample"] = txt[:3000]
                try:
                    payload = json.loads(txt)
                    row["json_top_level_keys"] = (
                        list(payload.keys()) if isinstance(payload, dict)
                        else f"list de {len(payload)} itens" if isinstance(payload, list)
                        else str(type(payload))
                    )
                except Exception:
                    pass
            except Exception as e:
                row["read_error"] = str(e)
            network_hits.append(row)
            print(f"[JSON interessante] {rurl}  ({len(row.get('sample', ''))} bytes de amostra)")

        page.on("response", on_response)

        erro = ""
        try:
            page.goto(URL_AGENDA, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(6000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            # a pagina usa hash routing - da um tempo extra pro JS montar o conteudo
            page.wait_for_timeout(4000)
        except Exception as e:
            erro = str(e)
            print(f"[ERRO ao carregar pagina] {e}")

        html = ""
        texto_visivel = ""
        try:
            html = page.content()
            texto_visivel = page.inner_text("body")
        except Exception as e:
            print(f"[ERRO ao capturar conteudo] {e}")

        browser.close()

    (OUT_DIR / "pagina_renderizada.html").write_text(html, encoding="utf-8")
    (OUT_DIR / "pagina_texto_visivel.txt").write_text(texto_visivel, encoding="utf-8")
    (OUT_DIR / "rede_hits_interessantes.json").write_text(
        json.dumps(network_hits, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "rede_todas_urls.txt").write_text("\n".join(network_all_urls), encoding="utf-8")

    resumo = {
        "erro_carregamento": erro,
        "total_requests_rede": len(network_all_urls),
        "total_json_interessante": len(network_hits),
        "urls_json_interessante": [h["url"] for h in network_hits],
        "tamanho_html_final": len(html),
        "tamanho_texto_visivel": len(texto_visivel),
        "primeiras_linhas_texto_visivel": texto_visivel.splitlines()[:40],
    }
    (OUT_DIR / "_resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== RESUMO ===")
    print(json.dumps(resumo, ensure_ascii=False, indent=2)[:3000])


if __name__ == "__main__":
    main()
