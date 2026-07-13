#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper FBF (Campeonato Baiano) - com Playwright

Segue o mesmo padrão de scrap_fmf_competicoes_playwright_seguro.py, adaptado
para o site da Federação Bahiana de Futebol (fbf.org.br).

STATUS (confirmado rodando de verdade via GitHub Actions, já que este sandbox
não tem acesso de rede a fbf.org.br):
- A home (BASE_URL) tem uma seção "PRÓXIMOS JOGOS" com o formato
  Competição / DD/MM/AAAA / Mandante / x / Visitante / DETALHES DE JOGO.
  parse_text_patterns_fbf() já extrai isso corretamente (validado com jogos
  reais em 2026-07).
- As páginas /competicoes/{id} (classificação) têm um formato DIFERENTE: um
  carrossel "Rodada N" com um jogo por vez (Estádio / Data Hora / Mandante /
  placar / placar / Visitante / DETALHES DE JOGO), navegável via botões
  Previous/Next. parse_carousel_fbf() extrai o estado inicial, e
  render_page_collect() clica em "Next" repetidamente para varrer rodadas.
  Ainda pode precisar de ajuste fino (nº de cliques, rodadas futuras sem
  placar etc.) — usar --debug-html para conferir.


Como a FBF costuma ter várias competições (Baianão Série A, Série B, Sub-20,
Sub-17, Sub-15, Intermunicipal, etc.), o script tenta:
1. Descobrir competições/páginas de jogos a partir da home e de
   /competicoes/{id} para um range de ids.
2. Abrir cada página com Playwright, esperar o carregamento dinâmico.
3. Clicar em abas/selects de fase/rodada, se existirem.
4. Capturar HTML renderizado e respostas JSON/HTML de rede.
5. Extrair jogos do texto renderizado e dos payloads JSON.
6. Salvar no mesmo formato/CSV usado no projeto (FIELDS compatível).

Requisitos:
    py -m pip install requests beautifulsoup4 playwright
    py -m playwright install chromium

Teste (poucas competições, com debug):
    py scrap_fbf_baiano_playwright.py --somente-id 1 --somente-id 2 --incluir-passados --debug-html

Completo:
    py scrap_fbf_baiano_playwright.py --max-id 40 --dias 365 --dias-atras 60 --debug-html
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
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)
HTML_DIR = OUT_DIR / "debug_fbf_html"

BASE_URL = "https://www.fbf.org.br/"
COMPETICOES_URL = "https://www.fbf.org.br/competicoes/{id}"

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
    "Accept-Language": "pt-BR,pt;q=0.9,es;q=0.8,en;q=0.7",
}

MESES = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3,
    "abril": 4, "maio": 5, "junho": 6, "julho": 7,
    "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
}

TIME_RE = re.compile(r"\b(?P<hora>\d{1,2}:\d{2})\b")
DATE_NUM_RE = re.compile(r"\b(?P<dia>\d{1,2})/(?P<mes>\d{1,2})/(?P<ano>\d{2,4})\b")
DATE_ISO_RE = re.compile(r"\b(?P<ano>20\d{2})-(?P<mes>\d{2})-(?P<dia>\d{2})")
DATE_LONG_RE = re.compile(
    r"(?P<dia>\d{1,2})\s+de\s+(?P<mes>[a-zçãé]+)\s+de\s+(?P<ano>\d{4})",
    re.I,
)
X_ONLY_RE = re.compile(r"^\s*[xX]\s*$")
DETALHES_RE = re.compile(r"detalhes\s+d[eo]\s+jogo", re.I)
RODADA_STRICT_RE = re.compile(r"^\s*(?:\d{1,2}[ºª]?\s*rodada|rodada\s*\d{1,2})\b", re.I)

BAD = {
    "fbf federacao bahiana de futebol", "federacao bahiana de futebol",
    "fbf - federacao bahiana de futebol", "bem vindo a federacao bahiana de futebol",
    "o campeonato", "noticias", "videos", "classificacao", "classificação",
    "galeria", "voltar", "tabela completa", "artilharia", "regulamento",
    "documentos", "imprensa", "home", "competicoes", "competições",
    "selecao", "seleção", "clique aqui para saber mais", "detalhes de jogo",
    "leia mais",
}


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
    x = x.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", x).strip()


def norm(x: Any) -> str:
    x = unicodedata.normalize("NFD", clean_text(x))
    x = "".join(c for c in x if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", x.lower()).strip()


def parse_year(y: str) -> int:
    n = int(y)
    return 2000 + n if n < 100 else n


def parse_date_any(txt: Any, fallback: str = "") -> str:
    s = clean_text(txt) or fallback

    m = DATE_ISO_RE.search(s)
    if m:
        try:
            return date(int(m.group("ano")), int(m.group("mes")), int(m.group("dia"))).isoformat()
        except Exception:
            pass

    m = DATE_NUM_RE.search(s)
    if m:
        try:
            return date(parse_year(m.group("ano")), int(m.group("mes")), int(m.group("dia"))).isoformat()
        except Exception:
            pass

    ns = norm(s)
    m = DATE_LONG_RE.search(ns)
    if m:
        try:
            mes = MESES.get(m.group("mes").lower(), 0)
            if mes:
                return date(int(m.group("ano")), mes, int(m.group("dia"))).isoformat()
        except Exception:
            pass

    return ""


def parse_time_any(txt: Any) -> str:
    m = TIME_RE.search(clean_text(txt))
    return m.group("hora") if m else ""


def is_bad_name(x: str) -> bool:
    s = norm(x)
    if not s:
        return True
    if s in BAD:
        return True
    if len(clean_text(x)) > 60:
        return True
    if any(k in s for k in ["copyright", "todos os direitos", "detalhes de jogo", "leia mais", "clique aqui"]):
        return True
    return False


def discover_urls(max_id: int) -> list[dict]:
    """Descobre páginas de competições/jogos.

    1) A home (BASE_URL) é sempre incluída, pois costuma listar os próximos
       jogos de várias competições de uma vez.
    2) Tenta também /competicoes/{id} para id em 1..max_id, já que o site
       parece usar esse padrão (ex.: https://www.fbf.org.br/competicoes/1).
    """
    found: dict[str, dict] = {
        "home": {"id": "home", "url": BASE_URL, "nome": "FBF - Home (proximos jogos)", "origem": "home"}
    }

    # Tenta achar links reais de competições a partir da home.
    for home in ["https://www.fbf.org.br/", "http://www.fbf.org.br/"]:
        try:
            r = requests.get(home, headers=HEADERS, timeout=45)
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a"):
                href = a.get("href") or ""
                text = clean_text(a.get_text(" ", strip=True))
                if "/competicoes/" not in href:
                    continue
                url = urljoin(home, href)
                cid = urlparse(url).path.rstrip("/").split("/")[-1]
                if cid and cid.isdigit():
                    found[cid] = {"id": cid, "url": url, "nome": text or f"FBF competicao {cid}", "origem": "home_link"}
        except Exception:
            pass

    for i in range(1, max_id + 1):
        sid = str(i)
        if sid not in found:
            found[sid] = {
                "id": sid,
                "url": COMPETICOES_URL.format(id=i),
                "nome": f"FBF competicao {i}",
                "origem": "range",
            }

    ordered = [found["home"]]
    resto = [v for k, v in found.items() if k != "home"]
    resto.sort(key=lambda x: int(x["id"]) if str(x["id"]).isdigit() else 999999)
    ordered.extend(resto)
    return ordered


def html_to_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text("\n", strip=True)
    lines = []
    for raw in text.splitlines():
        s = clean_text(raw)
        if not s:
            continue
        if len(s) > 180:
            continue
        lines.append(s)
    return lines


def detect_competicao(lines: list[str], fallback: str) -> str:
    for line in lines[:150]:
        s = clean_text(line)
        ns = norm(s)
        if any(k in ns for k in ["baianao", "baiano", "serie a", "serie b", "sub 20", "sub 17", "sub 15", "intermunicipal", "feminino", "copa"]):
            if len(s) <= 90 and not any(b in ns for b in BAD):
                return s
    return fallback


def first_value(obj: dict, keys: list[str]) -> str:
    if not isinstance(obj, dict):
        return ""
    for k in keys:
        if k in obj and clean_text(obj[k]):
            return clean_text(obj[k])
    normalized = {norm(k): v for k, v in obj.items()}
    for want in keys:
        nw = norm(want)
        for nk, val in normalized.items():
            if nw == nk or nw in nk:
                txt = clean_text(val)
                if txt:
                    return txt
    return ""


def obj_to_partido(obj: dict, url: str, cid: str, competicao_fallback: str, fallback_date: str = "") -> Partido | None:
    if not isinstance(obj, dict):
        return None

    mandante = first_value(obj, ["Mandante", "NomeMandante", "ClubeMandante", "TimeMandante", "EquipeMandante", "TimeCasa", "mandante", "home", "homeTeam"])
    visitante = first_value(obj, ["Visitante", "NomeVisitante", "ClubeVisitante", "TimeVisitante", "EquipeVisitante", "TimeFora", "visitante", "away", "awayTeam"])
    data = parse_date_any(first_value(obj, ["Data", "DataJogo", "DataFormatada", "DataHora", "DATA_HORA", "Dia", "date"]), fallback=fallback_date)
    hora = parse_time_any(first_value(obj, ["Hora", "Horario", "Horário", "DataHora", "HoraJogo", "time"]))
    estadio = first_value(obj, ["Estadio", "Estádio", "NomeEstadio", "Local", "Campo", "venue", "stadium"])
    cidade = first_value(obj, ["Cidade", "Municipio", "Município", "city"])
    rodada = first_value(obj, ["Rodada", "Fase", "round"])
    jogo = first_value(obj, ["Jogo", "NumeroJogo", "Numero", "Número"])
    comp = first_value(obj, ["Competicao", "Competição", "Campeonato", "DescricaoCampeonato", "NomeCampeonato"]) or competicao_fallback

    if not data:
        joined = " ".join(clean_text(v) for v in obj.values() if isinstance(v, (str, int, float)))
        data = parse_date_any(joined, fallback=fallback_date)
        hora = hora or parse_time_any(joined)

    if not (mandante and visitante and data):
        return None
    if is_bad_name(mandante) or is_bad_name(visitante) or mandante == visitante:
        return None

    extra = ["pais=Brasil", "estado=Bahia", f"codigo_fbf={cid}"]
    if jogo:
        extra.append(f"jogo_numero={jogo}")
    if cidade:
        extra.append(f"cidade={cidade}")

    return Partido(
        fonte="FBF",
        competicao=f"Brasil - FBF - {comp}",
        data=data,
        hora=hora,
        mandante=mandante,
        visitante=visitante,
        pais="Brasil",
        cidade=cidade,
        estadio=estadio,
        rodada=rodada,
        url=url,
        extra="; ".join(extra),
    )


def walk_json(data: Any, url: str, cid: str, competicao_fallback: str, fallback_date: str = "") -> list[Partido]:
    out = []
    if isinstance(data, dict):
        p = obj_to_partido(data, url, cid, competicao_fallback, fallback_date=fallback_date)
        if p:
            out.append(p)
        for v in data.values():
            out.extend(walk_json(v, url, cid, competicao_fallback, fallback_date=fallback_date))
    elif isinstance(data, list):
        for item in data:
            out.extend(walk_json(item, url, cid, competicao_fallback, fallback_date=fallback_date))
    return out


def parse_text_patterns_fbf(lines: list[str], url: str, cid: str, competicao_nome: str) -> list[Partido]:
    """Parser adaptado ao formato observado publicamente para a FBF:

        <Competição> ... <DD/MM/AAAA> ... <Mandante> · x · <Visitante> · DETALHES DE JOGO

    Como não foi possível confirmar ao vivo se cada pedaço vira uma linha
    separada (mais provável, pelo padrão do BeautifulSoup) ou se tudo cai
    numa linha só, o parser cobre os dois casos:

    1) Linha única contendo data + "Time x Time".
    2) Bloco em várias linhas: uma linha de data (opcionalmente com o nome da
       competição), seguida (a poucas linhas de distância) por mandante,
       depois uma linha só com "x", depois visitante, terminando geralmente
       em "DETALHES DE JOGO".
    """
    out: list[Partido] = []
    current_date = ""
    current_round = ""
    competicao_atual = competicao_nome

    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        ns = norm(line)

        # Atualiza competição corrente quando a linha parece um cabeçalho
        # de competição (ex.: "Baianão 2026 - Sub-20").
        if any(k in ns for k in ["baianao", "baiano"]) and len(line) <= 90 and not DATE_NUM_RE.search(line):
            competicao_atual = line

        if RODADA_STRICT_RE.match(line) and len(line) <= 40:
            current_round = line
        elif any(k in ns for k in ["proximos jogos", "resultados", "ultimas noticias", "registros de eventos"]):
            # Marcadores de seção: zera a rodada "herdada" de blocos anteriores
            # (ex.: manchetes de notícia que citam "rodada" fora de contexto).
            current_round = ""

        dt = parse_date_any(line)
        if dt:
            current_date = dt
            # Se a mesma linha também tiver "Time x Time", resolve direto.
            mline = re.search(r"(.{2,40})\s+[xX]\s+(.{2,40})", line)
            if mline:
                mandante = clean_text(DATE_NUM_RE.sub("", mline.group(1)))
                visitante = clean_text(mline.group(2))
                if mandante and visitante and not is_bad_name(mandante) and not is_bad_name(visitante) and mandante != visitante:
                    out.append(Partido(
                        fonte="FBF",
                        competicao=f"Brasil - FBF - {competicao_atual}",
                        data=current_date,
                        hora=parse_time_any(line),
                        mandante=mandante,
                        visitante=visitante,
                        pais="Brasil",
                        cidade="",
                        estadio="",
                        rodada=current_round,
                        url=url,
                        extra=f"pais=Brasil; estado=Bahia; codigo_fbf={cid}; origem=linha_unica",
                    ))
            i += 1
            continue

        # Bloco multi-linha: procura um "x" isolado nas próximas linhas.
        if X_ONLY_RE.match(line) and current_date:
            # mandante = linha(s) anteriores válidas mais próximas
            j = i - 1
            mandante = ""
            while j >= 0 and j >= i - 4:
                cand = lines[j]
                if parse_date_any(cand) or X_ONLY_RE.match(cand):
                    break
                if not is_bad_name(cand):
                    mandante = cand
                    break
                j -= 1

            visitante = ""
            hora = ""
            k = i + 1
            steps = 0
            while k < n and steps < 4:
                cand = lines[k]
                if DETALHES_RE.search(cand):
                    k += 1
                    break
                if parse_date_any(cand):
                    break
                th = parse_time_any(cand)
                if th and clean_text(cand) == th:
                    hora = th
                    k += 1
                    steps += 1
                    continue
                if not is_bad_name(cand) and not visitante:
                    visitante = cand
                k += 1
                steps += 1

            if mandante and visitante and not is_bad_name(mandante) and not is_bad_name(visitante) and mandante != visitante:
                out.append(Partido(
                    fonte="FBF",
                    competicao=f"Brasil - FBF - {competicao_atual}",
                    data=current_date,
                    hora=hora,
                    mandante=mandante,
                    visitante=visitante,
                    pais="Brasil",
                    cidade="",
                    estadio="",
                    rodada=current_round,
                    url=url,
                    extra=f"pais=Brasil; estado=Bahia; codigo_fbf={cid}; origem=bloco_multilinha",
                ))
            i = max(k, i + 1)
            continue

        i += 1

    return out


def parse_carousel_fbf(lines: list[str], url: str, cid: str, competicao_nome: str) -> list[Partido]:
    """Extrai jogos do carrossel encontrado em /competicoes/{id}:

        Rodada 11
        Previous
        Next
        Arena Fonte Nova
        07/03/2026 17:00
        ECB
        2
        1
        ECV
        DETALHES DE JOGO

    Diferente do formato da home: tem estádio, data+hora juntos numa linha,
    e placar (não usa "x" como separador).
    """
    out: list[Partido] = []
    n = len(lines)
    i = 0
    while i < n:
        if not RODADA_STRICT_RE.match(lines[i]):
            i += 1
            continue

        rodada = clean_text(lines[i])
        j = i + 1
        while j < n and norm(lines[j]) in ("previous", "next", "anterior", "proxima", "próxima"):
            j += 1

        estadio = ""
        if j < n and not DATE_NUM_RE.search(lines[j]) and not is_bad_name(lines[j]) and len(lines[j]) <= 60:
            estadio = clean_text(lines[j])
            j += 1

        data = ""
        hora = ""
        if j < n and DATE_NUM_RE.search(lines[j]):
            data = parse_date_any(lines[j])
            hora = parse_time_any(lines[j])
            j += 1

        if not data:
            i += 1
            continue

        mandante = ""
        if j < n and not is_bad_name(lines[j]):
            mandante = clean_text(lines[j])
            j += 1

        placar_m = ""
        if j < n and re.fullmatch(r"\d{1,2}", clean_text(lines[j])):
            placar_m = clean_text(lines[j])
            j += 1

        placar_v = ""
        if j < n and re.fullmatch(r"\d{1,2}", clean_text(lines[j])):
            placar_v = clean_text(lines[j])
            j += 1

        visitante = ""
        if j < n and not is_bad_name(lines[j]):
            visitante = clean_text(lines[j])
            j += 1

        if mandante and visitante and data and mandante != visitante:
            extra = ["pais=Brasil", "estado=Bahia", f"codigo_fbf={cid}", "origem=carrossel_rodada"]
            if placar_m or placar_v:
                extra.append(f"placar={placar_m}x{placar_v}")
            out.append(Partido(
                fonte="FBF",
                competicao=f"Brasil - FBF - {competicao_nome}",
                data=data,
                hora=hora,
                mandante=mandante,
                visitante=visitante,
                pais="Brasil",
                cidade="",
                estadio=estadio,
                rodada=rodada,
                url=url,
                extra="; ".join(extra),
            ))

        i = max(j, i + 1)

    return out


def render_page_collect(item: dict, wait_ms: int, click: bool, debug_html: bool) -> tuple[list[Partido], dict, list[dict]]:
    cid = str(item["id"])
    url = item["url"]
    nome = item.get("nome", f"FBF {cid}")

    network = []
    network_partidos = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="pt-BR",
            ignore_https_errors=True,
        )
        page = context.new_page()

        def on_response(response):
            rurl = response.url
            ct = response.headers.get("content-type", "")
            row = {
                "id": cid,
                "url": rurl,
                "status": response.status,
                "content_type": ct,
                "interessante": "fbf.org.br" in rurl.lower(),
            }
            if "fbf.org.br" in rurl.lower():
                try:
                    if any(x in ct.lower() for x in ["json", "text", "html", "javascript"]):
                        txt = response.text()
                        row["sample"] = clean_text(txt[:500])
                        try:
                            payload = json.loads(txt)
                            found = walk_json(payload, rurl, cid, nome)
                            row["matches_json"] = len(found)
                            network_partidos.extend(found)
                        except Exception:
                            lines = html_to_lines(txt)
                            comp = detect_competicao(lines, nome)
                            found = parse_text_patterns_fbf(lines, rurl, cid, comp)
                            row["matches_text"] = len(found)
                            network_partidos.extend(found)
                except Exception as e:
                    row["read_error"] = str(e)
            network.append(row)

        page.on("response", on_response)

        info = {
            "id": cid,
            "url": url,
            "nome": nome,
            "origem": item.get("origem", ""),
            "status": "",
            "bytes": 0,
            "competicao_detectada": "",
            "jogos": 0,
            "erro": "",
            "final_url": "",
            "amostra_linhas": [],
            "network_matches": 0,
        }

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=70000)
            page.wait_for_timeout(wait_ms)

            try:
                page.wait_for_function(
                    """() => {
                        const t = document.body ? document.body.innerText : '';
                        return t && t.length > 300;
                    }""",
                    timeout=15000
                )
            except Exception:
                pass

            if click:
                try:
                    selects = page.locator("select")
                    scount = min(selects.count(), 5)
                    for si in range(scount):
                        options = selects.nth(si).locator("option")
                        opt_count = min(options.count(), 30)
                        for oi in range(opt_count):
                            try:
                                val = options.nth(oi).get_attribute("value")
                                if val is not None:
                                    selects.nth(si).select_option(value=val, timeout=1500)
                                    page.wait_for_timeout(1500)
                            except Exception:
                                pass
                except Exception:
                    pass

                for selector in ["a", "button", ".btn", "li", ".aba", ".nav-link", ".tab"]:
                    try:
                        locs = page.locator(selector)
                        count = min(locs.count(), 40)
                        for i in range(count):
                            try:
                                txt = clean_text(locs.nth(i).inner_text(timeout=300))
                                ntx = norm(txt)
                                if any(k in ntx for k in ["fase", "rodada", "proximos", "jogos", "tabela", "grupo", "serie a", "serie b", "sub 20", "sub 17", "sub 15"]):
                                    locs.nth(i).click(timeout=800)
                                    page.wait_for_timeout(1200)
                            except Exception:
                                pass
                    except Exception:
                        pass

            html = page.content()
            final_url = page.url
            info["status"] = "rendered"
            info["final_url"] = final_url
            info["bytes"] = len(html.encode("utf-8"))

            lines = html_to_lines(html)
            comp = detect_competicao(lines, nome)
            info["competicao_detectada"] = comp
            info["amostra_linhas"] = lines[:250]

            page_partidos = parse_text_patterns_fbf(lines, final_url, cid, comp)
            page_partidos.extend(parse_carousel_fbf(lines, final_url, cid, comp))
            info["jogos"] = len(page_partidos)
            info["network_matches"] = len(network_partidos)

            # Carrossel de rodadas em /competicoes/{id}: clica em "Next"
            # repetidamente e recaptura o texto a cada passo, pra pegar
            # várias rodadas (não só a que carrega por padrão).
            rodadas_capturadas = 0
            try:
                next_btn = None
                for sel in ["button", "a", "li", "span", ".btn"]:
                    locs = page.locator(sel)
                    count = min(locs.count(), 60)
                    for bi in range(count):
                        try:
                            txt = norm(locs.nth(bi).inner_text(timeout=250))
                        except Exception:
                            continue
                        if txt == "next":
                            next_btn = locs.nth(bi)
                            break
                    if next_btn is not None:
                        break

                if next_btn is not None:
                    for _ in range(20):
                        try:
                            next_btn.click(timeout=1000)
                        except Exception:
                            break
                        page.wait_for_timeout(1000)
                        step_html = page.content()
                        step_lines = html_to_lines(step_html)
                        step_partidos = parse_carousel_fbf(step_lines, final_url, cid, comp)
                        before = len(page_partidos)
                        existing_ids = {p.id for p in page_partidos}
                        for sp in step_partidos:
                            if sp.id not in existing_ids:
                                page_partidos.append(sp)
                                existing_ids.add(sp.id)
                        if len(page_partidos) > before:
                            rodadas_capturadas += 1
                        else:
                            # Não achou jogo novo: provavelmente deu a volta
                            # no carrossel ou chegou no fim.
                            pass
            except Exception:
                pass

            info["jogos"] = len(page_partidos)
            info["rodadas_carrossel_capturadas"] = rodadas_capturadas

            if debug_html:
                HTML_DIR.mkdir(exist_ok=True)
                (HTML_DIR / f"fbf_{cid}.html").write_text(html, encoding="utf-8")
                (HTML_DIR / f"fbf_{cid}_lines.txt").write_text("\n".join(lines), encoding="utf-8")

            browser.close()
            return page_partidos, info, network

        except Exception as e:
            info["erro"] = str(e)
            try:
                browser.close()
            except Exception:
                pass
            return network_partidos, info, network


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
    parser.add_argument("--max-id", type=int, default=40, help="maior id de /competicoes/{id} a tentar")
    parser.add_argument("--dias", type=int, default=365)
    parser.add_argument("--dias-atras", type=int, default=30)
    parser.add_argument("--incluir-passados", action="store_true")
    parser.add_argument("--somente-id", action="append", default=[], help="use 'home' para só a página inicial")
    parser.add_argument("--wait-ms", type=int, default=12000)
    parser.add_argument("--sem-clicar", action="store_true")
    parser.add_argument("--debug-html", action="store_true")
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    urls = discover_urls(args.max_id)
    if args.somente_id:
        wanted = set(str(x) for x in args.somente_id)
        urls = [u for u in urls if str(u["id"]) in wanted]

    all_partidos = []
    debug_pages = []
    debug_network = []

    print(f"[INFO] FBF páginas a testar: {len(urls)}")
    print(f"[INFO] Janela: {desde.isoformat()} até {ate.isoformat()}")

    for item in urls:
        partidos, info, network = render_page_collect(
            item,
            wait_ms=args.wait_ms,
            click=not args.sem_clicar,
            debug_html=args.debug_html,
        )
        debug_pages.append(info)
        debug_network.extend(network)

        partidos = [p for p in partidos if in_window(p, desde, ate, args.incluir_passados)]
        all_partidos.extend(partidos)

        if info.get("jogos") or info.get("network_matches") or len(partidos):
            print(
                f"[OK] id={item['id']} | {info.get('competicao_detectada')} | "
                f"page={info.get('jogos')} network={info.get('network_matches')} | na janela={len(partidos)}"
            )
        else:
            print(f"[--] id={item['id']} | sem jogos | linhas={len(info.get('amostra_linhas', []))}")

    all_partidos = dedupe_partidos(all_partidos)
    rows_new = [p.to_row() for p in all_partidos]

    (OUT_DIR / "debug_fbf_competicoes_urls.json").write_text(json.dumps(urls, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "debug_fbf_competicoes_pages.json").write_text(json.dumps(debug_pages, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "debug_fbf_competicoes_network.json").write_text(json.dumps(debug_network, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "debug_fbf_competicoes_raw.json").write_text(json.dumps(rows_new, ensure_ascii=False, indent=2), encoding="utf-8")

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    merged_current = merge_rows(load_json_rows(current_json), rows_new)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    merged_history = merge_rows(load_csv_rows(history_csv), rows_new)
    write_csv(history_csv, merged_history)

    print("")
    print(f"FBF jogos válidos adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")
    print("Debug páginas: data/debug_fbf_competicoes_pages.json")
    print("Debug rede: data/debug_fbf_competicoes_network.json")
    print("Debug jogos: data/debug_fbf_competicoes_raw.json")
    if args.debug_html:
        print("HTML renderizado: data/debug_fbf_html/")


if __name__ == "__main__":
    main()
