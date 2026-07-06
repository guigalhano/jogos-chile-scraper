#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper AFA - Asociación del Fútbol Argentino

Fonte: página "La agenda de la AFA" (texto livre, sem API/HTML estruturado).
https://www.afa.com.ar/Sitio/posts/la-agenda-de-la-afa

Formato da página (texto corrido):
- Cabeçalhos de competição em negrito: "Torneo Clausura", "Copa Argentina 2026", etc.
- Dentro do Torneo Clausura: cabeçalhos de data "Jueves 23 de julio" seguidos de
  linhas "19.30 Belgrano – Rosario Central (Zona B)".
- Copa Argentina / Supercopa: formato em prosa "Time vs Time, a las HH.MM horas
  en Estadio", agrupado sob cabeçalhos de data "Domingo 12/7".

Este scraper cobre apenas as competições domésticas da AFA (Torneo Clausura,
Copa Argentina, Supercopa Argentina) para não duplicar Libertadores/Sudamericana
já cobertos por adicionar_conmebol.py.

Uso:
    python scrap_afa_agenda.py --dias 180 --dias-atras 30
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

import requests
from bs4 import BeautifulSoup

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

URL = "https://www.afa.com.ar/Sitio/posts/la-agenda-de-la-afa"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.7",
}

FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em", "pais",
]

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

DATA_LONGA_RE = re.compile(
    r"^(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\s+"
    r"(\d{1,2})\s+de\s+([a-záéíóú]+)\.?\s*$",
    re.IGNORECASE,
)

DATA_CURTA_RE = re.compile(
    r"^(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\s+(\d{1,2})/(\d{1,2})\s*:?\s*$",
    re.IGNORECASE,
)

JOGO_LIGA_PREFIXO_RE = re.compile(r"^(\d{1,2})[.:](\d{2})\s+(.+)$")
ZONA_SUFIXO_RE = re.compile(
    r"^(?P<resto>.+?)\s*\(\s*(?P<zona>Zona\s+[A-Z]|Interzonal)\s*\)\s*$",
    re.IGNORECASE,
)

JOGO_PROSA_RE = re.compile(
    r"^(.+?)\s+vs\.?\s+(.+?),?\s+a\s+las\s+(\d{1,2})[.:](\d{2})\s+horas"
    r"(?:,?\s*en\s+(.+?))?\.?\s*$",
    re.IGNORECASE,
)

SECOES_DOMESTICAS = {
    "torneo clausura": "Argentina - Torneo Clausura",
    "copa argentina 2026": "Argentina - Copa Argentina",
    "supercopa argentina 2025": "Argentina - Supercopa Argentina",
    "supercopa argentina 2026": "Argentina - Supercopa Argentina",
    "primera nacional": "Argentina - Primera Nacional",
}

SECOES_PARAR = {
    "conmebol copa libertadores", "conmebol copa sudamericana",
    "copa del mundo", "eliminatorias sudamericanas", "torneo proyeccion",
    "torneo proyección", "primera b", "primera c", "promocional amateur",
    "futbol femenino", "fútbol femenino", "torneo femenino",
    "torneo federal a", "seleccion mayor femenina", "selección mayor femenina",
    "copa mundial", "juegos olimpicos", "juegos olímpicos",
    "intercontinental sub 20", "conmebol", "finalissima",
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
    pais: str = "Argentina"

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


def fetch_lines(url: str) -> list[str]:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [clean_text(l) for l in text.splitlines()]
    return [l for l in lines if l]


def resolve_year(mes: int, dia: int, today: date) -> int:
    year = today.year
    try:
        candidate = date(year, mes, dia)
    except ValueError:
        return year
    if (today - candidate).days > 60:
        return year + 1
    return year


def parse_afa_agenda(lines: list[str], today: date) -> list[Partido]:
    partidos: list[Partido] = []
    competicao_atual: str | None = None
    dentro_do_escopo = False
    data_atual: str = ""

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        chave = norm(line)

        matched_secao = None
        for nome, label in SECOES_DOMESTICAS.items():
            if chave == norm(nome):
                matched_secao = label
                break
        if matched_secao:
            competicao_atual = matched_secao
            dentro_do_escopo = True
            data_atual = ""
            continue

        if any(chave.startswith(norm(s)) for s in SECOES_PARAR):
            dentro_do_escopo = False
            continue

        if not dentro_do_escopo or not competicao_atual:
            continue

        m_data = DATA_LONGA_RE.match(line)
        if m_data:
            dia = int(m_data.group(1))
            mes_nome = norm(m_data.group(2))
            mes = MESES.get(mes_nome)
            if mes:
                year = resolve_year(mes, dia, today)
                try:
                    data_atual = date(year, mes, dia).isoformat()
                except ValueError:
                    data_atual = ""
            continue

        m_data2 = DATA_CURTA_RE.match(line)
        if m_data2:
            dia, mes = int(m_data2.group(1)), int(m_data2.group(2))
            year = resolve_year(mes, dia, today)
            try:
                data_atual = date(year, mes, dia).isoformat()
            except ValueError:
                data_atual = ""
            continue

        m_jogo = JOGO_LIGA_PREFIXO_RE.match(line)
        if m_jogo and data_atual:
            hora = f"{int(m_jogo.group(1)):02d}:{m_jogo.group(2)}"
            resto = clean_text(m_jogo.group(3))
            rodada = ""
            m_zona = ZONA_SUFIXO_RE.match(resto)
            if m_zona:
                resto = clean_text(m_zona.group("resto"))
                rodada = clean_text(m_zona.group("zona"))
            partes = re.split(r"\s*[–\-]\s*", resto, maxsplit=1)
            if len(partes) == 2:
                mandante, visitante = clean_text(partes[0]), clean_text(partes[1])
                if mandante and visitante and len(mandante) < 60 and len(visitante) < 60:
                    partidos.append(Partido(
                        fonte="AFA",
                        competicao=competicao_atual,
                        data=data_atual,
                        hora=hora,
                        mandante=mandante,
                        visitante=visitante,
                        rodada=rodada,
                        url=URL,
                    ))
            continue

        m_prosa = JOGO_PROSA_RE.match(line)
        if m_prosa and data_atual:
            mandante = clean_text(m_prosa.group(1))
            visitante = clean_text(m_prosa.group(2))
            hora = f"{int(m_prosa.group(3)):02d}:{m_prosa.group(4)}"
            estadio = clean_text(m_prosa.group(5) or "")
            if norm(estadio).startswith("estadio a confirmar") or norm(estadio) == "a confirmar":
                estadio = ""
            if mandante and visitante and len(mandante) < 60 and len(visitante) < 60:
                partidos.append(Partido(
                    fonte="AFA",
                    competicao=competicao_atual,
                    data=data_atual,
                    hora=hora,
                    mandante=mandante,
                    visitante=visitante,
                    estadio=estadio,
                    url=URL,
                ))
            continue

    return partidos


def in_window(p: Partido, desde: date, ate: date, incluir_passados: bool) -> bool:
    try:
        dt = date.fromisoformat(p.data)
    except Exception:
        return False
    return incluir_passados or (desde <= dt <= ate)


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
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    try:
        lines = fetch_lines(URL)
    except Exception as e:
        print(f"[ERRO] Falha ao baixar agenda AFA: {e}", file=sys.stderr)
        lines = []

    partidos = parse_afa_agenda(lines, today)
    partidos = [p for p in partidos if in_window(p, desde, ate, args.incluir_passados) and p.hora]
    partidos = dedupe(partidos)

    print(f"[INFO] Jogos AFA extraídos e na janela: {len(partidos)}")
    for p in partidos[:10]:
        print(f"  - {p.competicao} | {p.data} {p.hora} | {p.mandante} x {p.visitante}")

    rows_new = [p.to_row() for p in partidos]

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    current_existing = load_json_rows(current_json)
    merged_current = merge_rows(current_existing, rows_new)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    history_existing = load_csv_rows(history_csv)
    merged_history = merge_rows(history_existing, rows_new)
    write_csv(history_csv, merged_history)

    print(f"\nAFA (Argentina) adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")


if __name__ == "__main__":
    main()
