#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adiciona jogos CONMEBOL ao JSON/CSV já gerado pelo scraper principal.

Fontes oficiais usadas:
- https://gol.conmebol.com/libertadores/es
- https://gol.conmebol.com/sudamericana/es

Saídas atualizadas:
- data/jogos_programados.json
- data/jogos_programados.csv
- data/historico_jogos.csv

Uso:
    python adicionar_conmebol.py --dias 180 --dias-atras 30

Observações:
- A página da CONMEBOL usa horário UTC-3; o campo "extra" registra isso.
- Alguns jogos aparecem com "TBC"; nesses casos, "hora" fica vazio e "extra" indica hora_tbc.
- O script preserva os jogos já existentes no JSON e adiciona/atualiza os jogos CONMEBOL.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup


OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "es-CL,es;q=0.9,pt-BR;q=0.8,en;q=0.7",
}

CONMEBOL_URLS = [
    ("CONMEBOL Libertadores", "https://gol.conmebol.com/libertadores/es"),
    ("CONMEBOL Sudamericana", "https://gol.conmebol.com/sudamericana/es"),
]

MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
DATE_LINE_RE = re.compile(
    r"\b(\d{1,2})\s+"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
    r"\s*[-–—]\s*(\d{1,2}:\d{2}|TBC)\s*UTC\s*[-+]\s*\d+",
    re.I,
)
YEAR_RE = re.compile(r"\b(20\d{2})\b")
SCORE_RE = re.compile(r"^\d+\s*$")
NOISE = {
    "saltar al contenido principal", "libertadores mega navigation", "sudamericana mega navigation",
    "menú cerrar", "bienvenido", "noticias", "posiciones", "partidos", "gaming",
    "equipos", "estadísticas", "estadisticas", "tv", "conmebol id",
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

    @property
    def id(self) -> str:
        raw = "|".join([
            self.fonte, self.competicao, self.data, self.hora,
            self.mandante, self.visitante, self.estadio,
        ])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def to_row(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        d["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
        return d


def clean_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    value = re.sub(r"^Image:\s*", "", value, flags=re.I).strip()
    return value


def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    return r.text


def soup_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    lines = []
    for raw in soup.get_text("\n").splitlines():
        line = clean_text(raw)
        if not line:
            continue
        if line.lower() in NOISE:
            continue
        # Ignora linhas isoladas de parênteses ou imagens
        if line in {"()", "#"}:
            continue
        lines.append(line)
    return lines


def infer_year(lines: list[str]) -> int:
    # Nas páginas atuais há um "2026" antes da lista de jogos.
    for line in lines[:80]:
        m = YEAR_RE.search(line)
        if m:
            return int(m.group(1))
    return date.today().year


def parse_conmebol_date(line: str, year: int) -> tuple[Optional[date], str, str]:
    m = DATE_LINE_RE.search(line)
    if not m:
        return None, "", ""
    day = int(m.group(1))
    month = MONTHS_ES[m.group(2).lower()]
    hour = m.group(3).upper()
    extra = "timezone=UTC-3"
    if hour == "TBC":
        return date(year, month, day), "", "timezone=UTC-3; hora_tbc"
    return date(year, month, day), hour, extra


def split_vs(text: str) -> tuple[str, str]:
    text = clean_text(text)
    # Casos típicos: "CD Universidad CatólicavsBarcelona SC"
    parts = re.split(r"(?i)\s*vs\.?\s*", text, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return clean_text(parts[0]), clean_text(parts[1])
    return "", ""


def is_match_title(line: str) -> bool:
    if "vs" not in line.lower():
        return False
    if len(line) < 6 or len(line) > 140:
        return False
    if line.lower().startswith(("cruzeiro vs. barcelona", "highlights")):
        return False
    a, b = split_vs(line)
    return bool(a and b)


def looks_like_stadium(line: str) -> bool:
    low = line.lower()
    return (
        "estadio" in low
        or "arena" in low
        or "maracanã" in low
        or "maracana" in low
        or "campeón del siglo" in low
        or "campeon del siglo" in low
        or "la nueva olla" in low
        or "gran parque central" in low
        or "defensores del chaco" in low
    )


def parse_conmebol_page(competicao: str, url: str, html: str, desde: date, ate: date, incluir_passados: bool) -> list[Partido]:
    lines = soup_lines(html)
    year = infer_year(lines)
    out: list[Partido] = []

    for i, line in enumerate(lines):
        if not is_match_title(line):
            continue

        mandante, visitante = split_vs(line)
        if not mandante or not visitante:
            continue

        match_date = None
        hora = ""
        extra = "timezone=UTC-3"
        date_idx = None

        # A data costuma vir 1 a 8 linhas depois do título.
        for j in range(i + 1, min(i + 10, len(lines))):
            dt, hr, ex = parse_conmebol_date(lines[j], year)
            if dt:
                match_date = dt
                hora = hr
                extra = ex
                date_idx = j
                break

        if not match_date:
            continue

        estadio = ""
        for j in range((date_idx or i) + 1, min((date_idx or i) + 8, len(lines))):
            if looks_like_stadium(lines[j]):
                estadio = lines[j]
                break

        if not incluir_passados and not (desde <= match_date <= ate):
            continue

        out.append(Partido(
            fonte="gol.conmebol.com",
            competicao=competicao,
            data=match_date.isoformat(),
            hora=hora,
            mandante=mandante,
            visitante=visitante,
            estadio=estadio,
            rodada="",
            url=url,
            extra=extra,
        ))

    return dedupe(out)


def dedupe(partidos: list[Partido]) -> list[Partido]:
    seen = set()
    out = []
    for p in partidos:
        if p.id in seen:
            continue
        seen.add(p.id)
        out.append(p)
    return out


def load_json_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
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
        row.get("fonte", ""),
        row.get("competicao", ""),
        row.get("data", ""),
        row.get("hora", ""),
        row.get("mandante", ""),
        row.get("visitante", ""),
        row.get("estadio", ""),
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
    return sorted(by_id.values(), key=lambda r: (r.get("data", ""), r.get("hora", ""), r.get("competicao", ""), r.get("mandante", "")))


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "id", "fonte", "competicao", "data", "hora",
        "mandante", "visitante", "estadio", "rodada",
        "url", "extra", "atualizado_em",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dias", type=int, default=180, help="janela de jogos futuros")
    parser.add_argument("--dias-atras", type=int, default=30, help="janela de jogos passados recentes")
    parser.add_argument("--incluir-passados", action="store_true", help="inclui todos os jogos passados encontrados")
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    conmebol_rows: list[dict] = []

    for competicao, url in CONMEBOL_URLS:
        try:
            html = fetch(url)
            matches = parse_conmebol_page(competicao, url, html, desde, ate, args.incluir_passados)
            print(f"[OK] {competicao} -> {len(matches)} jogos | {url}")
            conmebol_rows.extend([m.to_row() for m in matches])
        except Exception as e:
            print(f"[ERRO] {url}: {e}", file=sys.stderr)

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    current_existing = load_json_rows(current_json)
    merged_current = merge_rows(current_existing, conmebol_rows)

    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    history_existing = load_csv_rows(history_csv)
    merged_history = merge_rows(history_existing, conmebol_rows)
    write_csv(history_csv, merged_history)

    print(f"\nCONMEBOL adicionados/atualizados: {len(conmebol_rows)}")
    print(f"Total JSON atual: {len(merged_current)}")
    print(f"JSON: {current_json.resolve()}")
    print(f"CSV: {current_csv.resolve()}")
    print(f"Histórico: {history_csv.resolve()}")


if __name__ == "__main__":
    main()
