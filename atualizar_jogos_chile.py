#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper atualizado para jogos programados e recentes do futebol chileno.

Fontes:
- campeonatochileno.cl
- anfaterceradivision.cl
- anfaterceradivision.cl/assets/php/calendario.php
- cf3.cl, para Tercera A e Tercera B Norte/Sur

Saídas:
- data/jogos_programados.csv
- data/jogos_programados.json
- data/historico_jogos.csv

Uso:
    python atualizar_jogos_chile.py --once --dias 180 --dias-atras 14
    python atualizar_jogos_chile.py --once --incluir-passados

Observação:
CF3 muitas vezes mostra partidas já finalizadas sem horário. Nesses casos, o campo
"hora" fica vazio e placar/status vão no campo "extra".
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
from typing import Iterable, Optional, Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "es-CL,es;q=0.9,pt-BR;q=0.8,pt;q=0.7,en;q=0.6",
    "Accept": "text/html,application/json,text/plain,*/*",
    "Referer": "https://www.google.com/",
}

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
MONTHS_ES_ABBR = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

CAMPEONATO_HOME = "https://www.campeonatochileno.cl/"
CAMPEONATO_CHILENO_URLS = [
    "https://www.campeonatochileno.cl/ligas/liga-de-primera-mercado-libre/",
    "https://www.campeonatochileno.cl/ligas/liga-de-ascenso-caixun/",
    "https://www.campeonatochileno.cl/ligas/segunda-la-liga-2d/",
    "https://www.campeonatochileno.cl/ligas/copa-chile-coca-cola-zero-azucar/",
    "https://www.campeonatochileno.cl/ligas/copa-de-la-liga/",
    "https://www.campeonatochileno.cl/ligas/campeonato-femenino/",
    "https://www.campeonatochileno.cl/ligas/ascenso-femenino/",
]

ANFA_URLS = ["https://anfaterceradivision.cl/"]
ANFA_CALENDARIO_URL = "https://anfaterceradivision.cl/assets/php/calendario.php"

CF3_BASE_URLS = [
    "https://cf3.cl/torneo/tercera-a/fecha/13",
    "https://cf3.cl/torneo/tercera-b/grupo-norte/fecha/13",
    "https://cf3.cl/torneo/tercera-b/grupo-sur/fecha/13",
]

TIME_RE = re.compile(r"[-–—]?\s*(\d{1,2}:\d{2})\s*(?:hrs?|h)?", re.I)
DATE_ES_RE = re.compile(
    r"\b(\d{1,2})\s+de\s+"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\b",
    re.I,
)
ANFA_DATE_RE = re.compile(r"\b(\d{1,2})\s+(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)\s+(\d{4})\b", re.I)
DATE_NUM_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
SCORE_RE = re.compile(r"^\d+\s*[-–]\s*\d+$|^\d+\s+\d+$|^[-–]\s*[-–]$|^v/s$|^vs$", re.I)
ONLY_NUMBER_RE = re.compile(r"^\d+$")

NOISE_WORDS = {
    "image", "publicidad", "inicio", "noticias", "tabla de posiciones", "posiciones",
    "estadísticas", "estadisticas", "bases de campeonato", "tribunal", "ver más",
    "ver mas", "read more", "partidos", "fecha", "competición", "competicion",
    "fixture", "programación", "programacion", "clasificación", "clasificacion",
    "ver tabla completa →", "el canal del fútbol de 3ra. división.",
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


def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    return r.text


def clean_text(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    s = re.sub(r"Image:\s*", "", s, flags=re.I).strip()
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
        if low.startswith("©"):
            continue
        lines.append(x)
    return lines


def parse_spanish_date(text: str, year: int) -> Optional[date]:
    m = DATE_ES_RE.search(text)
    if not m:
        return None
    try:
        return date(year, MONTHS_ES[m.group(2).lower()], int(m.group(1)))
    except ValueError:
        return None


def parse_anfa_date(text: str) -> Optional[date]:
    m = ANFA_DATE_RE.search(text)
    if not m:
        return None
    try:
        return date(int(m.group(3)), MONTHS_ES_ABBR[m.group(2).lower()], int(m.group(1)))
    except ValueError:
        return None


def parse_numeric_date(text: str, default_year: int) -> Optional[date]:
    m = DATE_NUM_RE.search(text)
    if not m:
        return None
    d = int(m.group(1))
    mo = int(m.group(2))
    y = int(m.group(3))
    if y < 100:
        y += 2000
    try:
        return date(y, mo, d)
    except ValueError:
        try:
            return date(y, d, mo)
        except ValueError:
            return None


def parse_any_date(text: str, default_year: int) -> Optional[date]:
    return parse_anfa_date(text) or parse_spanish_date(text, default_year) or parse_numeric_date(text, default_year)


def is_probably_stadium(line: str) -> bool:
    low = line.lower()
    stadium_markers = [
        "estadio", "municipal", "mun.", "bicentenario", "sausalito", "claro arena",
        "el cobre", "la portada", "el teniente", "monumental", "la cisterna",
        "francisco sánchez", "francisco sanchez", "huachipato", "nicolás chahuán",
        "nicolas chahuan", "lucio fariña", "lucio farina", "ester roa", "nelson oyarzún",
        "nelson oyarzun", "la florida", "jessica mella", "quilín", "quilin",
        "lo barnechea", "la pintana", "ruben marcos", "rubén marcos", "tucapel",
        "diaguita", "jorge silva", "regional de los andes", "federico schwager",
        "augusto rodríguez", "augusto rodriguez", "atlético municipal", "atletico municipal",
        "el morro", "elías figueroa", "elias figueroa", "san gregorio", "lo blanco",
        "las golondrinas", "felix gallardo", "félix gallardo", "olímpico", "olimpico",
        "santiago bueras", "por definir",
    ]
    return any(x in low for x in stadium_markers)


def is_probably_team(line: str) -> bool:
    line = clean_text(line)
    if not line or len(line) < 2:
        return False
    low = line.lower()
    if low in NOISE_WORDS:
        return False
    if ONLY_NUMBER_RE.match(line):
        return False
    if parse_any_date(line, date.today().year) or TIME_RE.search(line):
        return False
    if SCORE_RE.match(line):
        return False
    if low in {"finalizado", "suspendido", "programado", "por jugar", "postergado"}:
        return False
    if low.startswith(("estadio:", "estadio ", "municipal ", "bicentenario ")):
        return False
    if re.match(r"^jornada\s+\d+", low):
        return False
    if re.match(r"^fecha\s+\d+", low):
        return False
    if re.search(r"\b(arbitro|árbitro|pavez|fernandez|fernández|manzor|moya|ortega|avila|riquelme|duran|durán|yanez|yañez|valenzuela|cisternas|ramirez|ramírez|fuentes|sep[uú]lveda|gamboa|vejar|gilabert)\b", low):
        return False
    return True


def discover_campeonato_liga_urls() -> list[str]:
    urls = set(CAMPEONATO_CHILENO_URLS)
    try:
        html = fetch(CAMPEONATO_HOME)
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(CAMPEONATO_HOME, a["href"]).split("?")[0]
            if "campeonatochileno.cl/ligas/" not in href:
                continue
            ignored = ["sub-11", "sub-12", "sub-13", "sub-14", "sub-15", "sub-16", "sub-17", "sub-18", "sub-20", "formativo", "infantil", "futsal"]
            if any(x in href.lower() for x in ignored):
                continue
            urls.add(href)
    except Exception as e:
        print(f"[AVISO] Não consegui descobrir URLs Campeonato Chileno: {e}", file=sys.stderr)
    return sorted(urls)


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


def in_window(dt: date, desde: date, ate: date, incluir_passados: bool) -> bool:
    return incluir_passados or (desde <= dt <= ate)


def find_team_after(lines: list[str], start: int, max_ahead: int = 12) -> tuple[str, Optional[int]]:
    for j in range(start, min(start + max_ahead, len(lines))):
        if is_probably_team(lines[j]):
            return lines[j], j
    return "", None


def find_stadium_after(lines: list[str], start: int, max_ahead: int = 10) -> str:
    for j in range(start, min(start + max_ahead, len(lines))):
        if is_probably_stadium(lines[j]):
            return re.sub(r"^Estadio:\s*", "", lines[j], flags=re.I).strip()
    return ""


def parse_campeonato_chileno_page(url: str, html: str, year: int, desde: date, ate: date, incluir_passados: bool = False) -> list[Partido]:
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

        if in_window(match_date, desde, ate, incluir_passados):
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


def parse_anfa_home_page(url: str, html: str, year: int, desde: date, ate: date, incluir_passados: bool = False) -> list[Partido]:
    lines = soup_lines(html)
    partidos: list[Partido] = []

    for i, line in enumerate(lines):
        dt = parse_anfa_date(line)
        tm = TIME_RE.search(line)
        if not dt or not tm:
            continue

        text_window = " ".join(lines[max(0, i - 2):i + 3])
        comp = "Tercera A" if "tercera a" in text_window.lower() else "Tercera B" if "tercera b" in text_window.lower() else "ANFA Tercera División"

        teams = []
        stadium = ""
        for j in range(i + 1, min(i + 10, len(lines))):
            if is_probably_stadium(lines[j]) and not stadium:
                stadium = re.sub(r"^Estadio:\s*", "", lines[j], flags=re.I).strip()
            elif is_probably_team(lines[j]):
                teams.append(lines[j])
            if len(teams) >= 2:
                break

        if len(teams) >= 2 and in_window(dt, desde, ate, incluir_passados):
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


def parse_anfa_calendario_html(html: str, year: int, desde: date, ate: date, incluir_passados: bool = False) -> list[Partido]:
    # Parser genérico, mantido como fallback.
    stripped = html.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            return parse_anfa_calendario_json(json.loads(stripped), year, desde, ate, incluir_passados)
        except Exception:
            pass

    soup = BeautifulSoup(html, "html.parser")
    partidos: list[Partido] = []

    for tr in soup.find_all("tr"):
        cells = [clean_text(c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if len(cells) < 3:
            continue

        row_text = " | ".join(cells)
        dt = parse_any_date(row_text, year)
        tm = TIME_RE.search(row_text)
        if not dt or not tm:
            continue

        comp = "Tercera A" if "tercera a" in row_text.lower() else "Tercera B" if "tercera b" in row_text.lower() else "ANFA Tercera División"
        estadio = next((c for c in cells if is_probably_stadium(c)), "")

        mandante, visitante = "", ""
        for c in cells:
            a, b = split_teams(c)
            if a and b:
                mandante, visitante = a, b
                break

        if not mandante or not visitante:
            team_cells = [c for c in cells if is_probably_team(c) and not is_probably_stadium(c) and not TIME_RE.search(c) and not parse_any_date(c, year)]
            if len(team_cells) >= 2:
                mandante, visitante = team_cells[-2], team_cells[-1]

        if mandante and visitante and in_window(dt, desde, ate, incluir_passados):
            partidos.append(Partido(
                fonte="anfaterceradivision.cl/calendario",
                competicao=comp,
                data=dt.isoformat(),
                hora=tm.group(1),
                mandante=mandante,
                visitante=visitante,
                estadio=re.sub(r"^Estadio:\s*", "", estadio, flags=re.I).strip(),
                url=ANFA_CALENDARIO_URL,
                extra="calendario.php",
            ))

    return dedupe(partidos)


def parse_anfa_calendario_json(data: Any, year: int, desde: date, ate: date, incluir_passados: bool) -> list[Partido]:
    if isinstance(data, dict):
        for key in ("data", "aaData", "rows", "partidos", "calendario"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = [data]
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if isinstance(item, list):
            fields = {str(i): clean_text(str(x)) for i, x in enumerate(item)}
        elif isinstance(item, dict):
            fields = {str(k).lower(): clean_text(str(v)) for k, v in item.items()}
        else:
            continue
        text = " ".join(fields.values())
        dt = parse_any_date(text, year)
        tm = TIME_RE.search(text)
        if not dt or not tm:
            continue
        comp = "Tercera A" if "tercera a" in text.lower() else "Tercera B" if "tercera b" in text.lower() else "ANFA Tercera División"
        estadio = next((v for v in fields.values() if is_probably_stadium(v)), "")
        mandante, visitante = "", ""
        for v in fields.values():
            if any(k in v.lower() for k in [" v/s ", " vs ", " contra "]):
                mandante, visitante = split_teams(v)
                break
        if not mandante or not visitante:
            teams = [v for v in fields.values() if is_probably_team(v) and not is_probably_stadium(v)]
            if len(teams) >= 2:
                mandante, visitante = teams[-2], teams[-1]
        if mandante and visitante and in_window(dt, desde, ate, incluir_passados):
            out.append(Partido("anfaterceradivision.cl/calendario", comp, dt.isoformat(), tm.group(1), mandante, visitante, estadio, url=ANFA_CALENDARIO_URL, extra="calendario.php"))
    return dedupe(out)


def split_teams(value: str) -> tuple[str, str]:
    value = clean_text(value)
    patterns = [r"\s+v/s\s+", r"\s+vs\.?\s+", r"\s+[-–—]\s+", r"\s+\bcontra\b\s+"]
    for pat in patterns:
        parts = re.split(pat, value, maxsplit=1, flags=re.I)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            return clean_text(parts[0]), clean_text(parts[1])
    return "", ""


def discover_cf3_urls() -> list[str]:
    """
    CF3 tem links de Jornada 1..N na própria página. A partir das três páginas-base,
    descobre todos os links /torneo/.../fecha/<n>.
    """
    urls = set(CF3_BASE_URLS)
    for base in CF3_BASE_URLS:
        try:
            html = fetch(base)
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = urljoin(base, a["href"]).split("?")[0]
                if "cf3.cl/torneo/" in href and "/fecha/" in href:
                    urls.add(href)
        except Exception as e:
            print(f"[AVISO] Não consegui descobrir jornadas CF3 em {base}: {e}", file=sys.stderr)
    return sorted(urls)


def infer_cf3_competition(url: str, page_text: str = "") -> str:
    low = (url + " " + page_text).lower()
    if "tercera-b/grupo-norte" in low or "tercera b - norte" in low:
        return "Tercera B - Norte"
    if "tercera-b/grupo-sur" in low or "tercera b - sur" in low:
        return "Tercera B - Sur"
    if "tercera-a" in low or "tercera a" in low:
        return "Tercera A"
    return "Tercera División"


def parse_cf3_page(url: str, html: str, year: int, desde: date, ate: date, incluir_passados: bool = False) -> list[Partido]:
    """
    Parser para CF3.
    Estrutura observada:
      04/07/2026
      Lautaro de Buin
      1 - 5
      Comunal Cabrero
      Finalizado
      Estadio: Lautaro de Buin

    Em jogos futuros pode aparecer:
      dd/mm/yyyy
      Time A
      15:00
      Time B
      Programado
      Estadio: ...
    """
    lines = soup_lines(html)
    page_text = " ".join(lines[:40])
    competicao = infer_cf3_competition(url, page_text)
    rodada = ""
    partidos: list[Partido] = []

    for line in lines[:60]:
        m = re.search(r"Jornada\s+\d+", line, re.I)
        if m:
            rodada = m.group(0)
            break

    for i, line in enumerate(lines):
        dt = parse_numeric_date(line, year)
        if not dt:
            continue

        team1, team1_idx = find_team_after(lines, i + 1, 8)
        if team1_idx is None:
            continue

        score_or_time = ""
        score_idx = None
        for j in range(team1_idx + 1, min(team1_idx + 6, len(lines))):
            if SCORE_RE.match(lines[j]) or TIME_RE.search(lines[j]) or lines[j].lower() in {"finalizado", "programado", "suspendido", "postergado"}:
                score_or_time = lines[j]
                score_idx = j
                break

        if score_idx is None:
            team2, team2_idx = find_team_after(lines, team1_idx + 1, 8)
            hora = ""
            placar = ""
        else:
            team2, team2_idx = find_team_after(lines, score_idx + 1, 8)
            tm = TIME_RE.search(score_or_time)
            hora = tm.group(1) if tm and not SCORE_RE.match(score_or_time) else ""
            placar = score_or_time if SCORE_RE.match(score_or_time) else ""

        if team2_idx is None:
            continue

        status = ""
        estadio = ""
        for j in range(team2_idx + 1, min(team2_idx + 8, len(lines))):
            low = lines[j].lower()
            if low in {"finalizado", "programado", "suspendido", "postergado", "por jugar"}:
                status = lines[j]
            if is_probably_stadium(lines[j]):
                estadio = re.sub(r"^Estadio:\s*", "", lines[j], flags=re.I).strip()
                break

        if not estadio:
            estadio = find_stadium_after(lines, team2_idx + 1, 8)

        extra_parts = []
        if placar:
            extra_parts.append(f"placar={placar}")
        if status:
            extra_parts.append(f"status={status}")

        if in_window(dt, desde, ate, incluir_passados):
            partidos.append(Partido(
                fonte="cf3.cl",
                competicao=competicao,
                data=dt.isoformat(),
                hora=hora,
                mandante=team1,
                visitante=team2,
                estadio=estadio,
                rodada=rodada,
                url=url,
                extra="; ".join(extra_parts),
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


def update(dias: int = 180, dias_atras: int = 14, year: Optional[int] = None, incluir_passados: bool = False, no_discover: bool = False) -> list[dict]:
    today = date.today()
    desde = today - timedelta(days=dias_atras)
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
            found = parse_anfa_home_page(url, html, year, desde, ate, incluir_passados=incluir_passados)
            print(f"[OK] ANFA home -> {len(found)} jogos | {url}")
            all_matches.extend(found)
        except Exception as e:
            print(f"[ERRO] {url}: {e}", file=sys.stderr)

    try:
        html = fetch(ANFA_CALENDARIO_URL)
        found = parse_anfa_calendario_html(html, year, desde, ate, incluir_passados=incluir_passados)
        print(f"[OK] ANFA calendario.php -> {len(found)} jogos | {ANFA_CALENDARIO_URL}")
        all_matches.extend(found)
    except Exception as e:
        print(f"[ERRO] {ANFA_CALENDARIO_URL}: {e}", file=sys.stderr)

    cf3_urls = CF3_BASE_URLS if no_discover else discover_cf3_urls()
    print(f"[INFO] URLs CF3: {len(cf3_urls)}")
    for url in cf3_urls:
        try:
            html = fetch(url)
            found = parse_cf3_page(url, html, year, desde, ate, incluir_passados=incluir_passados)
            print(f"[OK] CF3 -> {len(found)} jogos | {url}")
            all_matches.extend(found)
        except Exception as e:
            print(f"[ERRO] {url}: {e}", file=sys.stderr)

    rows = [p.to_row() for p in dedupe(all_matches)]
    rows = sorted(rows, key=lambda r: (r["data"], r.get("hora", ""), r["competicao"], r["mandante"]))

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
    parser.add_argument("--dias", type=int, default=180, help="janela de jogos futuros em dias")
    parser.add_argument("--dias-atras", type=int, default=14, help="janela de jogos recentes em dias, útil para CF3/Tercera")
    parser.add_argument("--ano", type=int, default=None, help="ano da temporada, padrão: ano atual")
    parser.add_argument("--incluir-passados", action="store_true", help="inclui também todos os jogos passados encontrados nas páginas")
    parser.add_argument("--no-discover", action="store_true", help="não descobrir ligas/jornadas automaticamente; usa apenas URLs fixos")
    args = parser.parse_args()

    update(
        dias=args.dias,
        dias_atras=args.dias_atras,
        year=args.ano,
        incluir_passados=args.incluir_passados,
        no_discover=args.no_discover,
    )


if __name__ == "__main__":
    main()
