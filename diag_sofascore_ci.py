#!/usr/bin/env python3
"""Diagnostico: quais formas de acessar a API do SofaScore passam a partir do
GitHub Actions (o Chromium/Playwright leva 403 la). So imprime status."""
from __future__ import annotations

URLS = [
    "https://www.sofascore.com/api/v1/unique-tournament/155/seasons",
    "https://api.sofascore.com/api/v1/unique-tournament/155/seasons",
    "https://api.sofascore.app/api/v1/unique-tournament/155/seasons",
]


def tentar(nome, fn):
    for u in URLS:
        try:
            r = fn(u)
            print(f"{nome:28s} {r.status_code}  {u}  {r.text[:80]!r}")
        except Exception as e:  # noqa: BLE001
            print(f"{nome:28s} ERRO {type(e).__name__}: {e}  {u}")


import requests
tentar("requests", lambda u: requests.get(u, timeout=20, headers={"User-Agent": "Mozilla/5.0"}))
tentar("requests app-UA", lambda u: requests.get(u, timeout=20, headers={"User-Agent": "SofaScore/6.0 (Android)"}))

from curl_cffi import requests as cr
for imp in ("chrome", "safari", "safari_ios", "chrome_android"):
    tentar(f"curl_cffi {imp}", lambda u, imp=imp: cr.get(u, impersonate=imp, timeout=20))
