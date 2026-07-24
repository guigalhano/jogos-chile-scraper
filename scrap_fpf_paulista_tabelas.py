#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper - Federação Paulista de Futebol (FPF) - múltiplas competições via PDF

Generaliza o padrão já usado em scrap_copa_paulista.py (que continua existindo
e funcionando sozinho, sem alterações) para várias competições de uma vez,
usando a URL "Repositorio/Competicao/Tabela/{id}/{id}_{timestamp}.pdf" —
um padrão mais estável do que os PDFs anexados a notícias individuais
(Repositorio/Noticia/{id}/...), porque cada competição parece ter 1 URL fixa
de tabela que é atualizada no lugar (mesma URL, conteúdo novo), em vez de uma
nova notícia a cada atualização.

CORREÇÃO (v2): diagnóstico feito sobre os .txt salvos em
data/debug_fpf_paulista_tabelas/ da última execução real (via GitHub Actions)
mostrou que, para 10 das 12 competições da lista, o pdfplumber extrai
perfeitamente a lista de clubes e o template do mata-mata (texto real), mas a
seção "JG RODADA 01 HORÁRIO MANDANTE..." com os jogos rodada-a-rodada vem
COMPLETAMENTE AUSENTE do texto (não embaralhada — ausente mesmo). Isso indica
que essas páginas específicas do PDF não têm camada de texto (são
provavelmente tabelas rasterizadas/vetoriais), então texto puro nunca vai
funcionar nelas, não importa o parser.

Correção: renderiza cada página como imagem via pypdfium2 (já era dependência
do projeto) e roda OCR com pytesseract nela como fallback SEMPRE que o texto
puro da página não contiver "HORÁRIO" + "MANDANTE" (sinal de que a tabela de
jogos não veio). Isso troca as ~10 competições que retornavam 0 jogos por
jogos extraídos via OCR — passível de pequenos erros de OCR, então os jogos
vindos desse caminho são marcados com extra="ocr_fallback" para facilitar
auditoria/revisão manual caso algo saia errado.

⚠️ IMPORTANTE: esta correção não pôde ser validada com rede real ao domínio
futebolpaulista.com.br (ambiente sem acesso a esse domínio). O pipeline OCR
foi testado localmente com uma imagem sintética e funciona, mas a fonte/
qualidade real do PDF da FPF pode se comportar diferente. Rode com
--debug-html e confira o resultado antes de confiar 100% em produção —
idealmente via workflow_dispatch manual, revisando o log e os arquivos em
data/debug_fpf_paulista_tabelas/*_ocr.txt antes de deixar rodar sozinho todo dia.

DOIS FORMATOS DE PDF ENCONTRADOS (validado com conteúdo real de 3 PDFs):

1) FORMATO LISTA (confirmado 100% funcional - Copa Paulista 2026):
     001 19/jul - dom 15:00 SÃO CAETANO FL X SÃO JOSÉ EC S.A.F São Caetano do Sul
   Extração de texto simples funciona perfeitamente aqui.

2) FORMATO GRADE/GRID (visto no Paulistão Feminino 2026 e no Sub-23 2ª
   Divisão 2026): times e rodadas organizados em colunas visuais que a
   extração de texto simples (page.extract_text()) embaralha — os nomes dos
   dois times de um mesmo confronto podem ficar longe um do outro no texto
   corrido. Para esses casos, este script tenta `page.extract_tables()` do
   pdfplumber, que respeita a estrutura de células/colunas do PDF.

Uso:
    python scrap_fpf_paulista_tabelas.py --once --dias 365 --dias-atras 30 --debug-html
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import pdfplumber

try:
    import pypdfium2 as pdfium
    import pytesseract
    from PIL import Image
    OCR_DISPONIVEL = True
except ImportError:
    OCR_DISPONIVEL = False

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)
DEBUG_DIR = OUT_DIR / "debug_fpf_paulista_tabelas"

# Seeds fornecidas manualmente (mesma convenção do SEED_PDF_URL em
# scrap_copa_paulista.py) — mudam de tempos em tempos, então quando o
# scraper parar de achar jogos novos, é sinal de ir atrás de uma URL nova
# (procurar "futebolpaulista.com.br Repositorio Competicao Tabela <nome>").
PDF_URLS = [
    "https://futebolpaulista.com.br/Repositorio/Competicao/Tabela/1628/1628_639149716452549605.pdf",
    "https://futebolpaulista.com.br/Repositorio/Competicao/Tabela/1610/1610_639124531966973263.pdf",
    "https://futebolpaulista.com.br/Repositorio/Competicao/Tabela/1573/1573_639142723083886749.pdf",
    "https://futebolpaulista.com.br/Repositorio/Competicao/Tabela/1621/1621_639142738433089344.pdf",
    "https://futebolpaulista.com.br/Repositorio/Competicao/Tabela/1633/1633_639166215861105962.pdf",
    "https://futebolpaulista.com.br/Repositorio/Competicao/Tabela/1600/1600_639142737232387937.pdf",
    "https://futebolpaulista.com.br/Repositorio/Competicao/Tabela/1612/1612_639142737530839548.pdf",
    "https://futebolpaulista.com.br/Repositorio/Competicao/Tabela/1597/1597_639142737100772921.pdf",
    "https://futebolpaulista.com.br/Repositorio/Competicao/Tabela/1595/1595_639142737396857731.pdf",
    "https://futebolpaulista.com.br/Repositorio/Competicao/Tabela/1584/1584_639142737876468197.pdf",
    "https://futebolpaulista.com.br/Repositorio/Competicao/Tabela/1579/1579_639142738037570503.pdf",
    "https://futebolpaulista.com.br/Repositorio/Competicao/Tabela/1578/1578_639142738191499345.pdf",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
    "Referer": "https://futebolpaulista.com.br/",
}

FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em", "pais", "cidade",
]

MESES = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}

# "001 17/jul - sex 19:30 MARÍLIA AC X GRÊMIO PRUDENTE Marília 2"
LINHA_JOGO_RE = re.compile(
    r"^(?P<jg>\d{3})\s+"
    r"(?P<dia>\d{1,2})/(?P<mes>jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)"
    r"\s*-\s*\w{3}\s+"
    r"(?P<hora>\d{1,2})\s*(?::|h)\s*(?P<minuto>\d{2})\s+"
    r"(?P<resto>.+)$",
    re.IGNORECASE,
)

RODADA_HEADER_RE = re.compile(r"^JG\s+RODADA\s+(\d+)", re.IGNORECASE)

# Nome da competição normalmente aparece assim em algum lugar do PDF:
#   "COPA PAULISTA DE FUTEBOL - RIVALO - 2026"
#   "TABELA DO 29º CAMPEONATO PAULISTA DE FUTEBOL FEMININO - 2026"
#   "CAMPEONATO PAULISTA DE FUTEBOL SUB-23 SEGUNDA DIVISÃO - 2026"
NOME_COMPETICAO_RE = re.compile(
    r"((?:TABELA\s+DO\s+)?(?:\d+[ºª°]?\s+)?"
    r"(?:CAMPEONATO\s+PAULISTA|COPA\s+PAULISTA)[^\n]{0,80}?20\d{2})",
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


def clean_text(value) -> str:
    value = "" if value is None else str(value)
    value = value.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", value).strip()


def norm(value) -> str:
    value = unicodedata.normalize("NFD", clean_text(value))
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


CIDADES_CONHECIDAS = {
    "birigui", "lins", "presidente prudente", "marilia", "ribeirao preto",
    "bauru", "piracicaba", "araras", "sao paulo", "osasco", "jundiai",
    "indaiatuba", "santo andre", "taubate", "sao caetano do sul",
    "sao jose dos campos", "diadema", "sao bernardo do campo",
    "mogi das cruzes", "franca", "sorocaba", "campinas", "santos",
    "sao jose do rio preto", "assis", "jose bonifacio", "santa fe do sul",
    "tupa", "santa cruz do rio pardo", "catanduva", "limeira", "mogi mirim",
    "sao carlos", "matao", "guarulhos", "paulinia", "votorantim",
    "guaratingueta", "maua", "itaquaquecetuba", "votuporanga", "leme",
    "aracatuba", "rio claro", "americana", "itu", "atibaia", "suzano",
    "barueri", "braganca paulista", "santana de parnaiba", "salto",
    "embu das artes", "araraquara",
}


def ocr_pagina(pdf_bytes: bytes, indice_pagina: int) -> str:
    """Renderiza uma pagina do PDF como imagem e roda OCR nela.

    Usa pypdfium2 (nao depende de poppler/binario externo, ja era
    dependencia do projeto) + pytesseract (precisa do binario tesseract
    instalado no runner: apt-get install tesseract-ocr tesseract-ocr-por).
    Escala em 3x para melhorar a acuracia do OCR em texto pequeno.
    """
    if not OCR_DISPONIVEL:
        return ""
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
        page = pdf[indice_pagina]
        bitmap = page.render(scale=3.0)
        img: Image.Image = bitmap.to_pil()
        texto = pytesseract.image_to_string(img, lang="por")
        return texto or ""
    except Exception as e:
        print(f"[OCR] falha na pagina {indice_pagina}: {e}", file=sys.stderr)
        return ""


def normalizar_ocr(texto: str) -> str:
    """Conserta colagens comuns de espaco que o OCR costuma introduzir,
    como 'sab09' (falta espaco entre dia da semana e hora) ou
    'EC XCA...' (falta espaco antes do X separador)."""
    texto = re.sub(r"([a-záéíóúâêôãõç])(\d)", r"\1 \2", texto, flags=re.IGNORECASE)
    texto = re.sub(r"(\d)([A-Za-záéíóúâêôãõç])", r"\1 \2", texto)
    texto = re.sub(r"\bX([A-ZÀ-Ú])", r"X \1", texto)
    texto = re.sub(r"([a-zà-ú])X\b", r"\1 X", texto)
    return texto


def fetch_pdf_text(url: str) -> tuple[str, list]:
    """Retorna (texto_simples, lista_de_tabelas_por_pagina).

    Se o texto puro da pagina nao contiver "HORARIO" + "MANDANTE" (sinal
    de que a secao de jogos rodada-a-rodada nao veio como texto real --
    muito comum nas competicoes de base, ver nota no topo do arquivo),
    tenta OCR nessa pagina especifica como fallback e usa o resultado do
    OCR (marcado internamente para o parser sinalizar extra=ocr_fallback).
    """
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    pdf_bytes = r.content
    texto_partes = []
    tabelas = []
    paginas_via_ocr: set[int] = set()
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, page in enumerate(pdf.pages):
            texto_pagina = page.extract_text() or ""
            precisa_ocr = not ("HORÁRIO" in texto_pagina.upper() and "MANDANTE" in texto_pagina.upper())
            if precisa_ocr and OCR_DISPONIVEL:
                texto_ocr = ocr_pagina(pdf_bytes, i)
                if "HORÁRIO" in texto_ocr.upper() and "MANDANTE" in texto_ocr.upper() or re.search(r"\b\d{3}\s+\d{1,2}/", texto_ocr):
                    texto_partes.append(normalizar_ocr(texto_ocr))
                    paginas_via_ocr.add(i)
                    continue
            texto_partes.append(texto_pagina)
            try:
                tabelas.extend(page.extract_tables() or [])
            except Exception:
                pass
    if paginas_via_ocr:
        print(f"    (paginas via OCR: {sorted(paginas_via_ocr)})")
    return "\n".join(texto_partes), tabelas


def detectar_competicao(texto: str, fallback: str) -> str:
    m = NOME_COMPETICAO_RE.search(texto)
    if not m:
        return fallback
    nome = clean_text(m.group(1)).title()
    # Evita duplicar a mesma competição sob dois nomes diferentes: o script
    # scrap_copa_paulista.py (já existente e funcionando) grava seus jogos
    # como "Brasil - FPF - Copa Paulista" — usa o mesmo nome aqui quando o
    # PDF detectado for da Copa Paulista, para que dedupe/merge por
    # competicao+data+times funcione corretamente em vez de duplicar.
    if "copa paulista" in norm(nome):
        return "Brasil - FPF - Copa Paulista"
    return nome


def extract_cidades_dos_clubes(texto: str) -> dict:
    mapa = {}
    for linha in texto.splitlines():
        s = clean_text(linha)
        if not s or not s.isupper():
            continue
        ns = norm(s)
        for cidade in sorted(CIDADES_CONHECIDAS, key=lambda c: -len(c)):
            if ns.endswith(cidade) and ns != cidade:
                nome_time = clean_text(s[: -(len(cidade))]).rstrip()
                mapa[norm(nome_time)] = cidade.title()
                break
    return mapa


def resolver_cidade(nome_time: str, mapa_cidades: dict, cidade_fallback: str) -> str:
    key = norm(nome_time)
    if key in mapa_cidades:
        return mapa_cidades[key]
    for k, cidade in mapa_cidades.items():
        if key in k or k in key:
            return cidade
    return cidade_fallback


def eh_maiusculo(tok: str) -> bool:
    """Um token 'e time' se, ignorando pontuacao/numeros, so tem letras
    maiusculas -- cidade vem em Titulo/minusculas (ex: 'SAO JOSE EC S.A.F'
    vs 'Sao Caetano do Sul'). Tokens sem letra (hifen solto em nomes como
    'COMERCIAL FC - RP') nao quebram o time."""
    letras = [c for c in tok if c.isalpha()]
    if not letras:
        return True
    return all(c == c.upper() for c in letras)


def parse_formato_lista(texto: str, url: str, competicao_nome: str, ano: int) -> list[Partido]:
    """Formato validado 100% com conteúdo real (Copa Paulista 2026)."""
    partidos: list[Partido] = []
    rodada_atual = ""

    for linha in texto.splitlines():
        s = clean_text(linha)
        if not s:
            continue

        m_rodada = RODADA_HEADER_RE.match(s)
        if m_rodada:
            rodada_atual = f"Rodada {m_rodada.group(1)}"
            continue

        m = LINHA_JOGO_RE.match(s)
        if not m:
            continue

        dia = int(m.group("dia"))
        mes = MESES.get(m.group("mes").lower())
        if not mes:
            continue
        try:
            data_iso = date(ano, mes, dia).isoformat()
        except ValueError:
            continue

        hora = f"{int(m.group('hora')):02d}:{m.group('minuto')}"
        resto = m.group("resto")

        tokens = resto.split()
        # O separador "X"/"x" entre mandante e visitante varia por
        # competição: a Copa Paulista usa "X" maiúsculo, mas todas as
        # competições de base/feminino usam "x" minúsculo. A comparação
        # precisa ser case-insensitive, senão essas 10+ competições nunca
        # batem aqui (bug real encontrado em diagnóstico: o texto extraído
        # estava correto, só essa checagem que descartava a linha).
        idx_candidatos = [i for i, t in enumerate(tokens) if t.upper() == "X"]
        if not idx_candidatos:
            continue
        idx_x = idx_candidatos[0]
        mandante = clean_text(" ".join(tokens[:idx_x]))
        resto_direita = tokens[idx_x + 1:]

        visitante_tokens = []
        i = 0
        while i < len(resto_direita) and eh_maiusculo(resto_direita[i]):
            visitante_tokens.append(resto_direita[i])
            i += 1
        visitante = clean_text(" ".join(visitante_tokens))
        cidade_jogo = clean_text(" ".join(resto_direita[i:]))
        # remove eventual numero de canal/TV colado no fim da cidade
        cidade_jogo = re.sub(r"\s+\d+\s*$", "", cidade_jogo).strip()

        if not mandante or not visitante or len(mandante) > 60 or len(visitante) > 60:
            continue

        partidos.append(Partido(
            fonte="FPF",
            competicao=competicao_nome,
            data=data_iso,
            hora=hora,
            mandante=mandante,
            visitante=visitante,
            rodada=rodada_atual,
            url=url,
            cidade=cidade_jogo,
        ))

    return partidos


DATA_RODADA_RE = re.compile(r"(\d{1,2})/(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\s*-\s*\w{3}", re.IGNORECASE)
RODADA_N_RE = re.compile(r"Rodada\s+(\d{1,2})", re.IGNORECASE)
TEAMS_X_RE = re.compile(r"^(?P<mandante>.+?)\s+X\s+(?P<visitante>.+)$", re.IGNORECASE)


def parse_formato_grade(texto: str, tabelas: list, url: str, competicao_nome: str, ano: int) -> list[Partido]:
    """
    Formato "grade" (Feminino, Sub-23, e provavelmente outras). NÃO
    VALIDADO com PDF real — ver aviso no topo do arquivo.

    Estratégia (best-effort): tenta achar pares "Rodada N ... DD/mes" para
    mapear rodada -> data, e linhas "TIME A X TIME B" em qualquer lugar do
    texto ou das tabelas extraídas, associando cada confronto à rodada mais
    recente vista antes dele. Como o layout é em grade, a ordem de leitura
    pode não bater exatamente com a rodada certa — por isso os jogos deste
    formato são sempre gravados com `extra="formato_grade_nao_validado"`,
    para que fiquem fáceis de filtrar/revisar separadamente dos jogos do
    formato lista (esses sim, validados).
    """
    partidos: list[Partido] = []

    rodada_para_data: dict[str, str] = {}
    rodada_atual = ""
    for linha in texto.splitlines():
        s = clean_text(linha)
        m_rodada = RODADA_N_RE.search(s)
        if m_rodada:
            rodada_atual = m_rodada.group(1)
        m_data = DATA_RODADA_RE.search(s)
        if m_data and rodada_atual:
            dia = int(m_data.group(1))
            mes = MESES.get(m_data.group(2).lower())
            if mes:
                try:
                    rodada_para_data[rodada_atual] = date(ano, mes, dia).isoformat()
                except ValueError:
                    pass

    # Percorre tanto o texto corrido quanto as células de tabela (podem se
    # sobrepor; dedupe() no final resolve duplicatas exatas).
    linhas_candidatas = list(texto.splitlines())
    for tabela in tabelas:
        for row in tabela:
            for cell in row:
                if cell:
                    linhas_candidatas.append(clean_text(cell))

    rodada_atual = ""
    for linha in linhas_candidatas:
        s = clean_text(linha)
        if not s:
            continue
        m_rodada = RODADA_N_RE.search(s)
        if m_rodada:
            rodada_atual = m_rodada.group(1)

        m = TEAMS_X_RE.match(s)
        if not m:
            continue
        mandante = clean_text(m.group("mandante"))
        visitante = clean_text(m.group("visitante"))
        if not mandante or not visitante or len(mandante) > 60 or len(visitante) > 60:
            continue

        data_iso = rodada_para_data.get(rodada_atual, "")

        partidos.append(Partido(
            fonte="FPF",
            competicao=competicao_nome,
            data=data_iso,
            hora="",
            mandante=mandante,
            visitante=visitante,
            rodada=f"Rodada {rodada_atual}" if rodada_atual else "",
            url=url,
            extra="formato_grade_nao_validado",
        ))

    return partidos


def in_window(p: Partido, desde: date, ate: date, incluir_passados: bool) -> bool:
    if not p.data:
        return True  # jogos sem data confirmada (formato grade) sempre entram, sem filtro de janela
    try:
        dt = date.fromisoformat(p.data)
    except Exception:
        return False
    return incluir_passados or (desde <= dt <= ate)


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
        key=lambda r: (r.get("data") == "", r.get("data", ""), r.get("hora", ""), r.get("competicao", ""), r.get("mandante", "")),
    )


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def update(ano: int, dias: int, dias_atras: int, incluir_passados: bool, debug_html: bool) -> None:
    today = date.today()
    desde = today - timedelta(days=dias_atras)
    ate = today + timedelta(days=dias)

    if debug_html:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    todos: list[Partido] = []
    for url in PDF_URLS:
        try:
            texto, tabelas = fetch_pdf_text(url)
        except Exception as e:
            print(f"[ERRO] {url}: {e}", file=sys.stderr)
            continue

        if debug_html:
            fname = re.sub(r"[^a-zA-Z0-9]+", "_", url)[-100:] + ".txt"
            (DEBUG_DIR / fname).write_text(texto, encoding="utf-8")

        competicao_nome = detectar_competicao(texto, fallback=f"FPF - {url.rsplit('/', 1)[-1]}")

        jogos_lista = parse_formato_lista(texto, url, competicao_nome, ano)
        if jogos_lista:
            print(f"[{competicao_nome}] formato lista: {len(jogos_lista)} jogo(s)")
            todos.extend(jogos_lista)
            continue

        # O fallback de formato grade (pdfplumber.extract_tables) foi testado
        # ao vivo via GitHub Actions e produziu dados INCORRETOS — o texto de
        # cabeçalho (número do jogo, data, hora) ficou colado ao nome do
        # time em vez de virar campos separados. Em vez de gravar dados
        # errados, este PDF é pulado e reportado aqui para revisão manual.
        print(f"[{competicao_nome}] formato não reconhecido (nem lista nem grade confiável) — pulado. URL: {url}")

    todos = dedupe(todos)
    na_janela = [p for p in todos if in_window(p, desde, ate, incluir_passados)]
    print(f"\nTotal extraído: {len(todos)} | dentro da janela: {len(na_janela)}")

    rows_new = [p.to_row() for p in na_janela]

    (OUT_DIR / "debug_fpf_paulista_tabelas_raw.json").write_text(
        json.dumps(rows_new, ensure_ascii=False, indent=2), encoding="utf-8"
    )

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
    parser.add_argument("--debug-html", action="store_true", help="salva o texto extraído de cada PDF em data/debug_fpf_paulista_tabelas/")
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
