#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper Uruguay (AUF - Asociación Uruguaya de Fútbol)

Cobre 3 competições, cada uma com sua própria página de calendário:
- Liga AUF Uruguaya (Primera División)
- Primera Divisional C
- Calendario de Primera División (página de calendário geral)

IMPORTANTE: este é um scraper de PRIMEIRA PASSAGEM. As páginas específicas
de cada competição retornaram 404 para fetch direto simples (mesmo estando
indexadas e linkadas na home do site), o que sugere alguma dependência de
sessão/cookies/JS. Por isso o scraper usa Playwright (navegador real) em vez
de requests puro, e grava HTML/linhas de debug completos para permitir
ajustar o parser com base em dados reais, em vez de estrutura assumida às
cegas — mesmo padrão usado para FMF/FPF neste projeto.

Uso:
    python scrap_uruguai_auf.py --dias 180 --dias-atras 30 --debug-html
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)
DEBUG_DIR = OUT_DIR / "debug_uruguai_html"

URLS = [
    ("Uruguai - Liga AUF Uruguaya", "https://www.auf.org.uy/liga-auf-uruguaya/"),
    ("Uruguai - Primera Divisional C", "https://www.auf.org.uy/primera-divisional-c/"),
    ("Uruguai - Calendario Primera División", "https://www.auf.org.uy/calendario-de-primera-division/"),
]

FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em", "pais", "cidade",
]

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# "09/03/2026 - 18:30 h" ou "09/03/2026 18:30 h" ou "09/03/2026 - 18:30hs"
DATA_HORA_RE = re.compile(
    r"(?P<dia>\d{1,2})/(?P<mes>\d{1,2})/(?P<ano>\d{4})\s*-?\s*(?P<hora>\d{1,2}):(?P<minuto>\d{2})\s*h",
    re.IGNORECASE,
)

BAD_WORDS = {
    "resultados", "posiciones", "tablas", "sistema", "comet", "contenido",
    "parcial", "pendiente", "actualizados", "consecuencia", "descargar",
    "compartir", "ver mas", "ver más", "fixture", "temporada", "fecha",
}


@dataclass
class Partido:
    fonte: str
    competicao: str
    data: str
    hora: str
    mandante: str
    visitante: str
    estadio: str = ""
    rodada: str = ""
    url: str = ""
    extra: str = ""
    pais: str = "Uruguai"
    cidade: str = ""

    @property
    def id(self) -> str:
        raw = "|".join([
            self.fonte, self.competicao, self.data, self.hora,
            self.mandante, self.visitante, self.estadio, self.rodada,
        ])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def to_row(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        d["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
        return d


def clean_text(value) -> str:
    value = "" if value is None else str(value)
    value = value.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", value).strip()


def norm(value) -> str:
    value = unicodedata.normalize("NFD", clean_text(value))
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def is_bad_line(x: str) -> bool:
    texto = clean_text(x)
    s = norm(x)
    if not s or len(texto) > 80:
        return True
    # códigos de abreviação de time (ex.: "ALB", "CDM", "PEÑ") aparecem como
    # linha própria logo depois do nome completo do time — sem isso, o
    # código do MANDANTE era capturado como se fosse o VISITANTE.
    if re.fullmatch(r"[A-ZÑÁÉÍÓÚÜ]{2,5}", texto):
        return True
    if re.search(r"\.(jpg|jpeg|png|gif|svg)$", texto, re.IGNORECASE):
        return True
    return any(w in s for w in BAD_WORDS)


def html_to_lines(html: str) -> list[str]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text("\n", strip=True)
    lines = []
    for raw in text.splitlines():
        s = clean_text(raw)
        if s:
            lines.append(s)
    return lines


def parse_lines(lines: list[str], url: str, competicao: str) -> list[Partido]:
    """Estratégia genérica de primeira passagem: procura por uma linha (ou
    junção de linhas vizinhas) com padrão de data+hora, e assume que o
    ESTÁDIO vem logo depois na mesma linha, e os NOMES DOS TIMES aparecem
    nas linhas seguintes até a próxima data+hora ou linha "ruim"."""
    partidos: list[Partido] = []
    i = 0
    while i < len(lines):
        texto_completo = lines[i]
        m = DATA_HORA_RE.search(texto_completo)
        if not m:
            i += 1
            continue

        try:
            data_iso = date(int(m.group("ano")), int(m.group("mes")), int(m.group("dia"))).isoformat()
        except ValueError:
            i += 1
            continue
        hora = f"{int(m.group('hora')):02d}:{m.group('minuto')}"

        # FIX: a ordem real na página é DATA+HORA (sozinha na linha), depois
        # ESTÁDIO, depois MANDANTE, depois VISITANTE — cada um em sua própria
        # linha. Antes o código assumia que o estádio vinha na MESMA linha da
        # data (resto_mesma_linha), o que empurrava tudo uma posição errada
        # (o nome do estádio virava "mandante" por engano).
        resto_mesma_linha = clean_text(texto_completo[m.end():])

        candidatos = []
        j = i + 1
        while j < len(lines) and len(candidatos) < 8:
            if DATA_HORA_RE.search(lines[j]):
                break
            if not is_bad_line(lines[j]):
                candidatos.append(lines[j])
            j += 1

        if resto_mesma_linha and not is_bad_line(resto_mesma_linha):
            estadio, mandante, visitante = (
                resto_mesma_linha,
                candidatos[0] if len(candidatos) >= 1 else "",
                candidatos[1] if len(candidatos) >= 2 else "",
            )
        elif len(candidatos) >= 3:
            estadio, mandante, visitante = candidatos[0], candidatos[1], candidatos[2]
        else:
            estadio, mandante, visitante = "", "", ""

        if mandante and visitante and mandante != visitante:
            partidos.append(Partido(
                fonte="AUF",
                competicao=competicao,
                data=data_iso,
                hora=hora,
                mandante=mandante,
                visitante=visitante,
                estadio=estadio,
                url=url,
            ))
        i += 1

    return partidos


def in_window(p: Partido, desde: date, ate: date, incluir_passados: bool) -> bool:
    try:
        dt = date.fromisoformat(p.data)
    except Exception:
        return False
    return (incluir_passados or (desde <= dt <= ate)) and bool(p.hora)


def dedupe(rows: list[Partido]) -> list[Partido]:
    seen = set()
    out = []
    for p in rows:
        if p.id in seen:
            continue
        seen.add(p.id)
        out.append(p)
    return out


def load_json_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def load_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def row_id(row: dict) -> str:
    if row.get("id"):
        return row["id"]
    raw = "|".join([
        row.get("fonte", ""), row.get("competicao", ""), row.get("data", ""),
        row.get("hora", ""), row.get("mandante", ""), row.get("visitante", ""),
        row.get("estadio", ""), row.get("rodada", ""),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def merge_rows(existing: list[dict], new_rows: list[dict]) -> list[dict]:
    by_id = {}
    for r in existing:
        rid = row_id(r)
        r["id"] = rid
        by_id[rid] = r
    for r in new_rows:
        rid = row_id(r)
        r["id"] = rid
        by_id[rid] = r
    return sorted(
        by_id.values(),
        key=lambda r: (r.get("data", ""), r.get("hora", ""), r.get("competicao", ""), r.get("mandante", ""))
    )


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dias", type=int, default=180)
    parser.add_argument("--dias-atras", type=int, default=30)
    parser.add_argument("--incluir-passados", action="store_true")
    parser.add_argument("--debug-html", action="store_true")
    parser.add_argument("--wait-ms", type=int, default=8000)
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    all_partidos: list[Partido] = []
    debug_pages = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125 Safari/537.36"
            ),
            locale="es-UY",
        )
        page = context.new_page()

        for competicao, url in URLS:
            info = {"competicao": competicao, "url": url, "status": "", "erro": "", "jogos": 0}
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(args.wait_ms)
                html = page.content()
                info["status"] = "rendered"
                info["bytes"] = len(html.encode("utf-8"))

                lines = html_to_lines(html)
                info["amostra_linhas"] = lines[:200]

                if args.debug_html:
                    DEBUG_DIR.mkdir(exist_ok=True)
                    slug = re.sub(r"[^a-z0-9]+", "_", norm(competicao))
                    (DEBUG_DIR / f"{slug}.html").write_text(html, encoding="utf-8")
                    (DEBUG_DIR / f"{slug}_lines.txt").write_text("\n".join(lines), encoding="utf-8")

                partidos = parse_lines(lines, url, competicao)
                info["jogos"] = len(partidos)
                info["amostra_jogos"] = [
                    {"data": p.data, "hora": p.hora, "mandante": p.mandante,
                     "visitante": p.visitante, "estadio": p.estadio}
                    for p in partidos[:25]
                ]
                all_partidos.extend(partidos)
                print(f"[OK] {competicao}: {len(partidos)} jogos extraídos brutos")
            except Exception as e:
                info["erro"] = str(e)
                print(f"[ERRO] {competicao}: {e}", file=sys.stderr)
            debug_pages.append(info)

        browser.close()

    (OUT_DIR / "debug_uruguai_pages.json").write_text(
        json.dumps(debug_pages, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    all_partidos = [p for p in all_partidos if in_window(p, desde, ate, args.incluir_passados)]
    all_partidos = dedupe(all_partidos)

    print(f"\n[INFO] Total jogos Uruguai na janela: {len(all_partidos)}")
    for p in all_partidos[:15]:
        print(f"  - {p.competicao} | {p.data} {p.hora} | {p.mandante} x {p.visitante} | {p.estadio}")

    rows_new = [p.to_row() for p in all_partidos]

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    merged_current = merge_rows(load_json_rows(current_json), rows_new)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    merged_history = merge_rows(load_csv_rows(history_csv), rows_new)
    write_csv(history_csv, merged_history)

    print(f"\nUruguai adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")


if __name__ == "__main__":
    main()
