#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper - Federação Paranaense de Futebol (FPF-PR)
https://federacaopr.com.br/

Cobre as 4 competições "Profissionais" de 2026:
  - Copa Paraná 2026
  - Paranaense 2026 (1a divisão)
  - Segundona 2026 (2a divisão)
  - Terceirona 2026 (3a divisão)

POR QUE ESTE SCRIPT NÃO USA PLAYWRIGHT / NÃO LÊ O WIDGET DA HOME:
A página https://federacaopr.com.br/campeonato/profissional/ mostra os jogos
num widget carregado por JavaScript (troca de abas por competição, setas de
rodada). O backend real por trás desse widget parece ser um serviço da CBF
(servicos-fdrs.cbf.com.br / campeonatos.cbf.com.br), e AMBOS os domínios
bloqueiam acesso automatizado via robots.txt. Não há forma de contornar isso
sem violar o robots.txt, então essa via foi descartada.

A ALTERNATIVA (usada aqui): a FPF publica notícias em texto normal (HTML
comum, sem JS) toda vez que divulga uma tabela/rodada, com um formato bem
regular, por exemplo:

    27/02 (sexta-feira): 20h – Paraná Clube x Prudentópolis (Vila Capanema)
    28/02 (sábado): 16h – Patriotas x Batel (Atílio Gionédis)
    01/03 (domingo): 15h30 – Paranavaí x Araucária (Waldemiro Wagner)
    16h – Nacional x Toledo (José Carlos Galbier)
    17h – Rio Branco x Laranja Mecânica (Gigante do Itiberê)

Esse padrão foi validado manualmente contra o texto de 2 notícias reais
(Segundona e Terceirona) durante o desenvolvimento deste script, com 9/9
jogos extraídos corretamente. NÃO foi possível testar o crawler completo
(descoberta de notícias + fetch em lote) ao vivo, porque o ambiente onde
este script foi escrito não tem acesso de rede ao domínio federacaopr.com.br
(só a alguns domínios de pacotes). Ver docs_correcoes/ para o checklist de
validação recomendado antes de rodar isso "de verdade" via GitHub Action.

Requisitos:
    pip install requests beautifulsoup4

Uso:
    python scrap_fpf_parana.py --once --dias 365 --debug-html
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
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)
HTML_DIR = OUT_DIR / "debug_fpf_parana_html"

BASE_URL = "https://federacaopr.com.br"

# Páginas de listagem por competição. Cada uma é uma categoria/tag do
# WordPress que reúne as notícias daquela competição (inclusive as de
# "tabela"/"rodada" que nos interessam, misturadas com outras notícias que
# o parser simplesmente vai ignorar por não bater o regex).
LISTAGENS = {
    "Copa Paraná 2026": [
        f"{BASE_URL}/tag/copa-parana/",
        f"{BASE_URL}/category/noticias/copa-parana/",
    ],
    "Paranaense 2026": [
        f"{BASE_URL}/tag/paranaense/",
        f"{BASE_URL}/category/noticias/paranaense/1-divisao/",
    ],
    "Segundona 2026": [
        f"{BASE_URL}/tag/segundona/",
        f"{BASE_URL}/category/noticias/paranaense/2-divisao/",
    ],
    "Terceirona 2026": [
        f"{BASE_URL}/tag/terceirona/",
        f"{BASE_URL}/category/noticias/paranaense/3-divisao/",
    ],
}

# Palavras-chave que uma notícia precisa ter no título para valer a pena
# abrir e tentar extrair jogos dela (evita gastar requests em notícias que
# claramente não têm tabela nenhuma, tipo "fulano marca hat-trick").
PALAVRAS_TABELA = [
    "tabela", "rodada", "datas e hor", "confira os jogos", "jogos da",
    "definidos os jogos", "divulgada a tabela",
]

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

MESES_EXT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}

# Formato principal observado nas notícias da FPF:
#   "27/02 (sexta-feira): 20h – Paraná Clube x Prudentópolis (Vila Capanema)"
#   "16h – Nacional x Toledo (José Carlos Galbier)"   <- mesma data da linha anterior
LINHA_JOGO_RE = re.compile(
    r"^(?:(?P<dia>\d{1,2})/(?P<mes>\d{1,2})\s*(?:\([^)]*\))?\s*:\s*)?"
    r"(?P<hora>\d{1,2})h(?P<min>\d{2})?\s*[–\-:]\s*"
    r"(?P<mandante>.+?)\s+[xX]\s+(?P<visitante>.+?)\s*\((?P<estadio>[^)]+)\)\s*$"
)

# Formato alternativo visto em notícias "Saiba como assistir" (horário de
# transmissão, NÃO tem estádio):
#   "Athletico x Coritiba – 17/01, às 16h: Canal GOAT, no YouTube, e RIC Record"
# O campo depois dos dois-pontos aqui é o CANAL de transmissão, não o
# estádio — por isso vai para `extra`, e `estadio` fica vazio (fica por
# conta do fallback de estádio-padrão-por-mandante, como já fazemos para
# o Chile em script.js).
LINHA_JOGO_ALT_RE = re.compile(
    r"^(?P<mandante>.+?)\s+[xX]\s+(?P<visitante>.+?)\s*[–\-]\s*"
    r"(?P<dia>\d{1,2})/(?P<mes>\d{1,2}).*?(?P<hora>\d{1,2})h(?P<min>\d{2})?"
    r"(?:\s*:\s*(?P<transmissao>.+))?$"
)

RODADA_RE = re.compile(r"(\d+)[ºªa°]\s*[Rr]odada")


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
            self.mandante, self.visitante, self.estadio, self.rodada,
        ])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def to_row(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        d["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
        return d


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return s.lower().strip()


def clean_team_name(nome: str) -> str:
    nome = re.sub(r"\s+", " ", nome).strip(" -–:")
    return nome


def get(url: str, debug_html: bool = False) -> Optional[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        if debug_html:
            HTML_DIR.mkdir(parents=True, exist_ok=True)
            fname = re.sub(r"[^a-zA-Z0-9]+", "_", url)[-120:] + ".html"
            (HTML_DIR / fname).write_text(r.text, encoding="utf-8")
        return r.text
    except Exception as e:
        print(f"[ERRO] GET {url}: {e}", file=sys.stderr)
        return None


def descobrir_urls_noticias(listagem_url: str, debug_html: bool = False, max_paginas: int = 5) -> list[str]:
    """Percorre uma página de listagem (categoria/tag) do WordPress e coleta
    links de notícias cujo título sugere conter uma tabela/rodada. Faz
    paginação simples (?page/2/, ?page/3/, ...) até max_paginas ou até não
    encontrar mais links novos.

    NÃO TESTADO AO VIVO — a estrutura exata dos links (seletor CSS do
    título/link de cada card de notícia) pode variar; por isso a busca de
    links aqui é propositalmente genérica (qualquer <a href> que aponte para
    /noticias/ e cujo texto bata com PALAVRAS_TABELA), em vez de depender de
    uma classe CSS específica que eu não pude inspecionar ao vivo.
    """
    urls: list[str] = []
    vistos: set[str] = set()
    for pagina in range(1, max_paginas + 1):
        url = listagem_url if pagina == 1 else urljoin(listagem_url, f"page/{pagina}/")
        html = get(url, debug_html=debug_html)
        if not html:
            break
        soup = BeautifulSoup(html, "html.parser")
        encontrados_nesta_pagina = 0
        for a in soup.find_all("a", href=True):
            href = a["href"]
            texto = normalize(a.get_text(" "))
            if "/noticias/" not in href:
                continue
            if href in vistos:
                continue
            if not any(p in texto for p in PALAVRAS_TABELA):
                continue
            vistos.add(href)
            urls.append(href)
            encontrados_nesta_pagina += 1
        if encontrados_nesta_pagina == 0:
            break
    return urls


# Linha que contém SÓ a data (às vezes com "\xa0" no lugar do espaço, visto
# em HTML real da FPF): "31/01 (sábado):" ou "01/02 (domingo):"
DATA_ISOLADA_RE = re.compile(r"^(?P<dia>\d{1,2})/(?P<mes>\d{1,2})\s*\([^)]*\)\s*:?\s*$")

# Linha que começa com a hora, com ou sem o resto do jogo na mesma linha:
#   "16h – Cianorte x Coritiba"   (jogo completo na mesma linha)
#   "16h –"                        (equipes vêm na(s) próxima(s) linha(s))
HORA_PREFIXO_RE = re.compile(r"^(?P<hora>\d{1,2})h(?P<min>\d{2})?\s*[–\-]\s*(?P<resto>.*)$")

TEAMS_RE = re.compile(r"^(?P<mandante>.+?)\s+[xX]\s+(?P<visitante>.+)$")

# Linha que é só o estádio entre parênteses: "(Albino Turbay)", "(a definir)"
ESTADIO_LINHA_RE = re.compile(r"^\((?P<estadio>[^)]+)\)$")


def _extrair_jogos_sequencial(linhas: list[str], competicao: str, ano: int, url: str) -> list[Partido]:
    """Parser stateful para o formato real observado em várias notícias da
    FPF, onde data / hora+times / estádio podem vir cada um em sua própria
    linha (o HTML quebra em <br>/<p> no meio do que visualmente é uma frase
    só). Validado contra HTML real (não simulado) de uma notícia de tabela
    do Paranaense 2026 — ver docs_correcoes/fpf_parana_README.md."""
    partidos: list[Partido] = []
    dia_atual, mes_atual = None, None
    rodada_atual = ""
    i = 0
    n = len(linhas)

    while i < n:
        linha = linhas[i]

        m_rodada = RODADA_RE.search(linha)
        if m_rodada:
            rodada_atual = m_rodada.group(0)

        m_data = DATA_ISOLADA_RE.match(linha)
        if m_data:
            dia_atual, mes_atual = int(m_data.group("dia")), int(m_data.group("mes"))
            i += 1
            continue

        m_hora = HORA_PREFIXO_RE.match(linha)
        if m_hora and dia_atual is not None:
            hora = f"{int(m_hora.group('hora')):02d}:{m_hora.group('min') or '00'}"
            texto_times = m_hora.group("resto").strip()
            j = i
            tentativas = 0
            # os nomes dos times podem continuar na(s) próxima(s) linha(s)
            while not TEAMS_RE.match(texto_times) and tentativas < 3 and j + 1 < n:
                j += 1
                texto_times = (texto_times + " " + linhas[j]).strip()
                tentativas += 1

            m_teams = TEAMS_RE.match(texto_times)
            if m_teams:
                estadio = ""
                k = j + 1
                while k < n and k < j + 3:
                    if DATA_ISOLADA_RE.match(linhas[k]) or HORA_PREFIXO_RE.match(linhas[k]):
                        break
                    m_est = ESTADIO_LINHA_RE.match(linhas[k])
                    if m_est:
                        estadio = m_est.group("estadio").strip()
                        break
                    k += 1

                partidos.append(Partido(
                    fonte="federacaopr.com.br",
                    competicao=competicao,
                    data=f"{ano}-{mes_atual:02d}-{dia_atual:02d}",
                    hora=hora,
                    mandante=clean_team_name(m_teams.group("mandante")),
                    visitante=clean_team_name(m_teams.group("visitante")),
                    estadio="" if normalize(estadio) in {"a definir", "por definir", ""} else estadio,
                    rodada=rodada_atual,
                    url=url,
                    extra="status=Sin fecha/hora definida" if normalize(estadio) in {"a definir", "por definir"} else "",
                ))
                i = j + 1
                continue

        i += 1

    return partidos


def extrair_jogos_de_noticia(url: str, html: str, competicao: str, ano: int) -> list[Partido]:
    soup = BeautifulSoup(html, "html.parser")
    # Tenta focar no corpo do artigo (WordPress costuma usar <article> ou
    # a classe "entry-content"); se não achar, usa o body inteiro mesmo,
    # o regex é seletivo o bastante para não pegar lixo do menu/rodapé.
    corpo = soup.find("article") or soup.find(class_=re.compile("entry-content|post-content")) or soup

    texto = corpo.get_text("\n")
    linhas = [l.replace("\xa0", " ").strip() for l in texto.split("\n") if l.strip()]

    partidos: list[Partido] = []
    dia_atual, mes_atual = None, None
    rodada_atual = ""

    for linha in linhas:
        m_rodada = RODADA_RE.search(linha)
        if m_rodada:
            rodada_atual = m_rodada.group(0)

        m = LINHA_JOGO_RE.match(linha)
        if m:
            if m.group("dia"):
                dia_atual, mes_atual = int(m.group("dia")), int(m.group("mes"))
            if dia_atual is None:
                continue
            hora = f"{int(m.group('hora')):02d}:{m.group('min') or '00'}"
            partidos.append(Partido(
                fonte="federacaopr.com.br",
                competicao=competicao,
                data=f"{ano}-{mes_atual:02d}-{dia_atual:02d}",
                hora=hora,
                mandante=clean_team_name(m.group("mandante")),
                visitante=clean_team_name(m.group("visitante")),
                estadio=clean_team_name(m.group("estadio")),
                rodada=rodada_atual,
                url=url,
            ))
            continue

        m2 = LINHA_JOGO_ALT_RE.match(linha)
        if m2:
            hora = f"{int(m2.group('hora')):02d}:{m2.group('min') or '00'}"
            transmissao = clean_team_name(m2.group("transmissao") or "")
            partidos.append(Partido(
                fonte="federacaopr.com.br",
                competicao=competicao,
                data=f"{ano}-{int(m2.group('mes')):02d}-{int(m2.group('dia')):02d}",
                hora=hora,
                mandante=clean_team_name(m2.group("mandante")),
                visitante=clean_team_name(m2.group("visitante")),
                estadio="",
                rodada=rodada_atual,
                url=url,
                extra=f"transmissao: {transmissao}" if transmissao else "",
            ))

    # Formato multi-linha (data / hora+times / estádio cada um em sua linha).
    # Roda sempre também, e o dedupe() final cuida de eventuais jogos que os
    # dois métodos peguem em duplicidade (mesmo id = mesma data/hora/times).
    partidos.extend(_extrair_jogos_sequencial(linhas, competicao, ano, url))

    return partidos


def in_window(p: Partido, desde: date, ate: date) -> bool:
    try:
        dt = date.fromisoformat(p.data)
    except Exception:
        return False
    return desde <= dt <= ate


def dedupe(partidos: list[Partido]) -> list[Partido]:
    seen = set()
    out = []
    for p in partidos:
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


def merge_rows(existing: list[dict], new_rows: list[dict]) -> list[dict]:
    by_id = {}
    for r in existing:
        if r.get("data") and r.get("mandante") and r.get("visitante"):
            by_id[r.get("id") or r["mandante"]] = r
    for r in new_rows:
        if r.get("data") and r.get("mandante") and r.get("visitante"):
            by_id[r["id"]] = r
    return sorted(
        by_id.values(),
        key=lambda r: (r.get("data", ""), r.get("hora", ""), r.get("competicao", ""), r.get("mandante", "")),
    )


def update(ano: int = 2026, dias_atras: int = 30, dias: int = 365,
           debug_html: bool = False, max_paginas: int = 5) -> list[dict]:
    hoje = date.today()
    desde = hoje - timedelta(days=dias_atras)
    ate = hoje + timedelta(days=dias)

    todos: list[Partido] = []
    for competicao, listagens in LISTAGENS.items():
        urls_noticias: list[str] = []
        for listagem_url in listagens:
            urls_noticias.extend(descobrir_urls_noticias(listagem_url, debug_html=debug_html, max_paginas=max_paginas))
        urls_noticias = list(dict.fromkeys(urls_noticias))  # remove duplicatas preservando ordem
        print(f"[{competicao}] {len(urls_noticias)} notícia(s) candidata(s) encontradas")

        for url in urls_noticias:
            html = get(url, debug_html=debug_html)
            if not html:
                continue
            jogos = extrair_jogos_de_noticia(url, html, competicao, ano)
            if jogos:
                print(f"  -> {url}: {len(jogos)} jogo(s)")
            todos.extend(jogos)

    todos = dedupe(todos)
    todos_na_janela = [p for p in todos if in_window(p, desde, ate)]
    print(f"\nTotal de jogos extraídos: {len(todos)} | dentro da janela de datas: {len(todos_na_janela)}")

    rows_new = [p.to_row() for p in todos_na_janela]

    (OUT_DIR / "debug_fpf_parana_raw.json").write_text(
        json.dumps(rows_new, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    json_path = OUT_DIR / "jogos_programados.json"
    csv_path = OUT_DIR / "jogos_programados.csv"
    existing = load_json_rows(json_path)
    merged = merge_rows(existing, rows_new)

    json_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in merged:
            w.writerow({k: r.get(k, "") for k in FIELDS})

    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--once", action="store_true", help="roda uma vez e sai (padrão)")
    parser.add_argument("--ano", type=int, default=2026)
    parser.add_argument("--dias", type=int, default=365, help="janela para frente, em dias")
    parser.add_argument("--dias-atras", type=int, default=30, help="janela para trás, em dias")
    parser.add_argument("--max-paginas", type=int, default=5, help="páginas de listagem por competição")
    parser.add_argument("--debug-html", action="store_true", help="salva o HTML bruto de cada request em data/debug_fpf_parana_html/")
    args = parser.parse_args()

    update(
        ano=args.ano,
        dias_atras=args.dias_atras,
        dias=args.dias,
        debug_html=args.debug_html,
        max_paginas=args.max_paginas,
    )


if __name__ == "__main__":
    main()
