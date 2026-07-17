#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APF Paraguai - Copa de Primera + División Intermedia + Primera B + Primera C
+ Copa Paraguay

Páginas:
    https://www.apf.org.py/copa-de-primera
    https://www.apf.org.py/torneo-apertura   (Copa de Primera, mesmo rótulo)
    https://www.apf.org.py/torneo-clausura   (Copa de Primera, mesmo rótulo)
    https://www.apf.org.py/intermedia
    https://www.apf.org.py/primera-b
    https://www.apf.org.py/primera-c
    https://www.apf.org.py/copa-paraguay

O site é Next.js (Pages Router). Os dados de cada página, incluindo os
jogos da rodada atual, vêm embutidos direto no HTML inicial dentro de
uma tag <script id="__NEXT_DATA__">{...json...}</script> — não existe
uma chamada de API JSON separada para os jogos (confirmado via
interceptação de rede com Playwright; só há chamadas para sponsors,
modais, etc, nada de "matches"/"fixture").

Cada objeto de partida dentro desse JSON tem este formato (chaves úteis):
    {
      "slug": "temporada-2026-paraguay-primera-division-apertura-22-...",
      "gameweek": {"name": "Jornada 22", ...},
      "homeTeam": {"name": "Club 2 de Mayo", ...},
      "awayTeam": {"name": "Club Sportivo San Lorenzo", ...},
      "homeScore": 0, "awayScore": 1,
      "period": {"name": "Partido finalizado", "type": "FullTime"},
      "date": "2026-05-22",
      "time": "2026-05-22T21:00:00Z"   <- horário real do jogo, em UTC
    }
período.type == "PreMatch" identifica jogos ainda não disputados.

IMPORTANTE - troca de torneio (Apertura/Clausura): a página
/copa-de-primera mostra a "rodada atual" só enquanto ela está de fato
em andamento. Assim que o Apertura termina (ou antes do Clausura
começar), essa página fica presa mostrando a última rodada do Apertura,
já toda com jogos encerrados - por isso passamos também a tentar
/torneo-apertura e /torneo-clausura sob o mesmo rótulo de competição
("Copa de Primera"): quando um torneio específico está rolando, é a
respectiva página que traz a rodada atual de verdade. Confirmado em
16/07/2026: o Apertura 2026 terminou em 24/mai e o Clausura só começa
em 24/jul, então nesse intervalo nenhuma das três páginas tem jogo
futuro pra achar (o que é esperado, não é um bug).

LIMITAÇÃO CONHECIDA (Primera B / Primera C): diferente de Copa de
Primera e Intermedia, as páginas dedicadas /primera-b e /primera-c NÃO
têm nenhum objeto de partida (homeTeam/awayTeam/time) embutido no
__NEXT_DATA__ - só listam elenco de times e notícias/resultados em
texto. Isso é contornado (pelo menos pra Primera B, que é a que já foi
vista lá) usando a HOME do site (BASE_URL + "/"), que tem um módulo à
parte listando os PRÓXIMOS jogos misturando várias competições ao mesmo
tempo (confirmado ao vivo: Copa de Primera, Copa Paraguay, Intermedia,
Primera B, Femenino). Cada jogo achado nessa página tem sua competição
real inferida pelo slug (função competicao_from_slug); jogos cujo slug
não bate com nenhum padrão conhecido (Femenino, Formativas etc.) são
descartados, não adivinhados. Se a Primera C nunca aparecer nessa lista
da home (não vista até agora), essa competição realmente fica sem fonte
neste scraper.

NÃO usamos a API não-documentada do Sofascore como alternativa pra
Primera B/C mesmo ela tendo esses dados: a própria Sofascore afirma
publicamente que não disponibiliza essas rotas como API pra terceiros
por acordo com os provedores dos dados, então preferimos ficar só com
fontes que o próprio APF expõe publicamente em seu site.

IMPORTANTE - limitação conhecida: essas duas páginas mostram apenas a
RODADA ATUAL de cada torneio (módulo "football_competition_matches_
current_gameweek"), não o campeonato inteiro. Ou seja, este scraper
pega os próximos jogos da rodada em andamento (tipicamente uns 6 a 8
jogos por competição), não um calendário de meses inteiros como os
outros scrapers do projeto. Isso ainda é útil (mostra os jogos mais
próximos com data/hora reais) mas é bom estar ciente da diferença.

O campo "venue" (estádio) NÃO vem nesse bloco da página principal, só
na página de detalhe de cada partida (/partidos/{slug}), que tem seu
próprio __NEXT_DATA__ mais completo. Por isso, para cada jogo
encontrado, o script visita também a página de detalhe para pegar o
nome do estádio (são poucos jogos por rodada, o custo extra é baixo).
Confirmado por inspeção real: a Copa de Primera tem esse dado (é a
competição com o "match center" completo, estilo Opta); a División
Intermedia NÃO tem — o campo "venue" simplesmente não existe no JSON
dessas partidas, então o estádio fica vazio para jogos da Intermedia
(limitação real da fonte, não um bug do scraper).

Uso:
    python scrap_apf_paraguay.py --dias 60 --dias-atras 30
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

from playwright.sync_api import sync_playwright

try:
    from zoneinfo import ZoneInfo
    ASU_TZ = ZoneInfo("America/Asuncion")
except Exception:
    ASU_TZ = None

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

BASE_URL = "https://www.apf.org.py"
START_URLS = [
    # A Copa de Primera (1a. divisão paraguaia) tem dois torneios por ano
    # (Apertura e Clausura) e o site do APF passou a usar páginas
    # diferentes pra mostrar a "rodada atual" dependendo de qual torneio
    # está rolando (ex.: copa-de-primera ficou "preso" mostrando a última
    # rodada (já encerrada) do Apertura assim que ele terminou, e o
    # Clausura passou a aparecer só em /torneo-clausura). Por isso
    # tentamos as três URLs sob o mesmo rótulo de competição: cada uma
    # que não tiver jogos da rodada atual simplesmente não acha nada
    # (sem erro) e as que tiverem se somam (dedupe cuida de duplicatas).
    ("Copa de Primera", f"{BASE_URL}/copa-de-primera"),
    ("Copa de Primera", f"{BASE_URL}/torneo-apertura"),
    ("Copa de Primera", f"{BASE_URL}/torneo-clausura"),
    ("División Intermedia", f"{BASE_URL}/intermedia"),
    ("Primera B", f"{BASE_URL}/primera-b"),
    ("Primera C", f"{BASE_URL}/primera-c"),
    ("Copa Paraguay", f"{BASE_URL}/copa-paraguay"),
]

# A home do site (BASE_URL + "/") tem um módulo à parte que lista os
# PRÓXIMOS jogos misturando várias competições ao mesmo tempo (visto ao
# vivo: Copa de Primera, Copa Paraguay, Intermedia, Primera B, Femenino).
# É a única fonte encontrada que efetivamente traz jogos da Primera B (a
# página dedicada /primera-b não tem NENHUM objeto de partida no
# __NEXT_DATA__, só elenco/notícias - ver limitação documentada acima).
# Cada jogo achado aqui tem sua competição real inferida pelo slug
# (competicao_from_slug) - o que não bater com um padrão conhecido
# (Femenino, Formativas etc.) é descartado, não adivinhado.
HOME_URL = (None, BASE_URL + "/")

FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "pais", "cidade", "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em",
]

HEADERS_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
)

NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


@dataclass
class Partido:
    fonte: str
    competicao: str
    data: str
    hora: str
    mandante: str
    visitante: str
    pais: str = "Paraguay"
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


def extract_next_data(html: str) -> Any:
    m = NEXT_DATA_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def utc_iso_to_local(time_iso: str) -> tuple[str, str]:
    """Converte 'YYYY-MM-DDTHH:MM:SSZ' (UTC) para (data local, hora local)
    no fuso de Assunção. Sem zoneinfo, cai para um offset fixo -04:00."""
    try:
        dt_utc = datetime.strptime(time_iso, "%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return "", ""
    if ASU_TZ is not None:
        try:
            from datetime import timezone
            dt_local = dt_utc.replace(tzinfo=timezone.utc).astimezone(ASU_TZ)
            return dt_local.date().isoformat(), dt_local.strftime("%H:%M")
        except Exception:
            pass
    dt_local = dt_utc - timedelta(hours=3)
    return dt_local.date().isoformat(), dt_local.strftime("%H:%M")


def find_match_objects(node: Any, out: list[dict], seen_ids: set) -> None:
    """Percorre recursivamente o JSON do __NEXT_DATA__ procurando qualquer
    dict que pareça um objeto de partida (tem homeTeam/awayTeam/time)."""
    if isinstance(node, dict):
        if "homeTeam" in node and "awayTeam" in node and "time" in node:
            mid = node.get("id") or node.get("slug")
            if mid and mid not in seen_ids:
                seen_ids.add(mid)
                out.append(node)
        for v in node.values():
            find_match_objects(v, out, seen_ids)
    elif isinstance(node, list):
        for item in node:
            find_match_objects(item, out, seen_ids)


def find_venue_for_slug(node: Any, slug: str) -> str:
    """Procura no __NEXT_DATA__ da página de detalhe o objeto de partida
    com o slug pedido e retorna node['venue']['name'], se houver."""
    if isinstance(node, dict):
        if node.get("slug") == slug and isinstance(node.get("venue"), dict):
            return clean_text(node["venue"].get("name"))
        for v in node.values():
            found = find_venue_for_slug(v, slug)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = find_venue_for_slug(item, slug)
            if found:
                return found
    return ""


def team_name(obj: dict) -> str:
    if not isinstance(obj, dict):
        return ""
    return clean_text(obj.get("name") or obj.get("shortName") or obj.get("nickname") or "")


# A home do site (BASE_URL + "/") lista jogos futuros de VÁRIAS competições
# ao mesmo tempo (Copa de Primera, Copa Paraguay, Intermedia, Primera B,
# Femenino) num único módulo do __NEXT_DATA__. Pra saber a que competição
# cada partida pertence quando ela vem dessa página (em vez da página
# dedicada de cada torneio, onde já sabemos o rótulo de antemão), usamos o
# slug do jogo, que sempre carrega o nome do torneio de origem
# (ex.: "temporada-2026-paraguay-primera-division-apertura-22-...",
# "intermedia-2026-intermedia-14-...", "primera-b-2026-fecha-15-...").
SLUG_COMPETICAO_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"primera-division", re.I), "Copa de Primera"),
    (re.compile(r"^intermedia-|division-intermedia", re.I), "División Intermedia"),
    (re.compile(r"^primera-b-|primera-division-b", re.I), "Primera B"),
    (re.compile(r"^primera-c-|primera-division-c", re.I), "Primera C"),
    (re.compile(r"copa-paraguay", re.I), "Copa Paraguay"),
]


def competicao_from_slug(slug: str) -> str:
    """Tenta inferir o nome da competição a partir do slug do jogo. Retorna
    string vazia se não reconhecer o padrão (ex.: femenino, formativas)."""
    s = clean_text(slug)
    for pattern, label in SLUG_COMPETICAO_PATTERNS:
        if pattern.search(s):
            return label
    return ""


def match_to_partido(m: dict, competicao_label: str, require_slug_match: bool = False) -> Partido | None:
    mandante = team_name(m.get("homeTeam"))
    visitante = team_name(m.get("awayTeam"))
    time_iso = clean_text(m.get("time"))
    if not (mandante and visitante and time_iso):
        return None

    data_local, hora_local = utc_iso_to_local(time_iso)
    if not data_local:
        return None

    slug = clean_text(m.get("slug"))
    slug_label = competicao_from_slug(slug)
    if require_slug_match and not slug_label:
        # Fonte mista (ex.: a home do site) e não reconhecemos a que
        # competição esse jogo pertence (pode ser Femenino, Formativas,
        # etc, que não rastreamos aqui) - melhor descartar do que rotular
        # errado.
        return None
    # Prioriza o rótulo inferido do slug (mais confiável, principalmente
    # quando a origem é a home do site com várias competições misturadas);
    # só cai pro rótulo da página se o slug não bater com nenhum padrão
    # conhecido.
    competicao_final = slug_label or competicao_label
    gameweek = m.get("gameweek") if isinstance(m.get("gameweek"), dict) else {}
    rodada = clean_text(gameweek.get("name"))

    period = m.get("period") if isinstance(m.get("period"), dict) else {}
    period_type = clean_text(period.get("type"))
    period_name = clean_text(period.get("name"))

    extra_parts = []
    if period_type:
        extra_parts.append(f"status={period_type}")
    if period_name:
        extra_parts.append(f"status_nome={period_name}")
    home_score = m.get("homeScore")
    away_score = m.get("awayScore")
    if home_score is not None and away_score is not None:
        extra_parts.append(f"placar={home_score}-{away_score}")

    return Partido(
        fonte="APF",
        competicao=f"Paraguay - APF - {competicao_final}",
        data=data_local,
        hora=hora_local,
        mandante=mandante,
        visitante=visitante,
        pais="Paraguay",
        rodada=rodada,
        url=f"{BASE_URL}/partidos/{slug}" if slug else "",
        extra="; ".join(extra_parts),
    )


def collect(start_urls: list[tuple[str, str]], wait_ms: int, max_detalhes: int, timeout: int):
    partidos: list[Partido] = []
    debug_pages = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        matches_by_url: dict[str, tuple[dict, str]] = {}

        todas_as_paginas = start_urls + [HOME_URL]

        for idx, (competicao_label, url) in enumerate(todas_as_paginas):
            is_home = competicao_label is None
            label_exibicao = competicao_label or "Inicio (multi-competição, filtrado por slug)"
            info = {"competicao": label_exibicao, "url": url, "jogos": 0, "erro": ""}
            # Contexto novo por competição (em vez de reaproveitar a mesma
            # aba/sessão pra todas): reduz o risco de qualquer rate-limit ou
            # verificação anti-bot baseada em sessão que o site passe a
            # aplicar quando várias páginas são abertas em sequência rápida
            # (isso passou de 2 páginas para 5 quando adicionamos Primera
            # B/C/Copa Paraguay, e é onde o "sem __NEXT_DATA__" começou a
            # aparecer em todas as páginas, inclusive as que sempre
            # funcionaram antes).
            context = browser.new_context(user_agent=HEADERS_UA, locale="es-PY")
            page = context.new_page()
            try:
                next_data = None
                for tentativa in range(2):
                    print(f"[INFO] Abrindo APF: {url} (tentativa {tentativa + 1})")
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                    espera = wait_ms if tentativa == 0 else wait_ms * 2
                    page.wait_for_timeout(espera)
                    html = page.content()
                    next_data = extract_next_data(html)
                    if next_data is not None:
                        break
                    print(f"[WARN] sem __NEXT_DATA__ em {url} na tentativa {tentativa + 1}, tentando de novo...")

                if next_data is None:
                    info["erro"] = "sem __NEXT_DATA__"
                    debug_pages.append(info)
                    context.close()
                    if idx < len(todas_as_paginas) - 1:
                        time.sleep(2)
                    continue

                found: list[dict] = []
                find_match_objects(next_data, found, set())
                info["jogos"] = len(found)
                print(f"[OK] {label_exibicao}: {len(found)} jogos na rodada atual")

                for m in found:
                    part = match_to_partido(m, competicao_label or "", require_slug_match=is_home)
                    if not part:
                        continue
                    if part.url:
                        matches_by_url[part.url] = (m, part.competicao)
                    partidos.append(part)

            except Exception as e:
                info["erro"] = str(e)
                print(f"[ERRO] {label_exibicao}: {e}")
            debug_pages.append(info)
            context.close()
            if idx < len(todas_as_paginas) - 1:
                time.sleep(2)

        # Segunda passada: visita a página de detalhe de cada jogo achado
        # (poucos jogos por rodada) só para pegar o nome do estádio.
        # Precisa de um contexto/página novos: os da primeira passada foram
        # fechados a cada competição (ver comentário acima).
        venue_context = browser.new_context(user_agent=HEADERS_UA, locale="es-PY")
        page = venue_context.new_page()
        venue_by_url: dict[str, str] = {}
        venue_debug = []
        for i, (match_url, (m, _comp)) in enumerate(matches_by_url.items()):
            if i >= max_detalhes:
                break
            slug = match_url.rstrip("/").rsplit("/", 1)[-1]
            dbg = {"url": match_url, "slug": slug, "next_data": False, "venue": ""}
            try:
                page.goto(match_url, wait_until="domcontentloaded", timeout=timeout * 1000)
                page.wait_for_timeout(min(wait_ms, 6000))
                html = page.content()
                next_data = extract_next_data(html)
                if next_data is not None:
                    dbg["next_data"] = True
                    venue = find_venue_for_slug(next_data, slug)
                    if venue:
                        venue_by_url[match_url] = venue
                        dbg["venue"] = venue
                        print(f"[OK] estádio de {slug}: {venue}")
                    else:
                        print(f"[WARN] sem estadio encontrado para slug {slug}")
                else:
                    print(f"[WARN] sem __NEXT_DATA__ na pagina de detalhe {match_url}")
            except Exception as e:
                dbg["erro"] = str(e)
                print(f"[WARN] Falha ao buscar estádio de {match_url}: {e}")
            venue_debug.append(dbg)
        venue_context.close()

        browser.close()

    (OUT_DIR / "debug_apf_venue_lookup.json").write_text(
        json.dumps(venue_debug, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for part in partidos:
        if part.url in venue_by_url:
            part.estadio = venue_by_url[part.url]

    return partidos, debug_pages


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
    parser.add_argument("--dias-atras", type=int, default=30)
    parser.add_argument("--incluir-passados", action="store_true")
    parser.add_argument("--wait-ms", type=int, default=10000)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--max-detalhes", type=int, default=40,
                         help="Limite de páginas de detalhe visitadas para buscar o estádio.")
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    partidos, debug_pages = collect(START_URLS, wait_ms=args.wait_ms, max_detalhes=args.max_detalhes, timeout=args.timeout)

    partidos = [p for p in partidos if in_window(p, desde, ate, args.incluir_passados)]
    partidos = dedupe_partidos(partidos)
    rows_new = [p.to_row() for p in partidos]

    (OUT_DIR / "debug_apf_pages.json").write_text(json.dumps(debug_pages, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "debug_apf_jogos_raw.json").write_text(json.dumps(rows_new, ensure_ascii=False, indent=2), encoding="utf-8")

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    merged_current = merge_rows(load_json_rows(current_json), rows_new)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    merged_history = merge_rows(load_csv_rows(history_csv), rows_new)
    write_csv(history_csv, merged_history)

    print("")
    print(f"APF (Paraguai) jogos válidos adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")
    print("Debug páginas: data/debug_apf_pages.json")
    print("Debug jogos: data/debug_apf_jogos_raw.json")


if __name__ == "__main__":
    main()
