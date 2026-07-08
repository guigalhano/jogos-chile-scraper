#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Futebol Peruano - futbolperuano.com (Liga 1, Liga 2, Liga 3, Copa de la
Liga, Copa Perú, Futebol Feminino)

Páginas:
    https://www.futbolperuano.com/liga-1/
    https://www.futbolperuano.com/liga-2/
    https://www.futbolperuano.com/liga-3/
    https://www.futbolperuano.com/copa-de-la-liga/
    https://www.futbolperuano.com/copa-peru/
    https://www.futbolperuano.com/futbol-femenino/resultados

Essas páginas trazem um widget de resultados ("Powered by Score24")
renderizado no servidor (requests simples já basta, sem Playwright).
Estrutura (confirmada inspecionando o HTML real):

    <div class="accordion" id="score_contenido_ResultadosTabs">
      <div class="card-header">...<span class="fch-resul">Fase Regular</span>...</div>
      <div class="card-body">
        <ul class="list accordion">
          <li class="fase active">
            <div class="event-date ..."><span class="date">Sábado, 18 Julio 2026</span></div>
            <div class="event-wrapper">
              <div class="event-date ..."><span class="date">Grupo 1</span></div>  (opcional)
              <div class="event-body ...">
                <div class="match">
                  <div class="local-team">...<span class="team-name">Mannucci</span></div>
                  <div class="match-hour ...">8:00 PM</div>
                  <div class="match-result ...">
                    <span class="local-result"><span>2</span></span> - <span class="visit-result"><span>1</span></span>
                  </div>
                  <div class="visit-team">...<span class="team-name">Llacuabamba</span></div>
                  <div class="match-time"><span class="timer">Por jugar</span></div>
                </div>
              </div>
            </div>
          </li>
          ...

Ou seja: percorrendo o documento em ordem, cada ".date" encontrado é ou
uma DATA (padrão "DiaDaSemana, DD Mes AAAA") ou um rótulo de
grupo/rodada (ex.: "Grupo 1"); e cada ".match" usa a data e o rótulo
mais recentes vistos até ali.

IMPORTANTE: esse widget não expõe o estádio de cada partida (só times,
data, hora e placar), então o campo "estadio" fica vazio aqui — é uma
limitação real da fonte, não do scraper.

Uso:
    python scrap_futbolperuano.py --dias 60 --dias-atras 15
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup, Tag

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

URLS = [
    ("Liga 1", "https://www.futbolperuano.com/liga-1/"),
    ("Liga 2", "https://www.futbolperuano.com/liga-2/"),
    ("Liga 3", "https://www.futbolperuano.com/liga-3/"),
    ("Copa de la Liga", "https://www.futbolperuano.com/copa-de-la-liga/"),
    ("Copa Perú", "https://www.futbolperuano.com/copa-peru/"),
    ("Fútbol Femenino", "https://www.futbolperuano.com/futbol-femenino/resultados"),
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
    "Accept-Language": "es-PE,es;q=0.9,pt;q=0.8,en;q=0.7",
}

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

DATE_RE = re.compile(
    r"(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\s*,\s*"
    r"(\d{1,2})\s+([a-záéíóú]+)\s+(\d{4})",
    re.I,
)

TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(AM|PM)", re.I)


@dataclass
class Partido:
    fonte: str
    competicao: str
    data: str
    hora: str
    mandante: str
    visitante: str
    pais: str = "Peru"
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


def parse_date_label(txt: str) -> str:
    m = DATE_RE.search(txt)
    if not m:
        return ""
    dia, mes_nome, ano = m.groups()
    mes = MESES.get(mes_nome.lower().strip())
    if not mes:
        return ""
    try:
        return date(int(ano), mes, int(dia)).isoformat()
    except Exception:
        return ""


def parse_time_label(txt: str) -> str:
    m = TIME_RE.search(txt)
    if not m:
        return ""
    hora, minuto, ampm = m.groups()
    hora = int(hora)
    ampm = ampm.upper()
    if ampm == "PM" and hora != 12:
        hora += 12
    if ampm == "AM" and hora == 12:
        hora = 0
    return f"{hora:02d}:{minuto}"


def parse_match_div(match_div: Tag, competicao_label: str, data_atual: str, rodada_atual: str) -> Partido | None:
    if not data_atual:
        return None

    local = match_div.select_one(".local-team .team-name")
    visit = match_div.select_one(".visit-team .team-name")
    if not local or not visit:
        return None
    mandante = clean_text(local.get_text())
    visitante = clean_text(visit.get_text())
    if not mandante or not visitante or mandante == visitante:
        return None

    hora_el = match_div.select_one(".match-hour")
    hora = parse_time_label(clean_text(hora_el.get_text())) if hora_el else ""

    local_score_el = match_div.select_one(".local-result span")
    visit_score_el = match_div.select_one(".visit-result span")
    local_score = clean_text(local_score_el.get_text()) if local_score_el else ""
    visit_score = clean_text(visit_score_el.get_text()) if visit_score_el else ""

    timer_el = match_div.select_one(".match-time .timer")
    status = clean_text(timer_el.get_text()) if timer_el else ""

    extra_parts = []
    if status:
        extra_parts.append(f"status={status}")
    if local_score and visit_score:
        extra_parts.append(f"placar={local_score}-{visit_score}")

    return Partido(
        fonte="FUTBOLPERUANO",
        competicao=f"Peru - {competicao_label}",
        data=data_atual,
        hora=hora,
        mandante=mandante,
        visitante=visitante,
        pais="Peru",
        rodada=rodada_atual,
        extra="; ".join(extra_parts),
    )


def fetch_and_parse(label: str, url: str) -> list[Partido]:
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    out = []
    for accordion in soup.select(".accordion.list, ul.list.accordion"):
        pass  # placeholder; iteramos direto pelos containers abaixo

    # Percorre em ordem todos os elementos ".date" (cabeçalhos de data ou de
    # grupo/rodada) e ".match" (uma partida), mantendo o estado mais recente.
    data_atual = ""
    rodada_atual = ""
    for el in soup.select(".card-header .fch-resul, .event-date .date, .match"):
        classes = el.get("class") or []
        if "fch-resul" in classes:
            rodada_atual = clean_text(el.get_text())
            continue
        if "date" in classes:
            txt = clean_text(el.get_text())
            dt = parse_date_label(txt)
            if dt:
                data_atual = dt
            elif txt:
                rodada_atual = txt
            continue
        if "match" in classes:
            p = parse_match_div(el, label, data_atual, rodada_atual)
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
    parser.add_argument("--dias", type=int, default=60)
    parser.add_argument("--dias-atras", type=int, default=15)
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
            print(f"[OK] {label}: {len(partidos)} jogos encontrados")
            all_partidos.extend(partidos)
        except Exception as e:
            debug_pages.append({"label": label, "url": url, "erro": str(e)})
            print(f"[ERRO] {label}: {e}")

    window_partidos = [p for p in all_partidos if in_window(p, desde, ate, args.incluir_passados)]
    window_partidos = dedupe_partidos(window_partidos)
    rows_new = [p.to_row() for p in window_partidos]

    (OUT_DIR / "debug_futbolperuano_pages.json").write_text(json.dumps(debug_pages, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "debug_futbolperuano_raw.json").write_text(json.dumps(rows_new, ensure_ascii=False, indent=2), encoding="utf-8")

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    merged_current = merge_rows(load_json_rows(current_json), rows_new)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    merged_history = merge_rows(load_csv_rows(history_csv), rows_new)
    write_csv(history_csv, merged_history)

    print("")
    print(f"Futebol Peruano jogos válidos adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")


if __name__ == "__main__":
    main()
