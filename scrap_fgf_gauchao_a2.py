#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper - Federação Gaúcha de Futebol (FGF) - Gauchão Série A2 2026

Fonte: PDF "Tabela Básica" (ainda sem hora/estádio confirmados em todas as
rodadas — a "tabela detalhada" sai mais perto de cada rodada). Formato:

    1ª rodada – 1º ou 2/8 Brasil de Farroupilha x Aimoré
    10ª rodada (2 ou 3/09): Brasil-FAR x Esportivo – Estádio das Castanheiras
    5ª Rodada – 20/08 – 20 horas – União Frederiquense x Esportivo – Arena União

Validado com 6 linhas reais (de notícias que reproduzem a tabela por clube)
— 6/6 extraídas corretamente, incluindo os 3 formatos (sem hora/estádio, com
estádio, com hora+estádio) e o caso de datas alternativas ("1º ou 2/8").

Quando há duas datas possíveis ("D1 ou D2"), fica registrada a PRIMEIRA como
estimativa, marcada em `extra` como "data provisoria (Dx ou Dy)" — trate como
aproximada até a FGF publicar a tabela detalhada com a data definitiva.

Uso:
    python scrap_fgf_gauchao_a2.py --once --dias 365 --dias-atras 30
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import pdfplumber

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

# Mantida manualmente - ver docstring do scrap_fgf_gauchao.py sobre esse padrão.
SEED_PDF_URL = "https://fgf.com.br/public/uploads/uploads/6a4bf9a591fdatabela-basica-serie-a2---2026.pdf"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
    "Referer": "https://fgf.com.br/",
}

FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em", "pais", "cidade",
]

LINHA_RE = re.compile(
    r"^(?P<rodada>\d{1,2})[ªa°]\s*[Rr]odada\s*[–\-]?\s*"
    r"\(?(?:(?P<dia1>\d{1,2})º?\s+ou\s+)?(?P<dia2>\d{1,2})/(?P<mes>\d{1,2})\)?\s*"
    r"[:–\-]?\s*(?:(?P<hora>\d{1,2})\s*horas?\s*[–\-]?\s*)?"
    r"(?P<mandante>.+?)\s+[xX]\s+(?P<visitante>.+?)"
    r"(?:\s*[–\-]\s*(?P<estadio>[A-ZÀ-Úa-zà-ú0-9º°\.\s]+))?$"
)


@dataclass
class Partido:
    fonte: str
    competicao: str
    data: str
    hora: str
    mandante: str
    visitante: str
    estadio: str = ""
    rodada: str = ""
    url: str = ""
    extra: str = ""
    pais: str = "Brasil"
    cidade: str = ""

    @property
    def id(self) -> str:
        raw = "|".join([
            self.fonte, self.competicao, self.data, self.hora,
            self.mandante, self.visitante, self.estadio, self.rodada,
        ])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def to_row(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        d["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
        return d


def clean_text(value) -> str:
    value = "" if value is None else str(value)
    value = value.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", value).strip()


def fetch_pdf_text(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    partes = []
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        for page in pdf.pages:
            partes.append(page.extract_text() or "")
    return "\n".join(partes)


def parse_fgf_a2(texto: str, url: str, competicao_nome: str, ano: int) -> list[Partido]:
    partidos: list[Partido] = []
    for linha in texto.splitlines():
        s = clean_text(linha)
        if not s:
            continue
        m = LINHA_RE.match(s)
        if not m:
            continue

        mes = int(m.group("mes"))
        dia_provisorio = m.group("dia1") is not None
        dia = int(m.group("dia2"))
        try:
            data_iso = date(ano, mes, dia).isoformat()
        except ValueError:
            continue

        hora = f"{int(m.group('hora')):02d}:00" if m.group("hora") else ""
        mandante = clean_text(m.group("mandante"))
        visitante = clean_text(m.group("visitante"))
        estadio = clean_text(m.group("estadio") or "")

        if not mandante or not visitante or len(mandante) > 60 or len(visitante) > 60:
            continue

        extra = ""
        if dia_provisorio:
            extra = f"data provisoria ({m.group('dia1')} ou {m.group('dia2')}/{mes})"

        partidos.append(Partido(
            fonte="FGF",
            competicao=competicao_nome,
            data=data_iso,
            hora=hora,
            mandante=mandante,
            visitante=visitante,
            estadio=estadio,
            rodada=f"Rodada {m.group('rodada')}",
            url=url,
            extra=extra,
        ))

    return dedupe(partidos)


def dedupe(rows: list[Partido]) -> list[Partido]:
    seen = set()
    out = []
    for p in rows:
        if p.id in seen:
            continue
        seen.add(p.id)
        out.append(p)
    return out


def in_window(p: Partido, desde: date, ate: date, incluir_passados: bool) -> bool:
    try:
        dt = date.fromisoformat(p.data)
    except Exception:
        return False
    return incluir_passados or (desde <= dt <= ate)


def load_json_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
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


def merge_rows(existing: list[dict], new_rows: list[dict]) -> list[dict]:
    by_id = {}
    for r in existing:
        rid = row_id(r)
        r["id"] = rid
        by_id[rid] = r
    for r in new_rows:
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
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--ano", type=int, default=2026)
    parser.add_argument("--dias", type=int, default=365)
    parser.add_argument("--dias-atras", type=int, default=30)
    parser.add_argument("--incluir-passados", action="store_true")
    parser.add_argument("--url", default=SEED_PDF_URL)
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    try:
        texto = fetch_pdf_text(args.url)
    except Exception as e:
        print(f"[ERRO] Falha ao baixar/ler PDF do Gauchão A2: {e}", file=sys.stderr)
        return

    partidos = parse_fgf_a2(texto, args.url, "Gauchão Série A2 2026", args.ano)
    na_janela = [p for p in partidos if in_window(p, desde, ate, args.incluir_passados)]

    print(f"[INFO] Gauchão A2: {len(partidos)} jogos extraídos, {len(na_janela)} na janela")
    for p in na_janela[:10]:
        print(f"  - {p.data} {p.hora} | {p.mandante} x {p.visitante} | {p.estadio} | {p.rodada} | {p.extra}")

    rows_new = [p.to_row() for p in na_janela]

    (OUT_DIR / "debug_fgf_gauchao_a2_raw.json").write_text(
        json.dumps(rows_new, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    json_path = OUT_DIR / "jogos_programados.json"
    csv_path = OUT_DIR / "jogos_programados.csv"
    merged = merge_rows(load_json_rows(json_path), rows_new)
    json_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(csv_path, merged)

    print(f"\nGauchão A2 adicionados/atualizados: {len(rows_new)}")
    print(f"Total no JSON após merge: {len(merged)}")


if __name__ == "__main__":
    main()
