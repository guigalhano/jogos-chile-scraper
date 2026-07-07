#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper FMF v2 - com Playwright

Motivo:
A página da FMF retorna HTML inicial com:
- "Selecione uma fase da competição"
- "Aguarde um momento, por favor"

Ou seja, os jogos são carregados depois por JavaScript/AJAX.

Este script:
1. Abre ProxJogos.aspx?d=... com Playwright.
2. Espera o carregamento dinâmico.
3. Clica/troca selects de fases quando existirem.
4. Captura HTML renderizado e respostas JSON/HTML de rede.
5. Extrai jogos do texto renderizado e dos payloads.
6. Salva no padrão do projeto.

IMPORTANTE:
- Esta versão segura usa somente os jogos extraídos do HTML renderizado.
- As respostas de rede continuam no debug, mas não entram no JSON para evitar duplicações.

Requisitos:
    py -m pip install requests beautifulsoup4 playwright
    py -m playwright install chromium

Teste:
    py scrap_fmf_competicoes_playwright.py --somente-d 1 --incluir-passados --debug-html

Completo:
    py scrap_fmf_competicoes_playwright.py --max-d 80 --dias 730 --dias-atras 60 --debug-html
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import signal
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)
HTML_DIR = OUT_DIR / "debug_fmf_html"

BASE_URL = "http://www.fmf.com.br/"
PROX_URL = "http://www.fmf.com.br/Competicoes/ProxJogos.aspx"

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
JOGO_RE = re.compile(r"Jogo\s+(\d+)", re.I)
RODADA_RE = re.compile(r"(?:RODADA|Rodada)\s+([^\n|]+)", re.I)
VERSUS_RE = re.compile(r"(.{2,80}?)\s+(?:x|X|×|vs\.?|v/s)\s+(.{2,80})")

BAD = {
    "fmf federação mineira de futebol", "federação mineira de futebol",
    "selecione uma fase da competição", "aguarde um momento por favor",
    "por favor aguarde isto pode levar alguns segundos", "voltar",
    "tabela completa", "classificação", "classificacao", "artilharia",
    "regulamento", "documentos", "notícias", "noticias", "imprensa",
    "home", "competições", "competicoes", "seleção", "selecao",
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


CONECTIVOS_PT = {"de", "da", "do", "das", "dos", "e"}


def normalizar_cidade(x: str) -> str:
    """Cidades vêm em CAIXA ALTA da FMF (ex.: 'BELO HORIZONTE',
    'SÃO JOSÉ DOS CAMPOS'). Converte para Title Case mantendo conectivos em
    minúsculo ('de', 'da', 'do', 'dos', 'das', 'e'), sem mexer no primeiro
    termo mesmo que seja um conectivo."""
    s = clean_text(x)
    if not s:
        return s
    palavras = s.split(" ")
    out = []
    for i, p in enumerate(palavras):
        pl = p.lower()
        if i > 0 and pl in CONECTIVOS_PT:
            out.append(pl)
        else:
            out.append(pl.capitalize())
    return " ".join(out)


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
    if len(clean_text(x)) > 80:
        return True
    if re.fullmatch(r"\d+", clean_text(x)):
        return True
    if any(k in s for k in ["copyright", "todos os direitos", "aguarde", "selecione uma fase"]):
        return True
    return False


def discover_urls(max_d: int) -> list[dict]:
    found = {}

    # Home pode listar links reais.
    for home in ["http://www.fmf.com.br/", "https://www.fmf.com.br/"]:
        try:
            r = requests.get(home, headers=HEADERS, timeout=45)
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a"):
                href = a.get("href") or ""
                text = clean_text(a.get_text(" ", strip=True))
                if "Competicoes/ProxJogos.aspx" not in href:
                    continue
                url = urljoin(home, href)
                qs = parse_qs(urlparse(url).query)
                d = (qs.get("d") or [""])[0]
                if d:
                    found[d] = {"d": d, "url": url, "nome": text or f"FMF d={d}", "origem": "home"}
        except Exception:
            pass

    for d in range(1, max_d + 1):
        sd = str(d)
        if sd not in found:
            found[sd] = {
                "d": sd,
                "url": f"{PROX_URL}?d={d}&a=t",
                "nome": f"FMF d={d}",
                "origem": "range",
            }

    return sorted(found.values(), key=lambda x: int(x["d"]) if str(x["d"]).isdigit() else 999999)


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


NOMES_GENERICOS = {"tabela completa", "tabela", "proxjogos", "competicoes"}
NOMES_AMBIGUOS_RE = re.compile(r"^(1|2)ª?\s*divis[aã]o$", re.IGNORECASE)
HIERARQUIA_CATEGORIAS: dict[str, str] = {}  # preenchido uma vez em main()


def resolve_competicao(nome: str, lines: list[str], d: str = "") -> str:
    """FIX: detect_competicao() varria o texto da página procurando por
    palavras-chave de competição, mas a barra lateral de navegação da FMF
    (que lista TODAS as competições: MÓDULO I, MÓDULO II, SEGUNDA DIVISÃO...)
    aparece no topo de toda página, idêntica não importa qual "d" você está
    vendo. Como "MÓDULO I" é o primeiro item dessa lista, a varredura por
    texto sempre "detectava" MÓDULO I, mesmo em páginas de TAÇA BH, COPA
    ITATIAIA, SFAC etc. — o texto da barra lateral, não o conteúdo real da
    página.

    O nome real e confiável já vem do link clicado para descobrir esse "d"
    (ex.: "TAÇA BH", "COPA ITATIAIA", "FEMININO SUB-17"). Usamos isso como
    fonte primária; só caímos para a varredura de texto quando o nome for
    genérico demais (ex.: "TABELA COMPLETA", que não diz qual competição).

    Nomes como "1ª Divisão" se repetem em várias categorias de idade
    (SUB-13, SUB-14, SUB-15...) e sozinhos não dizem qual — usa
    HIERARQUIA_CATEGORIAS (descoberta uma vez via discover_hierarchy_via_playwright)
    para prefixar com a categoria correta quando disponível."""
    base = nome if (nome and norm(nome) not in NOMES_GENERICOS) else detect_competicao(lines, nome)

    if NOMES_AMBIGUOS_RE.match(clean_text(base)) and d in HIERARQUIA_CATEGORIAS:
        base = f"{HIERARQUIA_CATEGORIAS[d]} - {base}"

    ano = str(datetime.now().year)
    if ano not in base:
        base = f"{base} - {ano}"

    return base


def detect_competicao(lines: list[str], fallback: str) -> str:
    for line in lines[:120]:
        s = clean_text(line)
        ns = norm(s)
        if " - 20" in s and not any(k in ns for k in ["fmf", "federa", "noticia", "copyright"]):
            return s
        if any(k in ns for k in ["modulo", "segunda divisao", "sub 20", "sub 17", "sub 15", "feminino", "copa", "taca"]):
            if len(s) <= 90 and not any(b in ns for b in ["selecione", "aguarde", "noticias"]):
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


def obj_to_partido(obj: dict, url: str, d: str, competicao_fallback: str, fallback_date: str = "") -> Partido | None:
    if not isinstance(obj, dict):
        return None

    mandante = first_value(obj, ["Mandante", "NomeMandante", "ClubeMandante", "TimeMandante", "EquipeMandante", "mandante"])
    visitante = first_value(obj, ["Visitante", "NomeVisitante", "ClubeVisitante", "TimeVisitante", "EquipeVisitante", "visitante"])
    data = parse_date_any(first_value(obj, ["Data", "DataJogo", "DataFormatada", "DataHora", "DATA_HORA", "Dia"]), fallback=fallback_date)
    hora = parse_time_any(first_value(obj, ["Hora", "Horario", "Horário", "DataHora", "HoraJogo"]))
    estadio = first_value(obj, ["Estadio", "Estádio", "NomeEstadio", "Local", "Campo"])
    cidade = normalizar_cidade(first_value(obj, ["Cidade", "Municipio", "Município"]))
    rodada = first_value(obj, ["Rodada", "Fase"])
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

    extra = [f"pais=Brasil", "estado=Minas Gerais", f"codigo_fmf={d}"]
    if jogo:
        extra.append(f"jogo_numero={jogo}")
    if cidade:
        extra.append(f"cidade={cidade}")

    return Partido(
        fonte="FMF",
        competicao=f"Brasil - FMF - {comp}",
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


def walk_json(data: Any, url: str, d: str, competicao_fallback: str, fallback_date: str = "") -> list[Partido]:
    out = []
    if isinstance(data, dict):
        p = obj_to_partido(data, url, d, competicao_fallback, fallback_date=fallback_date)
        if p:
            out.append(p)
        for v in data.values():
            out.extend(walk_json(v, url, d, competicao_fallback, fallback_date=fallback_date))
    elif isinstance(data, list):
        for item in data:
            out.extend(walk_json(item, url, d, competicao_fallback, fallback_date=fallback_date))
    return out


def parse_text_patterns(lines: list[str], url: str, d: str, competicao_nome: str) -> list[Partido]:
    out = []
    current_date = ""
    current_round = ""

    for i, line in enumerate(lines):
        dt = parse_date_any(line)
        if dt:
            current_date = dt

        mr = RODADA_RE.search(line)
        if mr:
            current_round = clean_text(mr.group(0))

        # Caso linha única: "10/07/2026 20:00 Time A x Time B Estádio Cidade"
        if (" x " in line.lower() or " X " in line) and (parse_date_any(line) or current_date):
            mvs = VERSUS_RE.search(line)
            if mvs:
                before = clean_text(mvs.group(1))
                after = clean_text(mvs.group(2))
                data = parse_date_any(line) or current_date
                hora = parse_time_any(line)
                # remove data/hora do mandante
                before = DATE_NUM_RE.sub("", before)
                before = DATE_LONG_RE.sub("", before)
                before = TIME_RE.sub("", before)
                mandante = clean_text(before)
                visitante = clean_text(after.split(" Jogo ")[0])
                if mandante and visitante and not is_bad_name(mandante) and not is_bad_name(visitante):
                    out.append(Partido(
                        fonte="FMF",
                        competicao=f"Brasil - FMF - {competicao_nome}",
                        data=data,
                        hora=hora,
                        mandante=mandante,
                        visitante=visitante,
                        pais="Brasil",
                        cidade="",
                        estadio="",
                        rodada=current_round,
                        url=url,
                        extra=f"pais=Brasil; estado=Minas Gerais; codigo_fmf={d}; origem=linha_unica",
                    ))

    # Caso estruturado em linhas: data -> hora -> mandante -> X -> visitante -> jogo -> estádio -> cidade
    i = 0
    while i < len(lines):
        line = lines[i]
        dt = parse_date_any(line)
        if dt:
            current_date = dt
            i += 1
            continue
        if RODADA_RE.search(line):
            current_round = clean_text(line)
            i += 1
            continue
        hora = parse_time_any(line)
        if not (current_date and hora and clean_text(line) == hora):
            i += 1
            continue

        j = i + 1
        while j < len(lines) and is_bad_name(lines[j]):
            j += 1
        if j >= len(lines):
            i += 1
            continue
        mandante = clean_text(lines[j]); j += 1

        # procura X/placar
        while j < len(lines) and not re.fullmatch(r"\d*\s*[xX]\s*\d*|[xX]", clean_text(lines[j])):
            if parse_date_any(lines[j]) or parse_time_any(lines[j]) == clean_text(lines[j]):
                break
            j += 1
        if j >= len(lines) or not re.fullmatch(r"\d*\s*[xX]\s*\d*|[xX]", clean_text(lines[j])):
            i += 1
            continue
        placar = clean_text(lines[j]); j += 1

        # FIX: em jogos já disputados, o placar aparece como linhas separadas
        # em volta do "X" (ex.: "BOA" / "2" / "X" / "1" / "NAC.NOVA SERRANA"),
        # não só "2 X 1" numa linha só. Sem isso, o dígito do gol visitante
        # era lido como se fosse o nome do time visitante.
        if j < len(lines) and re.fullmatch(r"\d+", clean_text(lines[j])):
            j += 1

        while j < len(lines) and is_bad_name(lines[j]):
            j += 1
        if j >= len(lines):
            i += 1
            continue
        visitante = clean_text(lines[j]); j += 1

        jogo_num = ""
        estadio = ""
        cidade = ""

        for k in range(j, min(j + 6, len(lines))):
            mj = JOGO_RE.search(lines[k])
            if mj:
                jogo_num = mj.group(1)
                if k + 1 < len(lines):
                    estadio = clean_text(lines[k + 1])
                if k + 2 < len(lines):
                    cidade = normalizar_cidade(lines[k + 2])
                break

        if not is_bad_name(mandante) and not is_bad_name(visitante) and mandante != visitante:
            extra = [f"pais=Brasil", "estado=Minas Gerais", f"codigo_fmf={d}", f"placar_original={placar}"]
            if jogo_num:
                extra.append(f"jogo_numero={jogo_num}")
            if cidade and not is_bad_name(cidade):
                extra.append(f"cidade={cidade}")
            else:
                cidade = ""

            out.append(Partido(
                fonte="FMF",
                competicao=f"Brasil - FMF - {competicao_nome}",
                data=current_date,
                hora=hora,
                mandante=mandante,
                visitante=visitante,
                pais="Brasil",
                cidade=cidade,
                estadio=estadio if not is_bad_name(estadio) else "",
                rodada=current_round,
                url=url,
                extra="; ".join(extra),
            ))
        i = max(j, i + 1)

    return out


def discover_hierarchy_via_playwright(home_url: str) -> dict:
    """Nomes como '1ª Divisão' aparecem repetidos na barra lateral da FMF sob
    várias categorias diferentes (SUB-13, SUB-14, SUB-15, SUB-17, SUB-20), e
    o texto do link sozinho não diz qual delas é. Abre a home UMA vez com
    Playwright (para ver a barra lateral renderizada por JS) e monta um mapa
    d -> categoria (ex.: "13": "SUB-13"), usando a categoria mais recente
    (texto maiúsculo/cabeçalho de seção) que precede cada link na ordem do
    DOM. Retorna {} se não conseguir (comportamento atual como fallback)."""
    mapa: dict[str, str] = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(home_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4000)
            resultado = page.evaluate("""
                () => {
                    const out = {};
                    let categoriaAtual = '';
                    const categoriaRe = /^(MÓDULO\\s+\\S+|SEGUNDA\\s+DIVISÃO|SUB[\\s-]?\\d+|FEMININO(\\s+SUB[\\s-]?\\d+)?|SFAC\\S*)$/i;
                    const nodes = document.querySelectorAll('a, li, span, div');
                    for (const el of nodes) {
                        const text = (el.textContent || '').trim();
                        if (!text || text.length > 60) continue;
                        const link = el.tagName === 'A' ? el : el.querySelector('a[href*="ProxJogos.aspx"]');
                        if (link && link.getAttribute('href') && link.getAttribute('href').includes('d=')) {
                            const href = link.getAttribute('href');
                            const m = href.match(/[?&]d=(\\d+)/);
                            if (m && categoriaAtual) {
                                out[m[1]] = categoriaAtual;
                            }
                        } else if (categoriaRe.test(text) && el.children.length === 0) {
                            categoriaAtual = text.toUpperCase();
                        }
                    }
                    return out;
                }
            """)
            if isinstance(resultado, dict):
                mapa = resultado
            browser.close()
    except Exception as e:
        print(f"[WARN] Falha ao descobrir hierarquia de categorias: {e}", file=sys.stderr)
    return mapa


def render_page_collect(item: dict, wait_ms: int, click: bool, debug_html: bool) -> tuple[list[Partido], dict, list[dict]]:
    d = str(item["d"])
    url = item["url"]
    nome = item.get("nome", f"FMF d={d}")

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
                "d": d,
                "url": rurl,
                "status": response.status,
                "content_type": ct,
                "interessante": "fmf.com.br" in rurl.lower(),
            }
            if "fmf.com.br" in rurl.lower():
                try:
                    if any(x in ct.lower() for x in ["json", "text", "html", "javascript"]):
                        txt = response.text()
                        row["sample"] = clean_text(txt[:500])
                        # tenta JSON
                        try:
                            payload = json.loads(txt)
                            found = walk_json(payload, rurl, d, nome)
                            row["matches_json"] = len(found)
                            network_partidos.extend(found)
                        except Exception:
                            # tenta texto renderizado de resposta
                            lines = html_to_lines(txt)
                            comp = resolve_competicao(nome, lines, d)
                            found = parse_text_patterns(lines, rurl, d, comp)
                            row["matches_text"] = len(found)
                            network_partidos.extend(found)
                except Exception as e:
                    row["read_error"] = str(e)
            network.append(row)

        page.on("response", on_response)

        info = {
            "d": d,
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

            # Espera sair do loading, se possível.
            try:
                page.wait_for_function(
                    """() => {
                        const t = document.body ? document.body.innerText : '';
                        return t && !t.includes('Aguarde um momento') && t.length > 300;
                    }""",
                    timeout=15000
                )
            except Exception:
                pass

            if click:
                # FIX: a FMF costuma exibir por padrão uma tabela antiga (ex.: 2013)
                # mesmo na URL "principal" da competição; o ano atual normalmente é
                # um link separado no menu lateral (ex.: "MÓDULO I - 2026"), montado
                # via JS e por isso invisível ao discover_urls() (que só lê o HTML
                # estático). Aqui procuramos e clicamos nesse link pelo ANO ATUAL
                # antes de tentar qualquer outra interação.
                ano_atual = str(datetime.now().year)
                try:
                    links_ano = page.locator(f"a:has-text('{ano_atual}')")
                    n_links_ano = links_ano.count()
                    if n_links_ano > 0:
                        links_ano.first.click(timeout=2000)
                        page.wait_for_timeout(wait_ms)
                        try:
                            page.wait_for_function(
                                """() => {
                                    const t = document.body ? document.body.innerText : '';
                                    return t && !t.includes('Aguarde um momento') && t.length > 300;
                                }""",
                                timeout=15000
                            )
                        except Exception:
                            pass
                except Exception:
                    pass

                # FIX: a versão anterior clicava em TODAS as opções de TODOS os
                # selects (até 5 x 30 = 150 cliques, ~1.5s cada = até 3.75min só
                # aqui) e depois em TODOS os links/botões que batessem com uma
                # lista de palavras-chave (até 240 elementos verificados). Isso
                # deixava cada competição levando vários minutos. Agora: só
                # seleciona a opção do select que contém o ANO ATUAL no texto
                # (o que realmente importa), e limita a busca por abas/botões a
                # bem menos elementos com espera bem menor.
                try:
                    selects = page.locator("select")
                    scount = min(selects.count(), 5)
                    for si in range(scount):
                        options = selects.nth(si).locator("option")
                        opt_count = min(options.count(), 30)
                        for oi in range(opt_count):
                            try:
                                texto_opt = clean_text(options.nth(oi).inner_text(timeout=300))
                                if ano_atual not in texto_opt:
                                    continue
                                val = options.nth(oi).get_attribute("value")
                                if val is not None:
                                    selects.nth(si).select_option(value=val, timeout=1500)
                                    page.wait_for_timeout(800)
                                break  # achou a opção do ano atual, não precisa testar as outras
                            except Exception:
                                pass
                except Exception:
                    pass

                # Clica só nos primeiros links/botões que batem com palavras-chave
                # relevantes (bem mais rápido que a varredura exaustiva anterior).
                try:
                    locs = page.locator("a, button")
                    count = min(locs.count(), 15)
                    for i in range(count):
                        try:
                            txt = clean_text(locs.nth(i).inner_text(timeout=200))
                            ntx = norm(txt)
                            if any(k in ntx for k in ["fase", "rodada", "proximos", "tabela"]):
                                locs.nth(i).click(timeout=600)
                                page.wait_for_timeout(600)
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
            comp = resolve_competicao(nome, lines, d)
            info["competicao_detectada"] = comp
            info["amostra_linhas"] = lines[:250]

            page_partidos = parse_text_patterns(lines, final_url, d, comp)
            # Por segurança, a função retorna os dois grupos separados.
            # O main decide se aceita ou não os jogos vindos de network.
            all_partidos = page_partidos
            info["jogos"] = len(page_partidos)
            info["network_matches"] = len(network_partidos)

            if debug_html:
                HTML_DIR.mkdir(exist_ok=True)
                (HTML_DIR / f"fmf_d_{d}.html").write_text(html, encoding="utf-8")
                (HTML_DIR / f"fmf_d_{d}_lines.txt").write_text("\n".join(lines), encoding="utf-8")

            browser.close()
            return all_partidos, info, network

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
    hoje = date.today()
    # Trava de segurança: nunca deixa passar dados de anos claramente errados
    # (ex.: a FMF às vezes mostra uma tabela antiga por padrão, como vimos com
    # 2013). Aceita apenas o ano atual.
    if dt.year != hoje.year:
        return False
    # Somente próximos jogos (hoje em diante) — jogos já disputados ficam de
    # fora mesmo com --incluir-passados, que aqui só amplia o limite superior
    # (--dias), não reintroduz o passado.
    if dt < hoje:
        return False
    return dt <= ate


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


class CompeticaoTimeout(Exception):
    """Levantada quando uma única competição trava além do tempo limite."""


def _timeout_handler(signum, frame):
    raise CompeticaoTimeout("Tempo limite excedido para esta competição")


def render_page_collect_com_timeout(item: dict, wait_ms: int, click: bool, debug_html: bool,
                                      timeout_s: int = 90) -> tuple[list, dict, list]:
    """Mesma função render_page_collect, mas com uma trava de segurança de
    tempo (signal.alarm): se uma única competição travar (ex.: Playwright
    esperando por um elemento/navegação que nunca resolve), essa competição
    é abandonada e o script segue para a próxima, em vez de travar o job
    inteiro por horas."""
    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(timeout_s)
    try:
        return render_page_collect(item, wait_ms=wait_ms, click=click, debug_html=debug_html)
    except CompeticaoTimeout:
        info = {
            "d": str(item.get("d")),
            "url": item.get("url", ""),
            "nome": item.get("nome", ""),
            "status": "timeout",
            "erro": f"Excedeu {timeout_s}s, competição pulada",
            "jogos": 0,
            "network_matches": 0,
            "competicao_detectada": "",
            "amostra_linhas": [],
        }
        return [], info, []
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-d", type=int, default=80)
    parser.add_argument("--dias", type=int, default=365)
    parser.add_argument("--dias-atras", type=int, default=30)
    parser.add_argument("--incluir-passados", action="store_true")
    parser.add_argument("--somente-d", action="append", default=[])
    parser.add_argument("--wait-ms", type=int, default=12000)
    parser.add_argument("--sem-clicar", action="store_true")
    parser.add_argument("--debug-html", action="store_true")
    parser.add_argument("--usar-network", action="store_true", help="Reservado para testes. A versão segura salva por padrão somente jogos da página renderizada.")
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    urls = discover_urls(args.max_d)
    if args.somente_d:
        wanted = set(str(x) for x in args.somente_d)
        urls = [u for u in urls if str(u["d"]) in wanted]

    global HIERARQUIA_CATEGORIAS
    HIERARQUIA_CATEGORIAS = discover_hierarchy_via_playwright(BASE_URL)
    print(f"[INFO] Categorias descobertas para desambiguar nomes: {len(HIERARQUIA_CATEGORIAS)}")

    all_partidos = []
    debug_pages = []
    debug_network = []

    print(f"[INFO] FMF competições a testar: {len(urls)}")
    print(f"[INFO] Janela: {desde.isoformat()} até {ate.isoformat()}")

    for item in urls:
        partidos, info, network = render_page_collect_com_timeout(
            item,
            wait_ms=args.wait_ms,
            click=not args.sem_clicar,
            debug_html=args.debug_html,
            timeout_s=90,
        )
        debug_pages.append(info)
        debug_network.extend(network)

        partidos = [p for p in partidos if in_window(p, desde, ate, args.incluir_passados)]
        all_partidos.extend(partidos)

        if info.get("jogos") or info.get("network_matches") or len(partidos):
            print(
                f"[OK] d={item['d']} | {info.get('competicao_detectada')} | "
                f"page={info.get('jogos')} network={info.get('network_matches')} | na janela={len(partidos)}"
            )
        else:
            print(f"[--] d={item['d']} | sem jogos | linhas={len(info.get('amostra_linhas', []))}")

    all_partidos = dedupe_partidos(all_partidos)
    rows_new = [p.to_row() for p in all_partidos]

    (OUT_DIR / "debug_fmf_competicoes_urls.json").write_text(json.dumps(urls, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "debug_fmf_competicoes_pages.json").write_text(json.dumps(debug_pages, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "debug_fmf_competicoes_network.json").write_text(json.dumps(debug_network, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "debug_fmf_competicoes_raw.json").write_text(json.dumps(rows_new, ensure_ascii=False, indent=2), encoding="utf-8")

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    merged_current = merge_rows(load_json_rows(current_json), rows_new)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    merged_history = merge_rows(load_csv_rows(history_csv), rows_new)
    write_csv(history_csv, merged_history)

    print("")
    print(f"FMF jogos válidos adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")
    print("Debug páginas: data/debug_fmf_competicoes_pages.json")
    print("Debug rede: data/debug_fmf_competicoes_network.json")
    print("Debug jogos: data/debug_fmf_competicoes_raw.json")
    if args.debug_html:
        print("HTML renderizado: data/debug_fmf_html/")


if __name__ == "__main__":
    main()
