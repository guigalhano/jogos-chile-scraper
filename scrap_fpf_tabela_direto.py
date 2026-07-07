#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FPF - Scraper direto da página Competições/Tabela.aspx

Página:
https://futebolpaulista.com.br/competicoes/Tabela.aspx

A página usa templates Angular/JS, por exemplo:
  {{item.NomePopularMandante}}
  {{item.NomePopularVisitante}}
  {{item.Data}}
  {{item.Horario}}
  {{item.Municipio}}

Logo, os jogos são carregados por JavaScript/API.

Instalação:
    py -m pip install playwright requests beautifulsoup4
    py -m playwright install chromium

Diagnóstico:
    py scrap_fpf_tabela_direto.py --debug-html --wait-ms 15000

Tentar interagir com filtros:
    py scrap_fpf_tabela_direto.py --interagir --ano 2026 --debug-html --wait-ms 15000
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


URL = "https://futebolpaulista.com.br/competicoes/Tabela.aspx"

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

DEBUG_REQUESTS = OUT_DIR / "debug_fpf_tabela_requests.json"
DEBUG_PAYLOADS = OUT_DIR / "debug_fpf_tabela_payloads.json"
DEBUG_JOGOS = OUT_DIR / "debug_fpf_tabela_jogos_raw.json"
DEBUG_HTML = OUT_DIR / "debug_fpf_tabela_page.html"
DEBUG_LINES = OUT_DIR / "debug_fpf_tabela_page_lines.txt"

JOGOS_JSON = OUT_DIR / "jogos_programados.json"
JOGOS_CSV = OUT_DIR / "jogos_programados.csv"
HIST_CSV = OUT_DIR / "historico_jogos.csv"

FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "pais", "cidade", "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    )
}

DATE_BR_RE = re.compile(r"\b(?P<dia>\d{1,2})/(?P<mes>\d{1,2})/(?P<ano>\d{2,4})\b")
DATE_ISO_RE = re.compile(r"\b(?P<ano>20\d{2})-(?P<mes>\d{2})-(?P<dia>\d{2})")
TIME_RE = re.compile(r"\b(?P<hora>\d{1,2}:\d{2})\b")


@dataclass
class Jogo:
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


def parse_year(y: str) -> int:
    n = int(y)
    return 2000 + n if n < 100 else n


def parse_date_any(value: Any) -> str:
    s = clean_text(value)
    if not s:
        return ""

    m = DATE_ISO_RE.search(s)
    if m:
        try:
            return date(int(m.group("ano")), int(m.group("mes")), int(m.group("dia"))).isoformat()
        except Exception:
            pass

    m = DATE_BR_RE.search(s)
    if m:
        try:
            return date(parse_year(m.group("ano")), int(m.group("mes")), int(m.group("dia"))).isoformat()
        except Exception:
            pass

    return ""


def parse_time_any(value: Any) -> str:
    m = TIME_RE.search(clean_text(value))
    return m.group("hora") if m else ""


def first_value(obj: dict, keys: list[str]) -> str:
    if not isinstance(obj, dict):
        return ""

    lower_map = {str(k).lower(): v for k, v in obj.items()}

    for k in keys:
        if k in obj and clean_text(obj[k]):
            return clean_text(obj[k])

    for want in keys:
        want_l = want.lower()
        for k, v in lower_map.items():
            if want_l == k or want_l in k:
                txt = clean_text(v)
                if txt:
                    return txt

    return ""


def looks_like_game_obj(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False

    keys = {str(k).lower() for k in obj.keys()}
    joined = " ".join(keys)

    has_home = any(x in joined for x in ["mandante", "nomepopularmandante"])
    has_away = any(x in joined for x in ["visitante", "nomepopularvisitante"])
    has_date_or_number = any(x in joined for x in ["data", "horario", "horário", "numero", "rodada"])

    return has_home and has_away and has_date_or_number


def object_to_game(obj: dict, source_url: str, fallback_comp: str = "FPF") -> Jogo | None:
    mandante = first_value(obj, [
        "NomePopularMandante", "Mandante", "ClubeMandante", "NomeMandante", "EquipeMandante"
    ])
    visitante = first_value(obj, [
        "NomePopularVisitante", "Visitante", "ClubeVisitante", "NomeVisitante", "EquipeVisitante"
    ])

    data = parse_date_any(first_value(obj, ["Data", "DataJogo", "DataPartida", "Dia"]))
    hora = parse_time_any(first_value(obj, ["Horario", "Horário", "Hora", "HoraJogo"]))

    estadio = first_value(obj, ["Estadio", "Estádio", "NomePopularEstadio", "NomeEstadio", "Local"])
    cidade = first_value(obj, ["Municipio", "Município", "Cidade"])
    rodada = first_value(obj, ["Rodada"])
    numero = first_value(obj, ["Numero", "Número", "Jogo", "NumeroJogo"])

    comp = first_value(obj, [
        "Campeonato", "DescricaoCampeonato", "Competicao", "Competição",
        "CampeonatoDescricao", "Descricao"
    ]) or fallback_comp

    categoria = first_value(obj, ["Categoria"])
    if categoria and categoria.lower() not in comp.lower():
        comp = f"{comp} - {categoria}"

    if not (mandante and visitante):
        return None

    extra = [
        "pais=Brasil",
        "estado=São Paulo",
        "fonte=Tabela.aspx",
    ]
    if numero:
        extra.append(f"jogo_numero={numero}")

    for k in ["Grupo", "GrupoObservacao", "Fase", "NumFase", "CanaisTransmissao", "Suspencao", "DescricaoAlteracao"]:
        v = first_value(obj, [k])
        if v:
            extra.append(f"{k}={v}")

    return Jogo(
        fonte="FPF",
        competicao=f"Brasil - FPF - {comp}",
        data=data,
        hora=hora,
        mandante=mandante,
        visitante=visitante,
        pais="Brasil",
        cidade=cidade,
        estadio=estadio,
        rodada=f"Rodada {rodada}" if rodada and not str(rodada).lower().startswith("rodada") else rodada,
        url=source_url,
        extra="; ".join(extra),
    )


def walk_json_for_games(data: Any, source_url: str, fallback_comp: str = "FPF") -> list[Jogo]:
    found: list[Jogo] = []

    if isinstance(data, dict):
        if looks_like_game_obj(data):
            jogo = object_to_game(data, source_url, fallback_comp=fallback_comp)
            if jogo:
                found.append(jogo)

        for v in data.values():
            found.extend(walk_json_for_games(v, source_url, fallback_comp=fallback_comp))

    elif isinstance(data, list):
        for item in data:
            found.extend(walk_json_for_games(item, source_url, fallback_comp=fallback_comp))

    return found


def html_to_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")

    lines = []
    for raw in soup.get_text("\n", strip=True).splitlines():
        s = clean_text(raw)
        if s:
            lines.append(s)
    return lines


def dedupe_games(games: list[Jogo]) -> list[Jogo]:
    seen = set()
    out = []
    for g in games:
        if not (g.mandante and g.visitante):
            continue
        if g.id in seen:
            continue
        seen.add(g.id)
        out.append(g)
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
        row.get("estadio", ""), row.get("rodada", "")
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def merge_rows(existing: list[dict], new_rows: list[dict]) -> list[dict]:
    by_id = {}
    for r in existing + new_rows:
        if not (r.get("mandante") and r.get("visitante")):
            continue
        if not r.get("data"):
            continue
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


def interact_with_page(page, ano: int | None = None) -> None:
    for txt in ["Aceitar", "OK", "Concordo"]:
        try:
            page.get_by_text(txt, exact=True).click(timeout=1500)
            page.wait_for_timeout(800)
            break
        except Exception:
            pass

    if ano:
        try:
            selects = page.locator("select")
            for si in range(min(selects.count(), 8)):
                opts = selects.nth(si).locator("option")
                for oi in range(min(opts.count(), 80)):
                    try:
                        label = clean_text(opts.nth(oi).inner_text(timeout=300))
                        value = opts.nth(oi).get_attribute("value")
                        if str(ano) in label or str(ano) == clean_text(value):
                            if value is not None:
                                selects.nth(si).select_option(value=value, timeout=2000)
                                page.wait_for_timeout(1500)
                    except Exception:
                        pass
        except Exception:
            pass

    for label in ["Filtrar", "Buscar", "Pesquisar"]:
        try:
            page.get_by_text(label, exact=True).click(timeout=2000)
            page.wait_for_timeout(2500)
        except Exception:
            pass

    try:
        selects = page.locator("select")
        for si in range(min(selects.count(), 6)):
            opts = selects.nth(si).locator("option")
            count = min(opts.count(), 40)
            for oi in range(count):
                try:
                    value = opts.nth(oi).get_attribute("value")
                    label = clean_text(opts.nth(oi).inner_text(timeout=300))
                    if value and label and "todos" not in label.lower() and "rodadas" not in label.lower():
                        selects.nth(si).select_option(value=value, timeout=1500)
                        page.wait_for_timeout(1200)
                        break
                except Exception:
                    pass
    except Exception:
        pass

    for label in ["Filtrar", "Buscar", "Pesquisar"]:
        try:
            page.get_by_text(label, exact=True).click(timeout=2000)
            page.wait_for_timeout(2500)
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=URL)
    parser.add_argument("--ano", type=int, default=2026)
    parser.add_argument("--wait-ms", type=int, default=12000)
    parser.add_argument("--interagir", action="store_true")
    parser.add_argument("--debug-html", action="store_true")
    args = parser.parse_args()

    requests_debug: list[dict] = []
    payloads_debug: list[dict] = []
    games: list[Jogo] = []

    print(f"[INFO] Abrindo: {args.url}")
    print(f"[INFO] Ano alvo: {args.ano}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="pt-BR",
            ignore_https_errors=True,
        )
        page = context.new_page()

        def on_response(response):
            url = response.url
            status = response.status
            ct = response.headers.get("content-type", "")

            row = {
                "url": url,
                "status": status,
                "content_type": ct,
                "interessante": False,
                "jogos_detectados": 0,
            }

            lower_url = url.lower()
            interesting = (
                "futebolpaulista.com.br" in lower_url
                and any(x in lower_url for x in ["compet", "tabela", "jogo", "rodada", "campeonato", "handler", "ashx", "api"])
            )

            if interesting or any(x in ct.lower() for x in ["json", "text", "html", "javascript"]):
                row["interessante"] = interesting
                try:
                    txt = response.text()
                    sample = clean_text(txt[:600])
                    row["sample"] = sample

                    try:
                        data = json.loads(txt)
                        found = walk_json_for_games(data, url)
                        row["jogos_detectados"] = len(found)
                        if found:
                            games.extend(found)
                            payloads_debug.append({
                                "url": url,
                                "content_type": ct,
                                "tipo": "json",
                                "jogos_detectados": len(found),
                                "sample": sample,
                            })
                    except Exception:
                        pass
                except Exception as e:
                    row["read_error"] = str(e)

            requests_debug.append(row)

        page.on("response", on_response)

        page.goto(args.url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(args.wait_ms)

        # FIX: em vez de tentar clicar em selects/botões da UI (frágil e
        # lento), chama diretamente os endpoints reais descobertos via
        # interceptação de rede: ListarTodosCampeonatosExercicio.ashx lista
        # todos os campeonatos com seus IdCampeonato, e ListarTabela.ashx
        # aceita ?IdCampeonato=X diretamente (a chamada original usava
        # IdJogo=null, que a própria API retorna como "Nenhum filtro
        # informado" — o parâmetro certo é IdCampeonato).
        diag = {"etapa": "inicio"}
        try:
            resp = page.request.get(
                "https://futebolpaulista.com.br/Handlers/Competicoes/ListarTodosCampeonatosExercicio.ashx"
            )
            diag["status_lista_campeonatos"] = resp.status
            diag["texto_bruto_lista_campeonatos"] = clean_text(resp.text())[:800]
            payload = resp.json()
            campeonatos = payload.get("Retorno") or []
            diag["n_campeonatos"] = len(campeonatos)
            print(f"[INFO] Campeonatos encontrados via API direta: {len(campeonatos)}")

            for camp in campeonatos:
                id_camp = camp.get("IdCampeonato")
                nome_camp = camp.get("DescricaoSite") or camp.get("Campeonato") or f"Campeonato {id_camp}"
                if not id_camp:
                    continue
                try:
                    r2 = page.request.get(
                        f"https://futebolpaulista.com.br/Handlers/Competicoes/ListarTabela.ashx?IdCampeonato={id_camp}"
                    )
                    txt2 = r2.text()
                    payloads_debug.append({
                        "url": r2.url,
                        "campeonato": nome_camp,
                        "status": r2.status,
                        "sample": clean_text(txt2[:600]),
                    })
                    data2 = json.loads(txt2)
                    found2 = walk_json_for_games(data2, r2.url, fallback_comp=nome_camp)
                    print(f"  - {nome_camp} (Id={id_camp}): {len(found2)} jogos")
                    games.extend(found2)
                except Exception as e:
                    payloads_debug.append({"campeonato": nome_camp, "erro": str(e)})
                    print(f"[WARN] Falha ao buscar tabela do campeonato {nome_camp} ({id_camp}): {e}")
                page.wait_for_timeout(400)
        except Exception as e:
            diag["erro_geral"] = str(e)
            print(f"[WARN] Falha ao buscar lista de campeonatos via API direta: {e}")

        (OUT_DIR / "debug_fpf_tabela_diag.json").write_text(
            json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        if args.interagir:
            interact_with_page(page, ano=args.ano)
            page.wait_for_timeout(args.wait_ms)

        html = page.content()
        lines = html_to_lines(html)

        if args.debug_html:
            DEBUG_HTML.write_text(html, encoding="utf-8")
            DEBUG_LINES.write_text("\n".join(lines), encoding="utf-8")

        browser.close()

    games = dedupe_games(games)
    game_rows_debug = [g.to_row() for g in games]
    valid_rows = [r for r in game_rows_debug if r.get("data")]

    DEBUG_REQUESTS.write_text(json.dumps(requests_debug, ensure_ascii=False, indent=2), encoding="utf-8")
    DEBUG_PAYLOADS.write_text(json.dumps(payloads_debug, ensure_ascii=False, indent=2), encoding="utf-8")
    DEBUG_JOGOS.write_text(json.dumps(game_rows_debug, ensure_ascii=False, indent=2), encoding="utf-8")

    merged_current = merge_rows(load_json_rows(JOGOS_JSON), valid_rows)
    JOGOS_JSON.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(JOGOS_CSV, merged_current)

    merged_hist = merge_rows(load_csv_rows(HIST_CSV), valid_rows)
    write_csv(HIST_CSV, merged_hist)

    print("")
    print(f"Jogos detectados no debug: {len(game_rows_debug)}")
    print(f"Jogos com data salvos no JSON: {len(valid_rows)}")
    print(f"Total JSON atual: {len(merged_current)}")
    print(f"Debug requests: {DEBUG_REQUESTS}")
    print(f"Debug payloads: {DEBUG_PAYLOADS}")
    print(f"Debug jogos raw: {DEBUG_JOGOS}")
    if args.debug_html:
        print(f"HTML: {DEBUG_HTML}")
        print(f"Linhas: {DEBUG_LINES}")


if __name__ == "__main__":
    main()
