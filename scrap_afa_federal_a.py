#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper - Torneo Federal A (3ª divisão do interior da Argentina)
via https://ascensodelinterior.com.ar/

MOTIVO: a própria página da AFA ("la-agenda-de-la-afa", já coberta por
scrap_afa_agenda.py) tem uma seção "Torneo Federal A" no menu, mas ela
aparece VAZIA na maior parte das semanas (confirmado em 10/07/2026) - a
seção existe mas a AFA simplesmente não publica o Federal A ali. A página
dedicada da AFA (afa.com.ar/es/pages/federal-a) só tem um widget
carregado via JavaScript (info.afa.org.ar/deposito/...), sem HTML
estático - não dá pra ler sem navegador.

Achado: o site "Ascenso del Interior" publica toda semana um artigo com a
tag "Programación" (https://ascensodelinterior.com.ar/etiquetas/8/programacion/)
que traz o Federal A completo, por zona, com time, cidade (cabeceira da
liga de origem do clube) e data/hora - tudo em HTML renderizado no
servidor.

FORMATO (confirmado via fetch real em 10/07/2026, fecha 17):
    ZONA 1
    Sabado 11
    ESCOBAR FC ESCOBAR DOUGLAS HAIG PERGAMINO 11/07/2026 15:30  <árbitros...>

O texto concatena "Time1 Cidade1 Time2 Cidade2 dd/mm/aaaa hh:mm" sem
separador claro entre time e cidade - por isso este script usa um
DICIONÁRIO FIXO dos ~37 clubes do Federal A 2026 (por zona, com
apelidos/variações de nome) para localizar os dois times conhecidos
dentro da linha, em vez de tentar adivinhar onde termina o nome do time
e começa o nome da cidade.

⚠️ NÃO validado ao vivo com o scraper rodando de verdade (o sandbox onde
isso foi escrito não tem acesso de rede a ascensodelinterior.com.ar) - só
a estrutura foi conferida via fetch manual da edição da fecha 17 (semana
de 10-13/07/2026). Conferir o elenco de times por zona todo ano (o
Federal A muda de composição por causa de ascensos/descensos) e rodar com
--debug-html na primeira execução real.

Uso:
    python scrap_afa_federal_a.py --dias 60 --dias-atras 14 --debug-html
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
DEBUG_DIR = OUT_DIR / "debug_federal_a_html"

BASE_URL = "https://ascensodelinterior.com.ar"
TAG_PROGRAMACAO_URL = f"{BASE_URL}/etiquetas/8/programacion/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9,pt;q=0.7",
}

# Elenco do Torneo Federal A 2026 por zona - (nome canônico, aliases,
# cidade "cabeceira" usada pelo Consejo Federal, província, lat, lng
# aproximados). Conferir/atualizar a cada temporada (ascensos/descensos).
TIMES_FEDERAL_A = [
    # Zona 1
    ("El Linqueño", ["linqueno"], "Lincoln", "Buenos Aires", -34.8992, -61.5250),
    ("Gimnasia y Esgrima (Chivilcoy)", ["gim y esgrima ch", "gimnasia y esgrima chivilcoy"], "Chivilcoy", "Buenos Aires", -34.9186, -60.0154),
    ("Independiente (Chivilcoy)", ["independiente chi", "independiente chivilcoy"], "Chivilcoy", "Buenos Aires", -34.9186, -60.0154),
    ("Douglas Haig", ["douglas haig"], "Pergamino", "Buenos Aires", -33.8952, -60.5738),
    ("Escobar FC", ["escobar fc"], "Escobar", "Buenos Aires", -34.3480, -58.7967),
    ("Defensores de Belgrano (V. Ramallo)", ["def belgrano v r", "def belgrano vr", "defensores de belgrano villa ramallo"], "Villa Ramallo", "Buenos Aires", -33.4881, -60.0250),
    ("Gimnasia y Esgrima (Concepción del Uruguay)", ["g y esgrima cu", "gimnasia y esgrima concepcion del uruguay"], "Concepción del Uruguay", "Entre Ríos", -32.4825, -58.2372),
    ("Sportivo A.C. (Las Parejas)", ["sportivo at", "sportivo ac"], "Cañada de Gómez", "Santa Fe", -32.8225, -61.3989),
    ("9 de Julio (Rafaela)", ["nueve de julio", "9 de julio"], "Rafaela", "Santa Fe", -31.2503, -61.4867),
    ("Sportivo Belgrano (San Francisco)", ["sp belgrano", "sportivo belgrano"], "San Francisco", "Córdoba", -31.4272, -62.0847),

    # Zona 2
    ("Juventud Antoniana", ["juv antoniana", "juventud antoniana"], "Salta", "Salta", -24.7859, -65.4117),
    ("Tucumán Central", ["tucuman ctral", "tucuman central"], "San Miguel de Tucumán", "Tucumán", -26.8083, -65.2176),
    ("San Martín (Formosa)", ["san martin f", "san martin formosa"], "Formosa", "Formosa", -26.1849, -58.1731),
    ("Sol de América (Formosa)", ["sol de america"], "Formosa", "Formosa", -26.1849, -58.1731),
    ("Sarmiento (Resistencia)", ["sarmiento resistencia"], "Resistencia", "Chaco", -27.4514, -58.9867),
    ("Defensores de Puerto Vilelas", ["def de vilelas", "defensores de puerto vilelas"], "Puerto Vilelas", "Chaco", -27.4894, -58.9161),
    ("Sarmiento (La Banda)", ["sarmiento sgo", "sarmiento la banda"], "La Banda", "Santiago del Estero", -27.7317, -64.2381),
    ("Bartolomé Mitre (Posadas)", ["mitre posadas", "bartolome mitre"], "Posadas", "Misiones", -27.3671, -55.8961),
    ("Boca Unidos", ["boca unidos"], "Corrientes", "Corrientes", -27.4806, -58.8341),

    # Zona 3
    ("Cipolletti", ["cipolletti"], "Cipolletti", "Río Negro", -38.9339, -67.9911),
    ("Deportivo Rincón", ["dep rincon", "deportivo rincon"], "General Roca", "Río Negro", -39.0333, -67.5833),
    ("Huracán Las Heras", ["huracan l heras", "huracan las heras"], "Las Heras", "Mendoza", -32.8500, -68.8333),
    ("Atlético San Martín (Mendoza)", ["at c san martin", "atletico san martin mendoza"], "San Martín", "Mendoza", -33.0806, -68.4708),
    ("FADEP", ["fadep"], "Guaymallén", "Mendoza", -32.8983, -68.7783),
    ("Juventud Unida Universitario", ["j u universitario", "juventud unida universitario"], "San Luis", "San Luis", -33.2950, -66.3356),
    ("Costa Brava", ["costa brava"], "San Luis", "San Luis", -33.2950, -66.3356),
    ("Atenas (Río Cuarto)", ["atenas rc", "atenas rio cuarto"], "Río Cuarto", "Córdoba", -33.1232, -64.3499),
    ("Deportivo Argentino (Pascanas)", ["argentino p pascanas", "argentino pascanas"], "Pascanas", "Córdoba", -33.1167, -63.2667),

    # Zona 4
    ("Germinal (Rawson)", ["germinal"], "Rawson", "Chubut", -43.3002, -65.1023),
    ("Guillermo Brown", ["gmo brown", "guillermo brown"], "Puerto Madryn", "Chubut", -42.7692, -65.0385),
    ("Sol de Mayo (Viedma)", ["sol de mayo"], "Viedma", "Río Negro", -40.8135, -63.0000),
    ("Olimpo", ["olimpo"], "Bahía Blanca", "Buenos Aires", -38.7196, -62.2724),
    ("Villa Mitre", ["villa mitre"], "Bahía Blanca", "Buenos Aires", -38.7196, -62.2724),
    ("Santamarina (Tandil)", ["santamarina"], "Tandil", "Buenos Aires", -37.3217, -59.1332),
    ("Círculo Deportivo", ["circulo deportivo", "circulo dep"], "Mar del Plata", "Buenos Aires", -38.0055, -57.5426),
    ("Alvarado (Mar del Plata)", ["alvarado"], "Mar del Plata", "Buenos Aires", -38.0055, -57.5426),
    ("Kimberley (Mar del Plata)", ["kimberley"], "Mar del Plata", "Buenos Aires", -38.0055, -57.5426),
]

FIELDS = [
    "id", "fonte", "competicao", "data", "hora", "pais", "cidade",
    "mandante", "visitante", "estadio", "rodada", "url", "extra", "atualizado_em",
]

DATA_HORA_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\s+(\d{1,2}):(\d{2})\b")
ZONA_RE = re.compile(r"^ZONA\s+(\d+)", re.IGNORECASE)


def clean_text(v) -> str:
    v = "" if v is None else str(v)
    return re.sub(r"\s+", " ", v.replace("\u00a0", " ")).strip()


def norm(v) -> str:
    v = unicodedata.normalize("NFD", clean_text(v))
    v = "".join(c for c in v if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", v.lower()).strip()


# índice reverso: qualquer alias normalizado -> índice em TIMES_FEDERAL_A
_ALIAS_TO_IDX: dict[str, int] = {}
for _i, (_nome, _aliases, *_resto) in enumerate(TIMES_FEDERAL_A):
    for _a in [_nome] + _aliases:
        _ALIAS_TO_IDX[norm(_a)] = _i
# aliases mais compridos primeiro, pra "san martin f" não ser engolido
# por um "san martin" mais curto de outra zona, etc.
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
    pais: str = "Argentina"
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


def find_urls_programacao_recentes(max_links: int = 4) -> list[str]:
    """Retorna os links dos artigos de programação mais recentes (não só o
    primeiro): o site às vezes serve uma versão em cache desatualizada da
    página de listagem, então é mais seguro tentar os 2-4 primeiros e
    ficar com o que trouxer jogos dentro da janela de datas, em vez de
    confiar cegamente no primeiro link encontrado."""
    r = fetch(TAG_PROGRAMACAO_URL)
    soup = BeautifulSoup(r.text, "html.parser")
    urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/noticias/" in href and "programa" in href.lower():
            if href.startswith("/"):
                href = BASE_URL + href
            if href not in urls:
                urls.append(href)
        if len(urls) >= max_links:
            break
    return urls


def times_na_linha(line: str) -> list[tuple[int, int]]:
    """Retorna [(posicao_no_texto_normalizado, indice_do_time), ...] dos
    times conhecidos encontrados na linha, na ordem em que aparecem."""
    nline = norm(line)
    achados = []
    usado = [False] * len(nline)
    for alias in _ALIASES_ORDENADOS:
        start = 0
        while True:
            pos = nline.find(alias, start)
            if pos == -1:
                break
            # evita bater no meio de outra palavra maior já capturada
            if not any(usado[pos:pos + len(alias)]):
                for k in range(pos, pos + len(alias)):
                    usado[k] = True
                achados.append((pos, _ALIAS_TO_IDX[alias]))
            start = pos + len(alias)
    achados.sort(key=lambda x: x[0])
    return achados


def parse_federal_a_secao(lines: list[str], url: str, debug_html: bool) -> list[Partido]:
    partidos: list[Partido] = []

    # isola o trecho entre "TORNEO FEDERAL A" (cabeçalho da seção nesta
    # página) e o próximo torneio listado (ex.: "Primera Nacional").
    inicio = None
    fim = len(lines)
    for i, l in enumerate(lines):
        if inicio is None and re.match(r"^TORNEO FEDERAL A\b", l, re.IGNORECASE):
            inicio = i
            continue
        if inicio is not None and i > inicio:
            if re.match(r"^(Primera Nacional|Torneo Promocional Amateur|Primera B|Primera C|Copa Argentina)\b", l, re.IGNORECASE):
                fim = i
                break
    if inicio is None:
        return []

    secao = lines[inicio:fim]

    zona_atual = ""
    data_atual = ""
    for line in secao:
        m_zona = ZONA_RE.match(line)
        if m_zona:
            zona_atual = f"Zona {m_zona.group(1)}"
            continue

        m_dh = DATA_HORA_RE.search(line)
        if not m_dh:
            continue

        dia, mes, ano, hh, mm = m_dh.groups()
        try:
            data_iso = date(int(ano), int(mes), int(dia)).isoformat()
        except ValueError:
            continue
        hora = f"{int(hh):02d}:{mm}"

        trecho_times = line[:m_dh.start()]
        achados = times_na_linha(trecho_times)
        if len(achados) < 2:
            continue
        idx_mandante = achados[0][1]
        idx_visitante = achados[1][1]
        if idx_mandante == idx_visitante:
            continue

        nome_m, _, cidade_m, prov_m, lat_m, lng_m = TIMES_FEDERAL_A[idx_mandante]
        nome_v, *_ = TIMES_FEDERAL_A[idx_visitante]

        partidos.append(Partido(
            fonte="AFA-FederalA",
            competicao="Argentina - Torneo Federal A",
            data=data_iso,
            hora=hora,
            mandante=nome_m,
            visitante=nome_v,
            estadio=f"Sede de {nome_m}",
            cidade=cidade_m,
            rodada=zona_atual,
            url=url,
            extra=f"pais=Argentina; provincia={prov_m}; lat={lat_m}; lng={lng_m}; fonte_dados=ascensodelinterior.com.ar",
        ))

    if debug_html:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        (DEBUG_DIR / "federal_a_secao.txt").write_text("\n".join(secao), encoding="utf-8")

    return partidos


def scrape(debug_html: bool, desde: date, ate: date) -> list[Partido]:
    urls = find_urls_programacao_recentes()
    if not urls:
        print("[ERRO] não achei nenhum artigo de programação")
        return []

    melhor_jogos: list[Partido] = []
    melhor_url = ""
    for url in urls:
        print(f"[INFO] tentando artigo de programação: {url}")
        try:
            r = fetch(url)
        except Exception as e:
            print(f"[AVISO] falha ao buscar {url}: {e}")
            continue

        lines = get_lines(r.text)
        partidos = parse_federal_a_secao(lines, url, debug_html)
        na_janela = [p for p in partidos if in_window(p, desde, ate, False)]
        print(f"[INFO]   {len(partidos)} jogos achados, {len(na_janela)} dentro da janela de datas")
        if len(na_janela) > len(melhor_jogos):
            melhor_jogos = partidos
            melhor_url = url
        if len(na_janela) > 0:
            # já achou um artigo com jogos atuais, não precisa tentar os
            # mais antigos da lista
            break

    if melhor_url:
        print(f"[OK] usando artigo: {melhor_url}")

    seen = set()
    out = []
    for p in melhor_jogos:
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
    parser.add_argument("--dias", type=int, default=60)
    parser.add_argument("--dias-atras", type=int, default=14)
    parser.add_argument("--incluir-passados", action="store_true")
    parser.add_argument("--debug-html", action="store_true")
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    jogos = scrape(args.debug_html, desde, ate)
    na_janela = [p for p in jogos if in_window(p, desde, ate, args.incluir_passados)]
    print(f"[OK] Torneo Federal A | jogos={len(jogos)} | na janela={len(na_janela)}")

    rows_new = [p.to_row() for p in na_janela]

    (OUT_DIR / "debug_federal_a_raw.json").write_text(
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
    print(f"Torneo Federal A jogos válidos adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")
    if args.debug_html:
        print("Debug: data/debug_federal_a_html/")


if __name__ == "__main__":
    main()
