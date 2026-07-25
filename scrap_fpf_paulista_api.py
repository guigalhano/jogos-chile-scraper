#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FPF (Federação Paulista de Futebol) - JOGOS FUTUROS via API .ashx direta

Descoberta (validada com rede real em 25/07/2026):
- A página https://www.futebolpaulista.com.br/Competicoes/Tabela.aspx é Vue/JS
  e NÃO traz os jogos no HTML inicial (só templates {{item.NomePopular...}}).
- Mas os jogos vêm de handlers .ashx que retornam JSON puro e — ao contrário do
  que o scrap_fpf_playwright_api.py assumia — respondem a um GET simples com
  User-Agent de browser, SEM disparar o desafio do Cloudflare. Ou seja, dá pra
  buscar tudo com `requests`, sem Playwright/Chromium.

Endpoints usados:
  1) ListarTodosCampeonatosExercicio.ashx
     -> lista todos os campeonatos do exercício atual, cada um com
        IdCampeonato, IdCategoria, Categoria, Campeonato, DescricaoSite.
  2) ListarTabela.ashx?IdCampeonato={id}&Ano={ano}&IdCategoria={cat}
     -> Retorno.listTabela[] com TODAS as rodadas daquele campeonato/ano
        (passadas e futuras). Sem &Ano ele devolve o histórico desde 2008.

Como identificamos "jogo futuro":
  - A data do jogo é >= hoje; E
  - ResultadoMandante/ResultadoVisitante ainda são null (não jogado).
  Jogos com resultado preenchido (já realizados) são ignorados aqui — este
  scraper é focado em jogos PROGRAMADOS (é o que popula jogos_programados.*).

Saídas (mesmo formato/merge dos outros scrapers do projeto):
  data/jogos_programados.json
  data/jogos_programados.csv
  data/historico_jogos.csv
  data/debug_fpf_api_raw.json          # linhas raspadas (p/ merge_apos_reset.py)
  data/debug_fpf_api_campeonatos.json  # lista de campeonatos do exercício
  data/debug_fpf_api_resumo.json       # contagem futuros por campeonato

Uso:
  py -3 scrap_fpf_paulista_api.py --ano 2026
  py -3 scrap_fpf_paulista_api.py --ano 2026 --dias 365   # janela p/ frente
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

JOGOS_JSON = OUT_DIR / "jogos_programados.json"
JOGOS_CSV = OUT_DIR / "jogos_programados.csv"
HIST_CSV = OUT_DIR / "historico_jogos.csv"

# RAW_JOGOS guarda a LISTA de jogos raspados nesta rodada (uma linha por jogo,
# no formato final). É o arquivo consumido por merge_apos_reset.py --raw no
# workflow, para re-mesclar de forma segura contra origin/main após o reset.
RAW_JOGOS = OUT_DIR / "debug_fpf_api_raw.json"
DEBUG_CAMPEONATOS = OUT_DIR / "debug_fpf_api_campeonatos.json"
DEBUG_RESUMO = OUT_DIR / "debug_fpf_api_resumo.json"

BASE = "https://www.futebolpaulista.com.br/Handlers/Competicoes"
URL_CAMPEONATOS = f"{BASE}/ListarTodosCampeonatosExercicio.ashx"
URL_TABELA = f"{BASE}/ListarTabela.ashx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
    "Referer": "https://www.futebolpaulista.com.br/Competicoes/Tabela.aspx",
    "X-Requested-With": "XMLHttpRequest",
}

FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "pais", "cidade", "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em",
]

DATE_BR_RE = re.compile(r"\b(?P<dia>\d{1,2})/(?P<mes>\d{1,2})/(?P<ano>\d{2,4})\b")
TIME_RE = re.compile(r"\b(?P<hora>\d{1,2})[h:](?P<min>\d{2})\b")


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


def clean_text(x: Any) -> str:
    x = "" if x is None else str(x)
    x = x.replace(" ", " ")
    return re.sub(r"\s+", " ", x).strip()


def parse_year(y: str) -> int:
    n = int(y)
    return 2000 + n if n < 100 else n


def parse_date_br(value: Any) -> str:
    """dd/mm/aaaa -> aaaa-mm-dd (ISO). Vazio se não parsear."""
    m = DATE_BR_RE.search(clean_text(value))
    if not m:
        return ""
    try:
        return date(parse_year(m.group("ano")), int(m.group("mes")), int(m.group("dia"))).isoformat()
    except Exception:
        return ""


def parse_time(value: Any) -> str:
    """'20h00' / '20:00' -> '20:00'."""
    m = TIME_RE.search(clean_text(value))
    if not m:
        return ""
    return f"{int(m.group('hora')):02d}:{m.group('min')}"


def nome_competicao(camp: dict) -> str:
    """Monta um nome legível e estável para a competição."""
    nome = clean_text(camp.get("DescricaoSite")) or clean_text(camp.get("Campeonato")) \
        or f"Campeonato {camp.get('IdCampeonato')}"
    categoria = clean_text(camp.get("Categoria"))
    base = f"Brasil - FPF - {nome}"
    if categoria and unicodedata.normalize("NFKD", categoria.lower()) not in \
            unicodedata.normalize("NFKD", base.lower()):
        base = f"{base} ({categoria})"
    return base


def get_json(url: str, params: dict | None = None, tentativas: int = 3) -> Any:
    ultima_exc: Exception | None = None
    for i in range(tentativas):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=40)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:  # noqa: BLE001
            ultima_exc = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"Falha ao buscar {url} ({params}): {ultima_exc}")


def jogo_futuro(item: dict, hoje: date, limite: date) -> bool:
    data_iso = parse_date_br(item.get("Data"))
    if not data_iso:
        return False
    try:
        d = date.fromisoformat(data_iso)
    except Exception:
        return False
    if not (hoje <= d <= limite):
        return False
    # Jogo ainda não realizado: sem placar dos dois lados.
    if item.get("ResultadoMandante") is not None and item.get("ResultadoVisitante") is not None:
        return False
    if item.get("Adiado") is True:
        # adiado sem nova data confiável — mantém só se a data ainda é futura
        pass
    return True


def item_para_jogo(item: dict, competicao: str) -> Jogo | None:
    mandante = clean_text(item.get("NomePopularMandante"))
    visitante = clean_text(item.get("NomePopularVisitante"))
    if not (mandante and visitante):
        return None

    data = parse_date_br(item.get("Data"))
    hora = parse_time(item.get("Horario"))
    estadio = clean_text(item.get("Estadio")) or clean_text(item.get("NomePopularEstadio"))
    cidade = clean_text(item.get("Municipio"))
    rodada = clean_text(item.get("Rodada"))

    extra = ["status=Programado", "pais=Brasil", "estado=São Paulo", "fonte=api_ashx"]
    for chave, rotulo in [
        ("Numero", "jogo_numero"),
        ("Grupo", "grupo"),
        ("Fase", "fase"),
        ("CanaisTransmissao", "canais"),
        ("Suspencao", "suspencao"),
    ]:
        v = clean_text(item.get(chave))
        if v:
            extra.append(f"{rotulo}={v}")
    if item.get("Adiado") is True:
        extra.append("adiado=sim")

    link_sumula = clean_text(item.get("LinkSumula"))

    return Jogo(
        fonte="FPF",
        competicao=competicao,
        data=data,
        hora=hora,
        mandante=mandante,
        visitante=visitante,
        pais="Brasil",
        cidade=cidade,
        estadio=estadio,
        rodada=f"Rodada {rodada}" if rodada and not rodada.lower().startswith("rodada") else rodada,
        url=link_sumula or "https://www.futebolpaulista.com.br/Competicoes/Tabela.aspx",
        extra="; ".join(extra),
    )


# ---------------------------------------------------------------------------
# Merge / persistência (mesma convenção dos demais scrapers do projeto)
# ---------------------------------------------------------------------------
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
    parser = argparse.ArgumentParser(description="Scraper FPF - jogos futuros via API .ashx")
    parser.add_argument("--ano", type=int, default=date.today().year)
    parser.add_argument("--dias", type=int, default=365,
                        help="Janela para frente (dias a partir de hoje). Default 365.")
    parser.add_argument("--pausa", type=float, default=0.3,
                        help="Pausa (s) entre chamadas de campeonato, para não sobrecarregar o servidor.")
    args = parser.parse_args()

    hoje = date.today()
    limite = hoje + timedelta(days=args.dias)

    print(f"[INFO] FPF via API .ashx | ano={args.ano} | janela até {limite.isoformat()}")
    print(f"[INFO] Listando campeonatos: {URL_CAMPEONATOS}")

    payload = get_json(URL_CAMPEONATOS)
    campeonatos = payload.get("Retorno") or []
    DEBUG_CAMPEONATOS.write_text(
        json.dumps(campeonatos, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[INFO] {len(campeonatos)} campeonatos no exercício.")

    jogos: list[Jogo] = []
    raw_debug: list[dict] = []

    for camp in campeonatos:
        id_camp = camp.get("IdCampeonato")
        id_cat = camp.get("IdCategoria")
        if not id_camp:
            continue
        nome = nome_competicao(camp)
        params = {"IdCampeonato": id_camp, "Ano": args.ano, "IdCategoria": id_cat, "IdClube": 0}
        try:
            data = get_json(URL_TABELA, params=params)
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] {nome} (Id={id_camp}): {e}")
            continue

        lista = ((data or {}).get("Retorno") or {}).get("listTabela") or []
        futuros = [it for it in lista if jogo_futuro(it, hoje, limite)]

        n_add = 0
        for it in futuros:
            jogo = item_para_jogo(it, nome)
            if jogo and jogo.data:
                jogos.append(jogo)
                n_add += 1

        if lista:
            print(f"  - {nome} (Id={id_camp}): {len(lista)} jogos no ano, {n_add} futuros")
        raw_debug.append({
            "campeonato": nome, "IdCampeonato": id_camp, "IdCategoria": id_cat,
            "total_ano": len(lista), "futuros": n_add,
        })
        time.sleep(args.pausa)

    # Dedup por id
    vistos: set[str] = set()
    rows: list[dict] = []
    for g in jogos:
        r = g.to_row()
        if r["id"] in vistos:
            continue
        vistos.add(r["id"])
        rows.append(r)

    # Linhas reais desta rodada (para merge_apos_reset.py --raw no workflow) +
    # resumo por campeonato (diagnóstico de "0 futuros").
    RAW_JOGOS.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    DEBUG_RESUMO.write_text(json.dumps(raw_debug, ensure_ascii=False, indent=2), encoding="utf-8")

    merged_current = merge_rows(load_json_rows(JOGOS_JSON), rows)
    JOGOS_JSON.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(JOGOS_CSV, merged_current)

    merged_hist = merge_rows(load_csv_rows(HIST_CSV), rows)
    write_csv(HIST_CSV, merged_hist)

    print("")
    print(f"[OK] Jogos futuros FPF coletados: {len(rows)}")
    print(f"[OK] Total no {JOGOS_JSON.name}: {len(merged_current)}")
    print(f"[OK] Total no {HIST_CSV.name}: {len(merged_hist)}")


if __name__ == "__main__":
    main()
