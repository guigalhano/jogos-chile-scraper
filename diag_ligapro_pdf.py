#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostico rapido: acha a URL real do PDF por tras do visualizador
"Loading Viewer..." nas paginas de "acta de programacion" da LigaPro."""
import json
import re
from pathlib import Path

import requests

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

URL = "https://ligapro.ec/acta-de-programacion-fecha-18-fase-inicial-de-la-liga-ecuabet/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
}

r = requests.get(URL, headers=HEADERS, timeout=45)
html = r.text

info = {"status": r.status_code, "bytes": len(html.encode("utf-8"))}

# procura padroes comuns de embed de PDF (iframe viewer.html?file=..., <embed src=...pdf>, links diretos .pdf)
padroes = [
    r'viewer\.html\?file=([^"\'&]+\.pdf[^"\'&]*)',
    r'href="([^"]+\.pdf)"',
    r'src="([^"]+\.pdf)"',
    r'data-src="([^"]+\.pdf)"',
    r'data-pdf[a-z-]*="([^"]+)"',
    r'"file"\s*:\s*"([^"]+)"',
    r'wp-content/uploads/[^"\'\s]+\.pdf',
]
achados = set()
for p in padroes:
    for m in re.finditer(p, html, re.I):
        achados.add(m.group(1) if m.groups() else m.group(0))

info["pdf_urls_encontradas"] = sorted(achados)

# recorte em torno de qualquer ocorrencia de "pdfp" (plugin PDF Poster) pra
# entender como ele referencia o arquivo (id de midia, endpoint ajax, etc.)
idx_pdfp = html.find("pdfp_wrapper")
if idx_pdfp != -1:
    idx_pdfp2 = html.find("pdfp_wrapper", idx_pdfp + 200)
    trecho_ini = max(0, idx_pdfp2 - 200) if idx_pdfp2 != -1 else idx_pdfp
    info["snippet_pdfp"] = html[trecho_ini:trecho_ini + 3000]

# tambem salva um recorte perto de "viewer" ou ".pdf" pra inspecionar manualmente
idx = html.lower().find("viewer.html")
if idx == -1:
    idx = html.lower().find(".pdf")
if idx != -1:
    info["snippet"] = html[max(0, idx - 800):idx + 800]

(OUT_DIR / "debug_ligapro_pdf_diag.json").write_text(
    json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(info, ensure_ascii=False, indent=2)[:3000])
