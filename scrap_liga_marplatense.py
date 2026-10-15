#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Liga Marplatense de Futbol (LMF) - Primera Division e femenino, Mar del Plata.

Por que nao o SofaScore: a liga existe la (uniqueTournament 37591, categoria
"Argentina Amateur"), mas em 14/10/2026 a temporada 2026 nao tinha nenhum
jogo cadastrado (events/last e events/next = 404). A LMF tambem nao tem
site (lmf.com.ar = "En construccion") - divulga a programacao para a
imprensa local.

Fonte: El Marplatense (elmarplatense.com), que publica toda semana a
programacao oficial da fecha. Os artigos sao achados pelo sitemap mensal
(https://www.elmarplatense.com/sitemap.xml/notes/AAAA/M) - o site nao tem
RSS e as paginas de etiqueta vem desordenadas.

O texto muda de semana para semana; o parser aceita os formatos vistos:

  2025: "PROGRAMACION - TERCERA FECHA - TORNEO CLAUSURA"
        "SABADO 19 DE JULIO DE 2025"
        "Cancha: River - River vs Deportivo Norte"
        "Primera (15:15hs): arbitros"      (ou so "15:15hs: arbitros")
  2026: "afrontara este sabado 26 de septiembre una nueva jornada"
        "La jornada de Primera comenzara a las 16, con los siguientes encuentros:"
        "Alvarado vs. Talleres, en Alvarado."
        "Libertad vs. Quilmes - Arbitros: Romero, Cajal y Arrendazzi."
        "El partido ... entre Al Ver Veraz y Almagro Florida se disputara el
         miercoles 14 de octubre a las 16 hs."

So entra jogo em que OS DOIS times sao clubes conhecidos da LMF (lista
abaixo) - assim noticias de Aldosivi, Alvarado no Federal A, Selecao etc.
nao viram jogo da liga por engano. Clube novo na liga = acrescentar em
CLUBES_LMF (o log mostra os "vs" descartados por time desconhecido).

Uso:
  python scrap_liga_marplatense.py --meses 2
  python scrap_liga_marplatense.py --url https://www.elmarplatense.com/<artigo>   # testar um artigo
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from argentina_comum import OUT_DIR

BASE = "https://www.elmarplatense.com"
RAW_JOGOS = OUT_DIR / "debug_liga_marplatense_raw.json"
DEBUG_ARTIGOS = OUT_DIR / "debug_liga_marplatense_artigos.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
}

MDP_LAT, MDP_LNG = -38.0055, -57.5426

# Clubes da LMF (Primera e femenino) - nome canonico: aliases normalizados.
CLUBES_LMF = {
    "Aldosivi": ["aldosivi"],
    "Al Ver Verás": ["al ver veras", "al ver veraz"],
    "Almagro Florida": ["almagro florida", "almagro"],
    "Alvarado": ["alvarado"],
    "Argentinos del Sud": ["argentinos del sud", "argentinos"],
    "Atlético Mar del Plata": ["atletico mar del plata", "atletico mdp", "mar del plata", "atletico"],
    "Banfield (MdP)": ["banfield"],
    "Boca (MdP)": ["boca", "boca juniors"],
    "Cadetes de San Martín": ["cadetes", "cadetes de san martin"],
    "Chapadmalal": ["chapadmalal"],
    "Círculo Deportivo": ["circulo deportivo", "circulo"],
    "Colegiales (MdP)": ["colegiales"],
    "Deportivo Norte": ["deportivo norte", "norte"],
    "El Cañón": ["el canon", "canon"],
    "El Siciliano": ["el siciliano", "siciliano"],
    "General Mitre (MdP)": ["general mitre", "gral mitre", "mitre"],
    "General Urquiza (MdP)": ["general urquiza", "gral urquiza", "urquiza"],
    "Independiente (MdP)": ["independiente"],
    "Kimberley": ["kimberley"],
    "Libertad (MdP)": ["libertad"],
    "Los Patos": ["los patos"],
    "Nación": ["nacion", "club nacion"],
    "Once Unidos": ["once unidos"],
    "Peñarol (MdP)": ["penarol"],
    "Quilmes (MdP)": ["quilmes", "quilmes mdp"],
    "Racing (MdP)": ["racing"],
    "River (MdP)": ["river", "river plate"],
    "San Isidro (MdP)": ["san isidro", "casi"],
    "San José (MdP)": ["san jose"],
    "San Lorenzo (MdP)": ["san lorenzo"],
    "Talleres (MdP)": ["talleres"],
    "Unión (MdP)": ["union"],
}

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
DIAS_SEMANA = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}

SLUG_RE = re.compile(r"liga-marplatense|futbol-local|torneo-local|primera|fecha|clausura|apertura|16avos|dieciseisavos|octavos|cuartos|semifinal|final|femenin", re.I)


def norm(v) -> str:
    v = unicodedata.normalize("NFD", str(v or ""))
    v = "".join(c for c in v if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", v.lower()).strip()


_ALIAS = {}
for _nome, _als in CLUBES_LMF.items():
    for _a in [_nome] + _als:
        _ALIAS[norm(re.sub(r"\(.*?\)", "", _a))] = _nome


def clube(txt: str) -> str | None:
    """Nome canonico se o texto for um clube da LMF. Aceita lixo na frente
    ("Cajal y Arrendazzi. Independiente" -> Independiente: o regex do "vs"
    pega o fim da linha de arbitros do jogo anterior)."""
    palavras = re.sub(r"^(?:cancha|en cancha de|en)\s+", "", norm(txt)).split()
    for i in range(len(palavras)):
        achou = _ALIAS.get(" ".join(palavras[i:]))
        if achou:
            return achou
    return None


@dataclass
class Jogo:
    competicao: str
    data: str
    hora: str
    mandante: str
    visitante: str
    estadio: str = ""
    rodada: str = ""
    url: str = ""
    extra: str = ""

    def to_row(self) -> dict:
        d = asdict(self)
        # escopo "Regional": liga local (botao "Regional" da pagina, como as
        # federacoes estaduais do Brasil)
        d.update(fonte="El Marplatense", pais="Argentina", cidade="Mar del Plata",
                 lat=MDP_LAT, lng=MDP_LNG, escopo="Regional")
        if "Femenino" in self.competicao:
            d["categoria"] = "Femenino"
        raw = "|".join([d["fonte"], self.competicao, self.data, self.hora, self.mandante, self.visitante])
        d["id"] = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
        d["atualizado_em"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return d


def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def urls_candidatas(meses: int) -> list[tuple[str, str]]:
    """(url, lastmod) dos artigos dos ultimos `meses` meses cujo slug
    parece falar da liga."""
    hoje = date.today()
    out = []
    for k in range(meses):
        ano, mes = hoje.year, hoje.month - k
        while mes <= 0:
            mes += 12
            ano -= 1
        try:
            xml = fetch(f"{BASE}/sitemap.xml/notes/{ano}/{mes}")
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] sitemap {ano}/{mes}: {e}")
            continue
        for m in re.finditer(r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>", xml):
            url, lastmod = m.group(1), m.group(2)
            if SLUG_RE.search(url.rsplit("/", 1)[-1]):
                out.append((url, lastmod))
    return out


def texto_artigo(html: str) -> tuple[str, str, str]:
    """(titulo, data_publicacao_iso, texto corrido do corpo)."""
    s = BeautifulSoup(html, "html.parser")
    meta = s.find("meta", property="article:published_time")
    pub = (meta.get("content") if meta else "") or ""
    h1 = s.find("h1")
    titulo = h1.get_text(" ", strip=True) if h1 else ""
    corpo = s.find("article") or s
    for t in corpo(["script", "style", "noscript", "aside", "figure"]):
        t.decompose()
    for br in corpo.find_all("br"):
        br.replace_with("\n")
    for p in corpo.find_all(["p", "li", "h2", "h3", "h4", "div"]):
        p.insert_after("\n")
    txt = corpo.get_text(" ")
    # O corpo termina em "Sobre el autor" / "Relacionadas" (outras noticias).
    txt = re.split(r"Sobre el autor|Relacionadas", txt)[0]
    txt = re.sub(r"[ \t ]+", " ", txt)
    txt = re.sub(r" *\n[ \n]*", "\n", txt)
    return titulo, pub, txt


def _data(dia: int, mes_nome: str, ano: int | None, ref: date) -> date | None:
    mes = MESES.get(norm(mes_nome))
    if not mes:
        return None
    if ano is None:
        ano = ref.year
        # "sabado 3 de enero" num artigo de 30/12
        if mes < ref.month - 6:
            ano += 1
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


DATA_EXPLICITA_RE = re.compile(
    r"\b(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\s+(\d{1,2})"
    r"(?:\s+y\s+(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\s+\d{1,2})?"
    r"\s+de\s+([a-záéíóú]+)(?:\s+de\s+(\d{4}))?", re.I)
ESTE_DIA_RE = re.compile(r"\beste\s+(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\b", re.I)
HORA_PRIMERA_RE = re.compile(
    r"Primera(?:\s+Divisi[oó]n)?\s*(?:\(|comenzar[aá]\s+a\s+las|a\s+las|desde\s+las|:)\s*(\d{1,2})(?:[.:](\d{2}))?", re.I)
CANCHA_RE = re.compile(r"^Cancha:\s*(.+?)\s*[-–—]\s*(.+?)\s+vs\.?\s+(.+?)\s*$", re.I)
VS_RE = re.compile(
    r"([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ'’. ]{1,40}?)\s+vs\.?\s+([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ'’. ]{1,40}?)"
    r"\s*(?:,\s*en\s+([^.\n]+?)\s*[.\n]|[-–—]\s*[ÁA]rbitros|[.\n]|$)")
ENTRE_RE = re.compile(
    r"entre\s+([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ ]{1,40}?)\s+y\s+([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ ]{1,40}?)\s+se\s+"
    r"(?:disputar[aá]|jugar[aá])\s+el\s+(\w+\s+\d{1,2}\s+de\s+[a-záéíóú]+)(?:\s+a\s+las\s+(\d{1,2})(?:[.:](\d{2}))?)?", re.I)
FECHA_NUM_RE = re.compile(r"\bfecha\s+(\d{1,2})\b", re.I)
FECHA_ORD_RE = re.compile(r"\b(\w+)\s+fecha\b", re.I)
# "recta final" / "final del torneo" nao sao a rodada final
MATA_MATA_RE = re.compile(r"\b(dieciseisavos|16avos|octavos|cuartos|semifinal(?:es)?|(?:la|gran)\s+final)\b(?!\s+del?\s)", re.I)
ORDINAIS = {"primera": 1, "segunda": 2, "tercera": 3, "cuarta": 4, "quinta": 5, "sexta": 6, "septima": 7,
            "octava": 8, "novena": 9, "decima": 10, "undecima": 11, "duodecima": 12, "decimotercera": 13}


def data_da_fecha(txt: str, pub: date) -> date | None:
    m = DATA_EXPLICITA_RE.search(txt)
    if m:
        ano = int(m.group(4)) if m.group(4) else None
        d = _data(int(m.group(2)), m.group(3), ano, pub)
        if d and pub - timedelta(days=3) <= d <= pub + timedelta(days=21):
            return d
    # "este lunes se disputo ..." e passado: nao e a data da fecha
    m = next((x for x in ESTE_DIA_RE.finditer(txt)
              if not re.match(r"\s+(?:se\s+)?(?:disput|jug)[oó]\b", txt[x.end():x.end() + 20], re.I)), None)
    if m:
        alvo = DIAS_SEMANA[norm(m.group(1))]
        return pub + timedelta(days=(alvo - pub.weekday()) % 7)
    return None


def hora_padrao(txt: str) -> str:
    m = HORA_PRIMERA_RE.search(txt)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2) or '00'}"
    return ""


def rodada_de(titulo: str, txt: str) -> str:
    """Titulo antes do texto; em cada um, 'fecha N' vence mata-mata (a noticia
    da fecha 9 cita 'octavos' como objetivo, nao como rodada)."""
    for fonte in (titulo, txt[:600]):
        m = FECHA_NUM_RE.search(fonte)
        if m:
            return f"Fecha {int(m.group(1))}"
        for m in FECHA_ORD_RE.finditer(fonte):
            if norm(m.group(1)) in ORDINAIS:
                return f"Fecha {ORDINAIS[norm(m.group(1))]}"
        m = MATA_MATA_RE.search(fonte)
        if m:
            return {
                "16avos": "16avos de final", "dieciseisavos": "16avos de final",
                "octavos": "Octavos de final", "cuartos": "Cuartos de final",
                "semifinal": "Semifinal", "semifinales": "Semifinal",
            }.get(norm(m.group(1)), "Final")
    return ""


def parse_artigo(url: str, html: str, descartados: list[str]) -> list[Jogo]:
    titulo, pub_iso, txt = texto_artigo(html)
    try:
        pub = datetime.fromisoformat(pub_iso.replace("Z", "+00:00")).date()
    except ValueError:
        return []
    feminino = bool(re.search(r"femenin", titulo + " " + txt[:400], re.I))
    competicao = "Argentina - Liga Marplatense - " + ("Primera División Femenino" if feminino else "Primera División")
    # Data e hora "da fecha" so valem se vierem ANTES da lista de jogos; depois
    # dela vem o partido pendente, com data propria (na noticia dos 16avos de
    # 2026 a unica data era a do pendente e os cruzamentos a herdavam).
    inicios = [m.start() for m in VS_RE.finditer(txt.replace("\n", " "))]
    if "\nCancha:" in txt:
        inicios.append(txt.index("\nCancha:"))
    pre = txt[:min(inicios)] if inicios else txt
    dia = data_da_fecha(pre, pub)
    hora = hora_padrao(pre)
    rodada = rodada_de(titulo, txt)

    jogos: list[Jogo] = []
    vistos: set[tuple] = set()

    def add(m_txt: str, v_txt: str, cancha: str, d: date | None, h: str) -> None:
        mand, vis = clube(m_txt), clube(v_txt)
        if not (mand and vis) or mand == vis:
            if re.search(r"\w", m_txt) and re.search(r"\w", v_txt):
                descartados.append(f"{m_txt} vs {v_txt}")
            return
        if d is None:
            return
        k = (d, mand, vis)
        if k in vistos:
            return
        vistos.add(k)
        est = clube(cancha) if cancha else None
        estadio = f"Cancha de {est or mand}".replace(" (MdP)", "")
        jogos.append(Jogo(
            competicao=competicao, data=d.isoformat(), hora=h, mandante=mand, visitante=vis,
            estadio=estadio, rodada=rodada, url=url,
            # codigo_lmf = identidade estavel para o merge: a hora pode chegar
            # vazia num artigo e preenchida no seguinte (ver README_PREVENCAO_DUPLICATAS)
            extra=f"pais=Argentina; codigo_lmf={d.isoformat()}_{norm(mand).replace(' ', '-')}_{norm(vis).replace(' ', '-')}; "
                  f"provincia=Buenos Aires; estado=Buenos Aires; cidade=Mar del Plata; "
                  f"liga=Liga Marplatense de Fútbol; fonte_dados=elmarplatense.com"
                  + ("" if h else "; hora_a_confirmar=1"),
        ))

    # Partidos "remarcados" no fim do texto, com data/hora propria
    for m in ENTRE_RE.finditer(txt):
        d = data_da_fecha(m.group(3), pub)
        h = f"{int(m.group(4)):02d}:{m.group(5) or '00'}" if m.group(4) else hora
        add(m.group(1), m.group(2), "", d, h)

    linhas = txt.split("\n")
    # Formato 2025: "Cancha: X - A vs B" seguido das linhas de horario
    for i, linha in enumerate(linhas):
        m = CANCHA_RE.match(linha.strip())
        if not m:
            continue
        h = hora
        for prox in linhas[i + 1:i + 4]:
            mh = re.search(r"(?:Primera\s*\()?(\d{1,2})[:.](\d{2})\s*hs", prox, re.I)
            if mh:
                h = f"{int(mh.group(1)):02d}:{mh.group(2)}"  # o ultimo horario listado e o da Primera
            if prox.strip().lower().startswith("cancha:"):
                break
        add(m.group(2), m.group(3), m.group(1), dia, h)

    # Formato 2026: "A vs. B, en X." / "A vs. B - Arbitros: ..."
    corrido = re.sub(r"\s*\n\s*", " \n", txt)
    for m in VS_RE.finditer(corrido.replace(" \n", " ")):
        add(m.group(1), m.group(2), m.group(3) or "", dia, hora)

    return jogos


def main() -> None:
    ap = argparse.ArgumentParser(description="Liga Marplatense de Futbol via El Marplatense")
    ap.add_argument("--meses", type=int, default=2, help="quantos sitemaps mensais ler (mes atual para tras)")
    ap.add_argument("--dias-atras", type=int, default=14, dest="dias_atras")
    ap.add_argument("--url", action="append", default=[], help="processa so estes artigos (teste)")
    args = ap.parse_args()

    candidatas = [(u, "") for u in args.url] or urls_candidatas(args.meses)
    print(f"[INFO] {len(candidatas)} artigos candidatos")
    limite = date.today() - timedelta(days=args.dias_atras)

    todos: dict[tuple, dict] = {}
    debug = []
    for url, lastmod in candidatas:
        try:
            html = fetch(url)
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] {url}: {e}")
            continue
        descartados: list[str] = []
        jogos = parse_artigo(url, html, descartados)
        debug.append({"url": url, "lastmod": lastmod, "jogos": len(jogos), "vs_descartados": descartados[:20]})
        if jogos:
            print(f"  - {len(jogos):2d} jogos  {url}")
        for j in jogos:
            if date.fromisoformat(j.data) < limite:
                continue
            row = j.to_row()
            k = (row["competicao"], row["data"], row["mandante"], row["visitante"])
            # artigo mais novo (lido depois na ordem do sitemap? nao e garantido)
            # -> fica o que tiver hora preenchida, senao o primeiro
            if k not in todos or (row["hora"] and not todos[k]["hora"]):
                todos[k] = row
        time.sleep(0.3)

    rows = sorted(todos.values(), key=lambda r: (r["data"], r["hora"], r["mandante"]))
    RAW_JOGOS.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    DEBUG_ARTIGOS.write_text(json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")
    print("")
    print(f"Liga Marplatense: {len(rows)} jogos (desde {limite.isoformat()}) -> {RAW_JOGOS}")


if __name__ == "__main__":
    main()
