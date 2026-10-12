#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Renomeia as ligas do NonLeagueHQ da Escocia,
Pais de Gales e Irlanda do Norte ja gravadas em data/reino_unido/ usando a
nova regra do scrap_nonleaguehq.py (liga identificada pelos confrontos, nao
pelo codigo do site, que mistura ligas na Escocia).

O codigo_nlhq (chave do merge) inclui o nome da liga, entao renomear muda a
chave. Por isso o script REMOVE as linhas antigas dessas ligas na temporada e
grava as reconstruidas, nos dois arquivos, em vez de mesclar (o que deixaria
as duas versoes).

Reconstroi tudo a partir dos proprios dados (programados + historico); nao
acessa a internet. Idempotente: o workflow do NonLeagueHQ roda este script
toda vez depois do merge, o que tambem limpa versoes com nome antigo.

  python migrar_ligas_nlhq_confrontos.py            # aplica
  python migrar_ligas_nlhq_confrontos.py --dry-run  # so mostra o resumo
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date

from reino_unido_comum import (
    ESCOCIA, GALES, IRLANDA_NORTE, UK_DIR, load_csv_rows, load_json_rows, write_csv,
)
from scrap_nonleaguehq import CODIGO_RE, montar_jogos_finder, temporada

PAISES = (ESCOCIA, GALES, IRLANDA_NORTE)
FONTE = "NonLeagueHQ"


def extra_dict(extra: str) -> dict[str, str]:
    out = {}
    for p in (extra or "").split(";"):
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def alvo(row: dict, temp: str) -> bool:
    if row.get("fonte") != FONTE or row.get("pais") not in PAISES or not row.get("data"):
        return False
    try:
        return temporada(date.fromisoformat(row["data"])) == temp
    except ValueError:
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--temporada", default=temporada(date.today()))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    jogos_json = UK_DIR / "jogos_programados.json"
    jogos_csv = UK_DIR / "jogos_programados.csv"
    hist_csv = UK_DIR / "historico_jogos.csv"
    prog = load_json_rows(jogos_json)
    hist = load_csv_rows(hist_csv)

    # Uma linha por confronto da temporada (o mesmo jogo pode estar gravado
    # com o nome antigo e com o novo da liga): fica a atualizada por ultimo.
    antigas: dict[tuple, dict] = {}
    for r in sorted((r for r in hist + prog if alvo(r, args.temporada)),
                    key=lambda r: r.get("atualizado_em", "")):
        antigas[(r["pais"], r["mandante"], r["visitante"])] = r

    por_pais: dict[str, list[dict]] = {p: [] for p in PAISES}
    for r in antigas.values():
        e = extra_dict(r.get("extra", ""))
        codigo = e.get("codigo_liga_nlhq", "")
        if not CODIGO_RE.match(codigo):
            continue
        gh, ga = "", ""
        if "-" in e.get("placar", ""):
            gh, ga = e["placar"].split("-", 1)
        por_pais[r["pais"]].append({
            "codigo": codigo, "data": date.fromisoformat(r["data"]),
            "mandante": r["mandante"], "visitante": r["visitante"], "gh": gh, "ga": ga,
            "condado": e.get("condado", ""), "regiao": e.get("regiao", ""),
            "url": r.get("url", ""),
        })

    novas: list[dict] = []
    for pais, linhas in por_pais.items():
        if not linhas:
            continue
        jogos, _, avisos = montar_jogos_finder(linhas, pais, linhas[0]["url"])
        antes = Counter(r["competicao"] for r in antigas.values() if r["pais"] == pais)
        depois = Counter(j.competicao for j in jogos)
        print(f"== {pais}: {len(jogos)} jogos | ligas {len(antes)} -> {len(depois)}")
        for a in avisos:
            print(f"   [WARN] {a}")
        for comp, n in sorted(depois.items()):
            print(f"   {n:5d}  {comp}")
        novas += [j.to_row() for j in jogos]

    if args.dry_run:
        print("[dry-run] nada gravado")
        return

    hoje = date.today().isoformat()
    prog_out = [r for r in prog if not alvo(r, args.temporada)]
    prog_out += [r for r in novas if r["data"] >= hoje]
    prog_out.sort(key=lambda r: (r.get("data", ""), r.get("hora", ""), r.get("pais", ""),
                                 r.get("competicao", ""), r.get("mandante", "")))
    hist_out = [r for r in hist if not alvo(r, args.temporada)] + novas
    hist_out.sort(key=lambda r: (r.get("data", ""), r.get("hora", ""), r.get("pais", ""),
                                 r.get("competicao", ""), r.get("mandante", "")))

    jogos_json.write_text(
        "[\n" + ",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in prog_out) + "\n]\n",
        encoding="utf-8",
    )
    write_csv(jogos_csv, prog_out)
    write_csv(hist_csv, hist_out)
    print(f"[ok] programados: {len(prog)} -> {len(prog_out)} | historico: {len(hist)} -> {len(hist_out)}")


if __name__ == "__main__":
    main()
