#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Remove jogos passados de data/jogos_programados.json e data/jogos_programados.csv,
mas mantém data/historico_jogos.csv completo.

Uso:
    python limpar_jogos_passados_programados.py

Por padrão remove jogos com data anterior a hoje.
"""

from pathlib import Path
from datetime import date
import json
import csv

OUT_DIR = Path("data")
JSON_PATH = OUT_DIR / "jogos_programados.json"
CSV_PATH = OUT_DIR / "jogos_programados.csv"

FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em", "pais", "cidade",
]

def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})

def main():
    if not JSON_PATH.exists():
        print("Sem data/jogos_programados.json para limpar.")
        return

    today = date.today().isoformat()
    rows = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    before = len(rows)

    kept = []
    removed = 0
    removidos_sem_data_hora = 0
    for r in rows:
        d = r.get("data", "")
        h = r.get("hora", "")
        if not d or not h:
            removidos_sem_data_hora += 1
            continue
        if d >= today:
            kept.append(r)
        else:
            removed += 1

    JSON_PATH.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(CSV_PATH, kept)

    print(f"Jogos programados antes: {before}")
    print(f"Jogos passados removidos do JSON atual: {removed}")
    print(f"Jogos sem data/hora confirmada removidos: {removidos_sem_data_hora}")
    print(f"Jogos programados depois: {len(kept)}")
    print("Histórico não foi apagado.")

if __name__ == "__main__":
    main()
