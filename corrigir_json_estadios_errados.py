#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Correção emergencial para jogos com estádio errado já gravados no JSON.

Uso:
    python corrigir_json_estadios_errados.py
"""

from pathlib import Path
import json
import csv

DATA = Path("data/jogos_programados.json")
CSV = Path("data/jogos_programados.csv")
HIST = Path("data/historico_jogos.csv")

RULES = [
    {
        "competicao": "Liga de Ascenso Caixun",
        "data": "2026-08-31",
        "mandante": "Cobreloa",
        "visitante": "San Marcos de Arica",
        "estadio": "Zorros del Desierto",
    },
]

def match(row, rule):
    return (
        row.get("competicao") == rule["competicao"]
        and row.get("data") == rule["data"]
        and row.get("mandante") == rule["mandante"]
        and row.get("visitante") == rule["visitante"]
    )

def fix_rows(rows):
    changed = 0
    for row in rows:
        for rule in RULES:
            if match(row, rule) and row.get("estadio") != rule["estadio"]:
                row["estadio"] = rule["estadio"]
                changed += 1
    return changed

def write_csv(path, rows):
    fields = [
        "id", "fonte", "competicao", "data", "hora",
        "mandante", "visitante", "estadio", "rodada",
        "url", "extra", "atualizado_em",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})

if DATA.exists():
    rows = json.loads(DATA.read_text(encoding="utf-8"))
    changed = fix_rows(rows)
    DATA.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(CSV, rows)
    print(f"Corrigidos no JSON atual: {changed}")

if HIST.exists():
    with HIST.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    changed = fix_rows(rows)
    write_csv(HIST, rows)
    print(f"Corrigidos no histórico: {changed}")
