#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Partes comuns dos scrapers do Reino Unido + Irlanda
(scrap_reino_unido_sofascore.py e scrap_nonleaguehq.py).

Os jogos do Reino Unido NAO vao para data/jogos_programados.json (o arquivo
do site sul-americano): so o NonLeagueHQ traz dezenas de milhares de jogos
amadores por temporada, o que afogaria os ~1.300 jogos de la. Ficam em:

  data/reino_unido/jogos_programados.json / .csv
  data/reino_unido/historico_jogos.csv

Mesmo formato de linha (FIELDS) e mesma regra de merge do
merge_apos_reset.py. Nos workflows, depois do "git reset --hard", rodar
este arquivo direto faz o papel do merge_apos_reset.py:

  python reino_unido_comum.py --raw data/debug_x_raw.json --raw-historico data/debug_x_hist_raw.json
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    FUSO_UK = ZoneInfo("Europe/London")  # Irlanda (Europe/Dublin) tem o mesmo offset o ano todo
except Exception:  # noqa: BLE001 - Windows sem o pacote tzdata
    FUSO_UK = None

OUT_DIR = Path("data")
UK_DIR = OUT_DIR / "reino_unido"

FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "pais", "cidade", "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em",
]

INGLATERRA = "Inglaterra"
ESCOCIA = "Escócia"
GALES = "País de Gales"
IRLANDA = "Irlanda"
IRLANDA_NORTE = "Irlanda do Norte"


@dataclass
class Jogo:
    fonte: str
    competicao: str
    data: str
    hora: str
    mandante: str
    visitante: str
    pais: str
    cidade: str = ""
    estadio: str = ""
    rodada: str = ""
    url: str = ""
    extra: str = ""

    @property
    def id(self) -> str:
        raw = "|".join([
            self.fonte, self.competicao, self.data, self.hora,
            self.mandante, self.visitante,
        ])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def to_row(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        d["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
        return d


def dedup_rows(jogos: list[Jogo]) -> list[dict]:
    vistos: set[str] = set()
    rows: list[dict] = []
    for g in jogos:
        if not (g.data and g.mandante and g.visitante):
            continue
        r = g.to_row()
        k = merge_key(r)
        if k in vistos:
            continue
        vistos.add(k)
        rows.append(r)
    return rows


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


def merge_key(row: dict) -> str:
    # Mesma regra do merge_apos_reset.py: codigo estavel da fonte no extra
    # (codigo_sofascore=..., codigo_nlhq=...), senao o hash da linha.
    from merge_apos_reset import merge_key as _mk
    return _mk(row)


def merge_rows(existing: list[dict], new_rows: list[dict]) -> list[dict]:
    from merge_apos_reset import merge_rows as _mr
    return _mr(existing, new_rows)


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def salvar(rows_prog: list[dict], rows_hist: list[dict]) -> tuple[int, int]:
    """Mescla os jogos novos em data/reino_unido/. rows_prog entra nos
    programados E no historico; rows_hist so no historico."""
    UK_DIR.mkdir(parents=True, exist_ok=True)
    jogos_json = UK_DIR / "jogos_programados.json"
    jogos_csv = UK_DIR / "jogos_programados.csv"
    hist_csv = UK_DIR / "historico_jogos.csv"

    # Programados = so de hoje em diante; o que ja passou fica so no historico.
    hoje = date.today().isoformat()
    merged = [r for r in merge_rows(load_json_rows(jogos_json), rows_prog) if r.get("data", "") >= hoje]
    jogos_json.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(jogos_csv, merged)

    merged_hist = merge_rows(load_csv_rows(hist_csv), rows_prog + rows_hist)
    write_csv(hist_csv, merged_hist)
    return len(merged), len(merged_hist)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Merge pos-reset dos jogos do Reino Unido em data/reino_unido/")
    parser.add_argument("--raw", action="append", default=[], help="jogos programados (entram tambem no historico)")
    parser.add_argument("--raw-historico", action="append", default=[], dest="raw_historico", help="jogos so para o historico")
    args = parser.parse_args()
    if not args.raw and not args.raw_historico:
        parser.error("informe ao menos um --raw ou --raw-historico")

    rows_prog = [r for p in args.raw for r in load_json_rows(Path(p))]
    rows_hist = [r for p in args.raw_historico for r in load_json_rows(Path(p))]
    n_prog, n_hist = salvar(rows_prog, rows_hist)
    print(f"[reino_unido] {len(rows_prog)} programados + {len(rows_hist)} so historico lidos")
    print(f"[reino_unido] jogos_programados.json: {n_prog} | historico_jogos.csv: {n_hist}")


if __name__ == "__main__":
    main()
