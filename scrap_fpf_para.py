#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper - Federação Paraense de Futebol (FPF-PA) - https://www.fpfpara.com.br/

Diferente da FMF (que só carrega jogos via JS) e do Futebol Nacional (SPA
inteiro em JS, sem dar pra ler nada sem executar JavaScript), o site da
FPF-PA é renderizado no servidor: cada rodada de cada competição é uma URL
normal, sem precisar de Playwright.

Padrão de URL confirmado (visto tanto navegando o site quanto em resultados
de busca indexados pelo Google):
    https://www.fpfpara.com.br/competicao/{id}                       -> mostra a 1a fase/rodada por padrão
    https://www.fpfpara.com.br/competicao/{id}/fase/{fase_id}/rodada/{n}  -> rodada específica

O ID da fase (fase_id) muda por competição/fase e não é previsível, então
este script primeiro busca a página base da competição, extrai os links
reais "/competicao/{id}/fase/{fase_id}/rodada/{n}" que aparecem no HTML
(navegação de rodadas/fases) e usa esses fase_id descobertos para iterar
todas as rodadas de todas as fases.

Cada jogo aparece como um bloco de texto (confirmado via fetch real em
09/07/2026, competição 95 = Paraense Série A1):

    <mandante>
    <placar mandante> VS <placar visitante>      (ou só "VS" se ainda não jogou)
    <dd/mm/aaaa> - <hh:mm>
    <estadio> [- opcional]
    <apelido do estadio, em itálico>              (opcional)
    Arbitragem / Súmula / Boletim / PGA            (links, ignorados)
    <visitante>

Este parser trabalha em cima do texto puro da página (BeautifulSoup
get_text), então é resiliente a pequenas mudanças de HTML - mas ⚠️ NÃO foi
validado com uma execução ao vivo real (a rede do ambiente onde este script
foi escrito não tinha acesso a fpfpara.com.br). Rode com --debug-html na
primeira vez e confira data/debug_fpf_para_html/*.txt se os jogos não
baterem.

Uso:
    python scrap_fpf_para.py --once --dias 365 --dias-atras 30 --debug-html
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
DEBUG_DIR = OUT_DIR / "debug_fpf_para_html"

BASE = "https://www.fpfpara.com.br"

# Competições ativas listadas no menu do site em 10/07/2026. IDs mudam a
# cada temporada - conferir https://www.fpfpara.com.br/ e atualizar aqui
# quando a FPF abrir as competições do próximo ano.
COMPETICOES = {
    95: "Campeonato Paraense Série A1 2026",
    103: "Campeonato Paraense Série A2 2026",
    110: "Campeonato Paraense Série A3 2026",
    98: "Copa Grão-Pará 2026",
    97: "Super Copa Grão-Pará 2026",
    108: "Circuito Paraense de Base - Curionópolis 2026",
    102: "Copa Pará Feminino Adulto 2026",
    109: "Copa Pará Feminino Sub-15 2026",
    104: "Copa Pará Sub-17 Masculino - Metropolitana 2026",
    105: "Copa Pará Sub-17 Masculino - Nordeste 2026",
    106: "Copa Pará Sub-17 Masculino - Sul 2026",
    99: "Copa Pará Sub-20 Masculino - Metropolitana 2026",
    100: "Copa Pará Sub-20 Masculino - Nordeste 2026",
    101: "Copa Pará Sub-20 Masculino - Sul 2026",
    107: "Copa Pará Sub-20 Masculino - Super Campeão 2026",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
}

MAX_RODADAS_SEGURANCA = 40  # trava de segurança pra nao entrar em loop infinito

FASE_URL_RE = re.compile(r"/competicao/(\d+)/fase/(\d+)/rodada/(\d+)")
DATA_HORA_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\s*-\s*(\d{2}):(\d{2})\b")
PLACAR_RE = re.compile(r"^(?:(\d+)\s*)?VS(?:\s*(\d+))?$", re.IGNORECASE)
NENHUM_JOGO_RE = re.compile(r"nenhum jogo cadastrado", re.IGNORECASE)
IGNORAR_LINHA_RE = re.compile(
    r"^(arbitragem|s[uú]mula|boletim|pga|[aá]rbitro|assistente\s*[12]|"
    r"escala de arbitragem)\b",
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
    estadio_apelido: str = ""
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


def norm(v) -> str:
    v = unicodedata.normalize("NFD", clean_text(v))
    v = "".join(c for c in v if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", v.lower()).strip()


def fetch(url: str) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r


def get_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text("\n")
    return [clean_text(t) for t in text.split("\n") if clean_text(t)]


def discover_fases(competicao_id: int, html: str) -> set[tuple[int, int]]:
    """Retorna pares (fase_id, rodada_maxima_vista) encontrados na página
    base da competição - o link de navegação de rodada expõe o fase_id
    real usado pelo site."""
    fases: dict[int, int] = {}
    for comp_id, fase_id, rodada in FASE_URL_RE.findall(html):
        if int(comp_id) != competicao_id:
            continue
        fase_id = int(fase_id)
        rodada = int(rodada)
        fases[fase_id] = max(fases.get(fase_id, 0), rodada)
    return set(fases.items())


def parse_rodada_page(lines: list[str], url: str, competicao_nome: str, competicao_id: int,
                       debug_html: bool, raw_html: str = "") -> tuple[list[Partido], str]:
    """Extrai os jogos de uma página de rodada. Retorna (jogos, rodada_label)."""
    if any(NENHUM_JOGO_RE.search(l) for l in lines):
        return [], ""

    rodada_label = ""
    for l in lines:
        if re.match(r"^RODADA\s+\d+\s+DE\s+\d+", l, re.IGNORECASE):
            rodada_label = l
            break
        if re.match(r"^(PRÉ|1º|2º|3º|4º)\s*FASE", l, re.IGNORECASE):
            rodada_label = rodada_label or l

    partidos: list[Partido] = []
    n = len(lines)
    i = 0
    while i < n:
        m_placar = PLACAR_RE.match(lines[i])
        if not m_placar:
            i += 1
            continue

        # time mandante = linha imediatamente anterior ao placar/"VS"
        if i == 0:
            i += 1
            continue
        mandante = lines[i - 1]

        # data/hora: procura nas próximas linhas
        j = i + 1
        data_iso, hora = "", ""
        while j < n and j < i + 4:
            md = DATA_HORA_RE.search(lines[j])
            if md:
                dia, mes, ano, hh, mm = md.groups()
                try:
                    data_iso = date(int(ano), int(mes), int(dia)).isoformat()
                    hora = f"{hh}:{mm}"
                except ValueError:
                    pass
                j += 1
                break
            j += 1

        # estádio (+ apelido opcional na linha seguinte, sem ser um marcador
        # de arbitragem/link)
        estadio, apelido = "", ""
        if j < n and not IGNORAR_LINHA_RE.match(lines[j]) and not PLACAR_RE.match(lines[j]):
            estadio = clean_text(lines[j].rstrip(" -"))
            j += 1
            if j < n and not IGNORAR_LINHA_RE.match(lines[j]) and not PLACAR_RE.match(lines[j]) \
                    and len(lines[j]) < 60 and not DATA_HORA_RE.search(lines[j]):
                # provável apelido do estádio (linha em itálico na página).
                apelido = clean_text(lines[j])
                j += 1

        # pula linhas de arbitragem/links até achar o próximo nome (visitante)
        while j < n and IGNORAR_LINHA_RE.match(lines[j]):
            j += 1

        visitante = ""
        if j < n and not PLACAR_RE.match(lines[j]):
            visitante = lines[j]
            j += 1

        if mandante and visitante and mandante != visitante:
            placar_m, placar_v = m_placar.group(1), m_placar.group(2)
            extra_parts = ["pais=Brasil", "estado=Pará", f"competicao_id={competicao_id}"]
            if placar_m is not None and placar_v is not None:
                extra_parts.append(f"placar={placar_m}x{placar_v}")
            partidos.append(Partido(
                fonte="FPF-PA",
                competicao=f"Brasil - FPF-PA - {competicao_nome}",
                data=data_iso,
                hora=hora,
                mandante=clean_text(mandante),
                visitante=clean_text(visitante),
                estadio=estadio,
                estadio_apelido=apelido,
                rodada=rodada_label,
                url=url,
                extra="; ".join(extra_parts),
            ))
        i = max(j, i + 1)

    if debug_html:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        fname = re.sub(r"[^a-zA-Z0-9]+", "_", url)[-120:] + ".txt"
        (DEBUG_DIR / fname).write_text("\n".join(lines), encoding="utf-8")

    return partidos, rodada_label


def scrape_competicao(competicao_id: int, competicao_nome: str, debug_html: bool) -> list[Partido]:
    base_url = f"{BASE}/competicao/{competicao_id}"
    try:
        r = fetch(base_url)
    except Exception as e:
        print(f"[ERRO] {competicao_nome} (id={competicao_id}): {e}")
        return []

    lines = get_lines(r.text)
    partidos, _ = parse_rodada_page(lines, base_url, competicao_nome, competicao_id, debug_html, r.text)

    fases_vistas = discover_fases(competicao_id, r.text)
    for fase_id, rodada_max_vista in fases_vistas:
        rodada_max = max(rodada_max_vista, 1)
        rodada = 1
        vazias_seguidas = 0
        while rodada <= max(rodada_max, MAX_RODADAS_SEGURANCA) and rodada <= MAX_RODADAS_SEGURANCA:
            url = f"{BASE}/competicao/{competicao_id}/fase/{fase_id}/rodada/{rodada}"
            try:
                r2 = fetch(url)
            except Exception:
                break
            lines2 = get_lines(r2.text)
            jogos, rodada_label = parse_rodada_page(
                lines2, url, competicao_nome, competicao_id, debug_html, r2.text
            )
            if not jogos and not rodada_label:
                vazias_seguidas += 1
                if vazias_seguidas >= 2 and rodada > rodada_max:
                    break
            else:
                vazias_seguidas = 0
                partidos.extend(jogos)
            rodada += 1

    # dedupe (a URL base costuma repetir a rodada 1 de uma das fases)
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


FIELDS = [
    "id", "fonte", "competicao", "data", "hora", "pais", "cidade",
    "mandante", "visitante", "estadio", "rodada", "url", "extra", "atualizado_em",
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
    parser.add_argument("--incluir-passados", action="store_true")
    parser.add_argument("--somente-id", action="append", default=[], help="Limita a IDs de competição específicos (pode repetir)")
    parser.add_argument("--debug-html", action="store_true")
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    competicoes = COMPETICOES
    if args.somente_id:
        wanted = set(int(x) for x in args.somente_id)
        competicoes = {k: v for k, v in COMPETICOES.items() if k in wanted}

    all_partidos: list[Partido] = []
    print(f"[INFO] FPF-PA competições a varrer: {len(competicoes)}")
    for comp_id, comp_nome in competicoes.items():
        jogos = scrape_competicao(comp_id, comp_nome, args.debug_html)
        na_janela = [p for p in jogos if in_window(p, desde, ate, args.incluir_passados)]
        all_partidos.extend(na_janela)
        print(f"[OK] {comp_nome} (id={comp_id}) | jogos={len(jogos)} | na janela={len(na_janela)}")

    rows_new = [p.to_row() for p in all_partidos]

    (OUT_DIR / "debug_fpf_para_raw.json").write_text(
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
    print(f"FPF-PA jogos válidos adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")
    if args.debug_html:
        print("Debug HTML: data/debug_fpf_para_html/")


if __name__ == "__main__":
    main()
