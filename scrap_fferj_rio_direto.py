#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FFERJ - Scraper direto (Federação de Futebol do Estado do Rio de Janeiro)

Página:
    https://www.fferj.com.br/partidas?visao=dia&tab=agendados&pg=1

A página é renderizada no servidor (Next.js/SSR): o HTML já vem com os
jogos, sem precisar de navegador (Playwright). Cada partida é um link
<a href="/partidas/{id}">...</a> cujo texto (extraído "achatado", sem
tags) segue um padrão fixo e um pouco "cru" por causa de imagem+texto
duplicados no card:

    "SAB 04/07/2613:00h Greminho Futebol ClubeGreminho Futebol Clube"
    "XA.E Piscinão de RamosA.E Piscinão de Ramos"
    " Amador da Capital | Sub-17 | Amador da CapitalFERJ"

Ou seja: DIA_SEMANA DD/MM/AA + HH:MMh (colados) + [ESTÁDIO opcional]
+ nome do mandante (duplicado, colado) + "X" + nome do visitante
(duplicado, colado) + " " + Competição | Categoria | Órgão + "FERJ"
(selo fixo do site) + opcionalmente " VÍDEO".

Este script:
1. Faz requests.get() direto (sem JS) nas páginas paginadas de
   /partidas?tab=agendados&visao=dia&pg=N.
2. Extrai todos os <a href="/partidas/NUMERO"> e usa o texto "achatado".
3. Detecta o nome duplicado do mandante/visitante procurando o maior
   sufixo/prefixo que se repete colado (T+T), o que também separa
   automaticamente um possível nome de estádio que vier antes.
4. Encontra o separador "X" testando cada ocorrência e validando se o
   texto à esquerda termina em nome duplicado (evita falso positivo
   com times cujo nome contenha a letra X).
5. Salva no mesmo formato/arquivos usados pelos outros scrapers do
   projeto (data/jogos_programados.json, .csv e historico_jogos.csv).

IMPORTANTE (versão "segura"):
- Cobre apenas jogos AGENDADOS (tab=agendados). Jogos "ao vivo" (bloco
  destacado no topo da página, com placar) têm formato diferente e são
  ignorados de propósito para não gerar dados incorretos.
- Qualquer card que não bata com o padrão esperado é simplesmente
  pulado (não derruba o scraper).

Requisitos:
    py -m pip install requests beautifulsoup4

Teste:
    py scrap_fferj_rio_direto.py --max-pg 3 --debug-html

Completo:
    py scrap_fferj_rio_direto.py --max-pg 60 --dias 365 --dias-atras 15
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup


OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)
HTML_DIR = OUT_DIR / "debug_fferj_html"

BASE_URL = "https://www.fferj.com.br"
PARTIDAS_URL = f"{BASE_URL}/partidas"

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
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
}

MATCH_HREF_RE = re.compile(r"^/partidas/(\d+)$")

HEADER_RE = re.compile(
    r"^(?P<dow>[A-ZÀ-ÚÃÕ]{3})\s+"
    r"(?P<dia>\d{2})/(?P<mes>\d{2})/(?P<ano>\d{2})"
    r"(?P<hora>\d{2}:\d{2})h\s*"
    r"(?P<rest>.*)$"
)

MIN_TEAM_LEN = 3


@dataclass
class Partido:
    fonte: str
    competicao: str
    data: str
    hora: str
    mandante: str
    visitante: str
    pais: str = "Brasil"
    cidade: str = "Rio de Janeiro"
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


def parse_year(y: str) -> int:
    n = int(y)
    return 2000 + n if n < 100 else n


def split_doubled_suffix(s: str, min_len: int = MIN_TEAM_LEN) -> tuple[str, str]:
    """Encontra o maior T tal que s termina em T+T (colado).
    Retorna (prefixo_antes_do_T+T, T). Se não achar, devolve ("", s)."""
    n = len(s)
    for length in range(n // 2, min_len - 1, -1):
        if s[n - 2 * length:n - length] == s[n - length:]:
            return s[:n - 2 * length].strip(), s[n - length:].strip()
    return "", s.strip()


def split_doubled_prefix(s: str, min_len: int = MIN_TEAM_LEN) -> tuple[str, str]:
    """Encontra o maior T tal que s começa com T+T (colado), seguido de
    espaço ou fim de string. Retorna (T, resto_apos_T+T)."""
    n = len(s)
    for length in range(n // 2, min_len - 1, -1):
        if s[:length] == s[length:2 * length]:
            if 2 * length == n or s[2 * length] == " ":
                return s[:length].strip(), s[2 * length:].lstrip()
    return s.strip(), ""


def find_split_x(rest: str, min_len: int = MIN_TEAM_LEN):
    """Procura a letra 'X' que separa mandante/visitante, validando que o
    texto à esquerda termina em nome duplicado. Retorna
    (indice, estadio, mandante) ou (None, "", "")."""
    for i, ch in enumerate(rest):
        if ch != "X":
            continue
        left = rest[:i].rstrip()
        estadio, mandante = split_doubled_suffix(left, min_len=min_len)
        if mandante and len(mandante) >= min_len:
            return i, estadio, mandante
    return None, "", ""


def parse_info(info: str) -> tuple[str, str, str, bool]:
    """Quebra o bloco final 'Competicao | Categoria | OrgaoFERJ[ VÍDEO]'."""
    parts = [clean_text(p) for p in info.split("|")]
    comp = parts[0] if len(parts) > 0 else ""
    categoria = parts[1] if len(parts) > 1 else ""
    org = parts[2] if len(parts) > 2 else ""

    video = False
    if org.endswith("VÍDEO"):
        video = True
        org = org[:-len("VÍDEO")].strip()
    elif org.endswith("VIDEO"):
        video = True
        org = org[:-len("VIDEO")].strip()

    if org.endswith("FERJ"):
        org = org[:-len("FERJ")].strip()

    return comp, categoria, org, video


def parse_match_text(text: str, match_id: str) -> Partido | None:
    text = clean_text(text)
    m = HEADER_RE.match(text)
    if not m:
        return None

    rest = m.group("rest")
    idx, estadio, mandante = find_split_x(rest)
    if idx is None:
        return None

    right = rest[idx + 1:]
    visitante, info = split_doubled_prefix(right)
    if not visitante or len(visitante) < MIN_TEAM_LEN:
        return None
    if mandante == visitante:
        return None

    comp, categoria, org, video = parse_info(info)

    try:
        ano = parse_year(m.group("ano"))
        data_iso = date(ano, int(m.group("mes")), int(m.group("dia"))).isoformat()
    except Exception:
        return None

    competicao_nome = comp if comp else "Competição não identificada"
    competicao = f"Brasil - FFERJ - {competicao_nome}"
    if categoria:
        competicao += f" - {categoria}"

    extra_parts = [f"codigo_fferj={match_id}"]
    if org:
        extra_parts.append(f"orgao={org}")
    if categoria:
        extra_parts.append(f"categoria={categoria}")
    if video:
        extra_parts.append("video=1")

    return Partido(
        fonte="FFERJ",
        competicao=competicao,
        data=data_iso,
        hora=m.group("hora"),
        mandante=mandante,
        visitante=visitante,
        pais="Brasil",
        cidade="Rio de Janeiro",
        estadio=estadio,
        rodada=categoria,
        url=f"{BASE_URL}/partidas/{match_id}",
        extra="; ".join(extra_parts),
    )


def fetch_page(pg: int, tab: str, session: requests.Session, timeout: int) -> str:
    params = {"visao": "dia", "tab": tab, "pg": pg}
    r = session.get(PARTIDAS_URL, params=params, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text


def extract_matches_from_html(html: str) -> list[Partido]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        mh = MATCH_HREF_RE.match(a["href"])
        if not mh:
            continue
        match_id = mh.group(1)
        text = a.get_text(" ", strip=True)
        p = parse_match_text(text, match_id)
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
    parser.add_argument("--tab", default="agendados", choices=["agendados"],
                         help="Versão segura cobre apenas jogos agendados.")
    parser.add_argument("--max-pg", type=int, default=40)
    parser.add_argument("--dias", type=int, default=365)
    parser.add_argument("--dias-atras", type=int, default=7)
    parser.add_argument("--incluir-passados", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--pausa", type=float, default=0.5)
    parser.add_argument("--debug-html", action="store_true")
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    session = requests.Session()

    all_partidos: list[Partido] = []
    debug_pages = []
    empty_streak = 0

    print(f"[INFO] FFERJ (Rio de Janeiro) - tab={args.tab}")
    print(f"[INFO] Janela: {desde.isoformat()} até {ate.isoformat()}")

    for pg in range(1, args.max_pg + 1):
        try:
            html = fetch_page(pg, args.tab, session, args.timeout)
        except Exception as e:
            print(f"[ERRO] pg={pg}: {e}")
            debug_pages.append({"pg": pg, "erro": str(e), "jogos": 0})
            empty_streak += 1
            if empty_streak >= 2:
                break
            continue

        if args.debug_html:
            HTML_DIR.mkdir(exist_ok=True)
            (HTML_DIR / f"fferj_pg_{pg}.html").write_text(html, encoding="utf-8")

        page_partidos = extract_matches_from_html(html)
        n_hrefs = len(re.findall(r'href="(/partidas/\d+)"', html))

        soup_dbg = BeautifulSoup(html, "html.parser")
        sample_anchors = []
        for a in soup_dbg.find_all("a", href=True)[:60]:
            if MATCH_HREF_RE.match(a["href"]):
                sample_anchors.append({
                    "href": a["href"],
                    "text_space": a.get_text(" ", strip=True)[:300],
                    "text_nosep": a.get_text("", strip=True)[:300],
                    "outer_html": str(a)[:1500],
                })
            if len(sample_anchors) >= 3:
                break

        debug_pages.append({
            "pg": pg,
            "jogos": len(page_partidos),
            "html_len": len(html),
            "n_match_hrefs": n_hrefs,
            "sample_anchors": sample_anchors,
        })

        if not page_partidos:
            empty_streak += 1
            print(f"[--] pg={pg} | sem jogos")
            if empty_streak >= 2:
                print("[INFO] Duas páginas vazias seguidas, encerrando paginação.")
                break
            time.sleep(args.pausa)
            continue

        empty_streak = 0
        window_partidos = [p for p in page_partidos if in_window(p, desde, ate, args.incluir_passados)]
        all_partidos.extend(window_partidos)
        print(f"[OK] pg={pg} | jogos={len(page_partidos)} | na janela={len(window_partidos)}")

        time.sleep(args.pausa)

    all_partidos = dedupe_partidos(all_partidos)
    rows_new = [p.to_row() for p in all_partidos]

    (OUT_DIR / "debug_fferj_rio_pages.json").write_text(json.dumps(debug_pages, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "debug_fferj_rio_raw.json").write_text(json.dumps(rows_new, ensure_ascii=False, indent=2), encoding="utf-8")

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    merged_current = merge_rows(load_json_rows(current_json), rows_new)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    merged_history = merge_rows(load_csv_rows(history_csv), rows_new)
    write_csv(history_csv, merged_history)

    print("")
    print(f"FFERJ jogos válidos adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")
    print("Debug páginas: data/debug_fferj_rio_pages.json")
    print("Debug jogos: data/debug_fferj_rio_raw.json")
    if args.debug_html:
        print("HTML renderizado: data/debug_fferj_html/")


if __name__ == "__main__":
    main()
