#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper Copa Paulista de Futebol (FPF)

Fonte: PDF de tabela publicado no site da FPF (futebolpaulista.com.br),
formato "JG RODADA NN HORÁRIO MANDANTE PLACAR VISITANTE LOCAL TV":

    001 17/jul - sex 19:30 MARÍLIA AC X GRÊMIO PRUDENTE Marília 2

O PDF também traz a lista de clubes participantes com suas cidades
("CLUBES PARTICIPANTES"), usada aqui para separar corretamente o nome do
time visitante da cidade-sede na mesma linha (evita que "GRÊMIO PRUDENTE
Marília 2" vire time="GRÊMIO PRUDENTE Marília" por engano).

A URL do PDF é específica de uma notícia (Repositorio/Noticia/<id>/<id>_0.pdf)
e muda a cada atualização da CBF/FPF — mantida manualmente em SEED_PDF_URL,
igual ao padrão já usado para os PDFs da CBF neste projeto.

Uso:
    python scrap_copa_paulista.py --dias 180 --dias-atras 30
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import pdfplumber
import io

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

# Mantida manualmente - ver docstring acima. Atualize buscando
# "Copa Paulista tabela detalhada <ano> pdf" ou olhando as notícias da FPF.
SEED_PDF_URL = "https://futebolpaulista.com.br/Repositorio/Noticia/32647/32647_0.pdf"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
    "Referer": "https://futebolpaulista.com.br/",
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

# "001 17/jul - sex 19:30 MARÍLIA AC X GRÊMIO PRUDENTE Marília 2"
LINHA_JOGO_RE = re.compile(
    r"^(?P<jg>\d{3})\s+"
    r"(?P<dia>\d{1,2})/(?P<mes>jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)"
    r"\s*-\s*\w{3}\s+"
    r"(?P<hora>\d{1,2}):(?P<minuto>\d{2})\s+"
    r"(?P<resto>.+)$",
    re.IGNORECASE,
)

RODADA_HEADER_RE = re.compile(r"^JG\s+RODADA\s+(\d+)", re.IGNORECASE)


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
    text_parts = []
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            text_parts.append(t)
    return "\n".join(text_parts)


CIDADES_CONHECIDAS = {
    "birigui", "lins", "presidente prudente", "marilia", "ribeirao preto",
    "bauru", "piracicaba", "araras", "sao paulo", "osasco", "jundiai",
    "indaiatuba", "santo andre", "taubate", "sao caetano do sul",
    "sao jose dos campos", "diadema", "sao bernardo do campo",
    "mogi das cruzes", "franca", "sorocaba", "campinas", "santos",
}


def extract_cidades_dos_clubes(texto: str) -> dict:
    """A seção 'CLUBES PARTICIPANTES' lista NOME COMPLETO + CIDADE por linha,
    ex.: 'MARÍLIA ATLÉTICO CLUBE MARÍLIA'. Como não há separador explícito,
    assume-se que a(s) última(s) palavra(s) maiúsculas repetidas no fim é a
    cidade quando ela também aparece como sufixo do nome (heurística simples:
    tenta the last 1-3 palavras como cidade, mantém a que fizer mais sentido
    ficando de fora do nome do clube)."""
    mapa = {}
    for linha in texto.splitlines():
        s = clean_text(linha)
        if not s or not s.isupper():
            continue
        ns = norm(s)
        for cidade in sorted(CIDADES_CONHECIDAS, key=lambda c: -len(c)):
            if ns.endswith(cidade) and ns != cidade:
                nome_time = clean_text(s[: -(len(cidade))]).rstrip()
                mapa[norm(nome_time)] = cidade.title()
                break
    return mapa


def resolver_cidade(nome_time: str, mapa_cidades: dict, cidade_fallback: str) -> str:
    key = norm(nome_time)
    if key in mapa_cidades:
        return mapa_cidades[key]
    # tenta por correspondência parcial (nomes abreviados na tabela de jogos
    # vs. nome completo no cabeçalho de clubes participantes)
    for k, cidade in mapa_cidades.items():
        if key in k or k in key:
            return cidade
    return cidade_fallback


def parse_copa_paulista(texto: str, url: str, competicao_nome: str, ano: int) -> list[Partido]:
    mapa_cidades = extract_cidades_dos_clubes(texto)
    partidos: list[Partido] = []
    rodada_atual = ""

    for linha in texto.splitlines():
        s = clean_text(linha)
        if not s:
            continue

        m_rodada = RODADA_HEADER_RE.match(s)
        if m_rodada:
            rodada_atual = f"Rodada {m_rodada.group(1)}"
            continue

        m = LINHA_JOGO_RE.match(s)
        if not m:
            continue

        dia = int(m.group("dia"))
        mes = MESES.get(m.group("mes").lower())
        if not mes:
            continue
        try:
            data_iso = date(ano, mes, dia).isoformat()
        except ValueError:
            continue

        hora = f"{int(m.group('hora')):02d}:{m.group('minuto')}"
        resto = m.group("resto")

        partes = re.split(r"\s+X\s+", resto, maxsplit=1, flags=re.IGNORECASE)
        if len(partes) != 2:
            continue
        mandante = clean_text(partes[0])

        # do lado direito, o último token costuma ser o código do canal de TV
        # (número); o que sobra depois de tirar isso é "visitante + cidade".
        direita = clean_text(partes[1])
        direita_sem_tv = re.sub(r"\s+\d+\s*$", "", direita).strip()

        cidade_mandante = resolver_cidade(mandante, mapa_cidades, "")

        # tenta separar visitante da cidade usando a lista completa de
        # cidades conhecidas como sufixo da string restante (não só as que
        # aparecem no cabeçalho de clubes participantes — o local do jogo
        # pode ser uma cidade diferente da sede oficial do time, ex.: um
        # time de Taubaté jogando em Diadema).
        visitante = direita_sem_tv
        cidade_jogo = cidade_mandante
        ns_direita = norm(direita_sem_tv)
        for cidade in sorted(CIDADES_CONHECIDAS, key=lambda c: -len(c)):
            if ns_direita.endswith(cidade) and ns_direita != cidade:
                visitante = clean_text(direita_sem_tv[: len(direita_sem_tv) - len(cidade)])
                cidade_jogo = cidade.title()
                break

        if not mandante or not visitante or len(mandante) > 60 or len(visitante) > 60:
            continue

        partidos.append(Partido(
            fonte="FPF",
            competicao=competicao_nome,
            data=data_iso,
            hora=hora,
            mandante=mandante,
            visitante=visitante,
            rodada=rodada_atual,
            url=url,
            cidade=cidade_jogo,
        ))

    return partidos


def in_window(p: Partido, desde: date, ate: date, incluir_passados: bool) -> bool:
    try:
        dt = date.fromisoformat(p.data)
    except Exception:
        return False
    return (incluir_passados or (desde <= dt <= ate)) and bool(p.hora)


def dedupe(rows: list[Partido]) -> list[Partido]:
    seen = set()
    out = []
    for p in rows:
        if p.id in seen:
            continue
        seen.add(p.id)
        out.append(p)
    return out


def load_json_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def load_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


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
        key=lambda r: (r.get("data", ""), r.get("hora", ""), r.get("competicao", ""), r.get("mandante", ""))
    )


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dias", type=int, default=180)
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
        print(f"[ERRO] Falha ao baixar/ler PDF da Copa Paulista: {e}", file=sys.stderr)
        return

    partidos = parse_copa_paulista(texto, args.url, "Brasil - FPF - Copa Paulista", today.year)
    partidos = [p for p in partidos if in_window(p, desde, ate, args.incluir_passados)]
    partidos = dedupe(partidos)

    print(f"[INFO] Copa Paulista: {len(partidos)} jogos extraídos e na janela")
    for p in partidos[:10]:
        print(f"  - {p.data} {p.hora} | {p.mandante} x {p.visitante} | {p.cidade} | {p.rodada}")

    rows_new = [p.to_row() for p in partidos]

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    merged_current = merge_rows(load_json_rows(current_json), rows_new)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    merged_history = merge_rows(load_csv_rows(history_csv), rows_new)
    write_csv(history_csv, merged_history)

    print(f"\nCopa Paulista adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")


if __name__ == "__main__":
    main()
