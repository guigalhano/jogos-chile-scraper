#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cidade e coordenadas dos times do Torneo Regional Federal Amateur, para os
jogos do SofaScore que vem sem estadio (scrap_argentina_sofascore.py).

O SofaScore nao tem o venue da maioria dos clubes do Regional, entao ~60
jogos por semana ficavam fora do mapa. A "Programacion" semanal do
ascensodelinterior.com.ar (o mesmo artigo que o scrap_afa_federal_a.py le)
traz, na secao "Torneo Regional Federal Amateur 2026 - Fecha N", uma linha
por jogo:

    MITRE SALTA SALTA TALLERES PERICO JUJUY 18/10/2026 16:30 <arbitros...>

= "TIME1 CIDADE1 TIME2 CIDADE2 data hora", sem separador. A cidade e a
cabecera da liga de origem do clube. Como nao da para cortar a linha sozinha,
cada linha e casada com o evento do SofaScore dos mesmos dois times (ate 3
dias de diferenca - o SofaScore costuma ter data/hora provisorias): as
palavras do mandante e do visitante marcam onde cada time comeca, e o que
sobra entre o fim do nome do time e o comeco do proximo e a cidade.

A cidade e geocodificada no Nominatim (1 req/s, cache em
data/argentina/cache_geocoding.json) e so e aceita se cair numa provincia da
Region do torneio. O resultado fica por time do SofaScore em
data/argentina/cache_cidades_times.json, entao vale tambem nas semanas em que
o time nao aparece na programacao e em outras competicoes (Copa Pais).

E uma posicao APROXIMADA (centro da cidade da liga, nao o estadio): o
scraper marca esses jogos com local_aproximado=1.

Teste isolado (le data/debug_argentina_sofascore_*raw.json, nao grava cache
de time):
    python argentina_regional_cidades.py
"""

from __future__ import annotations

import json
import re
import time
from datetime import date, timedelta
from pathlib import Path

import requests

from argentina_comum import OUT_DIR, _STOP, norm, para_local

AR_DIR = OUT_DIR / "argentina"
CACHE_GEO = AR_DIR / "cache_geocoding.json"
CACHE_TIMES = AR_DIR / "cache_cidades_times.json"

NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS_OSM = {"User-Agent": "jogos-chile-scraper/1.0 (https://github.com/guigalhano/jogos-chile-scraper)"}

REGIONAL_RE = re.compile(r"regional federal amateur", re.IGNORECASE)
INICIO_SECAO_RE = re.compile(r"^Torneo Regional Federal Amateur \d{4}\b(?!.*femenin)", re.IGNORECASE)
FIM_SECAO_RE = re.compile(r"^(Liga Profesional|Torneo|Primera|Copa|Federal)\b", re.IGNORECASE)
DATA_HORA_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\s+(\d{1,2}):(\d{2})\b")
MAX_DIAS = 3

# Provincias aceitas por Region (com folga: clubes de fronteira, como os de
# Carmen de Patagones na Patagonica).
_BA, _LP = "buenos aires", "la pampa"
PROVINCIAS_REGIAO = {
    "norte": {"salta", "jujuy", "tucuman", "santiago del estero", "catamarca"},
    "litoral norte": {"misiones", "corrientes", "chaco", "formosa", "santa fe"},
    "litoral sur": {"entre rios", "santa fe", _BA},
    "centro": {"cordoba", "santiago del estero", "catamarca", "la rioja", "tucuman", "santa fe", "san luis"},
    "cuyo": {"mendoza", "san juan", "san luis", "la rioja", "neuquen", _LP, "cordoba"},
    "pampeana norte": {_BA, "santa fe", "entre rios", _LP, "ciudad autonoma de buenos aires"},
    "pampeana sur": {_BA, _LP},
    "patagonica": {"rio negro", "neuquen", "chubut", "santa cruz", "tierra del fuego", _BA, _LP},
}

# Abreviaturas da programacao -> nome por extenso para o Nominatim.
_EXPANDIR = {
    "gral": "general", "cnel": "coronel", "cdte": "comandante", "lib": "libertador",
    "pres": "presidencia", "pte": "presidente", "sgo": "santiago del estero", "mza": "mendoza",
    "ctes": "corrientes", "fsa": "formosa", "mdq": "mar del plata", "sta": "santa", "sto": "santo",
    "ing": "ingeniero", "dr": "doctor", "va": "villa",
}
# Cidades que o Nominatim nao acha pelo texto da programacao.
_CIDADES_FIXAS = {
    "presidencia roque s pena": "Presidencia Roque Sáenz Peña",
    "roque s pena": "Presidencia Roque Sáenz Peña",
    # capitais que a programacao chama pelo nome da provincia
    "jujuy": "San Salvador de Jujuy",
    "tucuman": "San Miguel de Tucumán",
    "catamarca": "San Fernando del Valle de Catamarca",
    "rio grande": "Río Grande, Tierra del Fuego",
}
# Sufixo de provincia que a programacao poe em algumas cidades: "COLON (ER)",
# "SAN VICENTE BA", "SAN PEDRO (J)", "GRAL ALVEAR (M)".
_PROVINCIA_SUFIXO = {
    "er": "Entre Ríos", "ba": "Buenos Aires", "j": "Jujuy", "m": "Mendoza", "c": "Corrientes",
    "sf": "Santa Fe", "cba": "Córdoba", "bs": "Buenos Aires",
}
# Palavras curtas que sao parte de nome de cidade (o resto, ate 3 letras, e
# sigla de time grudada na cidade: "LP LA PLATA", "SN SAN NICOLAS", "T TUCUMAN").
_CURTAS_DE_CIDADE = {"la", "el", "de", "del", "los", "las", "san", "rio", "25", "9", "villa"}
# Palavras que sozinhas nao identificam cidade.
_GENERICAS = {"general", "coronel", "villa", "puerto", "santo", "santa", "colonia", "presidencia",
              "libertador", "comandante", "ingeniero", "doctor", "presidente", "union", "central"}
# Tipo do lugar no Nominatim -> preferencia (menor = melhor). Provincia,
# departamento e partido ficam de fora: "Salta" e "Jujuy" davam o centro da
# provincia, nao a cidade.
_TIPOS_LUGAR = {"city": 0, "town": 0, "village": 1, "hamlet": 2, "municipality": 2, "suburb": 3}


# ---------------------------------------------------------------- programacao

def linhas_programacao() -> list[tuple[str, list[str]]]:
    """[(data_iso, palavras normalizadas antes da data), ...] das linhas do
    Regional nos artigos de programacao mais recentes."""
    from scrap_afa_federal_a import fetch, find_urls_programacao_recentes, get_lines

    out: list[tuple[str, list[str]]] = []
    vistos: set[str] = set()
    for url in find_urls_programacao_recentes():
        url = url.rstrip("/")
        if url in vistos:
            continue
        vistos.add(url)
        try:
            lines = get_lines(fetch(url + "/").text)
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] programacao {url}: {e}")
            continue
        out += parse_regional(lines)
    return out


def parse_regional(lines: list[str]) -> list[tuple[str, list[str]]]:
    out = []
    dentro = False
    for line in lines:
        if INICIO_SECAO_RE.match(line):
            dentro = True
            continue
        m = DATA_HORA_RE.search(line)
        if not m:
            if dentro and FIM_SECAO_RE.match(line):
                dentro = False
            continue
        if not dentro:
            continue
        d, mes, ano = m.group(1), m.group(2), m.group(3)
        try:
            data_iso = date(int(ano), int(mes), int(d)).isoformat()
        except ValueError:
            continue
        palavras = norm(line[:m.start()]).split()
        if len(palavras) >= 4:
            out.append((data_iso, palavras))
    return out


# --------------------------------------------------------------- casamento

def _quase_igual(a: str, b: str) -> bool:
    """Diferenca de no maximo 1 letra (erros de digitacao: 'HRACAN', 'MARTN')."""
    if abs(len(a) - len(b)) > 1 or min(len(a), len(b)) < 5:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    curta, longa = sorted((a, b), key=len)
    return any(longa[:i] + longa[i + 1:] == curta for i in range(len(longa)))


def _tokens(nome: str) -> set[str]:
    out = {t for t in norm(nome).split() if t not in _STOP and len(t) > 1}
    # "Sportivo Cultural": so palavras genericas, entao usa elas mesmo
    return out or {t for t in norm(nome).split() if len(t) > 3 and t not in ("club", "atletico")}


def _bate(palavra: str, tokens: set[str]) -> bool:
    for t in tokens:
        if palavra == t or _quase_igual(palavra, t):
            return True
        if min(len(palavra), len(t)) >= 4 and (palavra.startswith(t) or t.startswith(palavra)):
            return True
    return False


def separar(palavras: list[str], mandante: str, visitante: str) -> tuple[list[str], list[str]] | None:
    """(palavras da cidade do mandante, palavras da cidade do visitante), ou
    None se a linha nao for desse jogo. As palavras podem trazer sobra de
    nome de time ("c santo gral guemes"); o Geocoder.cidade() se vira."""
    tm, tv = _tokens(mandante), _tokens(visitante)
    if not tm or not tv:
        return None
    hm = [i for i, p in enumerate(palavras) if _bate(p, tm)]
    am = [i for i, p in enumerate(palavras) if _bate(p, tv)]
    if not hm or not am or hm[0] > 2:
        return None
    nome_v = norm(visitante).split()

    def do_visitante(p: str) -> bool:
        # "SAN MARTN RG", "AT SAN JULIAN", "DEP VILLALONGA": palavras genericas
        # ou abreviadas que o _tokens() descarta mas sao do nome do visitante
        if p in ("la", "el", "de", "del", "los", "las"):
            return False
        return p in nome_v or (len(p) >= 2 and any(w.startswith(p) and len(w) > len(p) for w in nome_v))

    for a in am:
        if a <= hm[0]:
            continue
        b = a
        while a - b < 2 and b - 1 > hm[0] and b - 1 not in hm and do_visitante(palavras[b - 1]):
            b -= 1
        fim_m = max(h for h in hm if h < b)
        if b - fim_m > 1 and any(len(p) > 2 for p in palavras[fim_m + 1:b]):
            cidade_m = palavras[fim_m + 1:b]
        elif b - 1 > hm[0]:
            # O nome do mandante contem a cidade ("MITRE SALTA SALTA", com o
            # mandante "Mitre Salta"): fica tudo depois da 1a palavra do time.
            cidade_m = palavras[hm[0] + 1:b]
        else:
            continue
        amv = [x for x in am if x >= b]
        cidade_v = palavras[max(amv) + 1:] or palavras[min(amv) + 1:]
        return cidade_m, cidade_v
    return None


def casar(eventos: list[tuple[str, dict]], linhas: list[tuple[str, list[str]]]) -> list[tuple[dict, str, list[str], list[str]]]:
    """eventos = [(nome do torneio, evento SofaScore)]. Devolve
    [(evento, regiao, cidade_mandante, cidade_visitante)], cada linha usada uma vez."""
    pares = []
    for nome_t, ev in eventos:
        ts = ev.get("startTimestamp")
        home = (ev.get("homeTeam") or {}).get("name") or ""
        away = (ev.get("awayTeam") or {}).get("name") or ""
        if not (ts and home and away):
            continue
        dia = para_local(ts).date()
        for li, (data_iso, palavras) in enumerate(linhas):
            dd = abs((date.fromisoformat(data_iso) - dia).days)
            if dd > MAX_DIAS:
                continue
            sep = separar(palavras, home, away)
            if sep:
                pares.append((dd, li, id(ev), ev, regiao_de(nome_t), sep))
    pares.sort(key=lambda p: (p[0], p[1]))
    usadas_l: set[int] = set()
    usados_e: set[int] = set()
    out = []
    for _, li, eid, ev, regiao, (cm, cv) in pares:
        if li in usadas_l or eid in usados_e:
            continue
        usadas_l.add(li)
        usados_e.add(eid)
        out.append((ev, regiao, cm, cv))
    return out


def regiao_de(nome_torneio: str) -> str:
    n = norm(nome_torneio)
    return next((r for r in PROVINCIAS_REGIAO if f"region {r}" in n), "")


# ----------------------------------------------------------- geocodificacao

def _nome_confere(nome_osm: str, consulta: str) -> bool:
    """O Nominatim acha alguma coisa para quase qualquer texto ("norte t
    tucuman" -> Banda del Rio Sali): o lugar tem de ter uma palavra da busca."""
    if not nome_osm:
        return True
    a = {t for t in norm(nome_osm).split() if len(t) >= 4}
    b = {t for t in norm(consulta).split() if len(t) >= 4}
    return any(x == y or x.startswith(y) or y.startswith(x) for x in a for y in b)


class Geocoder:
    def __init__(self, max_consultas: int = 150):
        try:
            self.cache: dict = json.loads(CACHE_GEO.read_text(encoding="utf-8"))
        except Exception:
            self.cache = {}
        self.restantes = max_consultas
        self.session = requests.Session()

    def _consultar(self, q: str) -> list[dict] | None:
        if q in self.cache:
            return self.cache[q]
        if self.restantes <= 0:
            return None
        self.restantes -= 1
        try:
            r = self.session.get(NOMINATIM, headers=HEADERS_OSM, timeout=30, params={
                "q": q, "countrycodes": "ar", "format": "jsonv2", "limit": 5,
                "featureType": "settlement", "addressdetails": 1,
            })
            r.raise_for_status()
            res = r.json()
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] Nominatim {q}: {e}")
            time.sleep(1.1)
            return None  # erro de rede: nao grava, tenta de novo na proxima
        time.sleep(1.1)
        val = []
        for x in res:
            ad = x.get("address") or {}
            val.append({
                "lat": round(float(x["lat"]), 5), "lng": round(float(x["lon"]), 5),
                "tipo": x.get("addresstype") or x.get("type") or "",
                "nome": next((ad[k] for k in ("city", "town", "village", "hamlet", "municipality") if ad.get(k)), ""),
                "provincia": norm(ad.get("state", "")),
            })
        self.cache[q] = val
        return val

    def cidade(self, palavras: list[str], regiao: str, so_finais: bool = False) -> dict | None:
        """{cidade, lat, lng} da cidade escrita nas palavras, numa provincia da
        regiao. As palavras podem ter sobra de nome de time antes ou depois
        ("lp las palmas mision", "c santo gral guemes"): tenta os trechos
        contiguos, do mais longo para o mais curto (no empate, o que fecha o
        texto). so_finais: so os finais - a cidade do visitante fecha a linha."""
        provs = PROVINCIAS_REGIAO.get(regiao)
        palavras = list(palavras)
        # sobra do nome do proximo time: "SAN VICENTE BA LOS (HORNOS)"
        while len(palavras) > 1 and palavras[-1] in ("la", "el", "los", "las", "de", "del"):
            palavras.pop()
        prov_hint = ""
        if len(palavras) > 1 and palavras[-1] in _PROVINCIA_SUFIXO:
            prov_hint = _PROVINCIA_SUFIXO[palavras.pop()]
        palavras = " ".join(_EXPANDIR.get(p, p) for p in palavras).split()
        # "MITRE SALTA SALTA", "MZA MENDOZA" -> uma vez so
        palavras = [p for k, p in enumerate(palavras) if k == 0 or p != palavras[k - 1]]
        n = len(palavras)
        trechos = sorted(((i, f) for i in range(n) for f in range(i + 1, n + 1) if f == n or not so_finais),
                         key=lambda t: (t[0] - t[1], t[1] != n, t[0]))
        for i, f in trechos:
            trecho = palavras[i:f]
            ini, fim = trecho[0], trecho[-1]
            if len(ini) <= 3 and ini not in _CURTAS_DE_CIDADE and not ini.isdigit():
                continue  # sigla de time: "LP LA PLATA", "SN SAN NICOLAS"
            if fim in _CURTAS_DE_CIDADE or fim in _STOP or (len(fim) <= 2 and not fim.isdigit() and fim != "fe"):
                continue
            if len(trecho) == 1 and (len(ini) < 4 or ini in _STOP or ini in _GENERICAS):
                continue
            texto = " ".join(trecho)
            nome_q = _CIDADES_FIXAS.get(texto, texto)
            q = ", ".join(x for x in (nome_q, prov_hint, "Argentina") if x)
            res = self._consultar(q)
            if res is None:
                return None  # sem cota/erro: tenta na proxima execucao
            validos = [
                x for x in res
                if x.get("tipo") in _TIPOS_LUGAR
                and (not provs or any(p in x["provincia"] for p in provs))
                and _nome_confere(x["nome"], nome_q)
            ]
            if validos:
                x = min(validos, key=lambda v: _TIPOS_LUGAR[v["tipo"]])
                nome = re.sub(r"^(Municipio|Distrito|Ciudad|Comuna) de\s+|^Distrito\s+", "", x["nome"]) or texto.title()
                return {"cidade": nome, "lat": x["lat"], "lng": x["lng"]}
        return None

    def salvar(self) -> None:
        AR_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_GEO.write_text(json.dumps(self.cache, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")


# ------------------------------------------------------------------ entrada

def _na_argentina(lat, lng) -> bool:
    # mesma caixa do dentro_da_argentina() do scraper: venue fora dela e
    # descartado la, entao o time precisa da cidade daqui
    try:
        return -55.5 <= float(lat) <= -21.5 and -73.8 <= float(lng) <= -53.5
    except (TypeError, ValueError):
        return False


def carregar_cache_times() -> dict[str, dict]:
    try:
        return json.loads(CACHE_TIMES.read_text(encoding="utf-8"))
    except Exception:
        return {}


def atualizar_cidades(eventos: list[tuple[str, dict]], venues: dict, gravar: bool = True) -> dict[str, dict]:
    """eventos = [(nome do torneio SofaScore, evento)] de todos os torneios.
    Atualiza e devolve o cache {time_sofascore: {cidade, lat, lng, ...}} com
    os times do Regional (e as selecoes "Liga de X" da Copa Pais) sem venue
    no SofaScore. Nunca levanta excecao: se
    a programacao ou o Nominatim falharem, fica o cache antigo."""
    cache = carregar_cache_times()
    try:
        regionais = [(n, ev) for n, ev in eventos if REGIONAL_RE.search(n)]
        casados = []
        if regionais:
            linhas = linhas_programacao()
            casados = casar(regionais, linhas)
            print(f"[INFO] Regional: {len(linhas)} linhas na programacao, {len(casados)} casadas com o SofaScore")
        geo = Geocoder()
        hoje = date.today().isoformat()
        novos = 0
        for ev, regiao, cm, cv in casados:
            for lado, palavras in (("homeTeam", cm), ("awayTeam", cv)):
                tid = str((ev.get(lado) or {}).get("id") or "")
                if not tid or not palavras:
                    continue
                v = venues.get(tid) or {}
                if _na_argentina(v.get("lat"), v.get("lng")):
                    continue  # o SofaScore ja tem o estadio
                # O texto do mandante (CIDADE1) e mais confiavel que o do
                # visitante (fim da linha); nao troca um pelo outro.
                if cache.get(tid, {}).get("lado") == "mandante" and lado == "awayTeam":
                    continue
                achou = geo.cidade(palavras, regiao, so_finais=lado == "awayTeam")
                if not achou:
                    continue
                if tid not in cache:
                    novos += 1
                cache[tid] = {**achou, "time": (ev.get(lado) or {}).get("name", ""), "texto": " ".join(palavras),
                              "lado": "mandante" if lado == "homeTeam" else "visitante", "visto_em": hoje}
        # Copa Pais: as selecoes de liga ("Liga de Catamarca") levam a cidade no nome.
        for nome_t, ev in eventos:
            if not re.search(r"copa pa[ií]s", nome_t, re.IGNORECASE):
                continue
            for lado in ("homeTeam", "awayTeam"):
                t = ev.get(lado) or {}
                tid = str(t.get("id") or "")
                m = re.match(r"Liga (?:de |del )?(.+)$", t.get("name") or "")
                v = venues.get(tid) or {}
                if not m or not tid or tid in cache or _na_argentina(v.get("lat"), v.get("lng")):
                    continue
                achou = geo.cidade(norm(m.group(1)).split(), "", so_finais=True)
                if achou:
                    novos += 1
                    cache[tid] = {**achou, "time": t.get("name", ""), "texto": norm(m.group(1)),
                                  "lado": "nome", "visto_em": hoje}
        geo.salvar()
        print(f"[INFO] Regional: {novos} times novos com cidade (total no cache: {len(cache)})")
        if gravar:
            AR_DIR.mkdir(parents=True, exist_ok=True)
            CACHE_TIMES.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] cidades do Regional: {e}")
    return cache


if __name__ == "__main__":
    # Diagnostico: mostra como cada linha da programacao foi cortada.
    linhas = linhas_programacao()
    for data_iso, palavras in linhas:
        print(data_iso, " ".join(palavras))
    print(f"{len(linhas)} linhas")
