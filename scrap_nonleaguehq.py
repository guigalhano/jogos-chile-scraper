#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reino Unido - futebol nao-liga (amador/semiamador) via NonLeagueHQ
(https://www.nonleaguehq.com), complementando o scrap_reino_unido_sofascore.py
nas divisoes que o SofaScore nao cobre.

Fontes (HTML estatico do WordPress/wpDataTables, requests simples funciona):

- Inglaterra: o indice https://www.nonleaguehq.com/england-next-fixtures/
  linka uma pagina por liga ("england-next-fixtures-<liga>/" e
  "english-next-fixtures-national-league-<north|south>/"), cada uma com UMA
  tabela com todos os jogos restantes da temporada:
      League | Date | Home | H | v | A | Away
  "League" vem como "5. Essex Senior League" (o numero e o step da piramide).
  Pulamos a National League (step 1), que ja vem do SofaScore com horario.

- Escocia / Gales / Irlanda do Norte: as paginas "fixture-finder-<pais>/"
  trazem a temporada inteira (resultados + proximos jogos) numa tabela so:
      League | Date | HOME | H | v | A | AWAY | County | Region
  com "League" num codigo curto (ex.: 1HL, 3NIPI, 4GCL). O primeiro digito e
  o nivel dentro do futebol nao-liga do pais. NAO ha legenda dos codigos no
  site; ver NOMES_CODIGOS abaixo (codigo desconhecido vira "Liga <codigo>").
  ATENCAO (Escocia): o codigo NAO e confiavel. O "2ESP", por exemplo, mistura
  jogos da East of Scotland, da North Caledonian e da North of Scotland. Por
  isso o nome da liga vem dos confrontos: cada grupo de times que se enfrentam
  (componente conexa do grafo de jogos da temporada) e uma liga real, e o
  grupo e identificado por clubes-ancora (LIGAS_ANCORA). O codigo so e usado
  quando o grupo nao tem ancora conhecida, ou tem ancoras de duas ligas.
  Gales: a Ardal (3A*, tier 3) vem daqui e nao do SofaScore, que so tem os
  resultados dela, sem os jogos programados.

O NonLeagueHQ so publica a DATA (sem horario): hora fica vazia.

Identidade do jogo (codigo_nlhq no extra): liga + mandante + visitante +
temporada. Numa liga cada confronto acontece uma vez com o mesmo mandante
por temporada, entao um jogo adiado para outra data atualiza a linha
existente em vez de duplicar.

Uso:
  python scrap_nonleaguehq.py --dias 270 --dias-atras 15
  python scrap_nonleaguehq.py --max-ligas 3          # teste rapido
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup

from reino_unido_comum import (
    ESCOCIA, GALES, INGLATERRA, IRLANDA_NORTE, OUT_DIR, Jogo, dedup_rows, salvar,
)

BASE = "https://www.nonleaguehq.com"
INDICE_INGLATERRA = f"{BASE}/england-next-fixtures/"
FIXTURE_FINDERS = [
    (ESCOCIA, f"{BASE}/fixture-finder-scotland/"),
    (GALES, f"{BASE}/fixture-finder-wales/"),
    (IRLANDA_NORTE, f"{BASE}/fixture-finder-northern-ireland/"),
]

RAW_JOGOS = OUT_DIR / "debug_nonleaguehq_raw.json"
RAW_HISTORICO = OUT_DIR / "debug_nonleaguehq_hist_raw.json"
DEBUG_PAGINAS = OUT_DIR / "debug_nonleaguehq_pages.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

# Paginas do indice ingles que NAO entram (ja cobertas pelo SofaScore).
PULAR_INGLATERRA = {"english-next-fixtures-national-league-premier"}

# Codigos dos fixture finders -> nome da liga. Montado em 11/10/2026 a
# partir dos clubes de cada codigo; so entram os que deu para confirmar.
NOMES_CODIGOS = {
    # Escocia
    "1HL": "Highland League",
    "1LLE": "Lowland League East",
    "1LLW": "Lowland League West",
    "2ESP": "East of Scotland League Premier",
    "2WSP": "West of Scotland League Premier",
    # Pais de Gales
    "3ANE": "Ardal League North East",
    "3ANW": "Ardal League North West",
    "3ASE": "Ardal League South East",
    "3ASW": "Ardal League South West",
    "4CWN": "Central Wales League North",
    "4CWS": "Central Wales League South",
    "4GCL": "Gwent County League",
    "4NCE": "North Wales Coast East League",
    "4NCW": "North Wales Coast West League",
    "4SWA": "South Wales Alliance League",
    "4WWP": "West Wales Premier League",
    "5CLP": "Carmarthenshire League Premier",
    "5CLD1": "Ceredigion League Division One",
    "5ALD1": "Aberystwyth League Division One",
    # Irlanda do Norte
    "3NIPI": "NIFL Premier Intermediate League",
    "4MULA": "Mid-Ulster League Intermediate A",
    "5MULB": "Mid-Ulster League Intermediate B",
    "4NALP": "Northern Amateur League Premier",
    "5NAL1A": "Northern Amateur League 1A",
    # Pais de Gales (confirmado pelos clubes: Castell Alun Colts, Saltney Town...)
    "4NE1": "North East Wales League Division One",
}

# Ligas que vem do SofaScore (com horario): nao entram daqui.
CODIGOS_DO_SOFASCORE = {"3NIPI"}  # NIFL Premier Intermediate League (SofaScore 31777)

# Codigos cujo primeiro digito nao bate com o nivel real.
NIVEL_CODIGO = {
    "4NE1": 5,  # abaixo da North East Wales Premier (nivel 4)
}

# Ligas identificadas pelos confrontos (ver docstring). Para cada pais:
# nome da liga -> (nivel_naoliga, clubes-ancora). Basta UMA ancora num grupo
# de times para nomear o grupo; usar clubes estaveis, que nao mudam de liga
# com frequencia. Montado em 12/10/2026 a partir da temporada 2026-27.
LIGAS_ANCORA = {
    ESCOCIA: {
        "Highland League": (1, {"Brora Rangers", "Buckie Thistle", "Huntly", "Keith"}),
        "Lowland League East": (1, {"Berwick Rangers", "Bonnyrigg Rose", "Linlithgow Rose", "Tranent"}),
        "Lowland League West": (1, {"Auchinleck Talbot", "Pollok", "Gretna 2008", "Clydebank"}),
        "East of Scotland League Premier": (2, {"Armadale Thistle", "Dunbar United", "Penicuik Athletic", "Haddington Athletic"}),
        "West of Scotland League Premier": (2, {"Hurlford United", "Glenafton Athletic", "Darvel", "Kirkintilloch Rob Roy"}),
        "Midlands League": (2, {"Downfield", "Carnoustie Panmure", "Dundee North End", "Lochee Harp"}),
        "North Caledonian League": (2, {"Golspie Sutherland", "Thurso", "Halkirk United", "Orkney"}),
        "North of Scotland League Premier": (2, {"Maud", "Dyce", "Culter", "Longside"}),
        "South of Scotland League": (2, {"Lochar Thistle", "Mid Annandale", "Creetown", "Nithsdale Wanderers"}),
        "East of Scotland League First Division": (3, {"Glenrothes", "Leith Athletic", "Whitehill Welfare", "Lochore Welfare"}),
        "West of Scotland League First Division": (3, {"Bellshill Athletic", "Cambuslang Rangers", "Petershill", "Maryhill"}),
        "North of Scotland League Championship": (3, {"Banchory St Ternan", "Cruden Bay", "Glentanar", "Dufftown"}),
    },
}

CODIGO_RE = re.compile(r"^(\d)([A-Z][A-Z0-9]*)$")
STEP_RE = re.compile(r"^(\d+)\.\s*(.+)$")


def clean(x) -> str:
    return re.sub(r"\s+", " ", ("" if x is None else str(x)).replace(" ", " ")).strip()


def baixar(session: requests.Session, url: str, timeout: int) -> str:
    r = session.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text


def parse_data(txt: str) -> date | None:
    txt = clean(txt)
    for fmt in ("%d-%b-%y", "%d-%m-%y", "%a, %b %d, %Y", "%d-%b-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            pass
    return None


def temporada(d: date) -> str:
    # Temporada britanica vai de julho a junho.
    ini = d.year if d.month >= 7 else d.year - 1
    return f"{ini}-{str(ini + 1)[2:]}"


def montar_jogo(pais: str, liga: str, nivel: str, d: date, mandante: str, visitante: str,
                gh: str, ga: str, url: str, extra_regiao: str = "") -> Jogo:
    competicao = f"{pais} - {liga}"
    chave = "|".join([competicao, mandante, visitante, temporada(d)])
    codigo = hashlib.sha1(chave.encode("utf-8")).hexdigest()[:12]

    extra = [f"codigo_nlhq={codigo}"]
    if gh.isdigit() and ga.isdigit():
        extra += ["status=Realizado", f"placar={gh}-{ga}"]
    elif d >= date.today():
        extra.append("status=Programado")
    else:
        extra.append("status=Sem resultado")
    if nivel:
        extra.append(nivel)
    if extra_regiao:
        extra.append(extra_regiao)
    extra.append("sem_horario=1")

    return Jogo(
        fonte="NonLeagueHQ",
        competicao=competicao,
        data=d.isoformat(),
        hora="",
        mandante=mandante,
        visitante=visitante,
        pais=pais,
        url=url,
        extra="; ".join(extra),
    )


def urls_ligas_inglaterra(session: requests.Session, timeout: int) -> list[str]:
    html = baixar(session, INDICE_INGLATERRA, timeout)
    urls = sorted(set(re.findall(
        r"https://www\.nonleaguehq\.com/(?:england|english)-next-fixtures-[a-z0-9-]+/", html
    )))
    return [u for u in urls if u.rstrip("/").rsplit("/", 1)[-1] not in PULAR_INGLATERRA]


def jogos_pagina_inglaterra(html: str, url: str) -> list[Jogo]:
    s = BeautifulSoup(html, "lxml")
    jogos: list[Jogo] = []
    for t in s.find_all("table"):
        for tr in t.find_all("tr"):
            c = [clean(td.get_text(" ")) for td in tr.find_all(["td", "th"])]
            if len(c) < 7 or c[0] == "League":
                continue
            d = parse_data(c[1])
            mandante, visitante = c[2], c[6]
            if not (d and mandante and visitante):
                continue
            m = STEP_RE.match(c[0])
            liga, nivel = (m.group(2), f"step={m.group(1)}") if m else (c[0], "")
            jogos.append(montar_jogo(INGLATERRA, liga, nivel, d, mandante, visitante, c[3], c[5], url))
    return jogos


def normalizar_codigo(codigo: str) -> str:
    """Alguns codigos vem com o numero do jogo colado (5ALD19, 5ALD33...
    sao todos jogos da 5ALD1). Se um codigo conhecido e prefixo, usa ele."""
    if codigo in NOMES_CODIGOS:
        return codigo
    prefixos = [k for k in NOMES_CODIGOS if codigo.startswith(k.rstrip("0123456789"))]
    return max(prefixos, key=len) if prefixos else codigo


def grupos_de_times(pares: list[tuple[str, str]]) -> dict[str, str]:
    """Componentes conexas do grafo de confrontos: time -> representante."""
    pai: dict[str, str] = {}

    def raiz(x: str) -> str:
        pai.setdefault(x, x)
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    for a, b in pares:
        ra, rb = raiz(a), raiz(b)
        if ra != rb:
            pai[ra] = rb
    return {t: raiz(t) for t in pai}


def nomear_grupos(linhas: list[dict], pais: str) -> tuple[dict[str, tuple[str, int]], list[str]]:
    """Representante do grupo -> (liga, nivel), so para grupos com ancora unica."""
    ancoras = LIGAS_ANCORA.get(pais)
    if not ancoras:
        return {}, []
    grupo = grupos_de_times([(l["mandante"], l["visitante"]) for l in linhas])
    times_por_grupo: dict[str, set[str]] = {}
    for t, g in grupo.items():
        times_por_grupo.setdefault(g, set()).add(t)
    nomes: dict[str, tuple[str, int]] = {}
    avisos: list[str] = []
    for g, times in times_por_grupo.items():
        achadas = [(liga, niv) for liga, (niv, anc) in ancoras.items() if times & anc]
        if len(achadas) == 1:
            nomes[g] = achadas[0]
        elif len(achadas) > 1:
            avisos.append(
                "grupo com ancoras de " + " + ".join(sorted(l for l, _ in achadas))
                + f" ({len(times)} times): usando o codigo do site"
            )
    return nomes, avisos


def jogos_fixture_finder(html: str, pais: str, url: str) -> tuple[list[Jogo], dict[str, int], list[str]]:
    s = BeautifulSoup(html, "lxml")
    linhas: list[dict] = []
    t = s.find("table")
    if not t:
        return [], {}, []
    for tr in t.find_all("tr"):
        c = [clean(td.get_text(" ")) for td in tr.find_all("td")]
        if len(c) < 7:
            continue
        if not CODIGO_RE.match(c[0]):
            continue
        if c[0] in CODIGOS_DO_SOFASCORE:
            continue
        d = parse_data(c[1])
        mandante, visitante = c[2], c[6]
        if not (d and mandante and visitante):
            continue
        linhas.append({
            "codigo": normalizar_codigo(c[0]), "data": d, "mandante": mandante, "visitante": visitante,
            "gh": c[3], "ga": c[5],
            "condado": c[7] if len(c) > 7 and c[7] not in ("", "#N/A") else "",
            "regiao": c[8] if len(c) > 8 and c[8] not in ("", "#N/A") else "",
        })
    return montar_jogos_finder(linhas, pais, url)


def montar_jogos_finder(linhas: list[dict], pais: str, url: str) -> tuple[list[Jogo], dict[str, int], list[str]]:
    nomes, avisos = nomear_grupos(linhas, pais)
    grupo = grupos_de_times([(l["mandante"], l["visitante"]) for l in linhas]) if nomes else {}
    jogos: list[Jogo] = []
    por_codigo: dict[str, int] = {}
    for l in linhas:
        codigo = l["codigo"]
        g = grupo.get(l["mandante"])
        if g in nomes:
            liga, nivel = nomes[g]
            origem = "confrontos"
        else:
            liga = NOMES_CODIGOS.get(codigo, f"Liga {codigo}")
            nivel = NIVEL_CODIGO.get(codigo, int(CODIGO_RE.match(codigo).group(1)))
            origem = "codigo"
        loc = "; ".join(x for x in (
            f"condado={l['condado']}" if l["condado"] else "",
            f"regiao={l['regiao']}" if l["regiao"] else "",
        ) if x)
        jogos.append(montar_jogo(
            pais, liga, f"nivel_naoliga={nivel}; codigo_liga_nlhq={codigo}; liga_por={origem}",
            l["data"], l["mandante"], l["visitante"], l["gh"], l["ga"], url, loc,
        ))
        por_codigo[codigo] = por_codigo.get(codigo, 0) + 1
    return jogos, por_codigo, avisos


def main() -> None:
    parser = argparse.ArgumentParser(description="Futebol nao-liga do Reino Unido via NonLeagueHQ")
    parser.add_argument("--dias", type=int, default=270)
    parser.add_argument("--dias-atras", type=int, default=15, dest="dias_atras")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--max-ligas", type=int, default=0, help="limita as paginas inglesas (teste)")
    args = parser.parse_args()

    hoje = date.today()
    limite_frente = hoje + timedelta(days=args.dias)
    limite_tras = hoje - timedelta(days=args.dias_atras)

    session = requests.Session()
    todos: list[Jogo] = []
    debug: list[dict] = []

    urls = urls_ligas_inglaterra(session, args.timeout)
    if args.max_ligas:
        urls = urls[: args.max_ligas]
    print(f"[INFO] Inglaterra: {len(urls)} paginas de liga")
    for url in urls:
        try:
            jogos = jogos_pagina_inglaterra(baixar(session, url, args.timeout), url)
            todos += jogos
            debug.append({"url": url, "jogos": len(jogos)})
            if not jogos:
                # Algumas ligas do step 7 aparecem so com "#N/A" no proprio site.
                print(f"[INFO] sem jogos publicados: {url}")
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] {url}: {e}")
            debug.append({"url": url, "erro": f"{type(e).__name__}: {e}"})
        time.sleep(0.5)

    for pais, url in FIXTURE_FINDERS:
        try:
            jogos, por_codigo, avisos = jogos_fixture_finder(baixar(session, url, args.timeout), pais, url)
            todos += jogos
            sem_nome = sorted({j.competicao for j in jogos if " - Liga " in j.competicao})
            debug.append({"url": url, "jogos": len(jogos), "por_codigo": por_codigo,
                          "sem_nome": sem_nome, "avisos": avisos})
            print(f"[INFO] {pais}: {len(jogos)} jogos" + (f" (sem nome: {', '.join(sem_nome)})" if sem_nome else ""))
            for a in avisos:
                print(f"[WARN] {pais}: {a}")
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] {url}: {e}")
            debug.append({"url": url, "erro": f"{type(e).__name__}: {e}"})
        time.sleep(0.5)

    jogos_prog: list[Jogo] = []
    jogos_hist: list[Jogo] = []
    for j in todos:
        d = date.fromisoformat(j.data)
        if not (limite_tras <= d <= limite_frente):
            continue
        if d >= hoje and "status=Realizado" not in j.extra:
            jogos_prog.append(j)
        else:
            jogos_hist.append(j)

    rows_prog = dedup_rows(jogos_prog)
    rows_hist = dedup_rows(jogos_hist)

    RAW_JOGOS.write_text(json.dumps(rows_prog, ensure_ascii=False, indent=2), encoding="utf-8")
    RAW_HISTORICO.write_text(json.dumps(rows_hist, ensure_ascii=False, indent=2), encoding="utf-8")
    DEBUG_PAGINAS.write_text(json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")

    n_prog, n_hist = salvar(rows_prog, rows_hist)
    print("")
    print(f"NonLeagueHQ: {len(todos)} jogos lidos | {len(rows_prog)} programados e {len(rows_hist)} passados na janela")
    print(f"data/reino_unido/jogos_programados.json: {n_prog} | historico_jogos.csv: {n_hist}")


if __name__ == "__main__":
    main()
