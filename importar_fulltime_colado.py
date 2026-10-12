#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Importa jogos do FA Full-Time COLADOS a mao em data/reino_unido/fulltime_colado/*.txt.

Por que colado e nao coletado: o robots.txt do fulltime.thefa.com proibe
qualquer coleta automatica ("User-agent: *" / "Disallow: /") e o site
responde a scripts com o bloqueio do Cloudflare. Entao nenhum script acessa
o Full-Time: uma pessoa abre a pagina de jogos da liga no navegador,
seleciona a tabela, copia e cola num .txt desta pasta. Este script so le
esses arquivos.

Formato do arquivo (ver hampshire.txt):

    # fonte: <link da pagina de jogos no Full-Time>
    # condado: Hampshire
    # competicao: <nome no Full-Time> = <nome no mapa> | step <N>
    # colado em: 2026-10-12
    <tabela colada: uma linha por jogo, colunas separadas por tab>

Cada linha colada: Tipo | Data/hora (dd/mm/aa hh:mm) | Mandante | VS |
Visitante | Local | Competicao | Status. O navegador poe colunas vazias em
volta do "VS"; o parser ignora. Competicao sem linha "# competicao:" vira
copa (sem nivel), com o patrocinador ("uhlsport ") tirado do nome.

O que o script faz, em cada execucao (idempotente):
- grava os jogos em data/reino_unido/ pela regra normal (reino_unido_comum.salvar);
- tira do NonLeagueHQ os jogos da mesma competicao/temporada que vieram do
  Full-Time (os nomes dos times diferem, ex.: "US Portsmouth" x "United
  Services Portsmouth", entao a comparacao e aproximada). O NonLeagueHQ so
  tem a data; o Full-Time tem horario e campo.

Roda tambem no workflow do NonLeagueHQ, depois do merge, para que a coleta
diaria nao traga de volta os jogos duplicados.

Uso:
    python importar_fulltime_colado.py
    python importar_fulltime_colado.py --dry-run
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
from datetime import date
from pathlib import Path

from reino_unido_comum import (
    INGLATERRA, OUT_DIR, UK_DIR, Jogo, dedup_rows, load_csv_rows, load_json_rows, salvar, write_csv,
)

PASTA = UK_DIR / "fulltime_colado"
RAW_JOGOS = OUT_DIR / "debug_fulltime_colado_raw.json"
RAW_HISTORICO = OUT_DIR / "debug_fulltime_colado_hist_raw.json"
FONTE = "Full-Time"

DATA_HORA_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{2,4})(?:\s+(\d{1,2}):(\d{2}))?$")
META_RE = re.compile(r"^#\s*([a-z ]+?)\s*:\s*(.+)$", re.I)
COMP_RE = re.compile(r"^(.+?)\s*=\s*(.+?)(?:\s*\|\s*step\s*(\d+))?$", re.I)
PATROCINIO_RE = re.compile(r"^uhlsport\s+", re.I)
STATUS = {"postponed": "Adiado", "cancelled": "Cancelado", "canceled": "Cancelado", "abandoned": "Cancelado"}


def temporada(d: date) -> str:
    ini = d.year if d.month >= 7 else d.year - 1
    return f"{ini}-{str(ini + 1)[2:]}"


def ler_arquivo(path: Path) -> tuple[dict, list[dict], list[str]]:
    meta: dict = {"fonte": "", "condado": "", "competicoes": {}}
    jogos: list[dict] = []
    ignoradas: list[str] = []
    for n, linha in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not linha.strip():
            continue
        if linha.lstrip().startswith("#"):
            m = META_RE.match(linha.strip())
            if not m:
                continue
            k, v = m.group(1).lower(), m.group(2).strip()
            if k == "fonte":
                meta["fonte"] = v
            elif k == "condado":
                meta["condado"] = v
            elif k == "competicao":
                mc = COMP_RE.match(v)
                if mc:
                    meta["competicoes"][mc.group(1).strip()] = (mc.group(2).strip(), int(mc.group(3)) if mc.group(3) else None)
            continue

        cel = [c.strip() for c in linha.split("\t")]
        if "VS" not in [c.upper() for c in cel]:
            ignoradas.append(f"{path.name}:{n}: sem coluna VS (a linha foi colada sem tabs?)")
            continue
        i_vs = [c.upper() for c in cel].index("VS")
        antes = [c for c in cel[:i_vs] if c]
        depois = [c for c in cel[i_vs + 1:] if c]
        dh = next((DATA_HORA_RE.match(c) for c in antes if DATA_HORA_RE.match(c)), None)
        if not dh or len(antes) < 2 or len(depois) < 3:
            ignoradas.append(f"{path.name}:{n}: colunas inesperadas")
            continue
        dia, mes, ano = int(dh.group(1)), int(dh.group(2)), int(dh.group(3))
        ano += 2000 if ano < 100 else 0
        jogos.append({
            "tipo": antes[0] if not DATA_HORA_RE.match(antes[0]) else "",
            "data": date(ano, mes, dia),
            "hora": f"{int(dh.group(4)):02d}:{dh.group(5)}" if dh.group(4) else "",
            "mandante": antes[-1],
            "visitante": depois[0],
            "local": depois[1],
            "competicao_ft": depois[2],
            "status": depois[3] if len(depois) > 3 else "",
        })
    return meta, jogos, ignoradas


def montar(j: dict, meta: dict) -> Jogo:
    nome, step = meta["competicoes"].get(j["competicao_ft"], (PATROCINIO_RE.sub("", j["competicao_ft"]), None))
    competicao = f"{INGLATERRA} - {nome}"
    chave = "|".join([competicao, temporada(j["data"]), j["mandante"], j["visitante"]])
    extra = [f"codigo_ftc={hashlib.sha1(chave.encode('utf-8')).hexdigest()[:12]}"]
    st = STATUS.get(j["status"].lower())
    extra.append(f"status={st}" if st else "status=Programado")
    if step:
        extra.append(f"step={step}")
    if meta["condado"]:
        extra.append(f"condado={meta['condado']}")
    if j["tipo"]:
        extra.append(f"tipo_ft={j['tipo']}")
    extra.append("colado_a_mao=1")
    return Jogo(
        fonte=FONTE,
        competicao=competicao,
        data=j["data"].isoformat(),
        hora=j["hora"],
        mandante=j["mandante"],
        visitante=j["visitante"],
        pais=INGLATERRA,
        estadio=j["local"],
        url=meta["fonte"],
        extra="; ".join(extra),
    )


def norm_time(nome: str) -> str:
    n = nome.lower().replace("&", " and ")
    n = re.sub(r"^us\b", "united services", n)
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = " ".join(t for t in n.split() if t not in {"fc", "afc"})
    return n


def parecido(a: str, b: str) -> bool:
    a, b = norm_time(a), norm_time(b)
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


def tirar_duplicatas_nlhq(rows: list[dict], ft: list[dict]) -> tuple[list[dict], int]:
    """Remove jogos do NonLeagueHQ que o Full-Time colado ja tem."""
    por_comp: dict[tuple, list[tuple[str, str]]] = {}
    for r in ft:
        por_comp.setdefault((r["competicao"], temporada(date.fromisoformat(r["data"]))), []).append((r["mandante"], r["visitante"]))
    out, tirados = [], 0
    for r in rows:
        if r.get("fonte") == "NonLeagueHQ" and r.get("data"):
            pares = por_comp.get((r.get("competicao"), temporada(date.fromisoformat(r["data"]))))
            if pares and any(parecido(r["mandante"], m) and parecido(r["visitante"], v) for m, v in pares):
                tirados += 1
                continue
        out.append(r)
    return out, tirados


def main() -> None:
    ap = argparse.ArgumentParser(description="Importa jogos colados do FA Full-Time")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    hoje = date.today()
    prog: list[Jogo] = []
    hist: list[Jogo] = []
    for path in sorted(PASTA.glob("*.txt")):
        meta, jogos, ignoradas = ler_arquivo(path)
        for msg in ignoradas[:10]:
            print(f"[WARN] {msg}")
        if not meta["fonte"]:
            print(f"[WARN] {path.name}: falta a linha '# fonte: <link>'")
        print(f"[INFO] {path.name}: {len(jogos)} jogos ({len(ignoradas)} linhas ignoradas)")
        for j in jogos:
            (prog if j["data"] >= hoje else hist).append(montar(j, meta))

    rows_prog = dedup_rows(prog)
    rows_hist = dedup_rows(hist)
    if args.dry_run:
        for r in rows_prog[:5]:
            print("   ", r["data"], r["hora"], r["competicao"], "|", r["mandante"], "x", r["visitante"], "@", r["estadio"])
        print(f"[dry-run] {len(rows_prog)} programados, {len(rows_hist)} passados; nada gravado")
        return

    RAW_JOGOS.write_text(json.dumps(rows_prog, ensure_ascii=False, indent=2), encoding="utf-8")
    RAW_HISTORICO.write_text(json.dumps(rows_hist, ensure_ascii=False, indent=2), encoding="utf-8")
    salvar(rows_prog, rows_hist)

    # Tira do NonLeagueHQ o que o Full-Time ja cobre (programados e historico).
    ft = rows_prog + rows_hist
    jogos_json = UK_DIR / "jogos_programados.json"
    p, t1 = tirar_duplicatas_nlhq(load_json_rows(jogos_json), ft)
    jogos_json.write_text(
        "[\n" + ",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in p) + "\n]\n",
        encoding="utf-8",
    )
    write_csv(UK_DIR / "jogos_programados.csv", p)
    h, t2 = tirar_duplicatas_nlhq(load_csv_rows(UK_DIR / "historico_jogos.csv"), ft)
    write_csv(UK_DIR / "historico_jogos.csv", h)
    print(f"[ok] Full-Time colado: {len(rows_prog)} programados, {len(rows_hist)} passados | "
          f"duplicatas do NonLeagueHQ removidas: {t1} programados, {t2} historico")


if __name__ == "__main__":
    main()
