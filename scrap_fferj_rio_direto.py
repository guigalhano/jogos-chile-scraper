#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FFERJ - Scraper direto (Federação de Futebol do Estado do Rio de Janeiro)

Página:
    https://www.fferj.com.br/partidas?visao=dia&tab=agendados&pg=1

A página é renderizada no servidor (Next.js/SSR): o HTML já vem com os
jogos, sem precisar de navegador (Playwright). Cada card de partida é
um <a class="game-sumula-card" href="/partidas/{id}"> com estrutura
fixa e bem definida (confirmado inspecionando o HTML real retornado
por requests.get(), não por uma ferramenta de renderização):

    <a class="game-sumula-card ..." href="/partidas/5348">
      <div class="space-x-2 relative">
        <span class="game-card--date">SAB 04/07/26</span>
        <span class="game-card--date">13:00h</span>
      </div>
      <span class="text-12 text-gray-700">ESTÁDIO ...</span>  (opcional)
      <div class="game-sumula-card--matchup">
        <div class="game-sumula-card--matchup__team">
          <img alt="Time Mandante" .../><span>Time Mandante</span>
        </div>
        <div class="...">X</div>  (placar, se já jogado)
        <div class="game-sumula-card--matchup__team">
          <img alt="Time Visitante" .../><span>Time Visitante</span>
        </div>
      </div>
      <div class="text-gray-700 uppercase text-14 my-5">
        <span>Competição</span>
        <span> | Categoria</span>
        <span> | Órgão</span>          (opcional)
        <span class="bg-primary-dark ...">FERJ</span>  (selo da fonte)
      </div>
    </a>

Este script:
1. Faz requests.get() direto (sem JS) nas páginas paginadas de
   /partidas?tab=agendados&visao=dia&pg=N.
2. Localiza cada <a class="game-sumula-card"> e extrai os campos pelos
   seletores/estrutura acima (não por regex em texto achatado, que é
   frágil pois nomes de time/estádio têm capitalização inconsistente).
3. Salva no mesmo formato/arquivos usados pelos outros scrapers do
   projeto (data/jogos_programados.json, .csv e historico_jogos.csv).

IMPORTANTE (versão "segura"):
- Cobre apenas jogos AGENDADOS (tab=agendados). Cards "AO VIVO" (sem os
  dois <span class="game-card--date">, com placar no lugar do "X") têm
  estrutura diferente e são ignorados de propósito.
- Qualquer card que não bata com a estrutura esperada é simplesmente
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

DATE_SPAN_RE = re.compile(
    r"^(?P<dow>[A-ZÀ-ÚÃÕ]{3})\s+(?P<dia>\d{2})/(?P<mes>\d{2})/(?P<ano>\d{2})$"
)
TIME_SPAN_RE = re.compile(r"^(?P<hora>\d{2}:\d{2})h$")


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


def has_class(tag, name: str) -> bool:
    classes = tag.get("class") or []
    return name in classes


def parse_card(a, debug_errors: list) -> Partido | None:
    href = a.get("href", "")
    mh = MATCH_HREF_RE.match(href)
    if not mh:
        return None
    match_id = mh.group(1)

    # --- data/hora: precisam dos dois <span class="game-card--date">.
    # Cards "AO VIVO" não têm essa dupla (têm um badge diferente), então
    # já ficam de fora aqui de propósito (versão segura = só agendados).
    date_spans = a.find_all("span", class_="game-card--date")
    if len(date_spans) != 2:
        return None

    dm = DATE_SPAN_RE.match(clean_text(date_spans[0].get_text()))
    tm = TIME_SPAN_RE.match(clean_text(date_spans[1].get_text()))
    if not dm or not tm:
        debug_errors.append({"match_id": match_id, "erro": "data_hora_invalida"})
        return None

    try:
        ano = parse_year(dm.group("ano"))
        data_iso = date(ano, int(dm.group("mes")), int(dm.group("dia"))).isoformat()
    except Exception:
        debug_errors.append({"match_id": match_id, "erro": "data_invalida"})
        return None
    hora = tm.group("hora")

    # --- estádio (opcional): <span class="text-12 ...">ESTÁDIO ...</span>
    estadio = ""
    for span in a.find_all("span"):
        if has_class(span, "text-12"):
            txt = clean_text(span.get_text(" "))
            if txt.upper().startswith("ESTÁDIO") or txt.upper().startswith("ESTADIO"):
                estadio = txt
            break

    # --- mandante/visitante: dois game-sumula-card--matchup__team
    matchup = a.find("div", class_="game-sumula-card--matchup")
    if not matchup:
        debug_errors.append({"match_id": match_id, "erro": "sem_matchup"})
        return None
    team_divs = matchup.find_all("div", class_="game-sumula-card--matchup__team")
    if len(team_divs) != 2:
        debug_errors.append({"match_id": match_id, "erro": f"n_times={len(team_divs)}"})
        return None

    def team_name(div):
        span = div.find("span")
        if span:
            return clean_text(span.get_text())
        img = div.find("img")
        if img and img.get("alt"):
            return clean_text(img["alt"])
        return ""

    mandante = team_name(team_divs[0])
    visitante = team_name(team_divs[1])
    if not mandante or not visitante or mandante == visitante:
        debug_errors.append({"match_id": match_id, "erro": "times_invalidos"})
        return None

    # --- competição / categoria / órgão / fonte:
    # <div class="text-gray-700 uppercase ..."><span>Comp</span>
    #   <span> | Categoria</span><span> | Orgao</span>
    #   <span class="bg-primary-dark ...">FERJ</span></div>
    info_div = None
    for div in a.find_all("div"):
        if has_class(div, "text-gray-700") and has_class(div, "uppercase"):
            info_div = div
            break

    comp, categoria, org, fonte_tag = "", "", "", ""
    if info_div:
        spans = info_div.find_all("span", recursive=False)
        texts = [clean_text(s.get_text(" ")).lstrip("|").strip() for s in spans]
        if spans and has_class(spans[-1], "bg-primary-dark"):
            fonte_tag = texts[-1]
            texts = texts[:-1]

    # A FFERJ lista também jogos de clubes afiliados (ex.: Flamengo) em
    # competições nacionais, marcados com o selo "CBF" em vez de "FERJ".
    # Esses não são organizados pela federação, não têm estádio/cidade
    # reais nesta página (fica "Rio de Janeiro" fixo, o que é errado
    # quando o jogo é em outro estado), e já são cobertos com dados
    # corretos pelo scraper oficial da CBF. Por isso pulamos aqui para
    # não duplicar com localização errada.
    if clean_text(fonte_tag).strip().upper() == "CBF":
        debug_errors.append({"match_id": match_id, "erro": "pulado_fonte_tag_cbf"})
        return None
        if len(texts) > 0:
            comp = texts[0]
        if len(texts) > 1:
            categoria = texts[1]
        if len(texts) > 2:
            org = texts[2]

    video = "VÍDEO" in a.get_text() or "VIDEO" in a.get_text()

    competicao_nome = comp if comp else "Competição não identificada"
    competicao = f"Brasil - FFERJ - {competicao_nome}"
    if categoria:
        competicao += f" - {categoria}"

    extra_parts = [f"codigo_fferj={match_id}"]
    if org:
        extra_parts.append(f"orgao={org}")
    if fonte_tag:
        extra_parts.append(f"fonte_tag={fonte_tag}")
    if categoria:
        extra_parts.append(f"categoria={categoria}")
    if video:
        extra_parts.append("video=1")

    return Partido(
        fonte="FFERJ",
        competicao=competicao,
        data=data_iso,
        hora=hora,
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


def extract_matches_from_html(html: str, debug_errors: list) -> list[Partido]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        if not has_class(a, "game-sumula-card"):
            continue
        if not MATCH_HREF_RE.match(a["href"]):
            continue
        p = parse_card(a, debug_errors)
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
    debug_errors: list = []
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

        page_partidos = extract_matches_from_html(html, debug_errors)
        n_hrefs = len(re.findall(r'href="(/partidas/\d+)"', html))
        debug_pages.append({"pg": pg, "jogos": len(page_partidos), "n_match_hrefs": n_hrefs})

        if not page_partidos:
            empty_streak += 1
            print(f"[--] pg={pg} | sem jogos | hrefs={n_hrefs}")
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
    (OUT_DIR / "debug_fferj_rio_errors.json").write_text(json.dumps(debug_errors, ensure_ascii=False, indent=2), encoding="utf-8")
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
    print("Debug erros: data/debug_fferj_rio_errors.json")
    print("Debug jogos: data/debug_fferj_rio_raw.json")
    if args.debug_html:
        print("HTML renderizado: data/debug_fferj_html/")


if __name__ == "__main__":
    main()
