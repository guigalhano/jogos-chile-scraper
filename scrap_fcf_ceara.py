#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper - Federação Cearense de Futebol (FCF) - https://futebolcearense.com.br/

Site legado em ASP clássico (não é SPA/React como FMF ou FPF-SP), então os
jogos vêm renderizados direto no HTML, sem precisar de Playwright - dá pra
usar requests + BeautifulSoup puro, como no FPF-PA.

⚠️ Confirmado ao vivo em 17/07/2026 que a homepage.asp carrega normal e traz
jogos embutidos direto no HTML, mas a página tabela.asp?idcamp=NNN (que
deveria ter a lista completa de jogos de uma competição) deu TIMEOUT
repetido no ambiente onde este script foi escrito - sinal de página pesada/
lenta no servidor da FCF, não de SPA. Por isso o timeout do requests aqui é
bem mais generoso (60s) que o padrão do projeto, com retry. Como a estrutura
exata de tabela.asp não pôde ser confirmada ao vivo, o parser usa o mesmo
método de texto-puro (BeautifulSoup get_text + regex) já usado com sucesso
na FMF-MG e na FPF-PA, que é resiliente a variações de HTML - mas rode com
--debug-html na primeira vez e confira data/debug_fcf_ceara_html/*.txt se os
jogos não baterem.

Padrão de URL confirmado (visto ao vivo na navegação do site):
    https://futebolcearense.com.br/2020/campeonatos.asp        -> lista as competições atuais
    https://futebolcearense.com.br/2020/tabela.asp?idcamp=NNN  -> jogos de uma competição

O "idcamp" muda toda temporada, então este script primeiro tenta descobrir
os IDs atuais direto na página de campeonatos (como já é feito no
discover_urls() da FMF-MG); os IDs abaixo em COMPETICOES_FALLBACK são só um
ponto de partida caso a descoberta automática falhe, confirmados ao vivo em
17/07/2026:
    - Série A e Série B do Cearense 2026 JÁ TERMINARAM em março/2026 (final
      Ceará x Fortaleza em 1º e 8/03) - por isso não aparecem mais no menu
      de competições "atuais" da home. Vão reaparecer só no início de 2027.
    - A competição profissional em andamento agora é a Série C 2026
      (idcamp=428, início confirmado em 25/07/2026).
    - O resto do menu atual é só categorias de base (Sub-20, Sub-17,
      Sub-14, Sub-12, Manjadinho/Manjadinha Cariri).

Uso:
    python scrap_fcf_ceara.py --dias 365 --dias-atras 30 --debug-html
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)
DEBUG_DIR = OUT_DIR / "debug_fcf_ceara_html"

BASE = "https://futebolcearense.com.br/2020"
CAMPEONATOS_URL = f"{BASE}/campeonatos.asp"
HOMEPAGE_URL = f"{BASE}/homepage.asp"

# Ponto de partida caso a descoberta automática em campeonatos.asp falhe
# (ex.: mudança de layout). Confirmado ao vivo em 17/07/2026 - ver nota no
# cabeçalho sobre por que Série A/B não estão aqui.
COMPETICOES_FALLBACK: dict[str, str] = {
    "428": "Cearense Série C 2026",
    "427": "Cearense Masculino Sub/20 2026",
    "426": "Cearense Masculino Sub/17 2026",
    "430": "Cearense Manjadinho Sub/14 2026",
    "429": "Cearense Manjadinho Sub/12 2026",
    "431": "Cearense Manjadinho Sub/15 - Cariri 2026",
    "432": "Cearense Manjadinha Sub/15 - Cariri 2026",
}

FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "pais", "cidade", "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

MESES = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}

DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
SCORE_RE = re.compile(r"^\s*(\d+)\s*[-x]\s*(\d+)\s*$", re.I)
IDCAMP_RE = re.compile(r"idcamp=(\d+)", re.I)


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
    estado: str = "Ceará"
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
        d.pop("estado", None)
        d["id"] = self.id
        d["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
        return d


def clean_text(x: Any) -> str:
    x = "" if x is None else str(x)
    x = x.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", x).strip()


def norm(x: Any) -> str:
    x = unicodedata.normalize("NFD", clean_text(x))
    x = "".join(c for c in x if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", x.lower()).strip()


BAD_NAMES = {
    "federacao cearense de futebol", "fcf", "site oficial",
    "resumo", "sumula", "boletim", "arbitragem", "pga", "ver mais",
}


def is_bad_name(x: str) -> bool:
    s = norm(x)
    if not s or s in BAD_NAMES:
        return True
    if len(clean_text(x)) > 60:
        return True
    return False


def fetch(url: str, timeout: int, tentativas: int = 2) -> str | None:
    for i in range(tentativas):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except Exception as e:
            print(f"[WARN] fetch {url} (tentativa {i + 1}/{tentativas}): {e}")
            if i < tentativas - 1:
                time.sleep(3)
    return None


MAX_COMPETICOES = 12  # rede de segurança: nunca processa mais que isso numa rodada


def descobrir_competicoes(timeout: int) -> dict[str, str]:
    """Busca as competições atuais. Usa SÓ homepage.asp (confirmado ao vivo
    em 17/07/2026 que ela lista as ~7 competições ATUAIS, uma por card).
    NÃO usa campeonatos.asp: essa página parece listar o arquivo histórico
    completo de competições (muitos anos), o que fez uma rodada real travar
    por quase 1h tentando dezenas de idcamp - um bug descoberto ao vivo, não
    hipotético. Se a home não trouxer nada, cai pro fallback hardcoded (não
    tenta campeonatos.asp como segundo recurso, pelo mesmo motivo)."""
    encontrados: dict[str, str] = {}

    html = fetch(HOMEPAGE_URL, timeout)
    if html:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = IDCAMP_RE.search(href)
            if not m:
                continue
            idcamp = m.group(1)
            nome = clean_text(a.get_text(" ", strip=True)) or f"Campeonato {idcamp}"
            if idcamp not in encontrados:
                encontrados[idcamp] = nome

    if not encontrados:
        print("[WARN] não achei nenhum idcamp na home - usando fallback hardcoded")
        return dict(COMPETICOES_FALLBACK)

    if len(encontrados) > MAX_COMPETICOES:
        print(f"[WARN] {len(encontrados)} competições encontradas na home (> {MAX_COMPETICOES}) - "
              f"cortando pra não travar a rodada; algo mudou no site, confirmar manualmente")
        encontrados = dict(list(encontrados.items())[:MAX_COMPETICOES])

    return encontrados


def parse_jogos_da_pagina(html: str, idcamp: str, nome_competicao: str) -> list[Partido]:
    """Parser genérico de texto puro (mesmo princípio da FMF-MG e da
    FPF-PA): varre as linhas de texto renderizado procurando o padrão
    'Estádio: X ... DD/MM/AAAA - HH:MM ... TimeA ... placar ... TimeB'."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    out: list[Partido] = []
    url = f"{BASE}/tabela.asp?idcamp={idcamp}"

    # Estratégia 1: blocos de link "Estádio: ... TimeA TimeA score - score TimeB TimeB"
    # (formato confirmado no widget "Jogos Anteriores" da homepage - a
    # tabela.asp provavelmente usa um formato parecido ou uma tabela HTML
    # tradicional; os dois são cobertos pela varredura de texto abaixo).
    for a in soup.find_all("a"):
        texto = clean_text(a.get_text(" ", strip=True))
        if "estádio" not in texto.lower() and "estadio" not in texto.lower():
            continue
        p = parse_bloco_texto(texto, url, idcamp, nome_competicao)
        if p:
            out.append(p)

    if out:
        return out

    # Estratégia 2 (fallback): varre linha a linha o texto da página
    # inteira, tratando cada <tr> ou bloco de texto isolado como uma
    # unidade candidata a "bloco de jogo".
    candidatos: list[str] = []
    for tr in soup.find_all("tr"):
        t = clean_text(tr.get_text(" ", strip=True))
        if t:
            candidatos.append(t)
    if not candidatos:
        for raw in soup.get_text("\n", strip=True).splitlines():
            t = clean_text(raw)
            if t and len(t) < 300:
                candidatos.append(t)

    for texto in candidatos:
        p = parse_bloco_texto(texto, url, idcamp, nome_competicao)
        if p:
            out.append(p)

    return out


def parse_bloco_texto(texto: str, url: str, idcamp: str, nome_competicao: str) -> Partido | None:
    m_date = DATE_RE.search(texto)
    m_time = TIME_RE.search(texto)
    if not m_date:
        return None
    dia, mes, ano = m_date.groups()
    try:
        data_iso = date(int(ano), int(mes), int(dia)).isoformat()
    except Exception:
        return None
    hora = f"{m_time.group(1).zfill(2)}:{m_time.group(2)}" if m_time else ""

    estadio = ""
    m_est = re.search(r"Estádio:\s*([^\d]+?)(?:Segunda|Terça|Quarta|Quinta|Sexta|Sábado|Domingo|\d{1,2}/\d{1,2}/\d{4})", texto, re.I)
    if m_est:
        estadio = clean_text(m_est.group(1))

    # Depois de tirar "Estádio: X <dia da semana>, DD/MM/AAAA - HH:MM ",
    # sobra algo como "TimeATimeAscore - score TimeBTimeB" (nomes
    # duplicados por causa do <img alt> + texto do link, típico desse
    # tipo de widget). Isolamos o trecho entre a hora e o fim.
    resto = texto
    if m_time:
        resto = texto[m_time.end():]
    resto = clean_text(resto)

    m_placar = re.search(r"(\d+)\s*-\s*(\d+)", resto)
    times_texto = resto
    if m_placar:
        antes = resto[:m_placar.start()]
        depois = resto[m_placar.end():]
        mandante = _dedup_nome(antes)
        visitante = _dedup_nome(depois)
    else:
        # Ainda não jogado: não tem placar, só "TimeATimeAVSTimeBTimeB" ou
        # "TimeATimeA VS TimeBTimeB". Sem exigir \b antes de "VS": o site
        # às vezes concatena o nome do time direto com "VS" sem espaço
        # (ex.: "FPIVS PSV"), o que quebraria um \bVS\b.
        m_vs = re.search(r"(.+?)VS(.+)", resto)
        if not m_vs:
            return None
        mandante = _dedup_nome(m_vs.group(1))
        visitante = _dedup_nome(m_vs.group(2))

    if not mandante or not visitante or is_bad_name(mandante) or is_bad_name(visitante):
        return None
    if mandante == visitante:
        return None

    return Partido(
        fonte="FCF",
        competicao=f"Brasil - Ceará - {nome_competicao}",
        data=data_iso,
        hora=hora,
        mandante=mandante,
        visitante=visitante,
        estadio=estadio,
        url=url,
        extra=f"idcamp={idcamp}",
    )


def _dedup_nome(texto: str) -> str:
    """Widgets desse site costumam repetir o nome do time 2x seguidas
    (uma vez do <img alt>, outra do texto do link) - ex.: 'CearáCeará'.
    Detecta e desfaz essa duplicação; senão só limpa o texto."""
    t = clean_text(texto).strip(" -")
    n = len(t)
    if n >= 4 and n % 2 == 0:
        metade = n // 2
        if t[:metade] == t[metade:]:
            return t[:metade]
    return t


def collect(dias: int, dias_atras: int, timeout: int, debug_html: bool) -> tuple[list[Partido], list[dict]]:
    today = date.today()
    desde = today - timedelta(days=dias_atras)
    ate = today + timedelta(days=dias)

    competicoes = descobrir_competicoes(timeout)
    print(f"[INFO] Competições encontradas: {len(competicoes)}")

    partidos: list[Partido] = []
    debug_pages = []

    for idcamp, nome in competicoes.items():
        url = f"{BASE}/tabela.asp?idcamp={idcamp}"
        html = fetch(url, timeout, tentativas=2)
        info = {"idcamp": idcamp, "nome": nome, "url": url, "jogos": 0, "erro": ""}
        if not html:
            info["erro"] = "falha ao buscar (timeout/erro de rede)"
            debug_pages.append(info)
            print(f"[ERRO] {nome} (idcamp={idcamp}): falha ao buscar")
            continue

        if debug_html:
            DEBUG_DIR.mkdir(exist_ok=True)
            (DEBUG_DIR / f"idcamp_{idcamp}.html").write_text(html, encoding="utf-8")

        encontrados = parse_jogos_da_pagina(html, idcamp, nome)
        na_janela = [p for p in encontrados if _in_window(p, desde, ate)]
        info["jogos"] = len(na_janela)
        debug_pages.append(info)
        partidos.extend(na_janela)
        print(f"[OK] {nome} (idcamp={idcamp}): {len(encontrados)} jogos achados, {len(na_janela)} na janela")

    return partidos, debug_pages


def _in_window(p: Partido, desde: date, ate: date) -> bool:
    try:
        dt = date.fromisoformat(p.data)
    except Exception:
        return False
    return desde <= dt <= ate


def dedupe_partidos(rows: list[Partido]) -> list[Partido]:
    seen = set()
    out = []
    for p in rows:
        if not p.data or not p.mandante or not p.visitante:
            continue
        if p.id in seen:
            continue
        seen.add(p.id)
        out.append(p)
    return out


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
    parser.add_argument("--dias", type=int, default=365)
    parser.add_argument("--dias-atras", type=int, default=30)
    parser.add_argument("--timeout", type=int, default=35)
    parser.add_argument("--debug-html", action="store_true")
    args = parser.parse_args()

    partidos, debug_pages = collect(args.dias, args.dias_atras, args.timeout, args.debug_html)
    partidos = dedupe_partidos(partidos)
    rows_new = [p.to_row() for p in partidos]

    (OUT_DIR / "debug_fcf_ceara_pages.json").write_text(json.dumps(debug_pages, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "debug_fcf_ceara_raw.json").write_text(json.dumps(rows_new, ensure_ascii=False, indent=2), encoding="utf-8")

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    merged_current = merge_rows(load_json_rows(current_json), rows_new)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    merged_history = merge_rows(load_csv_rows(history_csv), rows_new)
    write_csv(history_csv, merged_history)

    print("")
    print(f"Ceará (FCF) jogos válidos adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")


if __name__ == "__main__":
    main()
