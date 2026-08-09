#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adiciona os jogos do Campeonato Cearense Série C 2026 (FCF - Federação
Cearense de Futebol) ao dataset, seguindo o MESMO schema/campos usados
pelo scraper da FMF (scrap_fmf_competicoes_playwright_seguro.py):

    id, fonte, competicao, data, hora, pais, cidade, mandante, visitante,
    estadio, rodada, url, extra, atualizado_em

Fonte dos dados: PDF oficial "CAMPEONATO CEARENSE SÉRIE C - TABELA
DETALHADA / EDIÇÃO 2026" (FCF), emissão 08/06/2026, atualização 07/08/2026.

Jogos da 2ª fase (semifinal) e 3ª fase (final) ainda não têm mandante/
visitante definidos (ex.: "1º Colocado do Gr. A") e por isso NÃO são
incluídos aqui — serão adicionados quando a tabela detalhada os definir.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "pais", "cidade", "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em",
]

FONTE = "FCF"
COMPETICAO = "Brasil - Ceará - Cearense Série C 2026"
URL_FONTE = "https://futebolcearense.com.br/2020/tabela.asp?idcamp=428"
ANO = 2026


@dataclass
class Partido:
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


def dm(txt: str) -> str:
    """Converte 'dd/mm' (ano 2026) para ISO 'YYYY-MM-DD'."""
    dia, mes = txt.split("/")
    return date(ANO, int(mes), int(dia)).isoformat()


# REF, Rodada, Data(dd/mm), Hora, Mandante, Visitante, Estadio, Cidade, Placar(ou "" se ainda não jogado)
JOGOS_PRIMEIRA_FASE = [
    ("02", "1", "25/07", "17:00", "Vila Real", "Esporte Limoeiro", "Junco", "Sobral", "0 x 0"),
    ("03", "1", "26/07", "15:30", "Calouros do Ar", "Palmácia", "Raimundo de Oliveira", "Caucaia", "1 x 0"),
    ("01", "1", "27/07", "19:00", "FC Acopiara", "Pacatuba", "Morenão", "Iguatu", "0 x 0"),
    ("04", "2", "01/08", "15:00", "Pacatuba", "Vila Real", "Perilo Teixeira", "Itapipoca", "1 x 1"),
    ("05", "2", "02/08", "16:00", "Esporte Limoeiro", "Tianguá", "Bandeirão", "Limoeiro do Norte", "1 x 0"),
    ("06", "2", "02/08", "15:00", "Palmácia", "FC Acopiara", "Presidente Vargas", "Fortaleza", "2 x 3"),
    ("08", "3", "08/08", "17:00", "Vila Real", "Palmácia", "Junco", "Sobral", ""),
    ("09", "3", "10/08", "19:00", "FC Acopiara", "Calouros do Ar", "Morenão", "Iguatu", ""),
    ("07", "3", "11/08", "15:00", "Tianguá", "Pacatuba", "Junco", "Sobral", ""),
    ("10", "4", "15/08", "15:00", "Pacatuba", "Esporte Limoeiro", "Perilo Teixeira", "Itapipoca", ""),
    ("11", "4", "15/08", "15:30", "Calouros do Ar", "Vila Real", "Raimundo de Oliveira", "Caucaia", ""),
    ("12", "4", "18/08", "15:00", "Palmácia", "Tianguá", "Presidente Vargas", "Fortaleza", ""),
    ("14", "5", "22/08", "17:00", "Vila Real", "FC Acopiara", "Junco", "Sobral", ""),
    ("13", "5", "23/08", "16:00", "Esporte Limoeiro", "Palmácia", "Bandeirão", "Limoeiro do Norte", ""),
    ("15", "5", "23/08", "15:00", "Tianguá", "Calouros do Ar", "Tancredão*", "Tianguá", ""),
    ("17", "6", "29/08", "15:30", "Calouros do Ar", "Esporte Limoeiro", "Raimundo de Oliveira", "Caucaia", ""),
    ("18", "6", "31/08", "19:00", "FC Acopiara", "Tianguá", "Morenão", "Iguatu", ""),
    ("16", "6", "01/09", "15:00", "Palmácia", "Pacatuba", "Presidente Vargas", "Fortaleza", ""),
    ("19", "7", "06/09", "16:00", "Pacatuba", "Calouros do Ar", "Raimundo de Oliveira", "Caucaia", ""),
    ("20", "7", "06/09", "16:00", "Esporte Limoeiro", "FC Acopiara", "Bandeirão", "Limoeiro do Norte", ""),
    ("21", "7", "06/09", "16:00", "Tianguá", "Vila Real", "Tancredão*", "Tianguá", ""),
]


def build_partidos() -> list[Partido]:
    out = []
    for ref, rodada, data_txt, hora, mandante, visitante, estadio, cidade, placar in JOGOS_PRIMEIRA_FASE:
        extra = [
            "idcamp=428", "fase=1a_fase", "grupo=A", "jogo_ref=" + ref,
            "fonte_dado=tabela_oficial_fcf_pdf_08-06-2026",
        ]
        if placar:
            extra.append(f"placar={placar}")
        out.append(Partido(
            fonte=FONTE,
            competicao=COMPETICAO,
            data=dm(data_txt),
            hora=hora,
            mandante=mandante,
            visitante=visitante,
            pais="Brasil",
            cidade=cidade,
            estadio=estadio,
            rodada=f"RODADA {rodada}",
            url=URL_FONTE,
            extra="; ".join(extra),
        ))
    return out


def row_id(row: dict) -> str:
    if row.get("id"):
        return row["id"]
    raw = "|".join([
        row.get("fonte", ""), row.get("competicao", ""), row.get("data", ""),
        row.get("hora", ""), row.get("mandante", ""), row.get("visitante", ""),
        row.get("estadio", ""), row.get("rodada", ""),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def is_valid_row(row: dict) -> bool:
    return bool(row.get("data") and row.get("mandante") and row.get("visitante"))


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
    partidos = build_partidos()
    rows_new = [p.to_row() for p in partidos]

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    merged_current = merge_rows(load_json_rows(current_json), rows_new)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    merged_history = merge_rows(load_csv_rows(history_csv), rows_new)
    write_csv(history_csv, merged_history)

    print(f"Jogos do Cearense Série C adicionados/atualizados: {len(rows_new)}")
    print(f"Total no JSON atual: {len(merged_current)}")


if __name__ == "__main__":
    main()
