#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reino Unido + Irlanda - ligas profissionais/semiprofissionais e copas
nacionais via SofaScore (Playwright), com horario, rodada e placar.

Por que SofaScore e nao a API da ESPN (usada para Equador/Colombia/...):
a ESPN tem slugs para Inglaterra (eng.1-eng.5), Escocia (sco.1-sco.4),
Gales (wal.1), Irlanda (irl.1) e Irlanda do Norte (nir.1), mas em outubro
de 2026 Escocia L1/L2, Gales, Irlanda e Irlanda do Norte voltavam 0 jogos
em todos os sabados testados. O SofaScore cobre todas, e mais Cymru
North/South, Ardal, First Division irlandesa, NIFL Championship etc.

Mesmo esquema do scrap_sofascore_estaduais.py: api.sofascore.com bloqueia
requests simples (Cloudflare), entao abrimos sofascore.com no Chromium e
fazemos os fetch() de dentro da pagina.

As ligas abaixo do SofaScore (National League North/South, steps 3-7 na
Inglaterra, Highland/Lowland e abaixo na Escocia, ligas regionais de
Gales e da Irlanda do Norte) vem do scrap_nonleaguehq.py.

Os IDs de torneio (uniqueTournament) sao fixos no SofaScore; a temporada
atual e descoberta a cada execucao (/unique-tournament/{id}/seasons, a
primeira da lista), entao a virada de temporada nao quebra o scraper.
IDs levantados em 11/10/2026 via /category/{1,22,131,51,130}/unique-tournaments.

Estadio/cidade: o evento na listagem nao traz venue; usamos o venue do
time mandante (/team/{id}), com cache em data/reino_unido/cache_venues_sofascore.json
(so busca times novos). Em clubes pequenos o SofaScore as vezes traz
estadio errado (ex.: Denbigh Town com "Stadium mk"); a cidade costuma estar
certa. Para corrigir um time, editar a entrada dele no cache.

Uso:
  python scrap_reino_unido_sofascore.py --dias 60 --dias-atras 15
  python scrap_reino_unido_sofascore.py --so 17,36   # so alguns torneios (teste)
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

from reino_unido_comum import (
    ESCOCIA, FUSO_UK, GALES, INGLATERRA, IRLANDA, IRLANDA_NORTE,
    OUT_DIR, UK_DIR, Jogo, dedup_rows, salvar,
)

RAW_JOGOS = OUT_DIR / "debug_uk_sofascore_raw.json"
RAW_HISTORICO = OUT_DIR / "debug_uk_sofascore_hist_raw.json"
DEBUG_EVENTOS = OUT_DIR / "debug_uk_sofascore_eventos.json"
CACHE_VENUES = UK_DIR / "cache_venues_sofascore.json"

# (uniqueTournament_id, pais, nome da competicao)
TORNEIOS = [
    # Inglaterra - piramide ate o step 1 (National League) + copas
    (17, INGLATERRA, "Premier League"),
    (18, INGLATERRA, "Championship"),
    (24, INGLATERRA, "League One"),
    (25, INGLATERRA, "League Two"),
    (173, INGLATERRA, "National League"),
    (19, INGLATERRA, "FA Cup"),
    (1696, INGLATERRA, "FA Cup - Qualificação"),
    (21, INGLATERRA, "EFL Cup"),
    (334, INGLATERRA, "EFL Trophy"),
    (24029, INGLATERRA, "National League Cup"),
    (346, INGLATERRA, "Community Shield"),
    # Escocia - SPFL + copas (Highland/Lowland e abaixo: NonLeagueHQ)
    (36, ESCOCIA, "Premiership"),
    (206, ESCOCIA, "Championship"),
    (207, ESCOCIA, "League One"),
    (209, ESCOCIA, "League Two"),
    (347, ESCOCIA, "Scottish Cup"),
    (332, ESCOCIA, "League Cup"),
    (331, ESCOCIA, "Challenge Cup"),
    # Pais de Gales - tiers 1 e 2 + copas (Ardal = tier 3: o SofaScore so tem
    # resultados, sem jogos programados -> vem do NonLeagueHQ)
    (254, GALES, "Cymru Premier"),
    (13820, GALES, "Cymru North"),
    (13821, GALES, "Cymru South"),
    (388, GALES, "Welsh Cup"),
    (367, GALES, "Welsh League Cup"),
    # Irlanda (Republica) - League of Ireland + copas
    (192, IRLANDA, "Premier Division"),
    (193, IRLANDA, "First Division"),
    (36090, IRLANDA, "FAI National League"),
    (195, IRLANDA, "FAI Cup"),
    (1632, IRLANDA, "President's Cup"),
    # Irlanda do Norte - NIFL + copas (Premier Intermediate e abaixo: NonLeagueHQ)
    (200, IRLANDA_NORTE, "NIFL Premiership"),
    (701, IRLANDA_NORTE, "NIFL Championship"),
    (767, IRLANDA_NORTE, "Irish Cup"),
    (611, IRLANDA_NORTE, "League Cup"),
    (20621, IRLANDA_NORTE, "Charity Shield"),
]

# Busca temporada atual + eventos (last/next paginados) de um torneio.
# Para no 'last' quando passa do limite de dias para tras e no 'next'
# quando passa do limite para frente, para nao varrer a temporada toda.
JS_EVENTOS = """
async ({ uniqId, tsMin, tsMax }) => {
    const api = 'https://www.sofascore.com/api/v1';
    const rs = await fetch(`${api}/unique-tournament/${uniqId}/seasons`);
    if (!rs.ok) return { erro: `seasons HTTP ${rs.status}`, eventos: [] };
    const seasons = (await rs.json()).seasons || [];
    if (!seasons.length) return { erro: 'sem temporadas', eventos: [] };
    const season = seasons[0];
    const base = `${api}/unique-tournament/${uniqId}/season/${season.id}/events`;
    const eventos = [];
    for (const rota of ['last', 'next']) {
        for (let pagina = 0; pagina < 30; pagina++) {
            let resp;
            try { resp = await fetch(`${base}/${rota}/${pagina}`); } catch (e) { break; }
            if (!resp.ok) break;
            const j = await resp.json();
            const lista = j.events || [];
            if (!lista.length) break;
            eventos.push(...lista);
            const tss = lista.map(e => e.startTimestamp || 0);
            if (rota === 'last' && Math.min(...tss) < tsMin) break;
            if (rota === 'next' && Math.max(...tss) > tsMax) break;
            if (!j.hasNextPage) break;
        }
    }
    return { season: season.name, eventos };
}
"""

JS_VENUES = """
async (ids) => {
    const out = {};
    for (let i = 0; i < ids.length; i += 8) {
        const lote = ids.slice(i, i + 8);
        await Promise.all(lote.map(async (id) => {
            try {
                const r = await fetch(`https://www.sofascore.com/api/v1/team/${id}`);
                if (!r.ok) return;
                const v = ((await r.json()).team || {}).venue;
                out[id] = v
                    ? { estadio: (v.stadium || {}).name || v.name || '', cidade: (v.city || {}).name || '' }
                    : { estadio: '', cidade: '' };
            } catch (e) {}
        }));
    }
    return out;
}
"""


def para_local(ts: int) -> datetime:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.astimezone(FUSO_UK) if FUSO_UK else dt


def evento_para_jogo(ev: dict, pais: str, competicao: str, venues: dict) -> Jogo | None:
    home = ev.get("homeTeam") or {}
    away = ev.get("awayTeam") or {}
    mandante = (home.get("name") or home.get("shortName") or "").strip()
    visitante = (away.get("name") or away.get("shortName") or "").strip()
    ts = ev.get("startTimestamp")
    if not (mandante and visitante and ts):
        return None

    dt_local = para_local(ts)
    status = (ev.get("status") or {}).get("type", "")
    gh = (ev.get("homeScore") or {}).get("current")
    ga = (ev.get("awayScore") or {}).get("current")

    extra = [f"codigo_sofascore={ev.get('id')}"]
    if status == "finished" and gh is not None and ga is not None:
        extra += ["status=Realizado", f"placar={gh}-{ga}"]
    elif status in ("postponed", "canceled"):
        extra.append("status=Adiado" if status == "postponed" else "status=Cancelado")
    elif status == "inprogress":
        extra.append("status=Em andamento")
    else:
        extra.append("status=Programado")
    if FUSO_UK is None:
        extra.append("hora_utc=1")

    ri = ev.get("roundInfo") or {}
    if ri.get("name"):
        rodada = ri["name"]
    elif ri.get("round") is not None:
        rodada = f"Rodada {ri['round']}"
    else:
        rodada = ""

    venue = venues.get(str(home.get("id"))) or {}
    slug = ev.get("slug", "")
    url = f"https://www.sofascore.com/football/match/{slug}/{ev.get('customId', '')}#id:{ev.get('id')}" if slug else ""

    return Jogo(
        fonte="SofaScore",
        competicao=f"{pais} - {competicao}",
        data=dt_local.date().isoformat(),
        hora=dt_local.strftime("%H:%M"),
        mandante=mandante,
        visitante=visitante,
        pais=pais,
        cidade=venue.get("cidade", ""),
        estadio=venue.get("estadio", ""),
        rodada=rodada,
        url=url,
        extra="; ".join(extra),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Reino Unido + Irlanda via SofaScore/Playwright")
    parser.add_argument("--dias", type=int, default=60)
    parser.add_argument("--dias-atras", type=int, default=15, dest="dias_atras")
    parser.add_argument("--so", default="", help="lista de uniqueTournament ids separados por virgula (teste)")
    args = parser.parse_args()

    torneios = TORNEIOS
    if args.so:
        ids = {int(x) for x in args.so.split(",") if x.strip()}
        torneios = [t for t in TORNEIOS if t[0] in ids]

    hoje = date.today()
    limite_frente = hoje + timedelta(days=args.dias)
    limite_tras = hoje - timedelta(days=args.dias_atras)
    ts_min = int(datetime.combine(limite_tras, datetime.min.time(), tzinfo=timezone.utc).timestamp())
    ts_max = int(datetime.combine(limite_frente, datetime.max.time(), tzinfo=timezone.utc).timestamp())

    UK_DIR.mkdir(parents=True, exist_ok=True)
    try:
        venues: dict = json.loads(CACHE_VENUES.read_text(encoding="utf-8"))
    except Exception:
        venues = {}

    eventos_por_torneio: list[tuple[str, str, list[dict]]] = []
    debug: dict[str, dict] = {}

    print("[INFO] Abrindo Chromium (Playwright) para contornar bloqueio do SofaScore...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125 Safari/537.36"
            ),
            locale="en-GB",
        )
        page = context.new_page()
        page.goto("https://www.sofascore.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)

        for uniq_id, pais, nome in torneios:
            label = f"{pais} - {nome}"
            try:
                res = page.evaluate(JS_EVENTOS, {"uniqId": uniq_id, "tsMin": ts_min, "tsMax": ts_max})
            except Exception as e:  # noqa: BLE001
                print(f"[WARN] {label}: falha ao buscar eventos: {e}")
                debug[label] = {"id": uniq_id, "erro": str(e)}
                continue
            eventos = [ev for ev in res.get("eventos", []) if ts_min <= (ev.get("startTimestamp") or 0) <= ts_max]
            debug[label] = {"id": uniq_id, "temporada": res.get("season"), "eventos_janela": len(eventos), "erro": res.get("erro")}
            eventos_por_torneio.append((pais, nome, eventos))
            print(f"  - {label} ({res.get('season') or res.get('erro')}): {len(eventos)} eventos na janela")
            time.sleep(0.5)

        faltando = sorted({
            str((ev.get("homeTeam") or {}).get("id"))
            for _, _, evs in eventos_por_torneio for ev in evs
        } - set(venues))
        if faltando:
            print(f"[INFO] Buscando estadio de {len(faltando)} times sem cache...")
            try:
                venues.update(page.evaluate(JS_VENUES, faltando))
            except Exception as e:  # noqa: BLE001
                print(f"[WARN] falha ao buscar venues: {e}")

        browser.close()

    CACHE_VENUES.write_text(json.dumps(venues, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    jogos_prog: list[Jogo] = []
    jogos_hist: list[Jogo] = []
    for pais, nome, eventos in eventos_por_torneio:
        for ev in eventos:
            jogo = evento_para_jogo(ev, pais, nome, venues)
            if not jogo:
                continue
            d = date.fromisoformat(jogo.data)
            if d >= hoje and "status=Realizado" not in jogo.extra:
                jogos_prog.append(jogo)
            else:
                jogos_hist.append(jogo)

    rows_prog = dedup_rows(jogos_prog)
    rows_hist = dedup_rows(jogos_hist)

    RAW_JOGOS.write_text(json.dumps(rows_prog, ensure_ascii=False, indent=2), encoding="utf-8")
    RAW_HISTORICO.write_text(json.dumps(rows_hist, ensure_ascii=False, indent=2), encoding="utf-8")
    DEBUG_EVENTOS.write_text(json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")

    n_prog, n_hist = salvar(rows_prog, rows_hist)
    print("")
    print(f"SofaScore UK/IE: {len(rows_prog)} programados, {len(rows_hist)} realizados/passados")
    print(f"data/reino_unido/jogos_programados.json: {n_prog} | historico_jogos.csv: {n_hist}")


if __name__ == "__main__":
    main()
