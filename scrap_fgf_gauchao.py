#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper - Federação Gaúcha de Futebol (FGF) - Gauchão Série A 2026

Fonte: PDF "Tabela Detalhada" publicado numa notícia do site oficial
(fgf.com.br), formato de colunas bem definido:

    Nº DATA DIA_DA_SEMANA HORA LOCAL ESTÁDIO MANDANTE X VISITANTE TRANSMISSÃO
    1 10/jan SÁBADO 21:00 SANTA CRUZ DO SUL EUCALIPTOS AVENIDA X GRÊMIO Sportv e Premiere

Validado com o texto real do PDF (6 jogos de amostra, incluindo os casos em
que o "X" aparece colado ao time, ex. "MONSOONX INTERNACIONAL" — comum
quando o time termina e o separador "X" não tem espaço antes).

A URL do PDF muda a cada nova "tabela detalhada" publicada (mesmo padrão já
usado para Copa Paulista) — mantida manualmente em SEED_PDF_URL. Quando o
scraper parar de achar jogos novos, procure "fgf.com.br tabela detalhada
Gauchão <ano>" para achar o link atualizado.

Uso:
    python scrap_fgf_gauchao.py --once --dias 365 --dias-atras 30
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import pdfplumber

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

# Mantida manualmente - ver docstring acima.
SEED_PDF_URL = "https://www.fgf.com.br/public/uploads/noticias/69553f597d270-TABELA DETALHADA GAUCHÃO 2026.pdf"

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

MESES = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}

# Cidades que sediam jogos do Gauchão Série A 2026 (13 clubes participantes).
# Ordenado por comprimento decrescente para casar o prefixo mais específico
# primeiro (ex.: "novo hamburgo" antes de tentar algo mais curto).
CIDADES_RS = sorted([
    "santa cruz do sul", "porto alegre", "bage", "ijui", "caxias do sul",
    "santa maria", "erechim", "novo hamburgo", "sao jose do norte",
    "farroupilha", "gramado", "veranopolis", "passo fundo",
    "frederico westphalen", "pelotas", "lajeado", "santa cruz",
], key=len, reverse=True)

# Times do Gauchão Série A 2026, ordenado por comprimento (para casar
# "internacional sm" antes de "internacional" sozinho).
TIMES_GAUCHAO_A = sorted([
    "internacional sm", "internacional", "novo hamburgo", "sao jose",
    "sao luiz", "juventude", "avenida", "guarany", "gremio", "caxias",
    "monsoon", "ypiranga",
], key=len, reverse=True)

RODADA_HEADER_RE = re.compile(r"(\d{1,2})[ºª]\s*RODADA", re.IGNORECASE)

LINHA_JOGO_RE = re.compile(
    r"^(?P<num>\d{1,3})\s+"
    r"(?P<dia>\d{1,2})/(?P<mes>jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\s+"
    r"\S+\s+"  # dia da semana (SÁBADO, DOMINGO, ...)
    r"(?P<hora>\d{1,2}):(?P<minuto>\d{2})\s+"
    r"(?P<resto>.+)$",
    re.IGNORECASE,
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


def norm(value) -> str:
    value = unicodedata.normalize("NFD", clean_text(value))
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def fetch_pdf_text(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    partes = []
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        for page in pdf.pages:
            partes.append(page.extract_text() or "")
    return "\n".join(partes)


def parse_linha_jogo(linha: str, ano: int) -> dict | None:
    m = LINHA_JOGO_RE.match(clean_text(linha))
    if not m:
        return None

    mes_n = MESES.get(m.group("mes").lower())
    if not mes_n:
        return None
    try:
        data_iso = date(ano, mes_n, int(m.group("dia"))).isoformat()
    except ValueError:
        return None
    hora = f"{int(m.group('hora')):02d}:{m.group('minuto')}"

    resto = m.group("resto")
    resto_norm = norm(resto)

    cidade = ""
    resto_sem_cidade = resto
    for c in CIDADES_RS:
        if resto_norm.startswith(c):
            cidade = c.title()
            resto_sem_cidade = resto[len(c):].strip()
            break

    rn = norm(resto_sem_cidade)
    mandante = None
    estadio = ""
    resto2 = ""
    for time in TIMES_GAUCHAO_A:
        for sep in (f" {time} x ", f" {time}x "):
            idx = rn.find(sep)
            if idx != -1:
                estadio = clean_text(resto_sem_cidade[:idx])
                mandante = time.title()
                resto2 = resto_sem_cidade[idx + len(sep):].strip()
                break
        if mandante:
            break
    if not mandante:
        return None

    rn2 = norm(resto2)
    visitante = None
    transmissao = ""
    for time in TIMES_GAUCHAO_A:
        if rn2.startswith(time):
            visitante = time.title()
            transmissao = clean_text(resto2[len(time):])
            break
    if not visitante:
        return None

    if not estadio or normalize_a_definir(estadio):
        estadio = ""

    return {
        "data": data_iso, "hora": hora, "cidade": cidade, "estadio": estadio,
        "mandante": mandante, "visitante": visitante, "transmissao": transmissao,
    }


def normalize_a_definir(texto: str) -> bool:
    return norm(texto) in {"a definir", "por definir", ""}


def parse_fgf_gauchao(texto: str, url: str, competicao_nome: str, ano: int) -> list[Partido]:
    partidos: list[Partido] = []
    rodada_atual = ""

    for linha in texto.splitlines():
        m_rodada = RODADA_HEADER_RE.search(linha)
        if m_rodada:
            rodada_atual = f"Rodada {m_rodada.group(1)}"

        info = parse_linha_jogo(linha, ano)
        if not info:
            continue

        partidos.append(Partido(
            fonte="FGF",
            competicao=competicao_nome,
            data=info["data"],
            hora=info["hora"],
            mandante=info["mandante"],
            visitante=info["visitante"],
            estadio=info["estadio"],
            cidade=info["cidade"],
            rodada=rodada_atual,
            url=url,
            extra=f"transmissao: {info['transmissao']}" if info["transmissao"] else "",
        ))

    # A "rodada" impressa no cabeçalho de cada bloco de 6 colunas do PDF vem
    # antes dos jogos daquela rodada no texto extraído, mas o layout em
    # colunas pode fazer com que o cabeçalho real de cada jogo não seja o
    # imediatamente anterior no texto corrido. Como o número do jogo (col.
    # "Nº") já é sequencial e agrupado de 6 em 6 por rodada nas tabelas
    # vistas até agora, isso é usado como reforço: se não achou nenhum
    # cabeçalho de rodada antes de um jogo, deixa rodada="" (mais seguro
    # que adivinhar errado).
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
        print(f"[ERRO] Falha ao baixar/ler PDF do Gauchão: {e}", file=sys.stderr)
        return

    partidos = parse_fgf_gauchao(texto, args.url, "Gauchão Série A 2026", args.ano)
    na_janela = [p for p in partidos if in_window(p, desde, ate, args.incluir_passados)]

    print(f"[INFO] Gauchão: {len(partidos)} jogos extraídos, {len(na_janela)} na janela")
    for p in na_janela[:10]:
        print(f"  - {p.data} {p.hora} | {p.mandante} x {p.visitante} | {p.estadio} ({p.cidade}) | {p.rodada}")

    rows_new = [p.to_row() for p in na_janela]

    json_path = OUT_DIR / "jogos_programados.json"
    csv_path = OUT_DIR / "jogos_programados.csv"
    merged = merge_rows(load_json_rows(json_path), rows_new)
    json_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(csv_path, merged)

    print(f"\nGauchão adicionados/atualizados: {len(rows_new)}")
    print(f"Total no JSON após merge: {len(merged)}")


if __name__ == "__main__":
    main()
