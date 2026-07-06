#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adiciona jogos do Brasil ao mesmo JSON do projeto jogos-chile-scraper.

Fontes iniciais:
- CBF: https://www.cbf.com.br/
- FERJ: https://www.fferj.com.br/partidas
- FMF: https://www.fmf.com.br/
- FPF: https://www.futebolpaulista.com.br/Home/

Saídas atualizadas:
- data/jogos_programados.json
- data/jogos_programados.csv
- data/historico_jogos.csv

Uso:
    python adicionar_brasil_jogos.py --dias 180 --dias-atras 30

Observação:
FERJ é a fonte mais confiável nesta primeira versão, pois publica os jogos em texto
estruturado. CBF/FPF podem depender de JavaScript/API e podem exigir ajustes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, date, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,es;q=0.8,en;q=0.7",
}

SOURCES = [
    ("CBF", "https://www.cbf.com.br/"),
    ("CBF Série A", "https://www.cbf.com.br/futebol-brasileiro/tabelas/campeonato-brasileiro/serie-a"),
    ("CBF Série B", "https://www.cbf.com.br/futebol-brasileiro/tabelas/campeonato-brasileiro/serie-b"),
    ("CBF Série C", "https://www.cbf.com.br/futebol-brasileiro/tabelas/campeonato-brasileiro/serie-c"),
    ("CBF Série D", "https://www.cbf.com.br/futebol-brasileiro/tabelas/campeonato-brasileiro/serie-d"),
    ("FERJ", "https://www.fferj.com.br/partidas"),
    ("FMF", "https://www.fmf.com.br/"),
    ("FPF", "https://www.futebolpaulista.com.br/Home/"),
]

MESES = {
    "jan": 1, "janeiro": 1,
    "fev": 2, "fevereiro": 2,
    "mar": 3, "março": 3, "marco": 3,
    "abr": 4, "abril": 4,
    "mai": 5, "maio": 5,
    "jun": 6, "junho": 6,
    "jul": 7, "julho": 7,
    "ago": 8, "agosto": 8,
    "set": 9, "setembro": 9,
    "out": 10, "outubro": 10,
    "nov": 11, "novembro": 11,
    "dez": 12, "dezembro": 12,
}

DIAS_SEMANA = "SEG|TER|QUA|QUI|SEX|SAB|SÁB|DOM"

# FERJ:
# SEG 06/07/26 14:45h ESTÁDIO GIULITE COUTINHO (E. EDSON PASSOS) America F.C (RJ) X Bangu A.C Torneio OPG | Sub-20 | Torneio FERJ
FERJ_RE = re.compile(
    rf"\b(?:{DIAS_SEMANA})\s+"
    r"(?P<dia>\d{2})/(?P<mes>\d{2})/(?P<ano>\d{2,4})\s+"
    r"(?P<hora>\d{1,2}:\d{2})h?\s+"
    r"(?P<resto>.+?)$",
    re.I,
)

# Genérico:
# 06/07/2026 14:45 Time A X Time B Competição
GENERIC_NUMERIC_RE = re.compile(
    r"\b(?P<dia>\d{1,2})[/-](?P<mes>\d{1,2})[/-](?P<ano>\d{2,4})\s+"
    r"(?P<hora>\d{1,2}:\d{2})h?\s+"
    r"(?P<resto>.+?)$",
    re.I,
)

# Ex.: 6 jul 2026 14:45 Time A x Time B
GENERIC_TEXT_MONTH_RE = re.compile(
    r"\b(?P<dia>\d{1,2})\s+"
    r"(?P<mes_txt>jan|janeiro|fev|fevereiro|mar|março|marco|abr|abril|mai|maio|jun|junho|jul|julho|ago|agosto|set|setembro|out|outubro|nov|novembro|dez|dezembro)\.?\s+"
    r"(?P<ano>\d{2,4})\s+"
    r"(?P<hora>\d{1,2}:\d{2})h?\s+"
    r"(?P<resto>.+?)$",
    re.I,
)

VS_RE = re.compile(r"\s+(?:X|x|vs\.?|v/s)\s+")
PLACAR_RE = re.compile(r"\b\d+\s*[-xX]\s*\d+\b")


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


def clean_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    value = re.sub(r"^Image:\s*", "", value, flags=re.I).strip()
    return value


def norm(value: str) -> str:
    import unicodedata
    value = unicodedata.normalize("NFD", value or "")
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def parse_year(y: str) -> int:
    n = int(y)
    if n < 100:
        return 2000 + n
    return n


_PLAYWRIGHT = None
_BROWSER = None
_CONTEXT = None


def _get_context():
    """Lazily launches a single shared Chromium browser+context for the whole run."""
    global _PLAYWRIGHT, _BROWSER, _CONTEXT
    if _CONTEXT is None:
        from playwright.sync_api import sync_playwright
        _PLAYWRIGHT = sync_playwright().start()
        _BROWSER = _PLAYWRIGHT.chromium.launch(
            args=["--disable-blink-features=AutomationControlled"]
        )
        _CONTEXT = _BROWSER.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="pt-BR",
            extra_http_headers={"Accept-Language": HEADERS["Accept-Language"]},
        )
    return _CONTEXT


def close_browser() -> None:
    global _PLAYWRIGHT, _BROWSER, _CONTEXT
    if _CONTEXT is not None:
        try:
            _CONTEXT.close()
        except Exception:
            pass
    if _BROWSER is not None:
        try:
            _BROWSER.close()
        except Exception:
            pass
    if _PLAYWRIGHT is not None:
        try:
            _PLAYWRIGHT.stop()
        except Exception:
            pass
    _CONTEXT = None
    _BROWSER = None
    _PLAYWRIGHT = None


def fetch(url: str) -> str:
    """
    Busca o HTML da página usando um navegador real (Playwright/Chromium).

    Isso é necessário porque:
    1. Sites como CBF, FERJ, FMF e FPF bloqueiam requisições simples (requests)
       com 403, provavelmente por proteção anti-bot / fingerprint de TLS.
    2. Algumas páginas renderizam o conteúdo via JavaScript no lado do cliente,
       então o HTML "cru" (sem executar JS) não contém os jogos.

    Um navegador real headless resolve os dois problemas ao mesmo tempo.
    Se o Playwright não estiver disponível por algum motivo, cai de volta
    para requests simples (mantém compatibilidade).

    Timeouts são propositalmente curtos (15s/3s) porque este método é chamado
    para dezenas de URLs em sequência dentro de um único job do GitHub Actions;
    esperas longas por página aqui multiplicam rapidamente o tempo total.
    """
    try:
        context = _get_context()
        page = context.new_page()
        try:
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
            html = page.content()
        finally:
            page.close()
        return html
    except Exception as e:
        print(f"[WARN] Playwright falhou para {url} ({e}); tentando requests simples", file=sys.stderr)
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.text


def get_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    lines = []
    for raw in soup.get_text("\n").splitlines():
        line = clean_text(raw)
        if not line:
            continue
        if line in {"*", "* * *", "Home", "Contato"}:
            continue
        lines.append(line)
    return lines


def discover_links(html: str, base_url: str, fonte: str) -> list[str]:
    """
    Descobre links internos que podem ter jogos/tabelas.
    Mantém limitado para não raspar o site inteiro.
    """
    soup = BeautifulSoup(html, "html.parser")
    out = {base_url}
    wanted = [
        "partida", "partidas", "jogos", "tabela", "tabelas",
        "campeonato", "competicao", "competi", "placar"
    ]
    for a in soup.find_all("a", href=True):
        text = clean_text(a.get_text(" ", strip=True)).lower()
        href = urljoin(base_url, a["href"]).split("#")[0]
        low = href.lower() + " " + text
        if any(w in low for w in wanted):
            if any(domain in href for domain in ["cbf.com.br", "fferj.com.br", "fmf.com.br", "futebolpaulista.com.br"]):
                out.add(href)
    return sorted(out)[:6]


def looks_like_stadium(txt: str) -> bool:
    t = norm(txt)
    markers = [
        "estadio", "arena", "campo", "ct ", "centro de treinamento",
        "maracana", "engenhao", "moça bonita", "moca bonita",
        "luso brasileiro", "giulite coutinho", "nivaldo pereira",
        "municipal", "parque", "independencia", "mineirao", "allianz",
        "morumbi", "neo quimica", "pacaembu", "caninde", "brinco de ouro",
        "vila belmiro", "couto pereira", "beira rio", "ressacada"
    ]
    return any(m in t for m in markers)


def infer_competicao(resto: str, fonte: str) -> str:
    low = resto.lower()
    if "brasileiro" in low or "série" in low or "serie" in low:
        if "série a" in low or "serie a" in low:
            return "Brasil - Série A"
        if "série b" in low or "serie b" in low:
            return "Brasil - Série B"
        if "série c" in low or "serie c" in low:
            return "Brasil - Série C"
        if "série d" in low or "serie d" in low:
            return "Brasil - Série D"
        return "Brasil - CBF"
    if "copa do brasil" in low:
        return "Brasil - Copa do Brasil"
    if "copa rio" in low:
        return "Brasil - Copa Rio"
    if "carioca" in low or "ferj" in low or "estadual" in low:
        return "Brasil - FERJ"
    if "mineiro" in low or "fmf" in low or "módulo" in low or "modulo" in low:
        return "Brasil - FMF"
    if "paulista" in low or "paulistão" in low or "paulistao" in low or "fpf" in low:
        return "Brasil - FPF"
    return f"Brasil - {fonte}"


def split_match_parts(resto: str) -> tuple[str, str, str, str]:
    """
    Retorna mandante, visitante, estadio, competicao_txt.
    Tenta lidar com:
    - ESTÁDIO ... Time A X Time B Competição
    - Time A X Time B Competição
    """
    resto = clean_text(resto)
    estadio = ""

    # Se começa por ESTÁDIO/ARENA/CAMPO, o estádio vem antes dos times.
    if re.match(r"^(ESTÁDIO|ESTADIO|ARENA|CAMPO|CT)\b", resto, flags=re.I):
        # corta o estádio antes do primeiro padrão com X.
        parts = VS_RE.split(resto, maxsplit=1)
        if len(parts) == 2:
            before_x = parts[0]
            after_x = parts[1]

            # No "before_x", o mandante é o trecho final após o estádio.
            tokens = before_x.split()
            # Heurística: times costumam começar depois de parêntese final ou após palavras de estádio.
            # Tentamos procurar clubes comuns, mas mantendo flexível.
            possible_markers = [
                " America ", " Bangu ", " Vasco ", " Flamengo ", " Fluminense ", " Botafogo ",
                " Campos ", " Rio ", " Boavista ", " Nova ", " Maricá ", " Marica ",
                " Portuguesa ", " Paduano ", " Friburguense ", " Cobreloa "
            ]
            idx = None
            padded = " " + before_x + " "
            for mk in possible_markers:
                pos = padded.find(mk)
                if pos >= 0:
                    idx = max(0, pos - 1)
                    break
            if idx is None:
                # fallback: se tem ")", divide depois do último ")"
                pos = before_x.rfind(")")
                if pos > 0 and pos + 1 < len(before_x):
                    estadio = before_x[:pos + 1].strip()
                    mandante = before_x[pos + 1:].strip()
                else:
                    # fallback bruto: metade inicial estádio, 4 últimas palavras mandante
                    words = before_x.split()
                    mandante = " ".join(words[-4:]).strip()
                    estadio = " ".join(words[:-4]).strip()
            else:
                estadio = before_x[:idx].strip()
                mandante = before_x[idx:].strip()

            visitante, comp = split_visitante_comp(after_x)
            return mandante, visitante, estadio, comp

    parts = VS_RE.split(resto, maxsplit=1)
    if len(parts) != 2:
        return "", "", "", ""

    mandante = clean_text(parts[0])
    visitante, comp = split_visitante_comp(parts[1])
    return mandante, visitante, estadio, comp


def split_visitante_comp(txt: str) -> tuple[str, str]:
    txt = clean_text(txt)

    # Divide visitante e competição por palavras-chave frequentes.
    keys = [
        " BRASILEIRO ", " COPA DO BRASIL ", " COPA RIO ", " Estadual ",
        " Torneio ", " Amador ", " Paulista ", " Carioca ", " Mineiro ",
        " Sub-20 ", " Sub-17 ", " Sub-16 ", " Sub-15 ", " Profissional ",
        " CBF ", " FERJ ", " FMF ", " FPF "
    ]

    padded = " " + txt + " "
    best = None
    for key in keys:
        pos = padded.lower().find(key.lower())
        if pos > 0:
            if best is None or pos < best:
                best = pos

    if best is not None:
        visitante = txt[:best].strip()
        comp = txt[best:].strip()
        return visitante, comp

    # fallback: visitante até 5 palavras, resto competição
    words = txt.split()
    if len(words) > 6:
        return " ".join(words[:5]).strip(), " ".join(words[5:]).strip()
    return txt, ""


def parse_line(line: str, fonte: str, url: str, today: date) -> Partido | None:
    m = FERJ_RE.search(line) or GENERIC_NUMERIC_RE.search(line)
    if m:
        dt = date(parse_year(m.group("ano")), int(m.group("mes")), int(m.group("dia")))
        hora = m.group("hora")
        resto = m.group("resto")
    else:
        m2 = GENERIC_TEXT_MONTH_RE.search(line)
        if not m2:
            return None
        dt = date(parse_year(m2.group("ano")), MESES[norm(m2.group("mes_txt"))], int(m2.group("dia")))
        hora = m2.group("hora")
        resto = m2.group("resto")

    if PLACAR_RE.search(resto):
        # mantém, mas marca placar em extra
        placar = PLACAR_RE.search(resto).group(0)
        resto = PLACAR_RE.sub(" X ", resto, count=1)
    else:
        placar = ""

    mandante, visitante, estadio, comp_txt = split_match_parts(resto)
    if not mandante or not visitante:
        return None

    if len(mandante) > 80 or len(visitante) > 80:
        return None

    competicao = infer_competicao(comp_txt or resto, fonte)
    extra_parts = []
    if comp_txt:
        extra_parts.append(f"competicao_original={comp_txt}")
    if placar:
        extra_parts.append(f"placar={placar}")
    if fonte:
        extra_parts.append(f"pais=Brasil")

    return Partido(
        fonte=f"{fonte}",
        competicao=competicao,
        data=dt.isoformat(),
        hora=hora,
        mandante=mandante,
        visitante=visitante,
        estadio=estadio,
        rodada="",
        url=url,
        extra="; ".join(extra_parts),
    )


def in_window(dt: date, desde: date, ate: date, incluir_passados: bool) -> bool:
    return incluir_passados or (desde <= dt <= ate)


def parse_html_for_matches(fonte: str, url: str, html: str, desde: date, ate: date, incluir_passados: bool) -> list[Partido]:
    lines = get_lines(html)
    out = []
    for line in lines:
        p = parse_line(line, fonte, url, date.today())
        if not p:
            continue
        dt = date.fromisoformat(p.data)
        if not in_window(dt, desde, ate, incluir_passados):
            continue
        if norm(p.mandante) == norm(p.visitante):
            continue
        out.append(p)
    return dedupe(out)


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
        row.get("fonte", ""),
        row.get("competicao", ""),
        row.get("data", ""),
        row.get("hora", ""),
        row.get("mandante", ""),
        row.get("visitante", ""),
        row.get("estadio", ""),
        row.get("rodada", ""),
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
    return sorted(by_id.values(), key=lambda r: (r.get("data", ""), r.get("hora", ""), r.get("competicao", ""), r.get("mandante", "")))


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "id", "fonte", "competicao", "data", "hora",
        "mandante", "visitante", "estadio", "rodada",
        "url", "extra", "atualizado_em",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dias", type=int, default=180)
    parser.add_argument("--dias-atras", type=int, default=30)
    parser.add_argument("--incluir-passados", action="store_true")
    parser.add_argument("--no-discover", action="store_true", help="não descobre links internos")
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    urls = []
    for fonte, url in SOURCES:
        urls.append((fonte, url))
        if args.no_discover:
            continue
        try:
            html = fetch(url)
            for found in discover_links(html, url, fonte):
                urls.append((fonte, found))
        except Exception as e:
            print(f"[WARN] discover falhou {fonte} {url}: {e}", file=sys.stderr)

    # Dedup
    seen = set()
    urls_clean = []
    for fonte, url in urls:
        key = (fonte, url)
        if key in seen:
            continue
        seen.add(key)
        urls_clean.append((fonte, url))

    print(f"[INFO] URLs Brasil: {len(urls_clean)}")

    MAX_URLS = 40
    if len(urls_clean) > MAX_URLS:
        print(f"[WARN] Limitando de {len(urls_clean)} para {MAX_URLS} URLs para não estourar o tempo do job", file=sys.stderr)
        urls_clean = urls_clean[:MAX_URLS]

    all_new = []
    try:
        for fonte, url in urls_clean:
            try:
                html = fetch(url)
                matches = parse_html_for_matches(fonte, url, html, desde, ate, args.incluir_passados)
                print(f"[OK] {fonte} -> {len(matches)} jogos | {url}")
                all_new.extend([m.to_row() for m in matches])
            except Exception as e:
                print(f"[ERRO] {fonte} {url}: {e}", file=sys.stderr)
    finally:
        close_browser()

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    current_existing = load_json_rows(current_json)
    merged_current = merge_rows(current_existing, all_new)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    history_existing = load_csv_rows(history_csv)
    merged_history = merge_rows(history_existing, all_new)
    write_csv(history_csv, merged_history)

    print(f"\nBrasil adicionados/atualizados: {len(all_new)}")
    print(f"Total JSON atual: {len(merged_current)}")


if __name__ == "__main__":
    main()
