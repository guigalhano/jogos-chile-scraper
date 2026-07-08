#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CONMEBOL - Copa Libertadores + Copa Sudamericana

Páginas:
    https://gol.conmebol.com/libertadores/es
    https://gol.conmebol.com/sudamericana/es

Essas páginas (Drupal 11, plataforma oficial "gol.conmebol.com") trazem
na própria home um carrossel de jogos (2026) 100% renderizado no
servidor — dá pra pegar tudo com requests simples, sem Playwright.

Cada partida é um bloco:
    <div class="js--fixture-ajax ..." data-fixture-id="812"
         data-match-status="Played" data-start-time="1779328800"
         data-tbc="0">
      ...
      <span class="visually-hidden">Cusco FCvsDeportivo Independiente Medellín</span>
      ...
      <div class="m-fixture-teaser-card__venue">Estadio Inca Garcilaso de la Vega</div>
      ...
      <div class="m-fixture-teaser-card__team"> ... team-name ... team-score ...
      <div class="m-fixture-teaser-card__team--away"> ... team-name ... team-score ...
    </div>

- data-start-time é um timestamp Unix (segundos). Confirmado por
  cálculo: bate exatamente com o horário "UTC-3" que a própria página
  exibe em cada card (ex.: ts=1779328800 -> "20 Mayo - 23:00", que é
  precisamente 23:00 em UTC-3). Ou seja, o horário aqui usa sempre
  UTC-3 como referência oficial da CONMEBOL, independente do país onde
  o jogo é mandante — por isso convertemos para UTC-3 fixo, reproduzindo
  fielmente o que a própria fonte publica.
- data-match-status: "Played" (já disputado) ou "Fixture" (agendado,
  sem placar ainda). Times "Live" também podem aparecer mas não são o
  foco deste scraper (jogos ao vivo mudam rápido demais pra esse
  formato de coleta periódica).
- data-tbc="1": horário/data ainda sujeitos a confirmação oficial
  (fase mata-mata sem data fechada). Mantemos o valor de data-start-time
  mesmo assim (é a melhor estimativa disponível) e sinalizamos isso no
  campo "extra".

Os jogos são classificados com pais="Conmebol" (uma categoria especial,
não geográfica) já que são competições continentais entre clubes de
vários países.

Uso:
    python scrap_conmebol.py --dias 180 --dias-atras 30
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
from bs4 import BeautifulSoup

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

URLS = [
    ("Libertadores", "https://gol.conmebol.com/libertadores/es"),
    ("Sudamericana", "https://gol.conmebol.com/sudamericana/es"),
]

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
    "Accept-Language": "es-PY,es;q=0.9,pt;q=0.8,en;q=0.7",
}

FIXTURE_HREF_RE = re.compile(r"/fixture/view/(\d+)")


@dataclass
class Partido:
    fonte: str
    competicao: str
    data: str
    hora: str
    mandante: str
    visitante: str
    pais: str = "Conmebol"
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


def unix_to_utc3(ts: int) -> tuple[str, str]:
    dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
    dt_utc3 = dt_utc - timedelta(hours=3)
    return dt_utc3.date().isoformat(), dt_utc3.strftime("%H:%M")


def parse_card(card, competicao_label: str) -> Partido | None:
    fixture_id = card.get("data-fixture-id", "")
    status = card.get("data-match-status", "")
    start_time = card.get("data-start-time", "")
    tbc = card.get("data-tbc", "0")

    if not start_time:
        return None
    try:
        data_iso, hora = unix_to_utc3(int(start_time))
    except Exception:
        return None

    team_divs = card.select(".m-fixture-teaser-card__team")
    if len(team_divs) < 2:
        return None

    def team_name(div):
        el = div.select_one(".m-fixture-teaser-card__team-name")
        return clean_text(el.get_text()) if el else ""

    def team_score(div):
        el = div.select_one(".m-fixture-teaser-card__team-score")
        txt = clean_text(el.get_text()) if el else ""
        return txt

    mandante = team_name(team_divs[0])
    visitante = team_name(team_divs[1])
    if not mandante or not visitante or mandante == visitante:
        return None

    venue_el = card.select_one(".m-fixture-teaser-card__venue")
    estadio = clean_text(venue_el.get_text()) if venue_el else ""

    score_home = team_score(team_divs[0])
    score_away = team_score(team_divs[1])

    fixture_link = card.select_one(".m-fixture-teaser-card__match-centre-link")
    url = fixture_link["href"] if fixture_link and fixture_link.get("href") else ""

    extra_parts = [f"codigo_conmebol={fixture_id}"]
    if status:
        extra_parts.append(f"status={status}")
    if tbc == "1":
        extra_parts.append("horario_a_confirmar=1")
    if score_home and score_away:
        extra_parts.append(f"placar={score_home}-{score_away}")

    return Partido(
        fonte="CONMEBOL",
        competicao=f"Conmebol - {competicao_label}",
        data=data_iso,
        hora=hora,
        mandante=mandante,
        visitante=visitante,
        pais="Conmebol",
        estadio=estadio,
        url=url,
        extra="; ".join(extra_parts),
    )


def fetch_and_parse(label: str, url: str) -> list[Partido]:
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    out = []
    for card in soup.select(".js--fixture-ajax"):
        p = parse_card(card, label)
        if p:
            out.append(p)
    return out


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


def in_window(p: Partido, desde: date, ate: date, incluir_passados: bool) -> bool:
    try:
        dt = date.fromisoformat(p.data)
    except Exception:
        return False
    return incluir_passados or (desde <= dt <= ate)


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
    parser.add_argument("--dias", type=int, default=180)
    parser.add_argument("--dias-atras", type=int, default=30)
    parser.add_argument("--incluir-passados", action="store_true")
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    all_partidos: list[Partido] = []
    debug_pages = []

    for label, url in URLS:
        try:
            partidos = fetch_and_parse(label, url)
            debug_pages.append({"label": label, "url": url, "jogos": len(partidos)})
            print(f"[OK] {label}: {len(partidos)} jogos encontrados na home")
            all_partidos.extend(partidos)
        except Exception as e:
            debug_pages.append({"label": label, "url": url, "erro": str(e)})
            print(f"[ERRO] {label}: {e}")

    window_partidos = [p for p in all_partidos if in_window(p, desde, ate, args.incluir_passados)]
    window_partidos = dedupe_partidos(window_partidos)
    rows_new = [p.to_row() for p in window_partidos]

    (OUT_DIR / "debug_conmebol_pages.json").write_text(json.dumps(debug_pages, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "debug_conmebol_raw.json").write_text(json.dumps(rows_new, ensure_ascii=False, indent=2), encoding="utf-8")

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    merged_current = merge_rows(load_json_rows(current_json), rows_new)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    merged_history = merge_rows(load_csv_rows(history_csv), rows_new)
    write_csv(history_csv, merged_history)

    print("")
    print(f"CONMEBOL jogos válidos adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")


if __name__ == "__main__":
    main()
