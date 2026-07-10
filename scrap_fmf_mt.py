#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper - Federação Mato-grossense de Futebol (FMF-MT) - via PDF de tabela

MOTIVO: as páginas de jogos ao vivo do site (fmfmt.com.br/pt/competicoes/*)
retornam erro 409 de forma consistente (confirmado em várias tentativas em
10/07/2026, mesmo depois de nova tentativa), mesmo com outras seções do
mesmo site (home, notícias, listagem de documentos) funcionando normalmente
- parece uma proteção específica desse caminho. As "Tabelas" em PDF,
publicadas em fmfmt.com.br/assets/uploads/*.pdf e listadas em
fmfmt.com.br/pt/conteudo/?q=10&sc=14, continuam acessíveis e têm os dados
completos (data, hora, mandante, placar quando já jogado, visitante,
estádio, cidade).

FORMATO DO PDF (confirmado via fetch manual em 10/07/2026, tabela do
Mato-grossense Sub-20 2026):
    02/06 - Ter  16:00  VILA AURORA  UNIÃO  Luthero Lopes  Rondonópolis
    10/06 - Qua  ACADEMIA  UIRAPURU  ...

Cada linha começa com "dd/mm - Dia" (dia da semana abreviado), seguido de
hora, os dois times, e opcionalmente estádio + cidade. Como o texto que sai
de PDF vira uma sequência corrida sem colunas bem separadas, o parser usa
um DICIONÁRIO FIXO dos principais clubes de Mato Grosso (por cima do texto
entre a hora e a próxima data) pra achar mandante/visitante, e uma lista de
cidades mato-grossenses pra achar a cidade no final da linha - mesmo
princípio já usado em scrap_fgf_gauchao.py (CIDADES_RS/TIMES_GAUCHAO_A) e
em scrap_afa_federal_a.py.

⚠️ A URL do PDF muda a cada nova tabela publicada (mesmo padrão do
scrap_fgf_gauchao.py) - mantida manualmente em SEED_PDF_URL. Quando o
scraper parar de achar jogos novos/atuais, procure em
https://fmfmt.com.br/pt/conteudo/?q=10&sc=14 (ou
"fmfmt.com.br tabela [Sub-20|2ª Divisão|Feminino] <ano>" no Google) pelo
PDF mais recente e atualize a constante.

⚠️ NÃO validado ao vivo com o scraper rodando de verdade (o sandbox onde
isso foi escrito não tem acesso de rede a fmfmt.com.br) - só a estrutura
foi conferida via fetch manual. O elenco de clubes em TIMES_MT/CIDADES_MT
foi montado com o que apareceu nas fontes consultadas (site oficial,
Wikipédia, ogol.com.br, bolaamarelafc.com) - times muito pequenos/novos
podem não estar cobertos ainda.

Uso:
    python scrap_fmf_mt.py --dias 90 --dias-atras 14 --debug-html
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import pdfplumber

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)
DEBUG_DIR = OUT_DIR / "debug_fmf_mt"

# Mantida manualmente - ver docstring acima. Tabela do Mato-grossense
# Sub-20 2026 (1ª fase, publicada com dados até jul/2026).
SEED_PDF_URL = "https://www.fmfmt.com.br/assets/uploads/178034216422.pdf?v=178035223738"
COMPETICAO_NOME = "Mato-grossense Sub-20"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
    "Referer": "https://fmfmt.com.br/",
}

FIELDS = [
    "id", "fonte", "competicao", "data", "hora", "pais", "cidade",
    "mandante", "visitante", "estadio", "rodada", "url", "extra", "atualizado_em",
]

DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]

# Times mato-grossenses conhecidos - aliases ordenados por comprimento
# decrescente pra casar o mais específico primeiro (ex.: "sorriso fc" antes
# de um "sorriso" mais genérico).
TIMES_MT = [
    ("Cuiabá", ["cuiaba"], "Cuiabá"),
    ("Dom Bosco", ["dom bosco"], "Cuiabá"),
    ("Mato Grosso EC", ["mato grosso ec"], "Cuiabá"),
    ("Paulistano", ["paulistano"], "Cuiabá"),
    ("Uirapuru", ["uirapuru"], "Cuiabá"),
    ("Atlético MT", ["atletico mt", "atletico matogrossense"], "Cuiabá"),
    ("Mixto", ["mixto"], "Cuiabá"),
    ("Academia", ["academia"], "Cuiabá"),
    ("União", ["uniao rondonopolis", "uniao"], "Rondonópolis"),
    ("Vila Aurora", ["vila aurora"], "Rondonópolis"),
    ("Rondonópolis EC", ["rondonopolis ec"], "Rondonópolis"),
    ("CEOV Operário", ["ceov operario", "ceov"], "Várzea Grande"),
    ("Várzea Grande EC", ["varzea grande"], "Várzea Grande"),
    ("Operário VG", ["operario vg", "operario"], "Várzea Grande"),
    ("Luverdense", ["luverdense"], "Lucas do Rio Verde"),
    ("Nova Mutum", ["nova mutum"], "Nova Mutum"),
    ("Sorriso FC", ["sorriso fc"], "Sorriso"),
    ("Sorriso EC", ["sorriso ec"], "Sorriso"),
    ("Sinop FC", ["sinop fc"], "Sinop"),
    ("AA Sinop", ["aa sinop"], "Sinop"),
    ("Sport Sinop", ["sport sinop"], "Sinop"),
    ("Cáceres", ["caceres"], "Cáceres"),
    ("Cacerense", ["cacerense"], "Cáceres"),
    ("Santa Cruz", ["santa cruz"], "Barra do Bugres"),
    ("Chapada", ["chapada"], "Chapada dos Guimarães"),
    ("Campo Novo", ["campo novo"], "Campo Novo do Parecis"),
    ("Parecis", ["parecis"], "Campo Novo do Parecis"),
    ("Primavera", ["primavera"], "Primavera do Leste"),
    ("Juventude (Primavera)", ["juventude primavera"], "Primavera do Leste"),
    ("Tangará EC", ["tangara ec"], "Tangará da Serra"),
    ("SC Tangará", ["sc tangara"], "Tangará da Serra"),
    ("Serra", ["serra mt", "serra"], "Tangará da Serra"),
    ("Juara", ["juara atletico", "uniao de juara", "juara"], "Juara"),
    ("Alta Floresta", ["alta floresta"], "Alta Floresta"),
    ("Nova Xavantina", ["nova xavantina"], "Nova Xavantina"),
    ("Nova Ubiratã", ["nova ubirata"], "Nova Ubiratã"),
    ("União Garimpeira", ["uniao garimpeira"], "Nortelândia"),
    ("União de Vera", ["uniao de vera"], "Vera"),
    ("Tubarão", ["tubarao"], "Rio Branco"),
    ("Diamantino", ["diamantino"], "Diamantino"),
    ("Grêmio Jaciara", ["gremio jaciara"], "Jaciara"),
    ("Uirapuru Campo Verde", ["uirapuru campo verde"], "Campo Verde"),
    ("Ação", ["acao"], "Cuiabá"),
    ("Araguaia", ["aa araguaia", "araguaia"], "Água Boa"),
    ("Pontes e Lacerda", ["pontes e lacerda"], "Pontes e Lacerda"),
]

CIDADES_MT = sorted({cidade for _, _, cidade in TIMES_MT}, key=len, reverse=True)

MESES_ABREV = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}

DATA_CURTA_RE = re.compile(
    r"(\d{1,2})/(\d{1,2})\s*-\s*(seg|ter|qua|qui|sex|sab|s[áa]b|dom)\w*",
    re.IGNORECASE,
)
DATA_LONGA_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
HORA_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")


def clean_text(v) -> str:
    v = "" if v is None else str(v)
    return re.sub(r"\s+", " ", v.replace("\u00a0", " ")).strip()


def norm(v) -> str:
    v = unicodedata.normalize("NFD", clean_text(v))
    v = "".join(c for c in v if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", v.lower()).strip()


_ALIAS_TO_IDX: dict[str, int] = {}
for _i, (_nome, _aliases, _cidade) in enumerate(TIMES_MT):
    for _a in [_nome] + _aliases:
        na = norm(_a)
        # não sobrescreve um alias já mapeado por um time diferente (evita
        # que um alias genérico demais roube de um mais específico já
        # cadastrado antes na lista)
        _ALIAS_TO_IDX.setdefault(na, _i)
_ALIASES_ORDENADOS = sorted(_ALIAS_TO_IDX.keys(), key=len, reverse=True)


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


def times_no_trecho(trecho: str) -> list[tuple[int, int]]:
    """Acha os times conhecidos dentro do trecho, na ordem em que aparecem
    (mesma técnica usada em scrap_afa_federal_a.py)."""
    ntrecho = norm(trecho)
    achados = []
    usado = [False] * len(ntrecho)
    for alias in _ALIASES_ORDENADOS:
        start = 0
        while True:
            pos = ntrecho.find(alias, start)
            if pos == -1:
                break
            if not any(usado[pos:pos + len(alias)]):
                for k in range(pos, pos + len(alias)):
                    usado[k] = True
                achados.append((pos, _ALIAS_TO_IDX[alias]))
            start = pos + len(alias)
    achados.sort(key=lambda x: x[0])
    return achados


def fetch_pdf_text(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    partes = []
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        for page in pdf.pages:
            partes.append(page.extract_text() or "")
    return "\n".join(partes)


def parse_fmf_mt(texto: str, url: str, ano: int) -> list[Partido]:
    partidos: list[Partido] = []
    linha_unica = clean_text(texto)

    # posições de cada ocorrência de data no texto inteiro, pra poder
    # cortar "daqui até a próxima data" como o trecho de um jogo.
    matches_data = list(DATA_CURTA_RE.finditer(linha_unica))
    for i, m in enumerate(matches_data):
        dia, mes = int(m.group(1)), int(m.group(2))
        try:
            data_iso = date(ano, mes, dia).isoformat()
        except ValueError:
            continue

        fim = matches_data[i + 1].start() if i + 1 < len(matches_data) else len(linha_unica)
        trecho = linha_unica[m.end():fim]

        m_hora = HORA_RE.search(trecho)
        if not m_hora:
            continue
        hora = f"{int(m_hora.group(1)):02d}:{m_hora.group(2)}"

        resto = trecho[m_hora.end():]
        achados = times_no_trecho(resto)
        if len(achados) < 2:
            continue
        idx_mandante = achados[0][1]
        idx_visitante = achados[1][1]
        if idx_mandante == idx_visitante:
            continue

        nome_m, _, cidade_m = TIMES_MT[idx_mandante]
        nome_v, *_ = TIMES_MT[idx_visitante]

        # cidade: procura o nome de cidade mato-grossense mais específico
        # que aparece depois do 2º time no trecho (geralmente logo após o
        # nome do estádio); se não achar, usa a cidade-sede do mandante.
        depois_times = resto[achados[1][0] + len(_ALIASES_ORDENADOS[0]):] if achados else resto
        cidade_achada = ""
        n_depois = norm(resto)
        for c in CIDADES_MT:
            if norm(c) in n_depois:
                cidade_achada = c
                break

        partidos.append(Partido(
            fonte="FMF-MT",
            competicao=f"Brasil - FMF-MT - {COMPETICAO_NOME}",
            data=data_iso,
            hora=hora,
            mandante=nome_m,
            visitante=nome_v,
            estadio="",
            cidade=cidade_achada or cidade_m,
            rodada="",
            url=url,
            extra="pais=Brasil; estado=Mato Grosso",
        ))

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
    parser.add_argument("--dias", type=int, default=90)
    parser.add_argument("--dias-atras", type=int, default=14)
    parser.add_argument("--incluir-passados", action="store_true")
    parser.add_argument("--pdf-url", default=SEED_PDF_URL)
    parser.add_argument("--ano", type=int, default=None)
    parser.add_argument("--debug-html", action="store_true")
    args = parser.parse_args()

    today = date.today()
    ano = args.ano or today.year
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    try:
        texto = fetch_pdf_text(args.pdf_url)
    except Exception as e:
        print(f"[ERRO] falha ao baixar/ler PDF {args.pdf_url}: {e}")
        return

    if args.debug_html:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        (DEBUG_DIR / "pdf_texto.txt").write_text(texto, encoding="utf-8")

    jogos = parse_fmf_mt(texto, args.pdf_url, ano)
    na_janela = [p for p in jogos if in_window(p, desde, ate, args.incluir_passados)]
    print(f"[OK] {COMPETICAO_NOME} | jogos={len(jogos)} | na janela={len(na_janela)}")

    rows_new = [p.to_row() for p in na_janela]

    (OUT_DIR / "debug_fmf_mt_raw.json").write_text(
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
    print(f"FMF-MT jogos válidos adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")


if __name__ == "__main__":
    main()
