#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Colômbia - via API pública (não-oficial, mas amplamente usada e estável)
da ESPN.

Depois de tentar acessar a DIMAYOR diretamente (bloqueio Cloudflare em
navegação repetida + PDFs oficiais com nomes de times como imagem, sem
texto selecionável), a fonte escolhida foi a API JSON que o próprio
site da ESPN usa para seus widgets de placar/calendário:

    https://site.api.espn.com/apis/site/v2/sports/soccer/{liga}/scoreboard?dates=YYYYMMDD

Essa API é pública, não exige autenticação, é amplamente documentada
pela comunidade (ex.: github.com/pseudo-r/Public-ESPN-API) e cobre a
Categoría Primera A colombiana (liga "col.1"), entre muitas outras.

Cada evento retornado já tem: data/hora em UTC (campo "date", ISO
completo), nomes dos times, placar (quando já jogado), status
("scheduled"/"in"/"post") e, quando disponível, o estádio.

Uso:
    python scrap_colombia_espn.py --dias 60 --dias-atras 15
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# league slug -> nome amigável da competicao
LIGAS = [
    ("col.1", "Liga BetPlay"),
    ("col.2", "Torneo BetPlay"),
    ("col.copa", "Copa BetPlay"),
]
# Nota: tentamos "col.w.1" para a Liga Femenina BetPlay, mas o slug
# retornou erro em todos os dias testados (provavelmente incorreto).
# Revisitar depois para achar o slug certo da ESPN para essa competição.

FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "pais", "cidade", "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept": "application/json",
}


@dataclass
class Partido:
    fonte: str
    competicao: str
    data: str
    hora: str
    mandante: str
    visitante: str
    pais: str = "Colombia"
    cidade: str = ""
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


def clean_text(x: Any) -> str:
    x = "" if x is None else str(x)
    x = x.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", x).strip()


def utc_iso_to_colombia(date_iso: str) -> tuple[str, str]:
    """Colômbia é fixa em UTC-5 (sem horário de verão)."""
    try:
        dt_utc = datetime.strptime(date_iso, "%Y-%m-%dT%H:%MZ")
    except ValueError:
        dt_utc = datetime.strptime(date_iso, "%Y-%m-%dT%H:%M:%SZ")
    dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    dt_local = dt_utc - timedelta(hours=5)
    return dt_local.date().isoformat(), dt_local.strftime("%H:%M")


def fetch_scoreboard(league_slug: str, date_str: str, timeout: int) -> dict:
    url = f"{BASE_URL}/{league_slug}/scoreboard"
    r = requests.get(url, headers=HEADERS, params={"dates": date_str}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def event_to_partido(event: dict, competicao_label: str) -> Partido | None:
    date_iso = event.get("date", "")
    if not date_iso:
        return None
    data_local, hora_local = utc_iso_to_colombia(date_iso)

    competitions = event.get("competitions") or []
    if not competitions:
        return None
    comp = competitions[0]

    competitors = comp.get("competitors") or []
    if len(competitors) != 2:
        return None

    mandante = visitante = ""
    score_home = score_away = ""
    for c in competitors:
        nome = clean_text((c.get("team") or {}).get("displayName") or (c.get("team") or {}).get("name"))
        score = clean_text(c.get("score"))
        if c.get("homeAway") == "home":
            mandante, score_home = nome, score
        else:
            visitante, score_away = nome, score

    if not mandante or not visitante or mandante == visitante:
        return None

    venue = comp.get("venue") or {}
    estadio = clean_text(venue.get("fullName"))
    cidade = clean_text((venue.get("address") or {}).get("city"))

    status = ((comp.get("status") or {}).get("type") or {}).get("description", "")

    extra_parts = [f"codigo_espn={event.get('id','')}"]
    if status:
        extra_parts.append(f"status={status}")
    jogo_finalizado = status.lower() not in ("scheduled", "", "postponed", "cancelled")
    if jogo_finalizado and score_home and score_away:
        extra_parts.append(f"placar={score_home}-{score_away}")

    rodada = clean_text(event.get("shortName")) if False else ""
    # ESPN traz "week"/"season" em alguns esportes, mas para esta liga
    # normalmente não vem número de rodada limpo; deixamos em branco.

    return Partido(
        fonte="ESPN",
        competicao=f"Colombia - {competicao_label}",
        data=data_local,
        hora=hora_local,
        mandante=mandante,
        visitante=visitante,
        pais="Colombia",
        cidade=cidade,
        estadio=estadio,
        rodada=rodada,
        extra="; ".join(extra_parts),
    )


def collect(ligas: list[tuple[str, str]], dias: int, dias_atras: int, timeout: int):
    today = date.today()
    desde = today - timedelta(days=dias_atras)
    ate = today + timedelta(days=dias)

    partidos: list[Partido] = []
    debug_pages = []

    for league_slug, label in ligas:
        d = desde
        total_liga = 0
        erros = 0
        while d <= ate:
            date_str = d.strftime("%Y%m%d")
            try:
                data = fetch_scoreboard(league_slug, date_str, timeout)
                events = data.get("events") or []
                for ev in events:
                    p = event_to_partido(ev, label)
                    if p:
                        partidos.append(p)
                        total_liga += 1
            except Exception as e:
                erros += 1
                print(f"[WARN] {label} {date_str}: {e}")
            d += timedelta(days=1)
        debug_pages.append({"liga": label, "slug": league_slug, "jogos": total_liga, "erros": erros})
        print(f"[OK] {label}: {total_liga} jogos encontrados ({erros} erros de dia)")

    return partidos, debug_pages


def dedupe_partidos(rows: list[Partido]) -> list[Partido]:
    seen = set()
    out = []
    for p in rows:
        if not p.data or not p.mandante or not p.visitante:
            continue
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
        row.get("fonte", ""), row.get("competicao", ""), row.get("data", ""),
        row.get("hora", ""), row.get("mandante", ""), row.get("visitante", ""),
        row.get("estadio", ""), row.get("rodada", ""),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def is_valid_row(row: dict) -> bool:
    return bool(row.get("data") and row.get("mandante") and row.get("visitante"))


def merge_rows(existing: list[dict], new_rows: list[dict]) -> list[dict]:
    by_id = {}
    for r in existing:
        if not is_valid_row(r):
            continue
        rid = row_id(r)
        r["id"] = rid
        by_id[rid] = r
    for r in new_rows:
        if not is_valid_row(r):
            continue
        rid = row_id(r)
        r["id"] = rid
        by_id[rid] = r
    return sorted(
        by_id.values(),
        key=lambda r: (r.get("data", ""), r.get("hora", ""), r.get("pais", ""), r.get("competicao", ""), r.get("mandante", ""))
    )


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            if is_valid_row(r):
                w.writerow({k: r.get(k, "") for k in FIELDS})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dias", type=int, default=60)
    parser.add_argument("--dias-atras", type=int, default=15)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    partidos, debug_pages = collect(LIGAS, args.dias, args.dias_atras, args.timeout)
    partidos = dedupe_partidos(partidos)
    rows_new = [p.to_row() for p in partidos]

    (OUT_DIR / "debug_colombia_espn_pages.json").write_text(json.dumps(debug_pages, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "debug_colombia_espn_raw.json").write_text(json.dumps(rows_new, ensure_ascii=False, indent=2), encoding="utf-8")

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    merged_current = merge_rows(load_json_rows(current_json), rows_new)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    merged_history = merge_rows(load_csv_rows(history_csv), rows_new)
    write_csv(history_csv, merged_history)

    print("")
    print(f"Colômbia (ESPN) jogos válidos adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")


if __name__ == "__main__":
    main()
