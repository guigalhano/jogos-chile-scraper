#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Baixa o PDF oficial da acta de programacao da LigaPro e extrai o
texto, pra ver se os nomes dos times vem como texto de verdade ou como
imagem (como aconteceu com a DIMAYOR)."""
import json
from pathlib import Path

import requests
from pypdf import PdfReader

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

PDF_URL = "https://ligapro.ec/wp-content/uploads/2026/07/SERIE-A-FECHA-18-FASE-INICIAL-LIGA-ECUABET-2026.pdf"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
}

info = {"pdf_url": PDF_URL}

try:
    r = requests.get(PDF_URL, headers=HEADERS, timeout=45)
    r.raise_for_status()
    info["status"] = r.status_code
    info["bytes"] = len(r.content)

    local_path = Path("/tmp/acta.pdf")
    local_path.write_bytes(r.content)

    reader = PdfReader(str(local_path))
    info["n_paginas"] = len(reader.pages)
    textos = []
    for i, page in enumerate(reader.pages):
        txt = page.extract_text() or ""
        textos.append(txt)
    info["texto_por_pagina"] = textos
    info["texto_total_chars"] = sum(len(t) for t in textos)

except Exception as e:
    info["erro"] = str(e)

(OUT_DIR / "debug_ligapro_pdf_texto.json").write_text(
    json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps({k: v for k, v in info.items() if k != "texto_por_pagina"}, ensure_ascii=False, indent=2))
if info.get("texto_por_pagina"):
    print("\n--- Pagina 1 (primeiros 2000 chars) ---")
    print(info["texto_por_pagina"][0][:2000])
