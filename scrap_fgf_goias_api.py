#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FGF (Federação Goiana de Futebol) - jogos via API/AJAX oficial

Página: https://www.fgf.esp.br/pt/competicoes/jogos.php?q=<idcampeonato>

Descoberta (validada com rede real em 26/07/2026):
- A lista de competições ativas está em https://www.fgf.esp.br/pt/competicoes,
  com links "jogos.php?q=<idcampeonato>".
- Cada página de competição carrega uma ou mais "fases" (ex.: "Fase Única"),
  cada uma com data-id (=idcampeonato), data-fase, data-rodada.
- Os jogos vêm de um POST em jogos_ajax_ver3.php (idcampeonato, idfase,
  rodada) que devolve TODAS as rodadas da fase de uma vez (o parâmetro
  rodada não filtra - é só o valor inicial da UI). O corpo é JSON com uma
  chave "html" contendo o HTML já pronto pra exibir.
- Os jogos usam CÓDIGOS de 3 letras (ex. "TUP") em vez do nome completo do
  clube, com o escudo (<img src=".../escudo_clubes/ID.ext">) como única
  referência estável. O endpoint classificacao_ajax_ver3.php (mesmos
  parâmetros) traz o nome completo de cada clube ao lado do mesmo escudo,
  o que permite montar um mapa escudo -> nome completo por competição.
- Sem headers especiais, sem Cloudflare: funciona com `requests` puro.

Como jogo futuro/realizado é decidido:
- Jogo com os dois placares presentes (mesmo "0 X 0") = realizado.
- Jogo sem placar = programado.

Saídas (mesmo formato/merge dos outros scrapers do projeto):
  data/jogos_programados.json / .csv
  data/historico_jogos.csv
  data/debug_fgf_goias_raw.json       # programados (p/ merge_apos_reset.py --raw)
  data/debug_fgf_goias_hist_raw.json  # programados + resultados (--raw-historico)
  data/debug_fgf_goias_competicoes.json

Uso:
  py -3 scrap_fgf_goias_api.py --dias 365 --dias-atras 45
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

JOGOS_JSON = OUT_DIR / "jogos_programados.json"
JOGOS_CSV = OUT_DIR / "jogos_programados.csv"
HIST_CSV = OUT_DIR / "historico_jogos.csv"

RAW_JOGOS = OUT_DIR / "debug_fgf_goias_raw.json"
RAW_HISTORICO = OUT_DIR / "debug_fgf_goias_hist_raw.json"
DEBUG_COMPETICOES = OUT_DIR / "debug_fgf_goias_competicoes.json"

BASE = "https://www.fgf.esp.br"
URL_COMPETICOES = f"{BASE}/pt/competicoes"
URL_JOGOS_AJAX = f"{BASE}/pt/competicoes/jogos_ajax_ver3.php"
URL_CLASSIF_AJAX = f"{BASE}/pt/competicoes/classificacao_ajax_ver3.php"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
    "X-Requested-With": "XMLHttpRequest",
}

FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "pais", "cidade", "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em",
]

DATE_RE = re.compile(r"(?P<dia>\d{1,2})/(?P<mes>\d{1,2})")
TIME_RE = re.compile(r"(?P<hora>\d{1,2})h(?P<min>\d{2})")


@dataclass
class Jogo:
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


def clean_text(x: Any) -> str:
    x = "" if x is None else str(x)
    x = x.replace("\xa0", " ")
    return re.sub(r"\s+", " ", x).strip()


def norm(x: Any) -> str:
    x = unicodedata.normalize("NFD", clean_text(x))
    x = "".join(c for c in x if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", x.lower()).strip()


def get(url: str, params: dict | None = None, tentativas: int = 3) -> requests.Response:
    ultima: Exception | None = None
    for i in range(tentativas):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=40)
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            ultima = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"Falha GET {url} ({params}): {ultima}")


def post(url: str, data: dict, tentativas: int = 3) -> Any:
    """POST que espera resposta JSON (usado por jogos_ajax_ver3.php)."""
    ultima: Exception | None = None
    for i in range(tentativas):
        try:
            r = requests.post(url, data=data, headers=HEADERS, timeout=40)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            ultima = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"Falha POST {url} ({data}): {ultima}")


def post_texto(url: str, data: dict, tentativas: int = 3) -> str:
    """POST que espera resposta HTML crua (usado por classificacao_ajax_ver3.php
    - ao contrário de jogos_ajax_ver3.php, este NÃO devolve JSON)."""
    ultima: Exception | None = None
    for i in range(tentativas):
        try:
            r = requests.post(url, data=data, headers=HEADERS, timeout=40)
            r.raise_for_status()
            return r.text
        except Exception as e:  # noqa: BLE001
            ultima = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"Falha POST {url} ({data}): {ultima}")


def descobrir_competicoes() -> list[dict]:
    """Lista (nome, idcampeonato) a partir de /pt/competicoes."""
    html = get(URL_COMPETICOES).text
    soup = BeautifulSoup(html, "html.parser")
    out, vistos = [], set()
    for a in soup.select('a[href*="jogos.php?q="]'):
        m = re.search(r"jogos\.php\?q=(\d+)", a.get("href", ""))
        nome = clean_text(a.get_text(" ", strip=True))
        if not (m and nome):
            continue
        idcamp = m.group(1)
        if idcamp in vistos:
            continue
        vistos.add(idcamp)
        out.append({"idcampeonato": idcamp, "nome": nome})
    return out


def descobrir_fases(idcampeonato: str) -> list[dict]:
    """Extrai as fases (idfase/rodada inicial) da página de uma competição."""
    html = get(f"{BASE}/pt/competicoes/jogos.php", params={"q": idcampeonato}).text
    soup = BeautifulSoup(html, "html.parser")
    fases, vistos = [], set()
    for el in soup.select(".fase[data-id][data-fase]"):
        idfase = el.get("data-fase")
        if not idfase or idfase in vistos:
            continue
        vistos.add(idfase)
        fases.append({
            "idcampeonato": el.get("data-id") or idcampeonato,
            "idfase": idfase,
            "nome_fase": clean_text(el.get_text(" ", strip=True)),
        })
    return fases


def mapa_escudos(idcampeonato: str, idfase: str) -> dict[str, str]:
    """escudo (nome do arquivo) -> nome completo do clube, via classificação."""
    try:
        html = post_texto(URL_CLASSIF_AJAX, {"idcampeonato": idcampeonato, "idfase": idfase, "rodada": "1"})
    except Exception:
        return {}
    soup = BeautifulSoup(html or "", "html.parser")
    mapa: dict[str, str] = {}
    for tr in soup.select("tbody tr"):
        img = tr.select_one("img")
        span = tr.select_one("span.d-none.d-sm-block")
        if img and img.get("src") and span:
            arquivo = img["src"].rsplit("/", 1)[-1]
            mapa[arquivo] = clean_text(span.get_text())
    return mapa


def parse_jogos_html(html: str, escudos: dict[str, str]) -> list[dict]:
    """Extrai os jogos (todas as rodadas) do HTML retornado por jogos_ajax_ver3.php.

    Estrutura real (validada em 26/07/2026): .swiper-wrapper > .swiper-slide
    (um por rodada) > [.title-rodada, .pr-jogos, .pr-jogos, ...]. Cada rodada
    fica isolada dentro do seu próprio swiper-slide, então o contador de
    rodada_atual é resetado a cada slide (não pode vazar pro slide seguinte).
    """
    soup = BeautifulSoup(html or "", "html.parser")
    wrapper = soup.select_one(".swiper-wrapper") or soup
    jogos = []

    slides = wrapper.select(".swiper-slide") or [wrapper]
    for slide in slides:
        rodada_atual = ""
        for el in slide.find_all("div", recursive=False):
            classes = el.get("class") or []
            if "title-rodada" in classes:
                rodada_atual = clean_text(el.get_text())
                continue
            if "pr-jogos" not in classes:
                continue

            cronolog = el.select_one(".cronolog-sm")
            cronolog_txt = clean_text(cronolog.get_text()) if cronolog else ""
            # ex.: "SAB, 25/07 - 15h30 - Geraldo Rodrigues (Geraldão)"
            partes = cronolog_txt.split(" - ", 2)
            data_txt = partes[0] if len(partes) > 0 else ""
            hora_txt = partes[1] if len(partes) > 1 else ""
            estadio_txt = partes[2] if len(partes) > 2 else ""

            cols = el.select(".row.g-0.my-2 > .col-4")
            if len(cols) != 3:
                continue
            col_mandante, col_placar, col_visitante = cols

            def nome_time(col):
                img = col.select_one("img")
                texto_code = clean_text(col.get_text())
                if img and img.get("alt") and clean_text(img.get("alt")):
                    return clean_text(img.get("alt"))
                if img and img.get("src"):
                    arquivo = img["src"].rsplit("/", 1)[-1]
                    if arquivo in escudos:
                        return escudos[arquivo]
                return texto_code

            mandante = nome_time(col_mandante)
            visitante = nome_time(col_visitante)

            spans_placar = col_placar.select("span")
            placar_m = clean_text(spans_placar[0].get_text()) if len(spans_placar) > 0 else ""
            placar_v = clean_text(spans_placar[-1].get_text()) if len(spans_placar) > 1 else ""

            link = el.select_one('a[href*="jogo.php"]')
            url_jogo = ""
            if link and link.get("href"):
                url_jogo = urljoin(f"{BASE}/pt/competicoes/", link["href"])

            if not (mandante and visitante):
                continue

            jogos.append({
                "rodada": rodada_atual,
                "data_txt": data_txt,
                "hora_txt": hora_txt,
                "estadio": estadio_txt,
                "mandante": mandante,
                "visitante": visitante,
                "placar_mandante": placar_m,
                "placar_visitante": placar_v,
                "url": url_jogo,
            })

    return jogos


def parse_data(data_txt: str, ano: int) -> str:
    m = DATE_RE.search(data_txt)
    if not m:
        return ""
    try:
        return date(ano, int(m.group("mes")), int(m.group("dia"))).isoformat()
    except Exception:
        return ""


def parse_hora(hora_txt: str) -> str:
    m = TIME_RE.search(hora_txt)
    return f"{int(m.group('hora')):02d}:{m.group('min')}" if m else ""


def item_para_jogo(item: dict, competicao: str, ano: int, hoje: date) -> Jogo | None:
    data_iso = parse_data(item["data_txt"], ano)
    if not data_iso:
        return None
    hora = parse_hora(item["hora_txt"])

    tem_placar = bool(item["placar_mandante"]) and bool(item["placar_visitante"])
    try:
        d = date.fromisoformat(data_iso)
    except Exception:
        return None

    if tem_placar:
        extra = ["status=Realizado", f"placar={item['placar_mandante']}x{item['placar_visitante']}"]
    elif d >= hoje:
        extra = ["status=Programado"]
    else:
        extra = ["status=Sem resultado"]
    extra += ["pais=Brasil", "estado=Goiás", "fonte=api_ajax"]

    rodada = item["rodada"]
    if rodada and not norm(rodada).startswith("rodada"):
        rodada = f"Rodada {rodada}" if rodada.strip().isdigit() else rodada

    return Jogo(
        fonte="FGF",
        competicao=competicao,
        data=data_iso,
        hora=hora,
        mandante=item["mandante"],
        visitante=item["visitante"],
        pais="Brasil",
        cidade="",
        estadio=item["estadio"],
        rodada=rodada,
        url=item["url"] or URL_COMPETICOES,
        extra="; ".join(extra),
    )


def nome_competicao(nome_raw: str) -> str:
    nome = clean_text(nome_raw)
    return f"Brasil - FGF - {nome}"


def dedup_rows(jogos: list[Jogo]) -> list[dict]:
    vistos: set[str] = set()
    rows: list[dict] = []
    for g in jogos:
        r = g.to_row()
        if not r["data"] or r["id"] in vistos:
            continue
        vistos.add(r["id"])
        rows.append(r)
    return rows


# ---------------------------------------------------------------------------
# Merge / persistência (mesma convenção dos demais scrapers do projeto)
# ---------------------------------------------------------------------------
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
        row.get("estadio", ""), row.get("rodada", "")
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def merge_rows(existing: list[dict], new_rows: list[dict]) -> list[dict]:
    by_id = {}
    for r in existing + new_rows:
        if not (r.get("mandante") and r.get("visitante")):
            continue
        if not r.get("data"):
            continue
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
    parser = argparse.ArgumentParser(description="Scraper FGF Goiás via API/AJAX oficial")
    parser.add_argument("--ano", type=int, default=date.today().year)
    parser.add_argument("--dias", type=int, default=365)
    parser.add_argument("--dias-atras", type=int, default=45, dest="dias_atras")
    parser.add_argument("--pausa", type=float, default=0.3)
    args = parser.parse_args()

    hoje = date.today()
    limite_frente = hoje + timedelta(days=args.dias)
    limite_tras = hoje - timedelta(days=args.dias_atras)

    print(f"[INFO] FGF Goiás via API .ajax | ano={args.ano}")
    competicoes = descobrir_competicoes()
    DEBUG_COMPETICOES.write_text(json.dumps(competicoes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INFO] {len(competicoes)} competições encontradas.")

    jogos_prog: list[Jogo] = []
    jogos_hist: list[Jogo] = []

    for camp in competicoes:
        idcamp = camp["idcampeonato"]
        nome = nome_competicao(camp["nome"])
        try:
            fases = descobrir_fases(idcamp)
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] {nome} (Id={idcamp}): falha ao descobrir fases: {e}")
            continue

        n_prog = n_hist = 0
        for fase in fases:
            idfase = fase["idfase"]
            try:
                escudos = mapa_escudos(idcamp, idfase)
                payload = post(URL_JOGOS_AJAX, {"idcampeonato": idcamp, "idfase": idfase, "rodada": "1"})
            except Exception as e:  # noqa: BLE001
                print(f"[WARN] {nome} / fase {idfase}: {e}")
                continue

            html = payload.get("html", "") if isinstance(payload, dict) else ""
            itens = parse_jogos_html(html, escudos)
            for it in itens:
                jogo = item_para_jogo(it, nome, args.ano, hoje)
                if not (jogo and jogo.data):
                    continue
                try:
                    d = date.fromisoformat(jogo.data)
                except Exception:
                    continue
                tem_placar = "status=Realizado" in jogo.extra
                if hoje <= d <= limite_frente and not tem_placar:
                    jogos_prog.append(jogo)
                    n_prog += 1
                if limite_tras <= d <= limite_frente:
                    jogos_hist.append(jogo)
                    n_hist += 1
            time.sleep(args.pausa)

        if fases:
            print(f"  - {nome} (Id={idcamp}): {n_prog} programados | {n_hist} p/ histórico")

    rows_prog = dedup_rows(jogos_prog)
    rows_hist = dedup_rows(jogos_hist)

    RAW_JOGOS.write_text(json.dumps(rows_prog, ensure_ascii=False, indent=2), encoding="utf-8")
    RAW_HISTORICO.write_text(json.dumps(rows_hist, ensure_ascii=False, indent=2), encoding="utf-8")

    merged_current = merge_rows(load_json_rows(JOGOS_JSON), rows_prog)
    JOGOS_JSON.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(JOGOS_CSV, merged_current)

    merged_hist = merge_rows(load_csv_rows(HIST_CSV), rows_hist)
    write_csv(HIST_CSV, merged_hist)

    print("")
    print(f"[OK] Programados FGF-GO: {len(rows_prog)} | para histórico: {len(rows_hist)}")
    print(f"[OK] Total no {JOGOS_JSON.name}: {len(merged_current)}")
    print(f"[OK] Total no {HIST_CSV.name}: {len(merged_hist)}")


if __name__ == "__main__":
    main()
