#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper - Federação Gaúcha de Futebol (FGF) - unificado via páginas HTML

Substitui os scrapers baseados em PDF (scrap_fgf_gauchao.py e
scrap_fgf_gauchao_a2.py permanecem no repo, mas este é o caminho
recomendado daqui pra frente): lê diretamente
https://fgf.com.br/competicoes/profissional/{id}, que — ao contrário do que
se pensava inicialmente — é renderizado no servidor com dados reais (jogos,
datas, estádios), sem precisar de Playwright nem de PDF.

Cobre as 5 competições profissionais da FGF:
  23 = Gauchão (Série A1)
  24 = Gauchão Série A2
  25 = Gauchão Série B
  26 = Copa FGF
  27 = Recopa Gaúcha

FORMATO DO TEXTO (validado com conteúdo real da Copa FGF 2026):
    FINAL · Dom, 12/07 15:00 - Francisco Novelletto · 2 alterações · GRA · X · BRA · Sobre o jogo
    Dom, 19/07 11:00 - Bento Freitas · 2 alterações · BRA · X · GRA · Sobre o jogo

Os times aparecem como CÓDIGOS DE 3 LETRAS (ex.: GRA, BRA), não nome
completo — por isso este script mantém um dicionário best-effort de
código -> nome completo (TIMES_RS), com fallback para o próprio código
quando não reconhecido (mais seguro que adivinhar errado).

⚠️ NÃO totalmente validado ao vivo: o padrão foi confirmado para Copa FGF
(única competição com jogos futuros reais no momento em que este script foi
escrito — as demais ainda não haviam começado a temporada 2026). Rode
--debug-html na primeira vez para conferir se os códigos de time e o
regex continuam batendo para as outras competições.

Uso:
    python scrap_fgf_html.py --once --dias 365 --dias-atras 30 --debug-html
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
from bs4 import BeautifulSoup

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)
DEBUG_DIR = OUT_DIR / "debug_fgf_html"

BASE_URL = "https://fgf.com.br/competicoes/profissional"

COMPETICOES = {
    23: "Gauchão Série A1",
    24: "Gauchão Série A2",
    25: "Gauchão Série B",
    26: "Copa FGF",
    27: "Recopa Gaúcha",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
}

MESES_ABREV = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}

# Best-effort: código de 3 letras -> nome completo. Ampliar conforme forem
# aparecendo códigos novos nos outros campeonatos (rodar --debug-html e
# conferir data/debug_fgf_html/*.txt).
TIMES_RS = {
    "GRA": "Gramadense", "BRA": "Brasil-Pel", "GRE": "Grêmio",
    "INT": "Internacional", "JUV": "Juventude", "AVE": "Avenida",
    "SAJ": "São José", "GUA": "Guarany", "SAL": "São Luiz", "CAX": "Caxias",
    "NHA": "Novo Hamburgo", "MON": "Monsoon", "ISM": "Inter-SM",
    "YPI": "Ypiranga", "BAG": "Bagé",
}

# Âncora: "Dom, 12/07 15:00 - Francisco Novelletto" (dia da semana opcional
# antes da vírgula; hora opcional, "a definir" quando o jogo ainda não tem
# horário confirmado).
JOGO_HEADER_RE = re.compile(
    r"^(?:\w{3},?\s+)?(?P<dia>\d{1,2})/(?P<mes>\d{1,2})"
    r"(?:\s+(?P<hora>\d{1,2}):(?P<minuto>\d{2}))?"
    r"\s*[-–]\s*(?P<estadio>.+)$",
    re.IGNORECASE,
)

RODADA_RE = re.compile(r"(\d+)[ªa°]\s*RODADA|CLASSIFICAT[ÓO]RIA|SEMIFINAL|QUARTAS|FINAL", re.IGNORECASE)
SEPARADOR_X_RE = re.compile(r"^(?:\d+\s+)?X(?:\s+\d+)?$", re.IGNORECASE)


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


def clean_text(v) -> str:
    v = "" if v is None else str(v)
    return re.sub(r"\s+", " ", v.replace("\u00a0", " ")).strip()


def resolver_time(codigo: str) -> str:
    c = clean_text(codigo).upper()
    return TIMES_RS.get(c, codigo)


def fetch_page_tokens(url: str, debug_html: bool = False) -> list[str]:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    texto = soup.get_text("\n")
    if debug_html:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        fname = re.sub(r"[^a-zA-Z0-9]+", "_", url)[-100:] + ".txt"
        (DEBUG_DIR / fname).write_text(texto, encoding="utf-8")
    return [t.strip() for t in texto.split("\n") if t.strip()]


ANO_TITULO_RE = re.compile(r"\b(20[2-3]\d)\b")


def detectar_ano_pagina(tokens: list[str], ano_padrao: int) -> int:
    """A página mostra a temporada mais recente que já teve jogos (pode ser
    a atual OU a anterior, se a atual ainda não começou) — o título logo no
    topo (ex.: 'Gauchão Série A2  2025') diz qual é. Sem isso, corremos o
    risco de rotular partidas já disputadas de uma temporada passada como
    se fossem do ano corrente."""
    for tok in tokens[:60]:
        m = ANO_TITULO_RE.search(tok)
        if m:
            return int(m.group(1))
    return ano_padrao


def parse_competicao(tokens: list[str], url: str, competicao_nome: str, ano_padrao: int) -> list[Partido]:
    ano = detectar_ano_pagina(tokens, ano_padrao)
    partidos: list[Partido] = []
    rodada_atual = ""
    i = 0
    n = len(tokens)

    while i < n:
        tok = tokens[i]

        if RODADA_RE.search(tok) and len(tok) < 40:
            rodada_atual = clean_text(tok)
            i += 1
            continue

        m = JOGO_HEADER_RE.match(tok)
        if not m:
            i += 1
            continue

        mes = int(m.group("mes"))
        try:
            data_iso = date(ano, mes, int(m.group("dia"))).isoformat()
        except ValueError:
            i += 1
            continue
        hora = f"{int(m.group('hora')):02d}:{m.group('minuto')}" if m.group("hora") else ""
        estadio = clean_text(m.group("estadio"))

        # próximos tokens: opcional "N alterações", depois TIME1, "X", TIME2
        j = i + 1
        while j < n and re.match(r"^\d+\s+altera", tokens[j], re.IGNORECASE):
            j += 1

        if j + 2 < n and SEPARADOR_X_RE.match(tokens[j + 1].strip()):
            mandante_cod = tokens[j]
            visitante_cod = tokens[j + 2]
            placar = clean_text(tokens[j + 1])
            partidos.append(Partido(
                fonte="FGF",
                competicao=f"{competicao_nome} {ano}",
                data=data_iso,
                hora=hora,
                mandante=resolver_time(mandante_cod),
                visitante=resolver_time(visitante_cod),
                estadio=estadio,
                rodada=rodada_atual,
                url=url,
                extra=f"placar: {placar}" if placar.upper() != "X" else "",
            ))
            i = j + 3
            continue

        i += 1

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
    FIELDS = [
        "id", "fonte", "competicao", "data", "hora",
        "mandante", "visitante", "estadio", "rodada",
        "url", "extra", "atualizado_em", "pais", "cidade",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def update(ano: int, dias: int, dias_atras: int, incluir_passados: bool, debug_html: bool) -> None:
    hoje = date.today()
    desde = hoje - timedelta(days=dias_atras)
    ate = hoje + timedelta(days=dias)

    todos: list[Partido] = []
    for comp_id, nome in COMPETICOES.items():
        url = f"{BASE_URL}/{comp_id}"
        try:
            tokens = fetch_page_tokens(url, debug_html=debug_html)
        except Exception as e:
            print(f"[ERRO] {nome} ({url}): {e}", file=sys.stderr)
            continue
        jogos = parse_competicao(tokens, url, nome, ano)
        print(f"[{nome}] {len(jogos)} jogo(s) extraído(s)")
        todos.extend(jogos)

    todos = dedupe(todos)
    na_janela = [p for p in todos if in_window(p, desde, ate, incluir_passados)]
    print(f"\nTotal extraído: {len(todos)} | dentro da janela: {len(na_janela)}")

    rows_new = [p.to_row() for p in na_janela]

    json_path = OUT_DIR / "jogos_programados.json"
    csv_path = OUT_DIR / "jogos_programados.csv"
    merged = merge_rows(load_json_rows(json_path), rows_new)
    json_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(csv_path, merged)

    print(f"Total no JSON após merge: {len(merged)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--ano", type=int, default=2026)
    parser.add_argument("--dias", type=int, default=365)
    parser.add_argument("--dias-atras", type=int, default=30)
    parser.add_argument("--incluir-passados", action="store_true")
    parser.add_argument("--debug-html", action="store_true")
    args = parser.parse_args()

    update(
        ano=args.ano,
        dias=args.dias,
        dias_atras=args.dias_atras,
        incluir_passados=args.incluir_passados,
        debug_html=args.debug_html,
    )


if __name__ == "__main__":
    main()
