#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Faz o merge dos jogos recem-raspados (arquivo debug_*_raw.json de UM scraper)
contra o estado ATUAL de data/jogos_programados.json e data/historico_jogos.csv
- ou seja, deve ser chamado DEPOIS de "git reset --hard origin/main", nunca antes.

Isso substitui o padrao antigo (perigoso) de: salvar o jogos_programados.json
inteiro num /tmp ANTES do reset, e depois sobrescrever tudo com essa copia
desatualizada. Esse padrao antigo causava perda de jogos de outras fontes
quando dois workflows rodavam perto um do outro (condicao de corrida).

Uso:
    python merge_apos_reset.py --raw data/debug_fferj_rio_raw.json
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path

OUT_DIR = Path("data")
FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "pais", "cidade", "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em",
]


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


def is_valid_row(row: dict) -> bool:
    return bool(row.get("data") and row.get("mandante") and row.get("visitante"))


def row_id(row: dict) -> str:
    if row.get("id"):
        return row["id"]
    import hashlib
    raw = "|".join([
        row.get("fonte", ""), row.get("competicao", ""), row.get("data", ""),
        row.get("hora", ""), row.get("mandante", ""), row.get("visitante", ""),
        row.get("estadio", ""), row.get("rodada", ""),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def merge_rows(existing: list[dict], new_rows: list[dict]) -> list[dict]:
    by_id = {}
    for r in existing:
        if not is_valid_row(r):
            continue
        rid = row_id(r)
        r["id"] = rid
        by_id[rid] = r
    for r in new_rows:
        if not is_valid_row(r):
            continue
        rid = row_id(r)
        r["id"] = rid
        by_id[rid] = r
    return sorted(
        by_id.values(),
        key=lambda r: (r.get("data", ""), r.get("hora", ""), r.get("pais", ""), r.get("competicao", ""), r.get("mandante", ""))
    )


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            if is_valid_row(r):
                w.writerow({k: r.get(k, "") for k in FIELDS})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--raw", action="append", default=[],
        help="Caminho de um debug_*_raw.json com os jogos desta rodada. Pode repetir --raw varias vezes (uma por fonte) quando o job roda mais de um scraper na mesma rodada. Esses jogos entram em jogos_programados.* E no historico.",
    )
    parser.add_argument(
        "--raw-historico", action="append", default=[], dest="raw_historico",
        help="Caminho de um debug_*_raw.json cujos jogos entram SO no historico_jogos.csv (nao em jogos_programados). Use para resultados de jogos ja realizados, que nao devem aparecer na lista de proximos jogos.",
    )
    args = parser.parse_args()

    if not args.raw and not args.raw_historico:
        parser.error("informe ao menos um --raw ou --raw-historico")

    rows_prog: list[dict] = []
    for raw_arg in args.raw:
        raw_path = Path(raw_arg)
        rows = load_json_rows(raw_path)
        print(f"[merge_apos_reset] jogos (programados+historico) lidos de {raw_path}: {len(rows)}")
        rows_prog.extend(rows)

    rows_hist_only: list[dict] = []
    for raw_arg in args.raw_historico:
        raw_path = Path(raw_arg)
        rows = load_json_rows(raw_path)
        print(f"[merge_apos_reset] jogos (so historico) lidos de {raw_path}: {len(rows)}")
        rows_hist_only.extend(rows)

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    merged_current = merge_rows(load_json_rows(current_json), rows_prog)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    merged_history = merge_rows(load_csv_rows(history_csv), rows_prog + rows_hist_only)
    write_csv(history_csv, merged_history)

    print(f"[merge_apos_reset] jogos_programados.json agora tem {len(merged_current)} jogos no total")
    print(f"[merge_apos_reset] historico_jogos.csv agora tem {len(merged_history)} jogos no total")


if __name__ == "__main__":
    main()
