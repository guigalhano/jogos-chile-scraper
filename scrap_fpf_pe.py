#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper - Federação Pernambucana de Futebol (FPF-PE) - https://www.fpf-pe.com.br/

Confirmado ao vivo em 17/07/2026: a página https://www.fpf-pe.com.br/pt/competicoes
(e a home, que também tem widgets de "Jogos"/"Classificação") carrega os jogos via
JavaScript - o HTML inicial não traz nenhum jogo, só o layout (mesmo padrão já visto
na FMF-MG e na FPF-SP). Por isso este script usa a mesma estratégia genérica já usada
nesses dois: abre a página com Playwright, espera o carregamento dinâmico, e:
  1. Intercepta respostas de rede em busca de JSON com objetos de jogo
     (mandante/visitante/data em qualquer chave reconhecível).
  2. Como reforço/fallback, também extrai jogos do texto renderizado da página
     (get_text linha a linha), pro caso de o widget não usar uma chamada JSON separada
     e montar o HTML direto no servidor-render do client-side (comum em Vue/Nuxt com
     SSR parcial).

⚠️ Não foi possível validar ao vivo QUE campos exatos o JSON de rede desse site usa
(a rede do ambiente onde este script foi escrito não intercepta tráfego de terceiros
fora de busca/fetch pontuais) - o parser de JSON usa nomes de campo genéricos comuns
(Mandante/Visitante/Data/Hora/Estadio em várias variações de maiúsculas/idioma), o
mesmo dicionário de aliases já usado com sucesso na FMF-MG. Rode com --debug-html na
primeira vez e confira data/debug_fpf_pe_html/*.html e *_network.json se os jogos não
baterem.

Uso:
    python scrap_fpf_pe.py --dias 240 --dias-atras 30 --debug-html
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)
DEBUG_DIR = OUT_DIR / "debug_fpf_pe_html"

BASE = "https://www.fpf-pe.com.br"

START_URLS = [
    ("Campeonato Pernambucano", f"{BASE}/pt/competicoes"),
    ("Campeonato Pernambucano", f"{BASE}/pt/home"),
]

FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "pais", "cidade", "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em",
]

HEADERS_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
)

MESES = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}

DATE_NUM_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")
DATE_ISO_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})")
TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
VERSUS_RE = re.compile(r"(.{2,60}?)\s+(?:x|X|×|vs\.?)\s+(.{2,60})")

BAD_NAMES = {
    "federacao pernambucana de futebol", "fpf", "fpf pe", "site oficial",
    "classificacao", "estatisticas", "jogos", "competicoes", "noticias",
    "arbitragem", "credenciamento", "tjd", "a federacao", "regulamento geral",
}


@dataclass
class Partido:
    fonte: str
    competicao: str
    data: str
    hora: str
    mandante: str
    visitante: str
    pais: str = "Brasil"
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


def norm(x: Any) -> str:
    x = unicodedata.normalize("NFD", clean_text(x))
    x = "".join(c for c in x if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", x.lower()).strip()


def is_bad_name(x: str) -> bool:
    s = norm(x)
    if not s or s in BAD_NAMES:
        return True
    if len(clean_text(x)) > 60:
        return True
    return False


def parse_date_any(txt: str) -> str:
    s = clean_text(txt)
    m = DATE_ISO_RE.search(s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except Exception:
            pass
    m = DATE_NUM_RE.search(s)
    if m:
        dia, mes, ano = m.groups()
        ano_i = int(ano)
        if ano_i < 100:
            ano_i += 2000
        try:
            return date(ano_i, int(mes), int(dia)).isoformat()
        except Exception:
            pass
    return ""


def parse_time_any(txt: str) -> str:
    m = TIME_RE.search(clean_text(txt))
    return f"{m.group(1).zfill(2)}:{m.group(2)}" if m else ""


def first_value(obj: dict, keys: list[str]) -> str:
    if not isinstance(obj, dict):
        return ""
    for k in keys:
        if k in obj and clean_text(obj[k]):
            return clean_text(obj[k])
    normalized = {norm(k): v for k, v in obj.items()}
    for want in keys:
        nw = norm(want)
        for nk, val in normalized.items():
            if nw == nk or nw in nk:
                txt = clean_text(val)
                if txt:
                    return txt
    return ""


def obj_to_partido(obj: dict, url: str, competicao_fallback: str) -> Partido | None:
    if not isinstance(obj, dict):
        return None

    mandante = first_value(obj, ["Mandante", "NomeMandante", "TimeMandante", "EquipeMandante", "TimeCasa", "mandante", "home", "homeTeam"])
    visitante = first_value(obj, ["Visitante", "NomeVisitante", "TimeVisitante", "EquipeVisitante", "TimeFora", "visitante", "away", "awayTeam"])
    data = parse_date_any(first_value(obj, ["Data", "DataJogo", "DataHora", "Dia", "date"]))
    hora = parse_time_any(first_value(obj, ["Hora", "Horario", "Horário", "DataHora", "time"]))
    estadio = first_value(obj, ["Estadio", "Estádio", "NomeEstadio", "Local", "venue"])
    cidade = first_value(obj, ["Cidade", "Municipio", "Município", "city"])
    rodada = first_value(obj, ["Rodada", "Fase", "round"])
    comp = first_value(obj, ["Competicao", "Competição", "Campeonato", "competition"]) or competicao_fallback

    if not data:
        joined = " ".join(clean_text(v) for v in obj.values() if isinstance(v, (str, int, float)))
        data = parse_date_any(joined)
        hora = hora or parse_time_any(joined)

    if not (mandante and visitante and data):
        return None
    if is_bad_name(mandante) or is_bad_name(visitante) or mandante == visitante:
        return None

    return Partido(
        fonte="FPF-PE",
        competicao=f"Brasil - Pernambuco - {comp}",
        data=data,
        hora=hora,
        mandante=mandante,
        visitante=visitante,
        cidade=cidade,
        estadio=estadio,
        rodada=rodada,
        url=url,
    )


def walk_json(data: Any, url: str, competicao_fallback: str, out: list[Partido]) -> None:
    if isinstance(data, dict):
        p = obj_to_partido(data, url, competicao_fallback)
        if p:
            out.append(p)
        for v in data.values():
            walk_json(v, url, competicao_fallback, out)
    elif isinstance(data, list):
        for item in data:
            walk_json(item, url, competicao_fallback, out)


def html_to_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text("\n", strip=True)
    lines = []
    for raw in text.splitlines():
        s = clean_text(raw)
        if s and len(s) <= 180:
            lines.append(s)
    return lines


def parse_text_patterns(lines: list[str], url: str, competicao_nome: str) -> list[Partido]:
    out = []
    current_date = ""
    for line in lines:
        dt = parse_date_any(line)
        if dt:
            current_date = dt
        if (" x " in line.lower()) and (parse_date_any(line) or current_date):
            mvs = VERSUS_RE.search(line)
            if not mvs:
                continue
            before = DATE_NUM_RE.sub("", clean_text(mvs.group(1)))
            before = TIME_RE.sub("", before).strip()
            after = TIME_RE.sub("", clean_text(mvs.group(2))).strip()
            mandante, visitante = clean_text(before), clean_text(after)
            data_linha = parse_date_any(line) or current_date
            hora = parse_time_any(line)
            if mandante and visitante and not is_bad_name(mandante) and not is_bad_name(visitante) and mandante != visitante:
                out.append(Partido(
                    fonte="FPF-PE",
                    competicao=f"Brasil - Pernambuco - {competicao_nome}",
                    data=data_linha,
                    hora=hora,
                    mandante=mandante,
                    visitante=visitante,
                    url=url,
                    extra="origem=texto_renderizado",
                ))
    return out


def render_page_collect(competicao_nome: str, url: str, wait_ms: int, debug_html: bool) -> tuple[list[Partido], dict]:
    partidos: list[Partido] = []
    network_debug: list[dict] = []
    todas_urls_vistas: list[str] = []
    info = {"competicao": competicao_nome, "url": url, "jogos_json": 0, "jogos_texto": 0, "erro": "",
            "urls_json_vistas": [], "texto_amostra": ""}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=HEADERS_UA, locale="pt-BR")
        page = context.new_page()

        def on_response(response):
            rurl = response.url
            ct = response.headers.get("content-type", "")
            # Log qualquer resposta de API/AJAX (não só JSON) pra diagnosticar
            # se a chamada nem chega a acontecer, se é bloqueada, ou se
            # retorna erro - o próprio site mostrou "Jogos indisponíveis no
            # momento" numa rodada anterior, o que sugere que a chamada dele
            # está falhando também pro navegador normal, não só pro nosso.
            if any(k in rurl.lower() for k in ["/api/", "ajax", ".json", "webapi", "graphql"]) or "json" in ct.lower():
                todas_urls_vistas.append(f"{rurl} [{response.status}] ct={ct}")
            if "json" not in ct.lower():
                return
            try:
                payload = response.json()
            except Exception:
                return
            before = len(partidos)
            walk_json(payload, rurl, competicao_nome, partidos)
            network_debug.append({"url": rurl, "novos_jogos": len(partidos) - before})

        page.on("response", on_response)

        def on_request_failed(request):
            todas_urls_vistas.append(f"FALHOU: {request.url} [{request.failure}]")

        page.on("requestfailed", on_request_failed)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=70000)
            page.wait_for_timeout(wait_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            # Alguns widgets desse site parecem ser lazy-loaded (só carregam
            # quando entram na viewport, tipo Intersection Observer) - rola a
            # página inteira em passos pra forçar o carregamento antes de
            # capturar o HTML final.
            try:
                altura_total = page.evaluate("document.body.scrollHeight")
                passo = 600
                y = 0
                while y < altura_total:
                    page.evaluate(f"window.scrollTo(0, {y})")
                    page.wait_for_timeout(600)
                    y += passo
                    altura_total = page.evaluate("document.body.scrollHeight")
                page.wait_for_timeout(3000)
            except Exception:
                pass

            info["jogos_json"] = len(partidos)
            info["urls_json_vistas"] = todas_urls_vistas[:40]

            html = page.content()
            if debug_html:
                DEBUG_DIR.mkdir(exist_ok=True)
                slug = re.sub(r"[^a-z0-9]+", "_", url.lower()).strip("_")
                (DEBUG_DIR / f"{slug}.html").write_text(html, encoding="utf-8")
                (DEBUG_DIR / f"{slug}_network.json").write_text(json.dumps(network_debug, ensure_ascii=False, indent=2), encoding="utf-8")

            lines = html_to_lines(html)
            info["texto_amostra"] = " | ".join(lines)[:6000]
            texto_partidos = parse_text_patterns(lines, url, competicao_nome)
            info["jogos_texto"] = len(texto_partidos)
            partidos.extend(texto_partidos)

        except Exception as e:
            info["erro"] = str(e)
        finally:
            browser.close()

    return partidos, info


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


def in_window(p: Partido, desde: date, ate: date) -> bool:
    try:
        dt = date.fromisoformat(p.data)
    except Exception:
        return False
    return desde <= dt <= ate


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
    parser.add_argument("--dias", type=int, default=240)
    parser.add_argument("--dias-atras", type=int, default=30)
    parser.add_argument("--wait-ms", type=int, default=12000)
    parser.add_argument("--debug-html", action="store_true")
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    all_partidos: list[Partido] = []
    debug_pages = []

    for competicao_nome, url in START_URLS:
        partidos, info = render_page_collect(competicao_nome, url, args.wait_ms, args.debug_html)
        debug_pages.append(info)
        partidos = [p for p in partidos if in_window(p, desde, ate)]
        all_partidos.extend(partidos)
        print(f"[OK] {competicao_nome} ({url}): json={info['jogos_json']} texto={info['jogos_texto']} | na janela={len(partidos)} | erro={info['erro']}")

    all_partidos = dedupe_partidos(all_partidos)
    rows_new = [p.to_row() for p in all_partidos]

    (OUT_DIR / "debug_fpf_pe_pages.json").write_text(json.dumps(debug_pages, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "debug_fpf_pe_raw.json").write_text(json.dumps(rows_new, ensure_ascii=False, indent=2), encoding="utf-8")

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    merged_current = merge_rows(load_json_rows(current_json), rows_new)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    merged_history = merge_rows(load_csv_rows(history_csv), rows_new)
    write_csv(history_csv, merged_history)

    print("")
    print(f"Pernambuco (FPF-PE) jogos válidos adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")


if __name__ == "__main__":
    main()
