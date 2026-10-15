#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Argentina - todas as competicoes do SofaScore (profissionais, ascenso,
Consejo Federal e ligas regionais), via Playwright.

Mesmo esquema do scrap_reino_unido_sofascore.py: api.sofascore.com bloqueia
requests simples (Cloudflare), entao abrimos sofascore.com no Chromium e
fazemos os fetch() de dentro da pagina.

Os torneios NAO sao uma lista fixa: a cada execucao o scraper le as duas
categorias argentinas do SofaScore e pega tudo o que tiver jogo na janela:

  - categoria 48   "Argentina": LPF, Primera Nacional, Primera B Metro,
    Primera C, Federal A, Copa Argentina, Supercopa, Reserva, Femenino...
  - categoria 1783 "Argentina Amateur": Torneo Regional Federal Amateur
    (as 8 regioes), Copa Pais, Federal Juvenil e as ligas regionais que o
    SofaScore acompanha (General Roca, Laboulaye, Rionegrina, Centro Santa
    Cruz, San Francisco, Coronel Suarez, Riotercerense, Copa Cordoba...).

Assim uma liga que o SofaScore passar a cobrir entra sozinha. Em 14/10/2026
a Liga Marplatense (37591), a Liga del Sur de Bahia Blanca (37532), a
Santiaguena (37544) e a Sanluisena (37509) ja existem la, mas sem nenhum
jogo; a Marplatense vem do scrap_liga_marplatense.py.

Ficam de fora so os torneios de veteranos (Senior, +50, +55): nao sao o
publico do mapa e o SofaScore os cadastra em massa.

Saida no data/jogos_programados.json do site (formato/merge de sempre). As
divisoes que a AFA tambem publica viram duplicata ate o
`python argentina_comum.py --dedupe` rodar (o workflow ja chama).

Estadio/cidade/coordenadas: o evento na listagem nao traz venue; usamos o
venue do mandante (/team/{id}) com cache em data/argentina/cache_venues_sofascore.json.

Uso:
  python scrap_argentina_sofascore.py --dias 60 --dias-atras 7
  python scrap_argentina_sofascore.py --so 155,21340   # so alguns torneios (teste)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from argentina_comum import FONTE_SOFASCORE, OUT_DIR, para_local
from argentina_regional_cidades import atualizar_cidades

AR_DIR = OUT_DIR / "argentina"
RAW_JOGOS = OUT_DIR / "debug_argentina_sofascore_raw.json"
RAW_HISTORICO = OUT_DIR / "debug_argentina_sofascore_hist_raw.json"
DEBUG_EVENTOS = OUT_DIR / "debug_argentina_sofascore_eventos.json"
CACHE_VENUES = AR_DIR / "cache_venues_sofascore.json"

CATEGORIAS = [48, 1783]
VETERANOS_RE = re.compile(r"\bsenior|\+\s?5\d|super seniors?", re.IGNORECASE)
SUB_RE = re.compile(r"proyecc|\b(?:u|sub)[\s-]?\d{1,2}\b|juvenil|infantil|inferiores|newell'?s cup|reserv|cuarta|quinta|sexta|s[eé]ptima|octava|novena", re.IGNORECASE)
FEM_RE = re.compile(r"femen|women", re.IGNORECASE)

NOMES_TORNEIO = {
    # Mesmos rotulos do scrap_afa_agenda.py / scrap_afa_federal_a.py: o
    # filtro de campeonato do site fica com um nome so por competicao, e o
    # argentina_comum.py so deduplica jogos da MESMA competicao.
    703: "Primera Nacional",
    1347: "Primera B",
    11386: "Primera C",
    14090: "Torneo Federal A",
    1024: "Copa Argentina",
    1618: "Supercopa Argentina",
    18817: "Torneo Proyección",
    10495: "Fútbol Femenino Primera División A",
    # Nomes do SofaScore que nao dizem de que liga sao.
    31822: "Liga Regional San Francisco - Divisional A",
    31823: "Liga Regional San Francisco - Divisional B",
    31820: "Liga Regional San Francisco - Torneo Preparación",
}
ID_LPF = 155

# Ligas locais em que o SofaScore quase nunca tem o estadio dos times: sem
# venue, o jogo vai para a cidade-sede da liga (aproximacao, marcada no extra
# como local_aproximado=1). So ligas de uma cidade/microrregiao - o Regional
# Federal Amateur e nacional: la cada time vai para a cidade da sua liga,
# tirada da programacao do ascensodelinterior (argentina_regional_cidades.py).
_GENERAL_ROCA = ("General Roca", -39.0333, -67.5833)
_RIO_TERCERO = ("Río Tercero", -32.1730, -64.1141)
SEDE_LIGA = {
    21993: _GENERAL_ROCA, 25035: _GENERAL_ROCA, 25036: _GENERAL_ROCA,
    25037: _GENERAL_ROCA, 25038: _GENERAL_ROCA, 25039: _GENERAL_ROCA,
    22182: _RIO_TERCERO, 22183: _RIO_TERCERO, 22211: _RIO_TERCERO,
    25765: _RIO_TERCERO, 25766: _RIO_TERCERO,
    35872: ("Viedma", -40.8135, -63.0000),
    21967: ("Coronel Suárez", -37.4547, -61.9334),
    23050: ("Coronel Suárez", -37.4547, -61.9334),
    36552: ("Laboulaye", -34.1266, -63.3910),
    31820: ("San Francisco", -31.4272, -62.0847),
    31822: ("San Francisco", -31.4272, -62.0847),
    31823: ("San Francisco", -31.4272, -62.0847),
}


def nome_torneio(uid: int, nome_sofascore: str, data_jogo: date) -> str:
    if uid == ID_LPF:
        # A temporada da LPF no SofaScore junta Apertura (1o semestre) e Clausura
        return "Torneo Apertura" if data_jogo.month <= 6 else "Torneo Clausura"
    return NOMES_TORNEIO.get(uid) or re.sub(r"\s+", " ", nome_sofascore).strip()


def dentro_da_argentina(lat, lng) -> bool:
    """O SofaScore as vezes geocodifica pelo nome da cidade e erra o pais
    (Sportivo Belgrano de San Francisco/Cordoba caiu em San Francisco/EUA)."""
    try:
        return -55.5 <= float(lat) <= -21.5 and -73.8 <= float(lng) <= -53.5
    except (TypeError, ValueError):
        return False


@dataclass
class Jogo:
    fonte: str
    competicao: str
    data: str
    hora: str
    mandante: str
    visitante: str
    pais: str = "Argentina"
    cidade: str = ""
    estadio: str = ""
    rodada: str = ""
    url: str = ""
    extra: str = ""
    lat: float | None = None
    lng: float | None = None
    categoria: str = ""
    escopo: str = ""

    def to_row(self) -> dict:
        d = asdict(self)
        for k in ("lat", "lng", "categoria", "escopo"):
            if not d[k]:
                d.pop(k)
        raw = "|".join([self.fonte, self.competicao, self.data, self.hora, self.mandante, self.visitante])
        d["id"] = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
        d["atualizado_em"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return d


JS_TORNEIOS = """
async (cats) => {
    const out = [], status = [];
    for (const c of cats) {
        let r;
        try { r = await fetch(`https://www.sofascore.com/api/v1/category/${c}/unique-tournaments`); }
        catch (e) { status.push(`${c}: ${e}`); continue; }
        status.push(`${c}: HTTP ${r.status}`);
        if (!r.ok) continue;
        for (const g of ((await r.json()).groups || []))
            for (const t of (g.uniqueTournaments || [])) out.push({ id: t.id, nome: t.name, cat: c });
    }
    return { torneios: out, status };
}
"""

# Plano B se a listagem por categoria vier vazia (no GitHub Actions o
# primeiro fetch as vezes cai no challenge do Cloudflare): os torneios com
# jogo em 14/10/2026. (id, categoria, nome)
TORNEIOS_CONHECIDOS = [
    (155, 48, "Liga Profesional de Fútbol"), (1024, 48, "Copa Argentina"), (703, 48, "Primera Nacional"),
    (1347, 48, "Primera B Metropolitana"), (11386, 48, "Primera C Metropolitana"), (14090, 48, "Torneo Federal A"),
    (1618, 48, "Supercopa Argentina"), (10495, 48, "Campeonato de Fútbol Femenino"),
    (18817, 48, "Campeonato de Reserva de Primera División"),
    (21338, 1783, "Torneo Regional Federal Amateur – Región Norte"),
    (21339, 1783, "Torneo Regional Federal Amateur – Región Litoral Norte"),
    (21340, 1783, "Torneo Regional Federal Amateur – Región Centro"),
    (21341, 1783, "Torneo Regional Federal Amateur – Región Litoral Sur"),
    (21342, 1783, "Torneo Regional Federal Amateur – Región Cuyo"),
    (21343, 1783, "Torneo Regional Federal Amateur – Región Pampeana Norte"),
    (21344, 1783, "Torneo Regional Federal Amateur – Región Pampeana Sur"),
    (21345, 1783, "Torneo Regional Federal Amateur – Región Patagónica"),
    (21346, 1783, "Torneo Regional Federal Amateur"), (22246, 1783, "Torneo Regional Federal Juvenil Amateur"),
    (26840, 1783, "Copa País"), (29029, 1783, "Copa Córdoba"),
    (21836, 1783, "Liga Independiente de Las Colonias, Clausura"), (21919, 1783, "Liga Regional Colón, Primera"),
    (21993, 1783, "Liga Regional de Fútbol General Roca"), (22183, 1783, "Liga Regional Riotercerense de Fútbol - Primera B"),
    (23050, 1783, "Liga Regional de Coronel Suárez, Clausura"), (25035, 1783, "U20 Liga Regional de Fútbol General Roca"),
    (25036, 1783, "U15 Liga Regional de Fútbol General Roca"), (25037, 1783, "U13 Liga Regional de Fútbol General Roca"),
    (25038, 1783, "U11 Liga Regional de Fútbol General Roca"), (25396, 1783, "Liga Regional Colón, Reserva"),
    (25397, 1783, "Liga Regional Colón, Femenino"), (31822, 1783, "Divisional A"), (31823, 1783, "Divisional B"),
    (35872, 1783, "Liga Rionegrina de Fútbol"), (36087, 1783, "Liga de Fútbol Centro Santa Cruz"),
    (36552, 1783, "Liga Regional de Fútbol de Laboulaye"), (37591, 1783, "Liga Marplatense de Fútbol"),
]

# Temporada atual + eventos (last/next paginados) de um torneio, parando
# quando passa da janela de datas para nao varrer a temporada toda.
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
        for (let pagina = 0; pagina < 20; pagina++) {
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
                const c = (v && v.venueCoordinates) || {};
                out[id] = v
                    ? { estadio: (v.stadium || {}).name || v.name || '', cidade: (v.city || {}).name || '',
                        lat: c.latitude ?? null, lng: c.longitude ?? null }
                    : { estadio: '', cidade: '', lat: null, lng: null };
            } catch (e) {}
        }));
    }
    return out;
}
"""


# Na categoria "Argentina Amateur" (1783) quase tudo e liga local (escopo
# "Regional" no site, como as federacoes estaduais do Brasil); estes sao
# torneios nacionais do Consejo Federal / AFA e ficam "Nacional".
NACIONAIS_AMADORES_RE = re.compile(r"regional federal|copa pa[ií]s|federal juvenil|fiesta nacional|nacional b juvenil|\blpf\b|supercopa argentina", re.IGNORECASE)


def escopo_de(cat: int, nome: str) -> str:
    return "Regional" if cat == 1783 and not NACIONAIS_AMADORES_RE.search(nome) else ""


def categoria_de(nome: str) -> str:
    if SUB_RE.search(nome):
        return "Sub23"
    if FEM_RE.search(nome):
        return "Femenino"
    return ""


def evento_para_jogo(ev: dict, uid: int, cat: int, nome_sofascore: str, venues: dict,
                     cidades_times: dict | None = None) -> Jogo | None:
    home = ev.get("homeTeam") or {}
    away = ev.get("awayTeam") or {}
    mandante = (home.get("name") or home.get("shortName") or "").strip()
    visitante = (away.get("name") or away.get("shortName") or "").strip()
    ts = ev.get("startTimestamp")
    if not (mandante and visitante and ts):
        return None

    dt_local = para_local(ts)
    nome = nome_torneio(uid, nome_sofascore, dt_local.date())
    status = (ev.get("status") or {}).get("type", "")
    gh = (ev.get("homeScore") or {}).get("current")
    ga = (ev.get("awayScore") or {}).get("current")

    extra = ["pais=Argentina", f"codigo_sofascore={ev.get('id')}", f"time_sofascore={home.get('id')}"]
    if status == "finished" and gh is not None and ga is not None:
        extra += ["status=Realizado", f"placar={gh}-{ga}"]
    elif status in ("postponed", "canceled"):
        extra.append("status=Adiado" if status == "postponed" else "status=Cancelado")
    elif status == "inprogress":
        extra.append("status=Em andamento")
    else:
        extra.append("status=Programado")
    extra.append("fonte_dados=sofascore")

    ri = ev.get("roundInfo") or {}
    if ri.get("name"):
        rodada = ri["name"]
    elif ri.get("round") is not None:
        rodada = f"Fecha {ri['round']}"
    else:
        rodada = ""
    grupo = (ev.get("tournament") or {}).get("groupName") or ""
    if grupo and grupo not in rodada:
        rodada = f"{grupo} - {rodada}" if rodada else grupo

    venue = venues.get(str(home.get("id"))) or {}
    lat, lng = venue.get("lat"), venue.get("lng")
    if not dentro_da_argentina(lat, lng):
        lat = lng = None
    cidade = venue.get("cidade", "")
    if lat is None and uid in SEDE_LIGA:
        cidade, lat, lng = SEDE_LIGA[uid]
        extra.append("local_aproximado=1")
    elif lat is None and str(home.get("id")) in (cidades_times or {}):
        ct = cidades_times[str(home.get("id"))]
        cidade, lat, lng = ct["cidade"], ct["lat"], ct["lng"]
        extra.append("local_aproximado=1")
    slug = ev.get("slug", "")
    url = f"https://www.sofascore.com/football/match/{slug}/{ev.get('customId', '')}#id:{ev.get('id')}" if slug else ""

    return Jogo(
        fonte=FONTE_SOFASCORE,
        competicao=f"Argentina - {nome}",
        data=dt_local.date().isoformat(),
        hora=dt_local.strftime("%H:%M"),
        mandante=mandante,
        visitante=visitante,
        cidade=cidade,
        estadio=venue.get("estadio", ""),
        rodada=rodada,
        url=url,
        extra="; ".join(extra),
        lat=lat,
        lng=lng,
        categoria=categoria_de(nome),
        escopo=escopo_de(cat, nome),
    )


def chave_confronto_dia(ev: dict) -> tuple | None:
    ts = ev.get("startTimestamp")
    h = (ev.get("homeTeam") or {}).get("id")
    a = (ev.get("awayTeam") or {}).get("id")
    if not (ts and h and a):
        return None
    return (para_local(ts).date().isoformat(), h, a)


def main() -> None:
    parser = argparse.ArgumentParser(description="Argentina (todas as competicoes) via SofaScore/Playwright")
    parser.add_argument("--dias", type=int, default=60)
    parser.add_argument("--dias-atras", type=int, default=7, dest="dias_atras")
    parser.add_argument("--so", default="", help="lista de uniqueTournament ids separados por virgula (teste)")
    args = parser.parse_args()
    so = {int(x) for x in args.so.split(",") if x.strip()}

    hoje = date.today()
    limite_frente = hoje + timedelta(days=args.dias)
    limite_tras = hoje - timedelta(days=args.dias_atras)
    ts_min = int(datetime.combine(limite_tras, datetime.min.time(), tzinfo=timezone.utc).timestamp())
    ts_max = int(datetime.combine(limite_frente, datetime.max.time(), tzinfo=timezone.utc).timestamp())

    AR_DIR.mkdir(parents=True, exist_ok=True)
    try:
        venues: dict = json.loads(CACHE_VENUES.read_text(encoding="utf-8"))
    except Exception:
        venues = {}

    eventos_por_torneio: list[tuple[int, int, str, list[dict]]] = []
    debug: dict[str, dict] = {}

    print("[INFO] Abrindo Chromium (Playwright) para contornar bloqueio do SofaScore...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125 Safari/537.36"
            ),
            locale="es-AR",
        )
        page = context.new_page()
        page.goto("https://www.sofascore.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)

        torneios = []
        for tentativa in range(3):
            res = page.evaluate(JS_TORNEIOS, CATEGORIAS)
            torneios = res["torneios"]
            print(f"[INFO] categorias (tentativa {tentativa + 1}): {', '.join(res['status'])} -> {len(torneios)} torneios")
            if torneios:
                break
            page.wait_for_timeout(4000)
            page.goto("https://www.sofascore.com/football/argentina", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
        if not torneios:
            print("[WARN] listagem por categoria vazia; usando TORNEIOS_CONHECIDOS")
            torneios = [{"id": i, "cat": c, "nome": n} for i, c, n in TORNEIOS_CONHECIDOS]
        vistos: set[int] = set()
        for t in torneios:
            uid = t["id"]
            nome = t["nome"]
            if uid in vistos or (so and uid not in so):
                continue
            vistos.add(uid)
            if VETERANOS_RE.search(nome):
                continue
            try:
                res = page.evaluate(JS_EVENTOS, {"uniqId": uid, "tsMin": ts_min, "tsMax": ts_max})
            except Exception as e:  # noqa: BLE001
                print(f"[WARN] {nome}: falha ao buscar eventos: {e}")
                debug[nome] = {"id": uid, "erro": str(e)}
                continue
            eventos = [
                ev for ev in res.get("eventos", [])
                if ts_min <= (ev.get("startTimestamp") or 0) <= ts_max
                and ((ev.get("tournament") or {}).get("category") or {}).get("sport", {}).get("slug", "football") == "football"
            ]
            debug[nome] = {"id": uid, "categoria": t["cat"], "temporada": res.get("season"),
                           "eventos_janela": len(eventos), "erro": res.get("erro")}
            if eventos:
                eventos_por_torneio.append((uid, t["cat"], nome, eventos))
                print(f"  - {nome} ({res.get('season')}): {len(eventos)} eventos na janela")
            time.sleep(0.3)

        faltando = sorted({
            str((ev.get("homeTeam") or {}).get("id"))
            for _, _, _, evs in eventos_por_torneio for ev in evs
        } - set(venues))
        if faltando:
            print(f"[INFO] Buscando estadio de {len(faltando)} times sem cache...")
            try:
                venues.update(page.evaluate(JS_VENUES, faltando))
            except Exception as e:  # noqa: BLE001
                print(f"[WARN] falha ao buscar venues: {e}")

        browser.close()

    CACHE_VENUES.write_text(json.dumps(venues, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    cidades_times = atualizar_cidades(
        [(nome, ev) for _, _, nome, eventos in eventos_por_torneio for ev in eventos], venues)

    # Jogo remarcado: o SofaScore cria evento novo e o velho continua
    # "programado" no mesmo dia. Fica o evento mais novo (maior id).
    mais_novo: dict[tuple, int] = {}
    for _, _, _, eventos in eventos_por_torneio:
        for ev in eventos:
            ch = chave_confronto_dia(ev)
            if ch:
                mais_novo[ch] = max(mais_novo.get(ch, 0), int(ev.get("id") or 0))

    rows_prog: list[dict] = []
    rows_hist: list[dict] = []
    ids_vistos: set[int] = set()
    for uid, cat, nome, eventos in eventos_por_torneio:
        for ev in eventos:
            ch = chave_confronto_dia(ev)
            eid = int(ev.get("id") or 0)
            if (ch and eid != mais_novo[ch]) or eid in ids_vistos:
                continue
            ids_vistos.add(eid)
            jogo = evento_para_jogo(ev, uid, cat, nome, venues, cidades_times)
            if not jogo:
                continue
            if date.fromisoformat(jogo.data) >= hoje and "status=Realizado" not in jogo.extra:
                rows_prog.append(jogo.to_row())
            else:
                rows_hist.append(jogo.to_row())

    RAW_JOGOS.write_text(json.dumps(rows_prog, ensure_ascii=False, indent=2), encoding="utf-8")
    RAW_HISTORICO.write_text(json.dumps(rows_hist, ensure_ascii=False, indent=2), encoding="utf-8")
    DEBUG_EVENTOS.write_text(json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")

    print("")
    print(f"SofaScore Argentina: {len(eventos_por_torneio)} torneios com jogos | "
          f"{len(rows_prog)} programados, {len(rows_hist)} realizados/passados")
    print(f"Raw: {RAW_JOGOS} / {RAW_HISTORICO} (o merge e feito pelo merge_apos_reset.py)")


if __name__ == "__main__":
    main()
