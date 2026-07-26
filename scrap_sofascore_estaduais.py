#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Federações estaduais sem site oficial fácil de raspar - via SofaScore

Cobre (por ora):
  - Maranhense Série B (2ª divisão do Maranhão)
  - Sul-Mato-Grossense Série B (2ª divisão do Mato Grosso do Sul)

Por que SofaScore via Playwright (não requests puro):
- O site oficial da FMF-MA (futebolmaranhense.com.br) não expõe os jogos em
  nenhum endpoint HTML/AJAX acessível (a página /competicoes/ é só um shell
  de menu; o form POST com o ano não retorna jogos). O site da FFMS (MS) não
  foi validado a tempo. O SofaScore tem os dados prontos e estruturados, mas
  `api.sofascore.com`/`www.sofascore.com/api/...` bloqueia requests simples
  (403, mesmo com headers de browser completos - é proteção Cloudflare/JS
  challenge). Só funciona a partir de um browser real, então usamos
  Playwright: abre sofascore.com (passa o challenge) e faz os fetch() de
  dentro da página via page.evaluate, exatamente como um usuário real veria.

IDs de torneio/temporada (mudam por competição; ver README_estaduais_sofascore
se algum dia for criado). Descobertos via
https://www.sofascore.com/api/v1/search/all?q=<termo> em 26/07/2026:
  - Maranhense Série B:        uniqueTournament=20891, season 2026=95450
  - Sul-Mato-Grossense Série B: uniqueTournament=21158, season 2026=92663

Brasil não usa horário de verão desde 2019 -> um offset fixo por estado é
suficiente para converter startTimestamp (unix, UTC) em hora local correta.
IMPORTANTE: nem todo estado é UTC-3. Mato Grosso do Sul (e MT, RR, RO, AM)
usa o "horário do Amazonas" (UTC-4) -- confirmado batendo um jogo do MS
contra o horário publicado no Flashscore (SofaScore com UTC-3 fixo dava
20:30 para um jogo que o Flashscore mostra às 19:30 = UTC-4 real).

Saídas (mesmo formato/merge dos outros scrapers do projeto):
  data/jogos_programados.json / .csv
  data/historico_jogos.csv
  data/debug_sofascore_estaduais_raw.json
  data/debug_sofascore_estaduais_hist_raw.json

Uso:
  py -3 scrap_sofascore_estaduais.py --dias 365 --dias-atras 45
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

JOGOS_JSON = OUT_DIR / "jogos_programados.json"
JOGOS_CSV = OUT_DIR / "jogos_programados.csv"
HIST_CSV = OUT_DIR / "historico_jogos.csv"

RAW_JOGOS = OUT_DIR / "debug_sofascore_estaduais_raw.json"
RAW_HISTORICO = OUT_DIR / "debug_sofascore_estaduais_hist_raw.json"
DEBUG_EVENTOS = OUT_DIR / "debug_sofascore_estaduais_eventos.json"

FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "pais", "cidade", "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em",
]

# Offset fixo por estado (Brasil não usa horário de verão desde 2019).
UTC_MENOS_3 = timezone(timedelta(hours=-3))  # maioria do Brasil (incl. Maranhão)
UTC_MENOS_4 = timezone(timedelta(hours=-4))  # "horário do Amazonas": MS, MT, AM, RR, RO

# (fonte, nome_competicao, uniqueTournament_id, season_id, estado, fuso)
TORNEIOS = [
    ("FMF-MA", "Brasil - FMF-MA - Campeonato Maranhense Série B", 20891, 95450, "Maranhão", UTC_MENOS_3),
    ("FFMS", "Brasil - FFMS - Sul-Mato-Grossense Série B", 21158, 92663, "Mato Grosso do Sul", UTC_MENOS_4),
]


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


def buscar_eventos_via_browser(page, uniq_id: int, season_id: int) -> list[dict]:
    """Busca todos os eventos (proximos + recentes, paginados) de um torneio via
    fetch() executado dentro da pagina do SofaScore (contorna o bloqueio de
    requests direto)."""
    script = """
        async (args) => {
            const { uniqId, seasonId } = args;
            const base = `https://www.sofascore.com/api/v1/unique-tournament/${uniqId}/season/${seasonId}/events`;
            const eventos = [];
            for (const rota of ['last', 'next']) {
                for (let pagina = 0; pagina < 6; pagina++) {
                    let resp;
                    try {
                        resp = await fetch(`${base}/${rota}/${pagina}`);
                    } catch (e) {
                        break;
                    }
                    if (!resp.ok) break;
                    const j = await resp.json();
                    const lista = j.events || [];
                    if (!lista.length) break;
                    eventos.push(...lista);
                    if (rota === 'last' && !j.hasNextPage) break;
                }
            }
            return eventos;
        }
    """
    return page.evaluate(script, {"uniqId": uniq_id, "seasonId": season_id})


def evento_para_jogo(ev: dict, fonte: str, competicao: str, hoje: date, fuso: timezone) -> Jogo | None:
    home = ev.get("homeTeam") or {}
    away = ev.get("awayTeam") or {}
    mandante = (home.get("name") or home.get("shortName") or "").strip()
    visitante = (away.get("name") or away.get("shortName") or "").strip()
    if not (mandante and visitante):
        return None

    ts = ev.get("startTimestamp")
    if not ts:
        return None
    dt_local = datetime.fromtimestamp(ts, tz=fuso)
    data_iso = dt_local.date().isoformat()
    hora = dt_local.strftime("%H:%M")

    status = (ev.get("status") or {}).get("type", "")
    home_score = (ev.get("homeScore") or {}).get("current")
    away_score = (ev.get("awayScore") or {}).get("current")
    tem_placar = status == "finished" and home_score is not None and away_score is not None

    if tem_placar:
        extra = ["status=Realizado", f"placar={home_score}x{away_score}"]
    elif dt_local.date() >= hoje:
        extra = ["status=Programado"]
    else:
        extra = ["status=Sem resultado"]

    rodada = ev.get("roundInfo", {}).get("round")
    rodada_txt = f"Rodada {rodada}" if rodada is not None else ""

    slug = ev.get("slug", "")
    url = f"https://www.sofascore.com/pt/football/match/{slug}#id:{ev.get('id')}" if slug else "https://www.sofascore.com/"

    return Jogo(
        fonte=fonte,
        competicao=competicao,
        data=data_iso,
        hora=hora,
        mandante=mandante,
        visitante=visitante,
        pais="Brasil",
        cidade="",
        estadio="",
        rodada=rodada_txt,
        url=url,
        extra="; ".join(extra + ["fonte_dados=sofascore"]),
    )


def dedup_rows(jogos: list[Jogo]) -> list[dict]:
    vistos: set[str] = set()
    rows: list[dict] = []
    for g in jogos:
        r = g.to_row()
        if not r["data"] or r["id"] in vistos:
            continue
        vistos.add(r["id"])
        rows.append(r)
    return rows


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
        key=lambda r: (r.get("data", ""), r.get("hora", ""), r.get("competicao", ""), r.get("mandante", "")),
    )


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def main() -> None:
    parser = argparse.ArgumentParser(description="Estaduais (MA, MS...) via SofaScore/Playwright")
    parser.add_argument("--dias", type=int, default=365)
    parser.add_argument("--dias-atras", type=int, default=45, dest="dias_atras")
    args = parser.parse_args()

    hoje = date.today()
    limite_frente = hoje + timedelta(days=args.dias)
    limite_tras = hoje - timedelta(days=args.dias_atras)

    jogos_prog: list[Jogo] = []
    jogos_hist: list[Jogo] = []
    debug_eventos: dict[str, int] = {}

    print("[INFO] Abrindo Chromium (Playwright) para contornar bloqueio do SofaScore...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125 Safari/537.36"
            ),
            locale="pt-BR",
        )
        page = context.new_page()
        page.goto("https://www.sofascore.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)

        for fonte, competicao, uniq_id, season_id, estado, fuso in TORNEIOS:
            try:
                eventos = buscar_eventos_via_browser(page, uniq_id, season_id)
            except Exception as e:  # noqa: BLE001
                print(f"[WARN] {competicao}: falha ao buscar eventos: {e}")
                continue

            debug_eventos[competicao] = len(eventos)
            n_prog = n_hist = 0
            for ev in eventos:
                jogo = evento_para_jogo(ev, fonte, competicao, hoje, fuso)
                if not (jogo and jogo.data):
                    continue
                try:
                    d = date.fromisoformat(jogo.data)
                except Exception:
                    continue
                tem_placar = "status=Realizado" in jogo.extra
                if hoje <= d <= limite_frente and not tem_placar:
                    jogos_prog.append(jogo)
                    n_prog += 1
                if limite_tras <= d <= limite_frente:
                    jogos_hist.append(jogo)
                    n_hist += 1

            print(f"  - {competicao}: {len(eventos)} eventos | {n_prog} programados | {n_hist} p/ histórico")
            time.sleep(1)

        browser.close()

    rows_prog = dedup_rows(jogos_prog)
    rows_hist = dedup_rows(jogos_hist)

    RAW_JOGOS.write_text(json.dumps(rows_prog, ensure_ascii=False, indent=2), encoding="utf-8")
    RAW_HISTORICO.write_text(json.dumps(rows_hist, ensure_ascii=False, indent=2), encoding="utf-8")
    DEBUG_EVENTOS.write_text(json.dumps(debug_eventos, ensure_ascii=False, indent=2), encoding="utf-8")

    merged_current = merge_rows(load_json_rows(JOGOS_JSON), rows_prog)
    JOGOS_JSON.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(JOGOS_CSV, merged_current)

    merged_hist = merge_rows(load_csv_rows(HIST_CSV), rows_hist)
    write_csv(HIST_CSV, merged_hist)

    print("")
    print(f"[OK] Programados (estaduais SofaScore): {len(rows_prog)} | para histórico: {len(rows_hist)}")
    print(f"[OK] Total no {JOGOS_JSON.name}: {len(merged_current)}")
    print(f"[OK] Total no {HIST_CSV.name}: {len(merged_hist)}")


if __name__ == "__main__":
    main()
