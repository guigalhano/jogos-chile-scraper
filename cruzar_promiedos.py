#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cruzamento com Promiedos (via pacote EasySoccerData, sem chave de API).

Diferente da tentativa anterior com API-Football (cujo plano gratuito
bloqueia a temporada atual), o Promiedos é a própria API pública que o
site https://www.promiedos.com.ar usa internamente — sem chave, sem
restrição de temporada, com cobertura confirmada de Chile (Primera
División), Brasil (Brasileirão + Copa do Brasil) e Argentina (Liga
Profesional, Copa Argentina, categorias de base, etc.).

Objetivo: mesmo que o script anterior — auditar/cruzar
data/jogos_programados.json contra uma fonte independente, sem alterar
os dados existentes. Gera data/cruzamento_promiedos.json.

Uso:
    python cruzar_promiedos.py --dias 60
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

from curl_cffi import requests as curl_requests

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

PROMIEDOS_HEADERS = {"X-VER": "1.11.7.5"}
PROMIEDOS_URL = "https://api.promiedos.com.ar/games/{date}"

PAISES_ALVO = {"chile", "argentina", "brasil", "brazil"}

MAPA_PAIS = {
    "chile": "Chile",
    "argentina": "Argentina",
    "brasil": "Brasil",
    "brazil": "Brasil",
}


def norm(value) -> str:
    value = "" if value is None else str(value)
    value = unicodedata.normalize("NFD", value)
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def chave_confronto(data_iso: str, mandante: str, visitante: str) -> str:
    m = norm(mandante)[:6]
    v = norm(visitante)[:6]
    return f"{data_iso}|{m}|{v}"


def fetch_day_raw(date_str: str) -> list[dict]:
    """Chama a API do Promiedos diretamente (bypass do client da lib, que tem
    um bug na validação de data). Retorna a lista bruta de 'leagues' do dia."""
    url = PROMIEDOS_URL.format(date=date_str)
    r = curl_requests.get(url, headers=PROMIEDOS_HEADERS, impersonate="chrome", timeout=20)
    r.raise_for_status()
    data = r.json()
    return data.get("leagues", [])


def load_jogos_atuais() -> list[dict]:
    path = OUT_DIR / "jogos_programados.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dias", type=int, default=60)
    args = parser.parse_args()

    today = date.today()

    jogos_atuais = load_jogos_atuais()
    nosso_index = {}
    for j in jogos_atuais:
        if not j.get("data") or not j.get("hora"):
            continue
        k = chave_confronto(j["data"], j.get("mandante", ""), j.get("visitante", ""))
        nosso_index[k] = j

    por_pais = {"Chile": {"confirmados": 0, "so_na_promiedos": []},
                "Brasil": {"confirmados": 0, "so_na_promiedos": []},
                "Argentina": {"confirmados": 0, "so_na_promiedos": []}}
    total_eventos_lidos = 0
    dias_com_erro = []

    for offset in range(args.dias + 1):
        dia = today + timedelta(days=offset)
        dia_str = dia.isoformat()
        try:
            leagues_raw = fetch_day_raw(dia_str)
        except Exception as e:
            dias_com_erro.append({"data": dia_str, "erro": str(e)})
            continue

        for league_data in leagues_raw:
            liga_pais = norm(league_data.get("country_name", "") or "")
            if liga_pais not in PAISES_ALVO:
                continue
            pais_nosso = MAPA_PAIS[liga_pais]
            liga_nome = league_data.get("name", "")

            for game in league_data.get("games", []):
                total_eventos_lidos += 1
                teams = game.get("teams", [])
                if len(teams) < 2:
                    continue
                mandante = (teams[0] or {}).get("name", "") or ""
                visitante = (teams[1] or {}).get("name", "") or ""
                if not mandante or not visitante:
                    continue

                start_time_str = game.get("start_time", "")
                try:
                    dt = datetime.strptime(start_time_str, "%d-%m-%Y %H:%M")
                    data_iso = dt.date().isoformat()
                    hora = dt.strftime("%H:%M")
                except Exception:
                    continue

                k = chave_confronto(data_iso, mandante, visitante)
                if k in nosso_index:
                    por_pais[pais_nosso]["confirmados"] += 1
                else:
                    por_pais[pais_nosso]["so_na_promiedos"].append({
                        "data": data_iso,
                        "hora": hora,
                        "mandante": mandante,
                        "visitante": visitante,
                        "campeonato": liga_nome,
                        "rodada": game.get("stage_round_name", ""),
                    })

        time.sleep(0.5)  # cortesia com o servidor, não é uma API oficial com SLA

    relatorio = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "dias_verificados": args.dias + 1,
        "total_eventos_lidos_nos_3_paises": total_eventos_lidos,
        "dias_com_erro": dias_com_erro,
        "paises": {},
    }
    for pais, info in por_pais.items():
        relatorio["paises"][pais] = {
            "confirmados_com_nossos_dados": info["confirmados"],
            "apenas_no_promiedos_total": len(info["so_na_promiedos"]),
            "apenas_no_promiedos_amostra": info["so_na_promiedos"][:30],
        }

    (OUT_DIR / "cruzamento_promiedos.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n=== Resumo do cruzamento com Promiedos ===")
    for pais, info in relatorio["paises"].items():
        print(f"{pais}: {info['confirmados_com_nossos_dados']} confirmados, "
              f"{info['apenas_no_promiedos_total']} só no Promiedos (possível lacuna)")
    if dias_com_erro:
        print(f"Dias com erro ao consultar Promiedos: {len(dias_com_erro)}")


if __name__ == "__main__":
    main()
