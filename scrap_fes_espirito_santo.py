#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper - Federação de Futebol do Estado do Espírito Santo (FES)
https://futebolcapixaba.com/

Site WordPress renderizado no servidor (sem JS necessário, ao contrário do
Futebol Nacional). Cada página de campeonato (ex.:
https://futebolcapixaba.com/campeonatos/estadual-serie-b-2026/) traz:

  1. Tabela(s) de classificação por chave/grupo.
  2. Uma ou mais tabelas de JOGOS por fase (ex.: "1ª Fase", "Semifinal",
     "Final"), cada uma com TODAS as rodadas da fase de uma vez só -
     diferente da FMF/FPF-PA, que só mostram a rodada atual.

Colunas da tabela de jogos: Data | Mandante | Horário/Resultado | Visitante
| Estádio | Rodada. A coluna Estádio já vem no formato "Nome do Estádio,
Cidade" (ex.: "Gil Bernardes, Vila Velha"), então dá pra extrair a cidade
direto daqui sem precisar de uma base separada.

Identificação da tabela de jogos: procura por <table> cujo cabeçalho
contenha tanto "Mandante" quanto "Visitante" (a tabela de classificação
tem cabeçalho diferente: Pos/Time/P/J/V/E/D/GP/GC/SG/CA/CV/%).

Datas: cada célula de data tem um link para /jogos/{slug}/; o texto
completo da célula mistura um timestamp tipo "2026-07-12 16:00:07" (usado
pela ordenação da tabela) com a data por extenso "12 de julho de 2026" -
o regex de data ISO já resolve isso sem precisar entender o HTML exato.

⚠️ NÃO validado ao vivo com o scraper de verdade rodando (o sandbox onde
isso foi escrito não tem acesso de rede a futebolcapixaba.com) - só a
estrutura do HTML/tabela foi conferida via fetch manual em 10/07/2026
(Estadual Série B 2026). Rodar com --debug-html na primeira execução real
e conferir data/debug_fes_html/ se os jogos não baterem.

Uso:
    python scrap_fes_espirito_santo.py --dias 240 --dias-atras 30 --debug-html
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)
DEBUG_DIR = OUT_DIR / "debug_fes_html"

BASE_URL = "https://futebolcapixaba.com"

# Campeonatos ativos da temporada 2026 listados em
# https://futebolcapixaba.com/campeonatos/ em 10/07/2026. Conferir e
# atualizar essa lista quando a FES abrir a temporada seguinte.
COMPETICOES = {
    "capixabao-2026": "Capixabão (Série A)",
    "estadual-serie-b-2026": "Estadual Série B",
    "copa-es-2026": "Copa ES",
    "estadual-sub-20-2026": "Estadual Sub 20",
    "estadual-sub-17-2026": "Estadual Sub 17",
    "estadual-sub-15-2026": "Estadual Sub 15",
    "estadual-sub-13-2026": "Estadual Sub 13",
    "estadual-sub-11-2026": "Estadual Sub 11",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
}

FIELDS = [
    "id", "fonte", "competicao", "data", "hora", "pais", "cidade",
    "mandante", "visitante", "estadio", "rodada", "url", "extra", "atualizado_em",
]

DATA_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):\d{2}")
HORA_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")


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


def fetch(url: str) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r


def is_jogos_table(table) -> bool:
    header_text = clean_text(table.get_text(" ", strip=True))[:200].lower()
    return "mandante" in header_text and "visitante" in header_text


def parse_data_cell(cell) -> str:
    txt = clean_text(cell.get_text(" ", strip=True))
    m = DATA_ISO_RE.search(txt)
    if not m:
        # também tenta em qualquer atributo (data-sort/data-order etc.) que
        # o BeautifulSoup exponha na própria célula ou em filhos.
        for tag in [cell] + cell.find_all(True):
            for attr_val in tag.attrs.values():
                if isinstance(attr_val, str):
                    m2 = DATA_ISO_RE.search(attr_val)
                    if m2:
                        m = m2
                        break
            if m:
                break
    if not m:
        return ""
    ano, mes, dia = m.group(1), m.group(2), m.group(3)
    try:
        return date(int(ano), int(mes), int(dia)).isoformat()
    except ValueError:
        return ""


def parse_hora_cell(cell) -> str:
    txt = clean_text(cell.get_text(" ", strip=True))
    matches = HORA_RE.findall(txt)
    if not matches:
        return ""
    hh, mm = matches[-1]  # a última ocorrência é o horário visível (a
    # primeira, se houver, tende a vir do timestamp de ordenação)
    return f"{int(hh):02d}:{mm}"


def parse_time_nome(cell) -> str:
    a = cell.find("a")
    if a:
        # remove o texto de imagens/alt, mantém só o texto visível do link
        txt = clean_text(a.get_text(" ", strip=True))
        if txt:
            return txt
    return clean_text(cell.get_text(" ", strip=True))


def parse_estadio_cidade(cell) -> tuple[str, str]:
    txt = clean_text(cell.get_text(" ", strip=True))
    if not txt:
        return "", ""
    if "," in txt:
        estadio, cidade = txt.rsplit(",", 1)
        return clean_text(estadio), clean_text(cidade)
    return txt, ""


def parse_competicao_page(html: str, competicao_nome: str, url: str, debug_html: bool, slug: str) -> list[Partido]:
    soup = BeautifulSoup(html, "html.parser")
    partidos: list[Partido] = []

    tables = [t for t in soup.find_all("table") if is_jogos_table(t)]
    for table in tables:
        # tenta achar um rótulo de fase a partir do heading mais próximo
        # anterior à tabela (ex.: "Estadual Série B 2026 – 1ª Fase").
        fase_label = ""
        heading = table.find_previous(["h1", "h2", "h3", "h4", "h5"])
        if heading:
            fase_label = clean_text(heading.get_text(" ", strip=True))

        header_cells = [clean_text(th.get_text(" ", strip=True)).lower() for th in table.find_all("th")]
        # localiza os índices das colunas pelo cabeçalho, com fallback pra
        # ordem padrão observada (Data, Mandante, Horário, Visitante,
        # Estádio, Rodada) se o cabeçalho não vier como <th>.
        col_idx = {"data": 0, "mandante": 1, "horario": 2, "visitante": 3, "estadio": 4, "rodada": 5}
        if header_cells:
            for i, h in enumerate(header_cells):
                if "data" in h:
                    col_idx["data"] = i
                elif "mandante" in h:
                    col_idx["mandante"] = i
                elif "hor" in h or "resultado" in h:
                    col_idx["horario"] = i
                elif "visitante" in h:
                    col_idx["visitante"] = i
                elif "est" in h:
                    col_idx["estadio"] = i
                elif "rodada" in h:
                    col_idx["rodada"] = i

        body = table.find("tbody") or table
        for tr in body.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 4:
                continue
            try:
                data_iso = parse_data_cell(cells[col_idx["data"]])
                hora = parse_hora_cell(cells[col_idx["horario"]]) if col_idx["horario"] < len(cells) else ""
                mandante = parse_time_nome(cells[col_idx["mandante"]]) if col_idx["mandante"] < len(cells) else ""
                visitante = parse_time_nome(cells[col_idx["visitante"]]) if col_idx["visitante"] < len(cells) else ""
                estadio, cidade = ("", "")
                if col_idx["estadio"] < len(cells):
                    estadio, cidade = parse_estadio_cidade(cells[col_idx["estadio"]])
                rodada = clean_text(cells[col_idx["rodada"]].get_text(" ", strip=True)) if col_idx["rodada"] < len(cells) else ""
            except IndexError:
                continue

            if not (mandante and visitante and data_iso):
                continue
            if mandante == visitante:
                continue

            partidos.append(Partido(
                fonte="FES",
                competicao=f"Brasil - FES - {competicao_nome}",
                data=data_iso,
                hora=hora,
                mandante=mandante,
                visitante=visitante,
                estadio=estadio,
                cidade=cidade,
                rodada=rodada or fase_label,
                url=url,
                extra=f"pais=Brasil; estado=Espírito Santo; competicao_slug={slug}",
            ))

    if debug_html:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        (DEBUG_DIR / f"fes_{slug}.html").write_text(html, encoding="utf-8")

    return partidos


def scrape_competicao(slug: str, nome: str, debug_html: bool) -> list[Partido]:
    url = f"{BASE_URL}/campeonatos/{slug}/"
    try:
        r = fetch(url)
    except Exception as e:
        print(f"[ERRO] {nome} ({slug}): {e}")
        return []
    partidos = parse_competicao_page(r.text, nome, url, debug_html, slug)
    # dedupe (pode haver tabelas repetidas/sobrepostas na mesma página)
    seen = set()
    out = []
    for p in partidos:
        if p.id in seen:
            continue
        seen.add(p.id)
        out.append(p)
    return out


def in_window(p: Partido, desde: date, ate: date, incluir_passados: bool) -> bool:
    if not p.data:
        return False
    try:
        dt = date.fromisoformat(p.data)
    except Exception:
        return False
    return incluir_passados or (desde <= dt <= ate)


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--dias", type=int, default=240)
    parser.add_argument("--dias-atras", type=int, default=30)
    parser.add_argument("--incluir-passados", action="store_true")
    parser.add_argument("--somente-slug", action="append", default=[])
    parser.add_argument("--debug-html", action="store_true")
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    competicoes = COMPETICOES
    if args.somente_slug:
        wanted = set(args.somente_slug)
        competicoes = {k: v for k, v in COMPETICOES.items() if k in wanted}

    all_partidos: list[Partido] = []
    print(f"[INFO] FES competições a varrer: {len(competicoes)}")
    for slug, nome in competicoes.items():
        jogos = scrape_competicao(slug, nome, args.debug_html)
        na_janela = [p for p in jogos if in_window(p, desde, ate, args.incluir_passados)]
        all_partidos.extend(na_janela)
        print(f"[OK] {nome} ({slug}) | jogos={len(jogos)} | na janela={len(na_janela)}")

    rows_new = [p.to_row() for p in all_partidos]

    (OUT_DIR / "debug_fes_raw.json").write_text(
        json.dumps(rows_new, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    merged_current = merge_rows(load_json_rows(current_json), rows_new)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    merged_history = merge_rows(load_csv_rows(history_csv), rows_new)
    write_csv(history_csv, merged_history)

    print("")
    print(f"FES jogos válidos adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")
    if args.debug_html:
        print("Debug HTML: data/debug_fes_html/")


if __name__ == "__main__":
    main()
