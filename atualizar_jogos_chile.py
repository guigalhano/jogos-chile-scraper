#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Atualiza diariamente jogos programados do futebol chileno:
- campeonatochileno.cl
- anfaterceradivision.cl

Saídas:
- data/jogos_programados.csv
- data/jogos_programados.json
- data/historico_jogos.csv

Instalação:
    pip install -r requirements.txt

Uso:
    python atualizar_jogos_chile.py --once
    python atualizar_jogos_chile.py --once --dias 30

Agendamento diário no Windows:
    criar_tarefa_windows.bat

Observação:
Este scraper usa HTML público. Se os sites alterarem layout/classes, o fallback por texto
continua tentando extrair partidas, mas pode ser necessário ajustar os seletores.
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
from typing import Iterable, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "es-CL,es;q=0.9,pt-BR;q=0.8,pt;q=0.7,en;q=0.6",
}

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Ajuste aqui se quiser incluir/remover competições do campeonatochileno.cl
CAMPEONATO_CHILENO_URLS = [
    "https://www.campeonatochileno.cl/ligas/liga-de-primera-mercado-libre/",
    "https://www.campeonatochileno.cl/ligas/liga-de-ascenso-caixun/",
    "https://www.campeonatochileno.cl/ligas/liga-segunda-division/",
    "https://www.campeonatochileno.cl/ligas/copa-chile-coca-cola-zero-azucar/",
    "https://www.campeonatochileno.cl/ligas/copa-de-la-liga/",
]

ANFA_URLS = [
    "https://anfaterceradivision.cl/",
]

TIME_RE = re.compile(r"[-–—]?\s*(\d{1,2}:\d{2})\s*hrs?", re.I)
DATE_ES_RE = re.compile(
    r"\b(\d{1,2})\s+de\s+"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\b",
    re.I,
)
DATE_NUM_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
ANFA_DATE_RE = re.compile(r"\b(\d{1,2})\s+(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)\s+(\d{4})\b", re.I)
SCORE_RE = re.compile(r"^\d+\s*[-–]\s*\d+$|^\d+\s+\d+$|^[-–]\s*[-–]$")
NOISE_WORDS = {
    "image", "tabla de posiciones", "posiciones", "estadísticas", "noticias",
    "bases de campeonato", "tribunal", "ver más", "read more", "partidos",
    "fecha", "competición", "competicion", "fixture", "programación", "programacion",
}


@dataclass
class Partido:
    fonte: str
    competicao: str
    data: str          # YYYY-MM-DD
    hora: str          # HH:MM
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
            self.mandante, self.visitante, self.estadio
        ])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def to_row(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        d["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
        return d


def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def clean_text(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    s = s.replace("Image:", "").strip()
    return s


def soup_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    lines = []
    for x in soup.get_text("\n").splitlines():
        x = clean_text(x)
        if not x:
            continue
        low = x.lower()
        if low in NOISE_WORDS:
            continue
        if low.startswith("copyright"):
            continue
        lines.append(x)
    return lines


def parse_spanish_date(text: str, year: int) -> Optional[date]:
    m = DATE_ES_RE.search(text)
    if not m:
        return None
    day = int(m.group(1))
    month = MONTHS_ES[m.group(2).lower()]
    return date(year, month, day)


def parse_anfa_date(text: str) -> Optional[date]:
    months = {
        "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
    }
    m = ANFA_DATE_RE.search(text)
    if not m:
        return None
    return date(int(m.group(3)), months[m.group(2).upper()], int(m.group(1)))


def is_probably_team(line: str) -> bool:
    line = clean_text(line)
    if not line or len(line) < 2:
        return False
    low = line.lower()
    if low in NOISE_WORDS:
        return False
    if DATE_ES_RE.search(line) or ANFA_DATE_RE.search(line) or TIME_RE.search(line):
        return False
    if line.lower().startswith(("estadio ", "municipal ", "bicentenario ", "santa ", "sausalito", "claro arena")):
        return False
    if SCORE_RE.match(line):
        return False
    if re.match(r"^fecha\s+\d+", low):
        return False
    if re.search(r"\b(arbitro|árbitro|rebolledo|sep[uú]lveda|gamboa|vejar|gilabert|jona|salvo)\b", low):
        return False
    return True


def is_probably_stadium(line: str) -> bool:
    low = line.lower()
    stadium_markers = [
        "estadio", "municipal", "bicentenario", "sausalito", "claro arena",
        "el cobre", "la portada", "el teniente", "monumental", "la cisterna",
        "francisco sánchez", "huachipato", "nicolás chahuán", "lucio fariña",
        "ester roa", "nelson oyarzún", "la florida"
    ]
    return any(x in low for x in stadium_markers)


def infer_competition_from_url(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1]
    return slug.replace("-", " ").title()


def parse_campeonato_chileno_page(url: str, html: str, year: int, desde: date, ate: date) -> list[Partido]:
    """
    Parser por linhas. Funciona bem com as páginas atuais do Campeonato Chileno,
    onde o texto vem em sequência: Fecha, data, hora, mandante, placar, visitante, estádio.
    """
    lines = soup_lines(html)
    competicao = infer_competition_from_url(url)
    partidos: list[Partido] = []
    rodada = ""

    for i, line in enumerate(lines):
        if re.match(r"^Fecha\s+\d+", line, re.I):
            rodada = line

        match_date = parse_spanish_date(line, year)
        if not match_date:
            continue

        # Hora normalmente está na própria linha seguinte.
        hora = ""
        for j in range(i, min(i + 4, len(lines))):
            tm = TIME_RE.search(lines[j])
            if tm:
                hora = tm.group(1)
                time_idx = j
                break
        else:
            continue

        # Procura mandante após hora
        mandante = ""
        mandante_idx = None
        for j in range(time_idx + 1, min(time_idx + 8, len(lines))):
            if is_probably_team(lines[j]):
                mandante = lines[j]
                mandante_idx = j
                break
        if not mandante:
            continue

        # Procura visitante após mandante, pulando placar/imagens
        visitante = ""
        visitante_idx = None
        for j in range(mandante_idx + 1, min(mandante_idx + 10, len(lines))):
            if SCORE_RE.match(lines[j]):
                continue
            if is_probably_team(lines[j]):
                visitante = lines[j]
                visitante_idx = j
                break
        if not visitante:
            continue

        # Procura estádio logo depois do visitante
        estadio = ""
        for j in range(visitante_idx + 1, min(visitante_idx + 7, len(lines))):
            if is_probably_stadium(lines[j]):
                estadio = lines[j]
                break

        if desde <= match_date <= ate:
            partidos.append(Partido(
                fonte="campeonatochileno.cl",
                competicao=competicao,
                data=match_date.isoformat(),
                hora=hora,
                mandante=mandante,
                visitante=visitante,
                estadio=estadio,
                rodada=rodada,
                url=url,
            ))

    return dedupe(partidos)


def parse_anfa_page(url: str, html: str, desde: date, ate: date) -> list[Partido]:
    """
    Parser focado no bloco 'Partidos' da ANFA:
    Ex.: Tercera A Nacional 05 JUL 2026 - 12:00 Quintero Unido Aguará FC
    O estádio pode não estar visível na home; quando não aparecer, fica vazio.
    """
    lines = soup_lines(html)
    partidos: list[Partido] = []
    competitions = ("Tercera A", "Tercera A Nacional", "Tercera B", "Tercera B Norte", "Tercera B Centro", "Tercera B Sur")

    for i, line in enumerate(lines):
        dt = parse_anfa_date(line)
        tm = TIME_RE.search(line)
        if not dt or not tm:
            # às vezes competição e data/hora estão em linhas separadas
            continue

        comp = ""
        prefix = line[:tm.start()]
        for c in competitions:
            if c.lower() in prefix.lower():
                comp = c
                break
        if not comp:
            # procura competição nas 2 linhas anteriores
            for k in range(max(0, i - 2), i + 1):
                for c in competitions:
                    if c.lower() in lines[k].lower():
                        comp = c
                        break
                if comp:
                    break
        if not comp:
            comp = "ANFA Tercera División"

        teams = []
        stadium = ""
        for j in range(i + 1, min(i + 8, len(lines))):
            if is_probably_stadium(lines[j]) and not stadium:
                stadium = lines[j]
            elif is_probably_team(lines[j]):
                teams.append(lines[j])
            if len(teams) >= 2:
                break

        if len(teams) >= 2 and desde <= dt <= ate:
            partidos.append(Partido(
                fonte="anfaterceradivision.cl",
                competicao=comp,
                data=dt.isoformat(),
                hora=tm.group(1),
                mandante=teams[0],
                visitante=teams[1],
                estadio=stadium,
                url=url,
            ))

    return dedupe(partidos)


def dedupe(partidos: Iterable[Partido]) -> list[Partido]:
    seen = set()
    out = []
    for p in partidos:
        if p.id in seen:
            continue
        seen.add(p.id)
        out.append(p)
    return out


def load_existing_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


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


def merge_history(new_rows: list[dict], history_path: Path) -> list[dict]:
    old = load_existing_csv(history_path)
    by_id = {r["id"]: r for r in old if r.get("id")}
    for r in new_rows:
        by_id[r["id"]] = r
    return sorted(by_id.values(), key=lambda r: (r.get("data", ""), r.get("hora", ""), r.get("competicao", "")))


def update(dias: int = 45, year: Optional[int] = None) -> list[dict]:
    today = date.today()
    desde = today
    ate = today + timedelta(days=dias)
    year = year or today.year

    all_matches: list[Partido] = []

    for url in CAMPEONATO_CHILENO_URLS:
        try:
            html = fetch(url)
            found = parse_campeonato_chileno_page(url, html, year, desde, ate)
            print(f"[OK] {url} -> {len(found)} jogos")
            all_matches.extend(found)
        except Exception as e:
            print(f"[ERRO] {url}: {e}", file=sys.stderr)

    for url in ANFA_URLS:
        try:
            html = fetch(url)
            found = parse_anfa_page(url, html, desde, ate)
            print(f"[OK] {url} -> {len(found)} jogos")
            all_matches.extend(found)
        except Exception as e:
            print(f"[ERRO] {url}: {e}", file=sys.stderr)

    rows = [p.to_row() for p in dedupe(all_matches)]
    rows = sorted(rows, key=lambda r: (r["data"], r["hora"], r["competicao"], r["mandante"]))

    current_csv = OUT_DIR / "jogos_programados.csv"
    current_json = OUT_DIR / "jogos_programados.json"
    history_csv = OUT_DIR / "historico_jogos.csv"

    write_csv(current_csv, rows)
    current_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    hist = merge_history(rows, history_csv)
    write_csv(history_csv, hist)

    print(f"\nAtualizado: {len(rows)} jogos programados")
    print(f"CSV: {current_csv.resolve()}")
    print(f"JSON: {current_json.resolve()}")
    print(f"Histórico: {history_csv.resolve()}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="executa uma atualização e termina")
    parser.add_argument("--dias", type=int, default=45, help="janela de jogos futuros em dias")
    parser.add_argument("--ano", type=int, default=None, help="ano da temporada, padrão: ano atual")
    args = parser.parse_args()

    # --once fica por compatibilidade; o script sempre executa uma vez.
    update(dias=args.dias, year=args.ano)


if __name__ == "__main__":
    main()
