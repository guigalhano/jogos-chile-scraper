#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coordenadas dos times do Reino Unido + Irlanda para o mapa (reino-unido.html).

Gera data/reino_unido/geo_times.json:
    {"<pais>|<time mandante>": {"lat": .., "lng": .., "local": "..", "fonte": ".."}}

De onde vem cada coordenada, em ordem de preferencia:

1. "sofascore": coordenada do estadio do time no SofaScore
   (data/reino_unido/cache_venues_sofascore.json). So e aceita se ficar a
   menos de 40 km da cidade que o proprio SofaScore informa - em clubes
   pequenos ele traz estadio de outro clube (ex.: Denbigh Town com as
   coordenadas do Stadium mk, em Milton Keynes).
2. "cidade": a cidade informada pelo SofaScore, geocodificada.
3. "nome": o NonLeagueHQ nao informa local, entao tiramos do nome do clube
   os sufixos tipicos (Town, United, Athletic, Reserves, FC...) e
   geocodificamos o que sobra como localidade ("Carshalton Athletic" ->
   Carshalton), usando o condado do NonLeagueHQ como contexto quando houver.
   E uma posicao APROXIMADA (centro da cidade, nao o estadio).

Geocodificacao: Nominatim (OpenStreetMap), respeitando a politica de uso
(1 requisicao/s, User-Agent identificado, cache). As consultas ficam em
data/reino_unido/cache_geocoding.json; cada execucao so consulta lugares
novos, limitado por --max-consultas.

Uso:
    python geocodificar_reino_unido.py --max-consultas 400
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
from pathlib import Path

import requests

UK_DIR = Path("data") / "reino_unido"
JOGOS_JSON = UK_DIR / "jogos_programados.json"
HIST_CSV = UK_DIR / "historico_jogos.csv"
CACHE_VENUES = UK_DIR / "cache_venues_sofascore.json"
CACHE_GEO = UK_DIR / "cache_geocoding.json"
SAIDA = UK_DIR / "geo_times.json"

NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "jogos-chile-scraper/1.0 (https://github.com/guigalhano/jogos-chile-scraper)"}

PAIS_OSM = {
    "Inglaterra": ("gb", "England"),
    "Escócia": ("gb", "Scotland"),
    "País de Gales": ("gb", "Wales"),
    "Irlanda do Norte": ("gb", "Northern Ireland"),
    "Irlanda": ("ie", "Ireland"),
}
# Caixa grosseira de Reino Unido + Irlanda.
LAT_MIN, LAT_MAX, LNG_MIN, LNG_MAX = 49.8, 61.0, -11.0, 2.0
DIST_MAX_KM = 40

# Palavras de nome de clube que nao fazem parte do nome do lugar.
SUFIXOS = {
    "fc", "afc", "cfc", "town", "city", "united", "utd", "athletic", "athletico", "rovers", "rangers",
    "wanderers", "albion", "borough", "reserves", "res", "development", "dev", "juniors", "jnrs",
    "colts", "thistle", "celtic", "swifts", "villa", "sports", "amateurs", "amateur", "academy",
    "harriers", "dynamos", "dynamo", "corinthians", "corinthian", "welfare", "victoria", "hearts",
    "star", "stars", "youth", "recreation", "rec", "olympic", "sporting", "phoenix", "inter",
    "ladies", "women", "u23", "u21", "u18", "ii", "iii", "b", "football", "club", "fc.", "cf",
    "community", "the", "&", "and", "district", "glebe", "park", "vale", "argyle", "alexandra",
    "county", "orient", "wednesday", "hotspur", "palace", "wolves",
    "ceidwaid", "dragons", "saints", "tigers", "lions", "eagles", "magpies", "red", "blue", "blues",
    "whites", "white", "black", "comrades", "mills", "mill", "street", "boys", "old", "1st", "2nd",
    "18th", "st.", "fp", "jfc", "afc.", "railway", "unity", "tavern",
}
NUMEROS_RE = re.compile(r"\b\d+(st|nd|rd|th)?\b", re.I)


def dist_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def dentro(lat, lng) -> bool:
    return lat is not None and lng is not None and LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX


def lugar_do_nome(nome: str) -> str:
    nome = re.sub(r"\(.*?\)", " ", nome)
    nome = NUMEROS_RE.sub(" ", nome)
    palavras = [p for p in re.split(r"[\s/]+", nome.replace("'", "").strip()) if p]
    resto = [p for p in palavras if p.lower().strip(".,") not in SUFIXOS]
    return " ".join(resto).strip(" -,.")


class Geocoder:
    def __init__(self, max_consultas: int):
        try:
            self.cache: dict = json.loads(CACHE_GEO.read_text(encoding="utf-8"))
        except Exception:
            self.cache = {}
        self.restantes = max_consultas
        self.feitas = 0
        self.session = requests.Session()

    def buscar(self, lugar: str, pais: str, contexto: str = "") -> list | None:
        """[lat, lng, nome] ou None. Usa o cache; None = nao encontrado OU sem
        cota nesta execucao (sem cota nao grava no cache)."""
        cc, nome_pais = PAIS_OSM[pais]
        q = ", ".join(x for x in (lugar, contexto, nome_pais) if x)
        if q in self.cache:
            return self.cache[q]
        if self.restantes <= 0:
            return None
        self.restantes -= 1
        self.feitas += 1
        try:
            r = self.session.get(NOMINATIM, headers=HEADERS, timeout=30, params={
                "q": q, "countrycodes": cc, "format": "jsonv2", "limit": 1, "featureType": "settlement",
            })
            r.raise_for_status()
            res = r.json()
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] {q}: {e}")
            time.sleep(1.1)
            return None  # erro de rede: nao grava, tenta de novo na proxima
        time.sleep(1.1)
        val = None
        if res:
            lat, lng = float(res[0]["lat"]), float(res[0]["lon"])
            if dentro(lat, lng):
                val = [round(lat, 5), round(lng, 5), res[0].get("name") or lugar]
        self.cache[q] = val
        return val

    def salvar(self) -> None:
        CACHE_GEO.write_text(json.dumps(self.cache, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")


def ler_mandantes() -> dict[str, dict]:
    """pais|time (ou pais|time|fonte) -> {pais, time, time_sofascore, condado}."""
    import csv
    linhas: list[dict] = []
    if JOGOS_JSON.exists():
        linhas += json.loads(JOGOS_JSON.read_text(encoding="utf-8"))
    if HIST_CSV.exists():
        with HIST_CSV.open(encoding="utf-8-sig", newline="") as f:
            linhas += list(csv.DictReader(f))
    # Nomes que existem no SofaScore: um clube com o mesmo nome vindo de outra
    # fonte (NonLeagueHQ, FA) pode ser outro clube - ex.: "Bournemouth" e o
    # AFC Bournemouth no SofaScore e o Bournemouth FC (Wessex) no NonLeagueHQ.
    # Esses ficam numa chave propria "pais|time|fonte", que a pagina usa antes
    # da chave "pais|time".
    no_sofascore = {(r.get("pais"), r.get("mandante")) for r in linhas if r.get("fonte") == "SofaScore"}
    out: dict[str, dict] = {}
    for r in linhas:
        pais, time_ = r.get("pais", ""), r.get("mandante", "")
        if pais not in PAIS_OSM or not time_:
            continue
        chave = f"{pais}|{time_}"
        if r.get("fonte") != "SofaScore" and (pais, time_) in no_sofascore:
            chave += f"|{r.get('fonte', '')}"
        info = out.setdefault(chave, {"pais": pais, "time": time_, "time_sofascore": "", "condado": ""})
        extra = r.get("extra", "") or ""
        m = re.search(r"time_sofascore=(\d+)", extra)
        if m:
            info["time_sofascore"] = m.group(1)
        m = re.search(r"condado=([^;]+)", extra)
        if m and not info["condado"]:
            info["condado"] = m.group(1).strip()
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-consultas", type=int, default=400, help="limite de consultas novas ao Nominatim nesta execucao")
    args = parser.parse_args()

    try:
        venues = json.loads(CACHE_VENUES.read_text(encoding="utf-8"))
    except Exception:
        venues = {}
    geo = Geocoder(args.max_consultas)
    times = ler_mandantes()
    saida: dict[str, dict] = {}
    contagem = {"sofascore": 0, "cidade": 0, "nome": 0, "sem": 0}
    salvo_em = 0

    # SofaScore primeiro (poucos times, posicao melhor), depois o resto.
    for chave, t in sorted(times.items(), key=lambda kv: (not kv[1]["time_sofascore"], kv[0])):
        pais = t["pais"]
        v = venues.get(t["time_sofascore"]) if t["time_sofascore"] else None
        ponto = None
        if v and v.get("cidade"):
            cid = geo.buscar(v["cidade"], pais)
            est = (v.get("lat"), v.get("lng"))
            if dentro(*est) and (cid is None or dist_km(est, (cid[0], cid[1])) <= DIST_MAX_KM):
                ponto = {"lat": round(est[0], 5), "lng": round(est[1], 5), "local": v.get("estadio") or v["cidade"], "fonte": "sofascore"}
            elif cid:
                ponto = {"lat": cid[0], "lng": cid[1], "local": v["cidade"], "fonte": "cidade"}
        if ponto is None:
            lugar = lugar_do_nome(t["time"])
            if lugar:
                achou = geo.buscar(lugar, pais, t["condado"]) if t["condado"] else None
                achou = achou or geo.buscar(lugar, pais)
                if not achou and " " in lugar:
                    achou = geo.buscar(lugar.split(" ")[0], pais, t["condado"])
                if achou:
                    ponto = {"lat": achou[0], "lng": achou[1], "local": achou[2], "fonte": "nome"}
        if ponto:
            saida[chave] = ponto
            contagem[ponto["fonte"]] += 1
        else:
            contagem["sem"] += 1
        if geo.feitas - salvo_em >= 50:
            geo.salvar()
            salvo_em = geo.feitas

    geo.salvar()
    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    print(f"[geo] {len(times)} times mandantes | {contagem} | {geo.feitas} consultas novas ao Nominatim")
    if geo.restantes <= 0:
        print("[geo] limite de consultas atingido; o restante fica para a proxima execucao")


if __name__ == "__main__":
    main()
