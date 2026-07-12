#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calcula quais jogos foram adicionados/alterados por um job que roda varios
scrapers em sequencia (ex: atualizar-jogos.yml), comparando o
jogos_programados.json de ANTES da cadeia rodar com o de DEPOIS.

Isso evita ter que modificar cada scraper individualmente so para gerar um
debug_*_raw.json proprio - o "diff" observado já é equivalente a "tudo que
esse job contribuiu nesta rodada", pronto para ser re-mesclado com
merge_apos_reset.py depois do "git reset --hard origin/main".

Uso:
    python computar_diff_desde_baseline.py \
        --baseline /tmp/baseline_jogos_programados.json \
        --atual data/jogos_programados.json \
        --saida data/debug_orquestrador_diff_raw.json
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def load_json_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def row_id(row: dict) -> str:
    if row.get("id"):
        return row["id"]
    raw = "|".join([
        row.get("fonte", ""), row.get("competicao", ""), row.get("data", ""),
        row.get("hora", ""), row.get("mandante", ""), row.get("visitante", ""),
        row.get("estadio", ""), row.get("rodada", ""),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, help="jogos_programados.json ANTES da cadeia de scrapers rodar")
    parser.add_argument("--atual", required=True, help="jogos_programados.json DEPOIS da cadeia de scrapers rodar")
    parser.add_argument("--saida", required=True, help="onde salvar o diff (lista de jogos novos/alterados)")
    args = parser.parse_args()

    baseline_rows = load_json_rows(Path(args.baseline))
    atual_rows = load_json_rows(Path(args.atual))

    baseline_by_id = {row_id(r): r for r in baseline_rows}

    diff = []
    for r in atual_rows:
        rid = row_id(r)
        antigo = baseline_by_id.get(rid)
        if antigo is None or antigo != r:
            diff.append(r)

    Path(args.saida).write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[computar_diff_desde_baseline] baseline={len(baseline_rows)} atual={len(atual_rows)} diff (novos/alterados)={len(diff)}")


if __name__ == "__main__":
    main()
