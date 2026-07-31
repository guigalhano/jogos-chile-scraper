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


import re
import hashlib


def is_valid_row(row: dict) -> bool:
    if not (row.get("mandante") and row.get("visitante")):
        return False
    if row.get("fonte") == "CBF":
        # A CBF publica jogos de rodadas futuras com data/hora ainda "A
        # definir" (depende de TV/mando de campo). adicionar_brasil_jogos.py
        # já mantém esses jogos de propósito (ver in_window() lá), mas até
        # agora essa checagem aqui exigia "data" preenchida e descartava
        # essas linhas de volta bem no passo final do merge, depois do
        # reset -- ou seja, elas nunca chegavam a ser commitadas de fato.
        return True
    return bool(row.get("data"))


# Regex genérica: pega qualquer "codigo_xxx=valor" dentro do campo extra.
# A maioria dos scrapers grava um código de identificação estável da fonte
# original ali (codigo_espn, codigo_fbf, codigo_fferj, codigo_conmebol...).
CODIGO_GENERICO_RE = re.compile(r"codigo_(\w+)=([^;]+)")
JOGO_NUMERO_RE = re.compile(r"jogo_numero=([^;]+)")


def row_id(row: dict) -> str:
    """ID legado (hash de campo a campo), só usado como fallback quando não
    há nenhum código estável disponível no campo extra. NÃO inclui estádio,
    cidade nem rodada, porque esses três costumam ser corrigidos/preenchidos
    pela fonte depois da primeira coleta (ex.: 'Rodada 10' virando 'Ida' no
    PDF da CBF, ou 'Zona B' sumindo num evento seguinte da AFA), e se
    entrassem no hash o mesmo jogo ganharia um ID novo (e viraria uma linha
    duplicada) toda vez que esse dado mudasse. Times + data + hora +
    competição já bastam pra identificar o confronto de forma prática (duas
    equipes não jogam duas vezes entre si na mesma competição, no mesmo dia
    e horário).
    """
    raw = "|".join([
        row.get("fonte", ""), row.get("competicao", ""), row.get("data", ""),
        row.get("hora", ""), row.get("mandante", ""), row.get("visitante", ""),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def merge_key(row: dict) -> str:
    """Chave de identidade usada para decidir se duas linhas são 'o mesmo
    jogo'. Preferimos sempre um código estável da fonte original (que não
    muda quando estádio/horário/cidade são corrigidos depois):

    - FMF: precisa combinar codigo_fmf (a fase/divisão) + jogo_numero
      (o número do jogo dentro dela), porque codigo_fmf sozinho identifica
      só a divisão, não o confronto.
    - Demais fontes com algum "codigo_xxx=" no extra (ESPN, FBF, FFERJ,
      CONMEBOL, etc.): usa fonte + esse código.
    - Sem nenhum código disponível (ex.: PDFs da CBF, FES): cai no hash
      legado sem estádio/cidade.
    """
    extra = row.get("extra", "") or ""
    fonte = row.get("fonte", "")

    mc = CODIGO_GENERICO_RE.search(extra)
    if mc and mc.group(1) == "fmf":
        # codigo_fmf identifica só a fase/divisão, não o confronto, e
        # jogo_numero às vezes falha na extração (fica ausente numa coleta
        # e presente na outra), o que faria o mesmo jogo cair em duas
        # chaves diferentes. Times + data + hora + competição já bastam
        # pra identificar o confronto de forma confiável na FMF.
        return row_id(row)
    if mc:
        return f"{fonte}:{mc.group(1)}:{mc.group(2)}"

    return row_id(row)


def merge_rows(existing: list[dict], new_rows: list[dict]) -> list[dict]:
    by_key: dict[str, dict] = {}

    def put(r: dict) -> None:
        if not is_valid_row(r):
            return
        r["id"] = row_id(r)
        k = merge_key(r)
        prev = by_key.get(k)
        # Em caso de colisão (mesmo jogo, dado atualizado), mantém sempre a
        # linha mais recente pelo campo atualizado_em, não a última por
        # ordem de iteração.
        if prev is None or (r.get("atualizado_em", "") >= prev.get("atualizado_em", "")):
            by_key[k] = r

    for r in existing:
        put(r)
    for r in new_rows:
        put(r)
    return sorted(
        by_key.values(),
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
