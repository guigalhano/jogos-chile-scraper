#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copas nacionais inglesas pelo site da FA (thefa.com): FA Trophy, FA Vase,
FA Sunday Cup, Women's FA Cup e FA Youth Cup, com data, horario e, quando
publicado, o estadio.

Por que o site da FA e nao o Full-Time: as ligas e copas de condado ficam
no FA Full-Time (fulltime.thefa.com), cujo robots.txt proibe coleta
automatica - os sites das ligas (ex.: wessexleague.co.uk/fixtures) so
embutem o widget dele. Ja as paginas de jogos das copas nacionais em
thefa.com sao HTML server-side e o robots.txt permite.

Paginas (HTML, paginadas de 20 em 20):
    https://www.thefa.com/competitions/<slug>/fixtures
    https://www.thefa.com/Competitions/Fixtures/Fixtures?competitionId=<N>&page=<P>
A FA publica uma fase por vez (a proxima rodada sorteada), entao cada
execucao traz algumas dezenas de jogos por copa.

FA Cup NAO entra: ja vem do SofaScore (scrap_reino_unido_sofascore.py).

O parser le o texto da pagina em ordem (cabecalho de data -> horario ->
"No. N" -> mandante -> "v" -> visitante -> estadio), sem depender de
classes CSS. Para depurar: --debug-html grava o HTML em
data/debug_thefa_html/.

Uso:
    python scrap_thefa_copas.py --dias 270 --dias-atras 15
    python scrap_thefa_copas.py --dry-run --debug-html     # teste
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from reino_unido_comum import INGLATERRA, OUT_DIR, Jogo, dedup_rows, salvar

BASE = "https://www.thefa.com"
ID_URL = BASE + "/Competitions/Fixtures/Fixtures?competitionId={id}&page={page}"

# (nome, categoria, paginas da copa (primeira que responder), competitionId conhecido)
# competitionId levantados em 12/10/2026: 2 Sunday Cup, 3 Trophy, 5 Women's
# FA Cup, 6 Youth Cup. O da Vase nao apareceu; sai da paginacao da pagina dela.
COPAS = [
    ("FA Trophy", "", ["/competitions/fa-trophy/fixtures"], 3),
    ("FA Vase", "", ["/competitions/fa-vase/fixtures"], None),
    ("FA Sunday Cup", "", ["/competitions/grassroots/fa-sunday-cup/fixtures", "/competitions/fa-sunday-cup/fixtures"], 2),
    ("Women's FA Cup", "feminino", ["/competitions/womens-fa-cup/fixtures", "/competitions/the-womens-fa-cup/fixtures"], 5),
    ("FA Youth Cup", "reservas", ["/competitions/fa-youth-cup/fixtures"], 6),
]

RAW_JOGOS = OUT_DIR / "debug_thefa_raw.json"
RAW_HISTORICO = OUT_DIR / "debug_thefa_hist_raw.json"
DEBUG_PAGINAS = OUT_DIR / "debug_thefa_pages.json"
HTML_DIR = OUT_DIR / "debug_thefa_html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

MESES = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}
DATA_RE = re.compile(
    r"^(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)?,?\s*"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\s+(\d{4})$", re.I)
HORA_RE = re.compile(r"^(\d{1,2})[:.](\d{2})$")
NUMERO_RE = re.compile(r"^no\.?\s*(\d+)$", re.I)
VS_RE = re.compile(r"^(?:v|vs\.?|versus)$", re.I)
VS_INLINE_RE = re.compile(r"^(.+?)\s+(?:v|vs\.?)\s+(.+)$")
INFO_RE = re.compile(r"\(?information\)?", re.I)
FASE_RE = re.compile(r"(round|qualifying|preliminary|final|replay)", re.I)
PAGINA_RE = re.compile(r"Fixtures/Fixtures\?competitionId=(\d+)(?:&amp;|&)page=(\d+)", re.I)
RUIDO = ("live on", "bbc", "itv", "tnt sport", "sky sports", "youtube", "replay", "postponed",
         "fixture dates and times", "kick-off", "kick off", "tbc", "watch", "highlights")


def clean(x) -> str:
    return re.sub(r"\s+", " ", ("" if x is None else str(x)).replace("\xa0", " ")).strip()


def temporada(d: date) -> str:
    ini = d.year if d.month >= 7 else d.year - 1
    return f"{ini}-{str(ini + 1)[2:]}"


def parse_data(txt: str) -> date | None:
    m = DATA_RE.match(clean(txt))
    if not m or m.group(2).lower() not in MESES:
        return None
    try:
        return date(int(m.group(3)), MESES[m.group(2).lower()], int(m.group(1)))
    except ValueError:
        return None


def linhas_texto(html: str) -> list[str]:
    s = BeautifulSoup(html, "lxml")
    for tag in s(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        tag.decompose()
    raiz = s.find("main") or s.body or s
    return [l for l in (clean(x) for x in raiz.get_text("\n").splitlines()) if l]


def e_ruido(l: str) -> bool:
    n = l.lower()
    return any(k in n for k in RUIDO)


def e_time(l: str) -> bool:
    return bool(l) and len(l) <= 70 and not (
        parse_data(l) or HORA_RE.match(l) or NUMERO_RE.match(l) or VS_RE.match(l) or e_ruido(l)
    ) and not re.fullmatch(r"[\d\s\-:()<>|]+", l)


def parse_pagina(html: str) -> list[dict]:
    """Jogos de uma pagina: dicts com data, hora, numero, fase, mandante, visitante, estadio."""
    ls = linhas_texto(html)
    jogos: list[dict] = []
    data_atual: date | None = None
    fase = ""
    hora = ""
    numero = ""
    i = 0
    while i < len(ls):
        l = ls[i]
        d = parse_data(l)
        if d:
            data_atual, hora, numero = d, "", ""
            i += 1
            continue
        if FASE_RE.search(l) and len(l) <= 40 and not VS_INLINE_RE.match(l):
            fase = l
            i += 1
            continue
        mh = HORA_RE.match(l)
        if mh:
            hora = f"{int(mh.group(1)):02d}:{mh.group(2)}"
            i += 1
            continue
        mn = NUMERO_RE.match(l)
        if mn:
            numero = mn.group(1)
            i += 1
            continue

        mandante = visitante = ""
        prox = i + 1
        if VS_RE.match(l) and i > 0 and i + 1 < len(ls) and e_time(ls[i - 1]) and e_time(ls[i + 1]):
            mandante, visitante, prox = ls[i - 1], ls[i + 1], i + 2
        else:
            mv = VS_INLINE_RE.match(l)
            if mv and e_time(mv.group(1)) and e_time(mv.group(2)) and data_atual:
                mandante, visitante = mv.group(1), mv.group(2)
        if mandante and visitante and data_atual and mandante != visitante:
            # Estadio: a linha logo depois do visitante, se nao for o comeco
            # do proximo jogo (mandante seguido de "v") nem data/hora/numero.
            estadio = ""
            if prox < len(ls):
                cand = re.sub(r"^(?:at|venue:?)\s+", "", ls[prox], flags=re.I)
                seguinte = ls[prox + 1] if prox + 1 < len(ls) else ""
                # "information" e o texto de um link de detalhes, nao o estadio.
                if (e_time(cand) and not INFO_RE.fullmatch(cand)
                        and not VS_RE.match(seguinte) and not VS_INLINE_RE.match(ls[prox])):
                    estadio = cand
                    prox += 1
            jogos.append({
                "data": data_atual, "hora": hora, "numero": numero, "fase": fase,
                "mandante": mandante, "visitante": visitante, "estadio": estadio,
            })
            hora, numero = "", ""
            i = prox
            continue
        i += 1
    return jogos


def paginas_extras(html: str) -> dict[int, set[int]]:
    """competitionId -> paginas citadas na paginacao."""
    out: dict[int, set[int]] = {}
    for cid, pag in PAGINA_RE.findall(html):
        out.setdefault(int(cid), set()).add(int(pag))
    return out


def baixar(session: requests.Session, url: str, timeout: int) -> requests.Response:
    return session.get(url, headers=HEADERS, timeout=timeout)


def jogos_da_copa(session: requests.Session, nome: str, slugs: list[str], cid: int | None,
                  timeout: int, debug_html: bool, debug: list[dict]) -> list[dict]:
    htmls: list[tuple[str, str]] = []
    for slug in slugs:
        url = urljoin(BASE, slug)
        try:
            r = baixar(session, url, timeout)
        except Exception as e:  # noqa: BLE001
            debug.append({"copa": nome, "url": url, "erro": f"{type(e).__name__}: {e}"})
            continue
        debug.append({"copa": nome, "url": url, "status": r.status_code, "bytes": len(r.content)})
        if r.status_code == 200 and "find that page" not in r.text and "404 error" not in r.text:
            htmls.append((url, r.text))
            break

    pags = paginas_extras(htmls[0][1]) if htmls else {}
    if cid is None and len(pags) == 1:
        cid = next(iter(pags))
    if cid is not None:
        vistas = {1} if htmls else set()
        a_buscar = sorted((pags.get(cid, set()) | {1}) - vistas) or ([] if htmls else [1])
        while a_buscar:
            p = a_buscar.pop(0)
            url = ID_URL.format(id=cid, page=p)
            try:
                r = baixar(session, url, timeout)
            except Exception as e:  # noqa: BLE001
                debug.append({"copa": nome, "url": url, "erro": f"{type(e).__name__}: {e}"})
                break
            debug.append({"copa": nome, "url": url, "status": r.status_code, "bytes": len(r.content)})
            if r.status_code != 200:
                break
            htmls.append((url, r.text))
            vistas.add(p)
            novas = paginas_extras(r.text).get(cid, set()) - vistas - set(a_buscar)
            a_buscar = sorted(set(a_buscar) | {n for n in novas if n <= 30})
            time.sleep(0.5)

    jogos: list[dict] = []
    vistos: set[tuple] = set()
    for n, (url, html) in enumerate(htmls, 1):
        if debug_html:
            HTML_DIR.mkdir(parents=True, exist_ok=True)
            slug = re.sub(r"[^a-z0-9]+", "_", nome.lower()).strip("_")
            (HTML_DIR / f"{slug}_{n}.html").write_text(html, encoding="utf-8")
        achados = parse_pagina(html)
        debug.append({"copa": nome, "url": url, "jogos_parseados": len(achados),
                      "amostra": [f"{j['data']} {j['hora']} {j['mandante']} v {j['visitante']} @ {j['estadio']}"
                                  for j in achados[:3]]})
        for j in achados:
            k = (j["data"], j["mandante"], j["visitante"])
            if k in vistos:
                continue
            vistos.add(k)
            j["url"] = url
            jogos.append(j)
    return jogos


def montar(j: dict, nome: str, categoria: str) -> Jogo:
    competicao = f"{INGLATERRA} - {nome}"
    chave = "|".join([competicao, temporada(j["data"]), j["fase"], j["mandante"], j["visitante"]])
    extra = [f"codigo_fa={hashlib.sha1(chave.encode('utf-8')).hexdigest()[:12]}", "status=Programado"]
    if j["numero"]:
        extra.append(f"jogo_numero={j['numero']}")
    if categoria:
        extra.append(f"categoria={categoria}")
    if not j["hora"]:
        extra.append("sem_horario=1")
    return Jogo(
        fonte="FA",
        competicao=competicao,
        data=j["data"].isoformat(),
        hora=j["hora"],
        mandante=j["mandante"],
        visitante=j["visitante"],
        pais=INGLATERRA,
        estadio=j["estadio"],
        rodada=j["fase"],
        url=j["url"],
        extra="; ".join(extra),
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Copas nacionais inglesas via thefa.com")
    ap.add_argument("--dias", type=int, default=270)
    ap.add_argument("--dias-atras", type=int, default=15, dest="dias_atras")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--debug-html", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="so mostra, nao grava em data/reino_unido/")
    args = ap.parse_args()

    hoje = date.today()
    limite_frente = hoje + timedelta(days=args.dias)
    limite_tras = hoje - timedelta(days=args.dias_atras)

    session = requests.Session()
    debug: list[dict] = []
    prog: list[Jogo] = []
    hist: list[Jogo] = []
    for nome, categoria, slugs, cid in COPAS:
        jogos = jogos_da_copa(session, nome, slugs, cid, args.timeout, args.debug_html, debug)
        print(f"[INFO] {nome}: {len(jogos)} jogos")
        for j in jogos[:3]:
            print(f"        {j['data']} {j['hora'] or '--:--'} {j['mandante']} v {j['visitante']}"
                  + (f" ({j['estadio']})" if j["estadio"] else "") + (f" [{j['fase']}]" if j["fase"] else ""))
        for j in jogos:
            if not (limite_tras <= j["data"] <= limite_frente):
                continue
            (prog if j["data"] >= hoje else hist).append(montar(j, nome, categoria))

    rows_prog = dedup_rows(prog)
    rows_hist = dedup_rows(hist)
    RAW_JOGOS.write_text(json.dumps(rows_prog, ensure_ascii=False, indent=2), encoding="utf-8")
    RAW_HISTORICO.write_text(json.dumps(rows_hist, ensure_ascii=False, indent=2), encoding="utf-8")
    DEBUG_PAGINAS.write_text(json.dumps(debug, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"\nFA copas: {len(rows_prog)} programados, {len(rows_hist)} passados")
    if args.dry_run:
        print("[dry-run] nada gravado em data/reino_unido/")
        return
    n_prog, n_hist = salvar(rows_prog, rows_hist)
    print(f"data/reino_unido/jogos_programados.json: {n_prog} | historico_jogos.csv: {n_hist}")


if __name__ == "__main__":
    main()
