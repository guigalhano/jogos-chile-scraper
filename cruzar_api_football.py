#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cruzamento com API-Football (v3.football.api-sports.io)

Objetivo: NÃO substituir os scrapers atuais, e sim auditar/cruzar os dados
já coletados (data/jogos_programados.json) contra uma fonte independente,
para detectar:
  - jogos que a API tem e nós não temos (possível lacuna nos scrapers)
  - jogos que nós temos e a API não confirma (possível erro/duplicata)
  - divergências de data/hora para o "mesmo" confronto

Não grava nada em jogos_programados.json — apenas gera um relatório em
data/cruzamento_api_football.json para inspeção manual.

Autenticação: header "x-apisports-key" (variável de ambiente API_FOOTBALL_KEY).

Uso:
    python cruzar_api_football.py --dias 60
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

BASE_URL = "https://v3.football.api-sports.io"
OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

PAISES = {
    "Chile": "Chile",
    "Brasil": "Brazil",
    "Argentina": "Argentina",
}

# Nomes de ligas que nos interessam por país (correspondência parcial,
# case-insensitive, sem acento). Cobrem a primeira divisão + principais copas
# já rastreadas pelos nossos scrapers, para permitir comparação direta.
LIGAS_ALVO = {
    "Chile": ["primera division", "liga de primera", "primera a"],
    "Brazil": ["serie a", "serie b", "copa do brasil"],
    "Argentina": ["liga profesional", "primera division", "copa argentina"],
}


def norm(value) -> str:
    value = "" if value is None else str(value)
    value = unicodedata.normalize("NFD", value)
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def api_get(path: str, params: dict, api_key: str, retries: int = 3) -> dict:
    headers = {"x-apisports-key": api_key}
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(f"{BASE_URL}/{path}", params=params, headers=headers, timeout=30)
            r.raise_for_status()
            data = r.json()
            if data.get("errors"):
                last_err = data["errors"]
            return data
        except Exception as e:
            last_err = str(e)
            time.sleep(2)
    print(f"[WARN] Falha em {path} {params}: {last_err}", file=sys.stderr)
    return {"response": [], "errors": last_err}


def find_league_ids(pais_api: str, api_key: str, season: int) -> list[dict]:
    """Retorna [{id, name, type}] das ligas do país que batem com LIGAS_ALVO."""
    data = api_get("leagues", {"country": pais_api}, api_key)
    encontrados = []
    alvos = [norm(a) for a in LIGAS_ALVO.get(pais_api, [])]
    for item in data.get("response", []):
        liga = item.get("league", {})
        nome = norm(liga.get("name", ""))
        if any(alvo in nome for alvo in alvos):
            # confirma que a temporada solicitada existe para essa liga
            seasons = [s.get("year") for s in item.get("seasons", [])]
            encontrados.append({
                "id": liga.get("id"),
                "name": liga.get("name"),
                "type": liga.get("type"),
                "seasons_disponiveis": seasons,
                "season_alvo_disponivel": season in seasons,
            })
    return encontrados


def fetch_fixtures(league_id: int, season: int, desde: date, ate: date, api_key: str) -> list[dict]:
    data = api_get("fixtures", {
        "league": league_id,
        "season": season,
        "from": desde.isoformat(),
        "to": ate.isoformat(),
    }, api_key)
    return data.get("response", []), data.get("errors")


def load_jogos_atuais() -> list[dict]:
    path = OUT_DIR / "jogos_programados.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def chave_confronto(data_iso: str, mandante: str, visitante: str) -> str:
    """Chave tolerante para comparar confrontos entre fontes diferentes:
    data + primeiras 6 letras normalizadas de cada nome de time (evita
    problemas com sufixos de estado/sigla que uma fonte tem e outra não,
    ex.: "Botafogo (RJ)" vs "Botafogo")."""
    m = norm(mandante)[:6]
    v = norm(visitante)[:6]
    return f"{data_iso}|{m}|{v}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dias", type=int, default=60)
    args = parser.parse_args()

    api_key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if not api_key:
        print("[ERRO] API_FOOTBALL_KEY não definida no ambiente.", file=sys.stderr)
        (OUT_DIR / "cruzamento_api_football.json").write_text(
            json.dumps({"erro": "API_FOOTBALL_KEY não configurada"}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return

    today = date.today()
    ate = today + timedelta(days=args.dias)
    season = today.year

    jogos_atuais = load_jogos_atuais()
    nosso_index = {}
    for j in jogos_atuais:
        if not j.get("data") or not j.get("hora"):
            continue
        k = chave_confronto(j["data"], j.get("mandante", ""), j.get("visitante", ""))
        nosso_index[k] = j

    relatorio = {"gerado_em": datetime.now().isoformat(timespec="seconds"), "paises": {}}

    # Diagnóstico único: testa se o plano gratuito bloqueia a temporada atual
    # (hipótese: API-Football restringe temporadas no plano free). Usa a
    # Primera División do Chile como sonda, sem filtro de data (últimos jogos).
    diag = {}
    sonda = api_get("leagues", {"country": "Chile"}, api_key)
    sonda_id = None
    for item in sonda.get("response", []):
        if norm(item.get("league", {}).get("name", "")) == norm("Primera División"):
            sonda_id = item["league"]["id"]
            break
    if sonda_id:
        atual = api_get("fixtures", {"league": sonda_id, "season": today.year, "last": 5}, api_key)
        anterior = api_get("fixtures", {"league": sonda_id, "season": today.year - 1, "last": 5}, api_key)
        diag = {
            "liga_sonda": sonda_id,
            f"temporada_{today.year}_resultados": len(atual.get("response", [])),
            f"temporada_{today.year}_erros": atual.get("errors"),
            f"temporada_{today.year - 1}_resultados": len(anterior.get("response", [])),
            f"temporada_{today.year - 1}_erros": anterior.get("errors"),
        }
    relatorio["diagnostico_restricao_temporada"] = diag

    for pais_nosso, pais_api in PAISES.items():
        ligas = find_league_ids(pais_api, api_key, season)
        pais_report = {"ligas_encontradas": ligas, "por_liga": []}

        for liga in ligas:
            if not liga["id"]:
                continue
            fixtures, erros_api = fetch_fixtures(liga["id"], season, today, ate, api_key)

            so_na_api = []
            confirmados = 0

            for fx in fixtures:
                fixture = fx.get("fixture", {})
                teams = fx.get("teams", {})
                venue = fixture.get("venue", {}) or {}
                data_iso = (fixture.get("date") or "")[:10]
                mandante = teams.get("home", {}).get("name", "")
                visitante = teams.get("away", {}).get("name", "")
                k = chave_confronto(data_iso, mandante, visitante)

                if k in nosso_index:
                    confirmados += 1
                else:
                    so_na_api.append({
                        "data": data_iso,
                        "hora": (fixture.get("date") or "")[11:16],
                        "mandante": mandante,
                        "visitante": visitante,
                        "estadio": venue.get("name"),
                        "cidade": venue.get("city"),
                        "rodada": fx.get("league", {}).get("round"),
                    })

            pais_report["por_liga"].append({
                "liga": liga["name"],
                "liga_id": liga["id"],
                "total_fixtures_api": len(fixtures),
                "erros_api": erros_api,
                "confirmados_com_nossos_dados": confirmados,
                "apenas_na_api": so_na_api[:30],  # limite para o relatório não ficar gigante
                "apenas_na_api_total": len(so_na_api),
            })
            time.sleep(1)  # respeita rate limit do plano gratuito

        relatorio["paises"][pais_nosso] = pais_report

    (OUT_DIR / "cruzamento_api_football.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n=== Resumo do cruzamento ===")
    for pais, rep in relatorio["paises"].items():
        for liga_rep in rep["por_liga"]:
            print(f"{pais} - {liga_rep['liga']}: {liga_rep['total_fixtures_api']} na API, "
                  f"{liga_rep['confirmados_com_nossos_dados']} confirmados, "
                  f"{liga_rep['apenas_na_api_total']} só na API (possível lacuna)")


if __name__ == "__main__":
    main()
