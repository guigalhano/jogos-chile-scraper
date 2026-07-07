#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper FPF - Federação Paulista de Futebol

Melhor estratégia:
- A página da FPF usa JavaScript/Angular e o HTML inicial contém templates como:
  {{item.NomePopularMandante}}, {{item.NomePopularVisitante}}, {{item.Estadio}}, {{item.Data}}, {{item.Horario}}
- Por isso, o scraper abre a página com Playwright, captura respostas JSON/XHR e procura objetos com campos de jogos.

Saídas:
- data/jogos_programados.json
- data/jogos_programados.csv
- data/historico_jogos.csv
- data/debug_fpf_api_urls.json
- data/debug_fpf_matches_raw.json

Uso:
    python scrap_fpf_playwright_api.py --dias 180 --dias-atras 30

No GitHub Actions, precisa:
    python -m playwright install chromium
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import re
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright


OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

START_URLS = [
    "https://www.futebolpaulista.com.br/Home/",
    "https://www.futebolpaulista.com.br/Jogos/",
    "https://www.futebolpaulista.com.br/Competicoes/Tabela.aspx",
]

FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em", "pais", "cidade",
]

DATE_RE = re.compile(r"\b(?P<dia>\d{1,2})[/-](?P<mes>\d{1,2})[/-](?P<ano>\d{2,4})\b")
TIME_RE = re.compile(r"\b(?P<hora>\d{1,2}:\d{2})h?\b")


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


def clean_text(value: Any) -> str:
    value = "" if value is None else str(value)
    value = value.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", value).strip()


def norm(value: Any) -> str:
    import unicodedata
    value = unicodedata.normalize("NFD", clean_text(value))
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def parse_year(y: str) -> int:
    n = int(y)
    return 2000 + n if n < 100 else n


def parse_date(value: Any) -> str:
    txt = clean_text(value)
    if not txt:
        return ""

    # ISO: 2026-07-06T...
    m_iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})", txt)
    if m_iso:
        try:
            return date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))).isoformat()
        except Exception:
            pass

    m = DATE_RE.search(txt)
    if not m:
        return ""
    try:
        return date(parse_year(m.group("ano")), int(m.group("mes")), int(m.group("dia"))).isoformat()
    except Exception:
        return ""


def parse_time(value: Any) -> str:
    m = TIME_RE.search(clean_text(value))
    return m.group("hora") if m else ""


def first_value(obj: dict, keys: list[str]) -> str:
    """
    Busca por chaves exatas ou parciais normalizadas.
    """
    if not isinstance(obj, dict):
        return ""

    # exata primeiro
    for k in keys:
        if k in obj and clean_text(obj[k]):
            return clean_text(obj[k])

    # normalizada parcial
    normalized = {norm(k): v for k, v in obj.items()}
    for wanted in keys:
        nw = norm(wanted)
        for nk, val in normalized.items():
            if nw == nk or nw in nk:
                txt = clean_text(val)
                if txt:
                    return txt
    return ""


def guess_competicao(obj: dict, api_url: str) -> str:
    vals = [
        first_value(obj, ["Campeonato", "DescricaoCampeonato", "NomeCampeonato", "Competicao", "Competição"]),
        first_value(obj, ["Categoria", "DescricaoCategoria"]),
        first_value(obj, ["DescricaoSite"]),
    ]
    txt = " ".join(v for v in vals if v)
    if txt:
        return "Brasil - FPF - " + txt
    return "Brasil - FPF"


PAISES_SELECOES = {
    "brasil", "argentina", "uruguai", "chile", "colombia", "equador", "peru",
    "bolivia", "paraguai", "venezuela", "portugal", "espanha", "franca",
    "alemanha", "italia", "inglaterra", "belgica", "holanda", "croacia",
    "marrocos", "japao", "coreia do sul", "coreia", "estados unidos", "mexico",
    "canada", "suica", "polonia", "senegal", "gana", "camaroes", "tunisia",
    "egito", "nigeria", "australia", "arabia saudita", "qatar", "iran",
    "catar", "dinamarca", "servia", "suecia", "noruega", "escocia", "austria",
    "romenia", "eslovenia", "eslovaquia", "ucrania", "gales", "irlanda",
    "costa rica", "panama", "jamaica", "curacao", "haiti", "honduras",
    "nova zelandia", "uzbequistao", "jordania", "cabo verde", "africa do sul",
}


def is_selecao_nacional(nome: str) -> bool:
    return norm(nome) in PAISES_SELECOES


def obj_to_partido(obj: dict, api_url: str) -> Partido | None:
    """
    Converte um objeto JSON da FPF em Partido quando encontrar campos suficientes.
    """
    if not isinstance(obj, dict):
        return None

    mandante = first_value(obj, [
        "NomePopularMandante", "Mandante", "NomeMandante", "ClubeMandante", "TimeMandante"
    ])
    visitante = first_value(obj, [
        "NomePopularVisitante", "Visitante", "NomeVisitante", "ClubeVisitante", "TimeVisitante"
    ])

    data_raw = first_value(obj, ["Data", "DataJogo", "DataFormatada", "Dia"])
    hora_raw = first_value(obj, ["Horario", "Horário", "Hora", "HoraFormatada"])

    data = parse_date(data_raw)
    hora = parse_time(hora_raw) or clean_text(hora_raw)

    estadio = first_value(obj, ["Estadio", "Estádio", "NomePopularEstadio", "Local"])
    municipio = first_value(obj, ["Municipio", "Município", "Cidade"])
    rodada = first_value(obj, ["Rodada", "NumeroRodada", "RodadaNumero"])
    numero = first_value(obj, ["Numero", "Número", "NumeroJogo", "Jogo"])

    # Alguns objetos de placar usam nomes diferentes
    if not mandante:
        mandante = first_value(obj, ["MandanteNome", "EquipeMandante"])
    if not visitante:
        visitante = first_value(obj, ["VisitanteNome", "EquipeVisitante"])

    if not data:
        # Tenta juntar todos os valores e extrair data
        joined = " ".join(clean_text(v) for v in obj.values() if isinstance(v, (str, int, float)))
        data = parse_date(joined)
        if not hora:
            hora = parse_time(joined)

    if not (mandante and visitante and data):
        return None

    if len(mandante) > 80 or len(visitante) > 80:
        return None

    # A página da FPF costuma embutir um widget de "placar ao vivo" com jogos de
    # seleções (ex.: Copa do Mundo), que não têm nada a ver com o futebol paulista.
    # Rejeita explicitamente para não poluir os dados com jogos de seleções.
    if is_selecao_nacional(mandante) or is_selecao_nacional(visitante):
        return None

    extra_parts = []
    if municipio:
        extra_parts.append(f"cidade={municipio}")
    if numero:
        extra_parts.append(f"jogo_numero={numero}")

    return Partido(
        fonte="FPF API",
        competicao=guess_competicao(obj, api_url),
        data=data,
        hora=hora,
        mandante=mandante,
        visitante=visitante,
        estadio=estadio,
        rodada=rodada,
        url=api_url,
        extra="; ".join(extra_parts),
    )


def walk_json(data: Any, api_url: str) -> list[Partido]:
    """
    Percorre JSON profundamente e captura objetos que pareçam jogos.
    """
    out: list[Partido] = []

    if isinstance(data, dict):
        p = obj_to_partido(data, api_url)
        if p:
            out.append(p)
        for v in data.values():
            out.extend(walk_json(v, api_url))

    elif isinstance(data, list):
        for item in data:
            out.extend(walk_json(item, api_url))

    return out


def dedupe_partidos(rows: list[Partido]) -> list[Partido]:
    seen = set()
    out = []
    for p in rows:
        if p.id in seen:
            continue
        seen.add(p.id)
        out.append(p)
    return out


async def collect_fpf_json(start_urls: list[str], wait_ms: int = 7000) -> tuple[list[dict], list[dict]]:
    """
    Abre páginas da FPF, captura respostas JSON e retorna:
    - json_payloads: lista com url + data
    - api_urls: lista debug de URLs e status
    """
    json_payloads: list[dict] = []
    api_urls: list[dict] = []
    seen_urls = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
            ),
            locale="pt-BR",
        )

        async def on_response(response):
            url = response.url
            if url in seen_urls:
                return
            seen_urls.add(url)

            low = url.lower()
            ct = ""
            try:
                ct = response.headers.get("content-type", "")
            except Exception:
                pass

            interesting = (
                "json" in ct.lower()
                or any(x in low for x in [
                    "api", "handler", "ashx", "service", "competicoes",
                    "jogos", "placar", "tabela", "campeonato"
                ])
            )

            if not interesting:
                return

            item = {
                "url": url,
                "status": response.status,
                "content_type": ct,
            }

            try:
                data = await response.json()
                item["json"] = True
                json_payloads.append({"url": url, "data": data})
            except Exception:
                item["json"] = False

            api_urls.append(item)

        page.on("response", on_response)

        for url in start_urls:
            try:
                print(f"[INFO] Abrindo FPF: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(wait_ms)

                # tenta clicar nos selects/dropdowns principais, para disparar requests
                for selector in [
                    "select",
                    ".dropdown-toggle",
                    "button",
                    "a[href*='Competicoes']",
                    "a[href*='Jogos']",
                ]:
                    try:
                        locs = page.locator(selector)
                        count = await locs.count()
                        for i in range(min(count, 5)):
                            try:
                                await locs.nth(i).click(timeout=1000)
                                await page.wait_for_timeout(800)
                            except Exception:
                                pass
                    except Exception:
                        pass

                # recursos carregados pelo browser
                resources = await page.evaluate("""
                    () => performance.getEntriesByType('resource').map(r => r.name)
                """)
                for res in resources:
                    if isinstance(res, str) and res not in seen_urls:
                        low = res.lower()
                        if any(x in low for x in ["api", "handler", "ashx", "service", "jogos", "competicoes", "tabela"]):
                            api_urls.append({"url": res, "status": "", "content_type": "resource", "json": ""})
                            seen_urls.add(res)

            except Exception as e:
                print(f"[WARN] Erro abrindo {url}: {e}")

        await browser.close()

    return json_payloads, api_urls


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
        row.get("fonte", ""),
        row.get("competicao", ""),
        row.get("data", ""),
        row.get("hora", ""),
        row.get("mandante", ""),
        row.get("visitante", ""),
        row.get("estadio", ""),
        row.get("rodada", ""),
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


async def async_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dias", type=int, default=180)
    parser.add_argument("--dias-atras", type=int, default=30)
    parser.add_argument("--incluir-passados", action="store_true")
    parser.add_argument("--wait-ms", type=int, default=7000)
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    payloads, api_urls = await collect_fpf_json(START_URLS, wait_ms=args.wait_ms)

    (OUT_DIR / "debug_fpf_api_urls.json").write_text(
        json.dumps(api_urls, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    partidos: list[Partido] = []
    raw_debug = []

    for payload in payloads:
        url = payload["url"]
        data = payload["data"]
        found = walk_json(data, url)
        if found:
            raw_debug.append({"url": url, "quantidade": len(found)})
            print(f"[OK] FPF JSON {url} -> {len(found)} jogos")
        partidos.extend(found)

    partidos = dedupe_partidos([p for p in partidos if in_window(p, desde, ate, args.incluir_passados)])

    (OUT_DIR / "debug_fpf_matches_raw.json").write_text(
        json.dumps([p.to_row() for p in partidos], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

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

    print(f"\nFPF adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")
    print("Debug URLs: data/debug_fpf_api_urls.json")
    print("Debug jogos: data/debug_fpf_matches_raw.json")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
