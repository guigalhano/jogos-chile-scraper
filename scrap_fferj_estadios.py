#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FERJ - Descobrir estadios/sedes dos clubes filiados e geocodificar

A FERJ mantem uma pagina por clube em:
    https://servicos.fferj.com.br/ClubesLigas/ViewTeam?alias=<id>

com um bloco "informacoes gerais" contendo:
    Estadio <nome ou "NAO POSSUI ESTADIO">
    Capacidade <numero>
    Localizacao <endereco> (pode vir vazio)
    ...
e mais acima, sempre presente:
    Sede <endereco> - <cidade>
    CEP <cep>

Estrategia:
1. Para cada liga (Serie A, A2, B1, B2, C, Liga Municipal, Amador da Capital),
   listar os clubes filiados via ClubesLigas?alias=<liga_id>.
2. Para cada clube (deduplicado por id), abrir ViewTeam?alias=<id> e extrair
   nome do clube, estadio, localizacao (endereco do estadio) e sede (endereco
   do clube, usado como fallback quando nao ha estadio/localizacao).
3. Geocodificar o melhor endereco disponivel via Nominatim (OpenStreetMap),
   respeitando o limite de 1 req/s da politica de uso.
4. Gravar:
   - data/debug_fferj_estadios_raw.json (tudo que foi encontrado, com status)
   - estadios_ferj_rio.js (window.ESTADIOS_FERJ_RJ = [...] e
     window.ESTADIO_MANDANTE_PADRAO_FFERJ = { "nome do clube normalizado": {...} })

Requisitos:
    py -m pip install requests beautifulsoup4

Teste:
    py scrap_fferj_estadios.py --max-clubes 10 --debug-html

Completo:
    py scrap_fferj_estadios.py
"""
from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

BASE_URL = "https://servicos.fferj.com.br"
LIGAS_ALIASES = [1, 3, 4, 5, 7, 8, 9]  # Serie A, C, Liga Municipal, Amador da Capital, B1, B2, A2

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
}

# Nominatim exige um User-Agent identificavel e no maximo 1 requisicao por
# segundo (https://operations.osmfoundation.org/policies/nominatim/).
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {
    "User-Agent": "jogos-chile-scraper/1.0 (geocodificacao de estadios FFERJ; contato via GitHub)",
}

VIEWTEAM_HREF_RE = re.compile(r"/ClubesLigas/ViewTeam\?alias=(\d+)", re.I)

NAO_POSSUI_RE = re.compile(r"n[aã]o possui estadio", re.I)


def clean_text(x: Any) -> str:
    x = "" if x is None else str(x)
    x = x.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", x).strip()


def normalize(s: Any) -> str:
    s = unicodedata.normalize("NFD", clean_text(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def html_to_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text("\n", strip=True)
    return [clean_text(x) for x in text.splitlines() if clean_text(x)]


def discover_clubes(session: requests.Session, timeout: int) -> dict[str, str]:
    """Retorna {alias_id: nome_do_clube} para todos os clubes encontrados nas ligas."""
    clubes: dict[str, str] = {}
    for liga in LIGAS_ALIASES:
        url = f"{BASE_URL}/ClubesLigas"
        try:
            r = session.get(url, params={"alias": liga}, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
        except Exception as e:
            print(f"[AVISO] falha ao listar liga alias={liga}: {e}")
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            m = VIEWTEAM_HREF_RE.search(a["href"])
            if not m:
                continue
            alias_id = m.group(1)
            nome = clean_text(a.get_text(" ", strip=True)) or clean_text(a.get("title", ""))
            if alias_id and nome and alias_id not in clubes:
                clubes[alias_id] = nome
        time.sleep(0.5)
    return clubes


def parse_club_page(html: str) -> dict:
    """Extrai nome, estadio, localizacao (endereco do estadio) e sede (endereco do clube)."""
    lines = html_to_lines(html)

    estadio = ""
    localizacao = ""
    sede = ""
    capacidade = ""

    for i, line in enumerate(lines):
        if line.startswith("Estádio ") or line.startswith("Estadio "):
            valor = line.split(" ", 1)[1].strip() if " " in line else ""
            if valor and not normalize(valor).startswith("nao possui estadio"):
                estadio = valor
        elif line.startswith("Localização ") or line.startswith("Localizacao "):
            partes = line.split(" ", 1)
            localizacao = partes[1].strip() if len(partes) > 1 else ""
        elif line == "Localização" or line == "Localizacao":
            # label sozinho na linha = valor vazio (sem estadio cadastrado)
            localizacao = ""
        elif line.startswith("Sede "):
            sede = line.split(" ", 1)[1].strip()
        elif line.startswith("Capacidade "):
            capacidade = line.split(" ", 1)[1].strip()

    return {
        "estadio": estadio,
        "localizacao": localizacao,
        "sede": sede,
        "capacidade": capacidade,
    }


def montar_endereco_geocoding(info: dict) -> tuple[str, str]:
    """Escolhe o melhor endereco disponivel para geocodificar.
    Retorna (endereco_para_busca, fonte: 'localizacao'|'sede'|'')."""
    loc = clean_text(info.get("localizacao", ""))
    sede = clean_text(info.get("sede", ""))
    if loc:
        return f"{loc}, RJ, Brasil", "localizacao"
    if sede:
        return f"{sede}, RJ, Brasil", "sede"
    return "", ""


def geocode(endereco: str, session: requests.Session, cache: dict, timeout: int) -> dict | None:
    if not endereco:
        return None
    if endereco in cache:
        return cache[endereco]

    try:
        r = session.get(
            NOMINATIM_URL,
            params={"q": endereco, "format": "json", "limit": 1, "countrycodes": "br"},
            headers=NOMINATIM_HEADERS,
            timeout=timeout,
        )
        r.raise_for_status()
        results = r.json()
    except Exception as e:
        print(f"[AVISO] geocoding falhou para '{endereco}': {e}")
        cache[endereco] = None
        return None
    finally:
        # Nominatim: no maximo 1 requisicao por segundo.
        time.sleep(1.1)

    if not results:
        cache[endereco] = None
        return None

    top = results[0]
    coords = {"lat": float(top["lat"]), "lng": float(top["lon"])}
    cache[endereco] = coords
    return coords


def escrever_js(clubes_info: list[dict], path: Path) -> None:
    linhas = [
        "/*",
        "  Estadios/sedes dos clubes filiados a FERJ (Rio de Janeiro), obtidos via",
        "  scrap_fferj_estadios.py a partir de servicos.fferj.com.br/ClubesLigas.",
        "",
        "  window.ESTADIOS_FERJ_RJ: lista de estadios/sedes com coordenadas.",
        "  window.ESTADIO_MANDANTE_PADRAO_FFERJ: nome do clube (normalizado) -> objeto",
        "  de estadio/sede correspondente, usado como fallback em enrichGames() quando",
        "  o card de um jogo da FFERJ nao informa o nome do estadio.",
        "*/",
        "",
        "window.ESTADIOS_FERJ_RJ = [",
    ]
    mandante_padrao = {}
    for c in clubes_info:
        if not c.get("lat") or not c.get("lng"):
            continue
        nome_estadio = c["estadio"] or f"Sede do {c['nome_clube']}"
        obj_txt = (
            "  {\n"
            f"    nome: {json.dumps(nome_estadio, ensure_ascii=False)},\n"
            f"    aliases: [{json.dumps(normalize(nome_estadio), ensure_ascii=False)}],\n"
            f"    clube: {json.dumps(c['nome_clube'], ensure_ascii=False)},\n"
            "    cidade: \"\",\n"
            "    regiao: \"Rio de Janeiro\",\n"
            f"    lat: {c['lat']},\n"
            f"    lng: {c['lng']},\n"
            f"    fonte_endereco: {json.dumps(c.get('fonte_endereco', ''), ensure_ascii=False)},\n"
            "  },"
        )
        linhas.append(obj_txt)
        mandante_padrao[normalize(c["nome_clube"])] = {
            "nome": nome_estadio,
            "cidade": "",
            "regiao": "Rio de Janeiro",
            "lat": c["lat"],
            "lng": c["lng"],
        }
    linhas.append("];")
    linhas.append("")
    linhas.append("window.ESTADIO_MANDANTE_PADRAO_FFERJ = {")
    for chave, obj in mandante_padrao.items():
        linhas.append(
            f"  {json.dumps(chave, ensure_ascii=False)}: "
            f"{{ nome: {json.dumps(obj['nome'], ensure_ascii=False)}, "
            f"cidade: \"\", regiao: \"Rio de Janeiro\", "
            f"lat: {obj['lat']}, lng: {obj['lng']} }},"
        )
    linhas.append("};")

    path.write_text("\n".join(linhas), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-clubes", type=int, default=0, help="Limite de clubes a processar (0 = todos)")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--pausa", type=float, default=0.5)
    parser.add_argument("--cache", default="data/debug_fferj_geocoding_cache.json")
    args = parser.parse_args()

    session = requests.Session()

    print("[INFO] Descobrindo clubes filiados a FERJ...")
    clubes = discover_clubes(session, args.timeout)
    print(f"[INFO] {len(clubes)} clubes encontrados nas {len(LIGAS_ALIASES)} ligas.")

    cache_path = Path(args.cache)
    geocoding_cache: dict = {}
    if cache_path.exists():
        try:
            geocoding_cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            geocoding_cache = {}

    itens = list(clubes.items())
    if args.max_clubes:
        itens = itens[: args.max_clubes]

    resultados = []
    for i, (alias_id, nome_clube) in enumerate(itens, start=1):
        url = f"{BASE_URL}/ClubesLigas/ViewTeam"
        try:
            r = session.get(url, params={"alias": alias_id}, headers=HEADERS, timeout=args.timeout)
            r.raise_for_status()
        except Exception as e:
            print(f"[{i}/{len(itens)}] {nome_clube}: ERRO ao abrir pagina ({e})")
            resultados.append({"alias_id": alias_id, "nome_clube": nome_clube, "erro": str(e)})
            continue

        info = parse_club_page(r.text)
        endereco, fonte_endereco = montar_endereco_geocoding(info)
        coords = geocode(endereco, session, geocoding_cache, args.timeout) if endereco else None

        item = {
            "alias_id": alias_id,
            "nome_clube": nome_clube,
            "estadio": info["estadio"],
            "localizacao": info["localizacao"],
            "sede": info["sede"],
            "endereco_geocodificado": endereco,
            "fonte_endereco": fonte_endereco,
            "lat": coords["lat"] if coords else None,
            "lng": coords["lng"] if coords else None,
        }
        resultados.append(item)

        status = "OK" if coords else "SEM COORDENADA"
        print(f"[{i}/{len(itens)}] {nome_clube} | estadio='{info['estadio']}' | {status}")

        time.sleep(args.pausa)

        if i % 10 == 0:
            cache_path.write_text(json.dumps(geocoding_cache, ensure_ascii=False, indent=2), encoding="utf-8")

    cache_path.write_text(json.dumps(geocoding_cache, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT_DIR / "debug_fferj_estadios_raw.json").write_text(
        json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    escrever_js(resultados, Path("estadios_ferj_rio.js"))

    com_coord = sum(1 for r in resultados if r.get("lat"))
    print("")
    print(f"Clubes processados: {len(resultados)}")
    print(f"Com coordenada: {com_coord}")
    print(f"Sem coordenada: {len(resultados) - com_coord}")
    print("Arquivo gerado: estadios_ferj_rio.js")
    print("Debug: data/debug_fferj_estadios_raw.json")


if __name__ == "__main__":
    main()
