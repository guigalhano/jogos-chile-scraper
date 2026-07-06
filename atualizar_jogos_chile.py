#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper atualizado para jogos programados do futebol chileno.

Fontes:
- campeonatochileno.cl
- anfaterceradivision.cl

Agora inclui, entre outras:
- segunda-la-liga-2d
- campeonato-femenino
- copa-de-la-liga
- ascenso-femenino

Saídas:
- data/jogos_programados.csv
- data/jogos_programados.json
- data/historico_jogos.csv

Uso:
    python atualizar_jogos_chile.py --once --dias 90

Para pegar todo o ano, use:
    python atualizar_jogos_chile.py --once --dias 365
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

# URLs fixas importantes. O script também tenta descobrir outras ligas automaticamente.
CAMPEONATO_CHILENO_URLS = [
    "https://www.campeonatochileno.cl/ligas/liga-de-primera-mercado-libre/",
    "https://www.campeonatochileno.cl/ligas/liga-de-ascenso-caixun/",
    "https://www.campeonatochileno.cl/ligas/segunda-la-liga-2d/",
    "https://www.campeonatochileno.cl/ligas/copa-chile-coca-cola-zero-azucar/",
    "https://www.campeonatochileno.cl/ligas/copa-de-la-liga/",
    "https://www.campeonatochileno.cl/ligas/campeonato-femenino/",
    "https://www.campeonatochileno.cl/ligas/ascenso-femenino/",
]

CAMPEONATO_HOME = "https://www.campeonatochileno.cl/"

ANFA_URLS = [
    "https://anfaterceradivision.cl/",
]

TIME_RE = re.compile(r"[-–—]?\s*(\d{1,2}:\d{2})\s*hrs?", re.I)
DATE_ES_RE = re.compile(
    r"\b(\d{1,2})\s+de\s+"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\b",
    re.I,
)
ANFA_DATE_RE = re.compile(r"\b(\d{1,2})\s+(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)\s+(\d{4})\b", re.I)
SCORE_RE = re.compile(r"^\d+\s*[-–]\s*\d+$|^\d+\s+\d+$|^[-–]\s*[-–]$|^v/s$|^vs$", re.I)
ONLY_NUMBER_RE = re.compile(r"^\d+$")
NOISE_WORDS = {
    "image", "tabla de posiciones", "posiciones", "estadísticas", "estadisticas", "noticias",
    "bases de campeonato", "tribunal", "ver más", "ver mas", "read more", "partidos",
    "fecha", "competición", "competicion", "fixture", "programación", "programacion",
    "revisa todas las fechas", "campeonatos históricos", "campeonatos historicos",
    "todas las noticias", "ver todas las noticias", "formativo nacional", "formativo femenino",
    "copa futuro", "infantíl", "infantil", "futsal", "min. sub 21",
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
    r = requests.get(url, headers=HEADERS, timeout=35)
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


def discover_campeonato_liga_urls() -> list[str]:
    """
    Descobre links /ligas/ no menu/home para reduzir risco de faltar campeonato.
    Mantém os URLs fixos acima mesmo que a descoberta falhe.
    """
    urls = set(CAMPEONATO_CHILENO_URLS)
    try:
        html = fetch(CAMPEONATO_HOME)
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(CAMPEONATO_HOME, a["href"])
            if "campeonatochileno.cl/ligas/" not in href:
                continue
            # Evita algumas categorias formativas se você quiser só adultos/profissionais.
            # Se quiser TUDO, comente o bloco abaixo.
            ignored = [
                "sub-11", "sub-12", "sub-13", "sub-14", "sub-15", "sub-16", "sub-17",
                "sub-18", "sub-20", "formativo", "infantil", "futsal",
            ]
            if any(x in href.lower() for x in ignored):
                continue
            urls.add(href.split("?")[0])
    except Exception as e:
        print(f"[AVISO] Não consegui descobrir URLs automaticamente: {e}", file=sys.stderr)

    return sorted(urls)


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
    if ONLY_NUMBER_RE.match(line):
        return False
    if DATE_ES_RE.search(line) or ANFA_DATE_RE.search(line) or TIME_RE.search(line):
        return False
    if SCORE_RE.match(line):
        return False
    if re.match(r"^fecha\s+\d+", low):
        return False
    if low.startswith(("estadio ", "municipal ", "bicentenario ", "santa ", "sausalito", "claro arena")):
        return False
    # árbitros / ruído comum após estádio
    if re.search(r"\b(arbitro|árbitro|pavez|fernandez|fernández|manzor|moya|ortega|avila|riquelme|duran|durán|yanez|yañez|valenzuela|cisternas|ramirez|ramírez|fuentes|sep[uú]lveda|gamboa|vejar|gilabert)\b", low):
        return False
    # sanção não é time
    if "sanción" in low or "sancion" in low:
        return False
    return True


def is_probably_stadium(line: str) -> bool:
    low = line.lower()
    stadium_markers = [
        "estadio", "municipal", "bicentenario", "sausalito", "claro arena",
        "el cobre", "la portada", "el teniente", "monumental", "la cisterna",
        "francisco sánchez", "francisco sanchez", "huachipato", "nicolás chahuán",
        "nicolas chahuan", "lucio fariña", "lucio farina", "ester roa", "nelson oyarzún",
        "nelson oyarzun", "la florida", "jessica mella", "quilín", "quilin",
        "lo barnechea", "la pintana", "ruben marcos", "rubén marcos", "tucapel",
        "diaguitas", "jorge silva", "regional de los andes", "federico schwager",
        "augusto rodríguez", "augusto rodriguez", "atlético municipal", "atletico municipal",
    ]
    return any(x in low for x in stadium_markers)


def infer_competition_from_url(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1]
    names = {
        "liga-de-primera-mercado-libre": "Liga de Primera Mercado Libre",
        "liga-de-ascenso-caixun": "Liga de Ascenso Caixun",
        "segunda-la-liga-2d": "Liga de Segunda Panini",
        "copa-chile-coca-cola-zero-azucar": "Copa Chile Coca-Cola Zero Azúcar",
        "copa-de-la-liga": "Copa de la Liga",
        "campeonato-femenino": "Liga Femenina",
        "ascenso-femenino": "Ascenso Femenino",
    }
    return names.get(slug, slug.replace("-", " ").title())


def find_team_after(lines: list[str], start: int, max_ahead: int = 12) -> tuple[str, Optional[int]]:
    for j in range(start, min(start + max_ahead, len(lines))):
        if is_probably_team(lines[j]):
            return lines[j], j
    return "", None


def find_stadium_after(lines: list[str], start: int, max_ahead: int = 10) -> str:
    for j in range(start, min(start + max_ahead, len(lines))):
        if is_probably_stadium(lines[j]):
            return lines[j]
    return ""


def parse_campeonato_chileno_page(url: str, html: str, year: int, desde: date, ate: date, incluir_passados: bool = False) -> list[Partido]:
    """
    Parser por linhas para páginas de Campeonato Chileno.
    O HTML dessas páginas traz blocos como:
    Fecha X / data / hora / mandante / placar ou vs / visitante / estádio / árbitro.
    """
    lines = soup_lines(html)
    competicao = infer_competition_from_url(url)
    partidos: list[Partido] = []
    rodada = ""

    for i, line in enumerate(lines):
        if re.match(r"^Fecha\s+\d+", line, re.I):
            rodada = line
            continue

        match_date = parse_spanish_date(line, year)
        if not match_date:
            continue

        # hora: geralmente na mesma linha ou uma das 3 seguintes
        hora = ""
        time_idx = None
        for j in range(i, min(i + 5, len(lines))):
            tm = TIME_RE.search(lines[j])
            if tm:
                hora = tm.group(1)
                time_idx = j
                break
        if time_idx is None:
            continue

        mandante, mandante_idx = find_team_after(lines, time_idx + 1, 12)
        if mandante_idx is None:
            continue

        visitante, visitante_idx = find_team_after(lines, mandante_idx + 1, 12)
        if visitante_idx is None:
            continue

        estadio = find_stadium_after(lines, visitante_idx + 1, 12)

        if incluir_passados or (desde <= match_date <= ate):
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


def parse_anfa_page(url: str, html: str, desde: date, ate: date, incluir_passados: bool = False) -> list[Partido]:
    """
    Parser focado no bloco 'Partidos' da ANFA:
    Ex.: Tercera A Nacional 05 JUL 2026 - 12:00 Quintero Unido Aguará FC
    """
    lines = soup_lines(html)
    partidos: list[Partido] = []
    competitions = (
        "Tercera A Nacional", "Tercera A", "Tercera B Norte",
        "Tercera B Centro", "Tercera B Sur", "Tercera B"
    )

    for i, line in enumerate(lines):
        dt = parse_anfa_date(line)
        tm = TIME_RE.search(line)
        if not dt or not tm:
            continue

        comp = ""
        prefix = line[:tm.start()]
        for c in competitions:
            if c.lower() in prefix.lower():
                comp = c
                break
        if not comp:
            comp = "ANFA Tercera División"

        teams = []
        stadium = ""
        for j in range(i + 1, min(i + 10, len(lines))):
            if is_probably_stadium(lines[j]) and not stadium:
                stadium = lines[j]
            elif is_probably_team(lines[j]):
                teams.append(lines[j])
            if len(teams) >= 2:
                break

        if len(teams) >= 2 and (incluir_passados or desde <= dt <= ate):
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


def update(dias: int = 90, year: Optional[int] = None, incluir_passados: bool = False, no_discover: bool = False) -> list[dict]:
    today = date.today()
    desde = today
    ate = today + timedelta(days=dias)
    year = year or today.year

    all_matches: list[Partido] = []

    campeonato_urls = CAMPEONATO_CHILENO_URLS if no_discover else discover_campeonato_liga_urls()
    print(f"[INFO] URLs Campeonato Chileno: {len(campeonato_urls)}")

    for url in campeonato_urls:
        try:
            html = fetch(url)
            found = parse_campeonato_chileno_page(url, html, year, desde, ate, incluir_passados=incluir_passados)
            print(f"[OK] {infer_competition_from_url(url)} -> {len(found)} jogos | {url}")
            all_matches.extend(found)
        except Exception as e:
            print(f"[ERRO] {url}: {e}", file=sys.stderr)

    for url in ANFA_URLS:
        try:
            html = fetch(url)
            found = parse_anfa_page(url, html, desde, ate, incluir_passados=incluir_passados)
            print(f"[OK] ANFA -> {len(found)} jogos | {url}")
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

    print(f"\nAtualizado: {len(rows)} jogos")
    print(f"Janela: {'todos os passados também' if incluir_passados else f'{desde.isoformat()} até {ate.isoformat()}'}")
    print(f"CSV: {current_csv.resolve()}")
    print(f"JSON: {current_json.resolve()}")
    print(f"Histórico: {history_csv.resolve()}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="executa uma atualização e termina")
    parser.add_argument("--dias", type=int, default=90, help="janela de jogos futuros em dias")
    parser.add_argument("--ano", type=int, default=None, help="ano da temporada, padrão: ano atual")
    parser.add_argument("--incluir-passados", action="store_true", help="inclui também jogos passados encontrados nas páginas")
    parser.add_argument("--no-discover", action="store_true", help="não descobrir ligas automaticamente; usa apenas URLs fixos")
    args = parser.parse_args()

    update(
        dias=args.dias,
        year=args.ano,
        incluir_passados=args.incluir_passados,
        no_discover=args.no_discover,
    )


if __name__ == "__main__":
    main()
