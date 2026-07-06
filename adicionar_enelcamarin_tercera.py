#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adiciona jogos da Tercera A/B do site En El Camarín ao JSON atual.

Fontes:
- https://enelcamarin.cl/joomsport_season/tercera-division-a-3ra-tercera-a-2026/?action=calendar
- https://enelcamarin.cl/joomsport_season/tercera-division-b-3ra-tercera-b-2026/?action=calendar

Saídas atualizadas:
- data/jogos_programados.json
- data/jogos_programados.csv
- data/historico_jogos.csv

Uso:
    python adicionar_enelcamarin_tercera.py --dias 180 --dias-atras 60
    python adicionar_enelcamarin_tercera.py --incluir-passados

Observação:
O En El Camarín mostra muitos jogos já finalizados. Nesses casos o placar fica em "extra".
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
from urllib.parse import urljoin

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

URLS = [
    ("Tercera A", "https://enelcamarin.cl/joomsport_season/tercera-division-a-3ra-tercera-a-2026/?action=calendar"),
    ("Tercera B", "https://enelcamarin.cl/joomsport_season/tercera-division-b-3ra-tercera-b-2026/?action=calendar"),
]

DATE_TIME_RE = re.compile(r"\b(\d{2})-(\d{2})-(20\d{2})\s+(\d{1,2}:\d{2})\b")
SCORE_RE = re.compile(r"^\d+\s*[-–]\s*\d+$|^[-–]\s*[-–]$|^v/s$|^vs$", re.I)
FECHA_RE = re.compile(r"Fecha\s+\d+[^\\n]*", re.I)

NOISE = {
    "en el camarín", "femenino", "liga femenina", "tabla de posiciones", "fixture",
    "goleadores", "goleadoras", "planteles", "search", "previous", "next",
    "standings", "calendar", "player list", "rank", "teams", "played", "won",
    "drawn", "lost", "differential", "goal difference", "points", "current form",
    "desde 2009 siendo el sitio más estadístico del fútbol chileno",
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
            self.mandante, self.visitante, self.estadio, self.rodada
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


def norm(value: str) -> str:
    import unicodedata
    value = unicodedata.normalize("NFD", value or "")
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    return r.text


def soup_lines_and_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    lines = []
    for raw in soup.get_text("\n").splitlines():
        line = clean_text(raw)
        if not line:
            continue
        low = line.lower()
        if low in NOISE:
            continue
        if line.startswith("©"):
            continue
        lines.append(line)

    return lines


def discover_calendar_urls(html: str, base_url: str, fallback_comp: str) -> list[tuple[str, str]]:
    """
    A página de calendário tem links de cada Fecha. Descobre todos os hrefs da temporada.
    """
    soup = BeautifulSoup(html, "html.parser")
    urls = {(fallback_comp, base_url)}
    for a in soup.find_all("a", href=True):
        text = clean_text(a.get_text(" ", strip=True))
        href = urljoin(base_url, a["href"]).split("#")[0]
        if "joomsport_match" in href or "joomsport_season" in href:
            # Mantém só URLs de calendario/fecha/partida da Tercera.
            if "tercera" in href.lower() or "3ra" in href.lower() or "joomsport_match" in href:
                if "tercera-division-a" in href.lower():
                    comp = "Tercera A"
                elif "tercera-division-b" in href.lower():
                    comp = "Tercera B"
                else:
                    comp = fallback_comp
                if "action=calendar" in href or "joomsport_match" in href:
                    urls.add((comp, href))
        # Links de texto "Fecha X Tercera A 2026" às vezes não incluem action=calendar no parser
        if text.lower().startswith("fecha") and "tercera" in text.lower():
            if "href" in a.attrs:
                if "tercera-division-a" in href.lower():
                    urls.add(("Tercera A", href))
                elif "tercera-division-b" in href.lower():
                    urls.add(("Tercera B", href))
    return sorted(urls, key=lambda x: x[1])


def is_team(line: str) -> bool:
    line = clean_text(line)
    if not line:
        return False
    low = line.lower()
    if low in NOISE:
        return False
    if DATE_TIME_RE.search(line):
        return False
    if SCORE_RE.match(line):
        return False
    if FECHA_RE.search(line):
        return False
    if len(line) > 80:
        return False
    if low in {"w", "d", "l", "local", "visita", "visitante"}:
        return False
    if re.match(r"^\d+$", line):
        return False
    return True


def parse_dt(line: str) -> tuple[date | None, str]:
    m = DATE_TIME_RE.search(line)
    if not m:
        return None, ""
    d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return d, m.group(4)


def in_window(dt: date, desde: date, ate: date, incluir_passados: bool) -> bool:
    return incluir_passados or (desde <= dt <= ate)


def parse_enelcamarin_calendar(competicao: str, url: str, html: str, desde: date, ate: date, incluir_passados: bool) -> list[Partido]:
    lines = soup_lines_and_links(html, url)
    out: list[Partido] = []

    rodada = ""
    for line in lines:
        m = FECHA_RE.search(line)
        if m:
            # Ex.: Fecha 8 Tercera A 2026
            rodada = clean_text(m.group(0))
            break

    for i, line in enumerate(lines):
        dt, hora = parse_dt(line)
        if not dt:
            continue

        # Padrão:
        # data hora
        # mandante
        # [Image]
        # placar
        # [Image]
        # visitante
        # estadio
        candidates = []
        for j in range(i + 1, min(i + 12, len(lines))):
            if DATE_TIME_RE.search(lines[j]):
                break
            if lines[j].lower().startswith("image:"):
                continue
            candidates.append(lines[j])

        mandante = ""
        visitante = ""
        placar = ""
        estadio = ""

        # Primeiro time
        idx = 0
        while idx < len(candidates):
            if is_team(candidates[idx]):
                mandante = candidates[idx]
                idx += 1
                break
            idx += 1

        # Placar
        while idx < len(candidates):
            if SCORE_RE.match(candidates[idx]):
                placar = candidates[idx]
                idx += 1
                break
            idx += 1

        # Segundo time
        while idx < len(candidates):
            if is_team(candidates[idx]):
                visitante = candidates[idx]
                idx += 1
                break
            idx += 1

        # Estádio: primeira linha restante que não parece time duplicado; no En El Camarín vem após visitante.
        while idx < len(candidates):
            possible = candidates[idx]
            if possible and not SCORE_RE.match(possible) and not DATE_TIME_RE.search(possible):
                estadio = possible
                break
            idx += 1

        if not (mandante and visitante):
            continue

        if not in_window(dt, desde, ate, incluir_passados):
            continue

        # Evita nomes contaminados por menus
        if norm(mandante) == norm(visitante):
            continue

        out.append(Partido(
            fonte="enelcamarin.cl",
            competicao=competicao,
            data=dt.isoformat(),
            hora=hora,
            mandante=mandante,
            visitante=visitante,
            estadio=estadio,
            rodada=rodada,
            url=url,
            extra=f"placar={placar}" if placar else "",
        ))

    return dedupe(out)


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
        row.get("rodada", ""),
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
    parser.add_argument("--dias", type=int, default=180)
    parser.add_argument("--dias-atras", type=int, default=60)
    parser.add_argument("--incluir-passados", action="store_true")
    parser.add_argument("--no-discover", action="store_true", help="usa só os 2 URLs fixos")
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    all_new: list[dict] = []
    urls_to_parse: list[tuple[str, str]] = []

    for comp, url in URLS:
        try:
            html = fetch(url)
            if args.no_discover:
                urls_to_parse.append((comp, url))
            else:
                discovered = discover_calendar_urls(html, url, comp)
                # Inclui a página principal e as descobertas.
                urls_to_parse.extend(discovered)
        except Exception as e:
            print(f"[ERRO] Descobrir {url}: {e}", file=sys.stderr)
            urls_to_parse.append((comp, url))

    # Remove duplicatas
    seen_urls = set()
    clean_urls = []
    for comp, url in urls_to_parse:
        key = (comp, url)
        if key in seen_urls:
            continue
        seen_urls.add(key)
        clean_urls.append((comp, url))

    print(f"[INFO] URLs En El Camarín: {len(clean_urls)}")

    for comp, url in clean_urls:
        try:
            html = fetch(url)
            matches = parse_enelcamarin_calendar(comp, url, html, desde, ate, args.incluir_passados)
            print(f"[OK] {comp} -> {len(matches)} jogos | {url}")
            all_new.extend([m.to_row() for m in matches])
        except Exception as e:
            print(f"[ERRO] {url}: {e}", file=sys.stderr)

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    current_existing = load_json_rows(current_json)
    merged_current = merge_rows(current_existing, all_new)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    history_existing = load_csv_rows(history_csv)
    merged_history = merge_rows(history_existing, all_new)
    write_csv(history_csv, merged_history)

    print(f"\nEn El Camarín adicionados/atualizados: {len(all_new)}")
    print(f"Total JSON atual: {len(merged_current)}")


if __name__ == "__main__":
    main()
