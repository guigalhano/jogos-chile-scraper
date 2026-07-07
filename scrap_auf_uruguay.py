#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper AUF (Asociación Uruguaya de Fútbol)

As 3 URLs de competições (Liga AUF Uruguaya, Segunda Profesional/Primera
Divisional C) retornam 404 em fetch direto (confirmado), mesmo aparecendo
como links reais e válidos na navegação do site — sinal forte de SPA
(Single Page Application) com roteamento client-side via JavaScript, igual
ao padrão já visto na FMF e na FPF. Este script usa Playwright para
renderizar a página de verdade e intercepta respostas de rede em busca de
JSON com dados de jogos (mesma estratégia genérica usada em
scrap_fpf_playwright_api.py), em vez de tentar parsear HTML estático.

Uso:
    python scrap_auf_uruguay.py --dias 180 --dias-atras 30
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
from typing import Any

from playwright.sync_api import sync_playwright

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

START_URLS = [
    ("Uruguay - Liga AUF Uruguaya", "https://www.auf.org.uy/liga-auf-uruguaya/"),
    ("Uruguay - Primera Divisional C", "https://www.auf.org.uy/primera-divisional-c/"),
]

FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em", "pais", "cidade",
]

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

DATE_RE = re.compile(r"\b(?P<dia>\d{1,2})[/-](?P<mes>\d{1,2})[/-](?P<ano>\d{2,4})\b")
TIME_RE = re.compile(r"\b(?P<hora>\d{1,2}):(?P<minuto>\d{2})\b")


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
    pais: str = "Uruguay"
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


def clean_text(value: Any) -> str:
    value = "" if value is None else str(value)
    value = value.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", value).strip()


def norm(value: Any) -> str:
    value = unicodedata.normalize("NFD", clean_text(value))
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def parse_year(y: str) -> int:
    n = int(y)
    return 2000 + n if n < 100 else n


def parse_date(value: Any) -> str:
    txt = clean_text(value)
    if not txt:
        return ""
    m_iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})", txt)
    if m_iso:
        try:
            return date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))).isoformat()
        except Exception:
            pass
    m = DATE_RE.search(txt)
    if m:
        try:
            return date(parse_year(m.group("ano")), int(m.group("mes")), int(m.group("dia"))).isoformat()
        except Exception:
            pass
    return ""


def parse_time(value: Any) -> str:
    m = TIME_RE.search(clean_text(value))
    return f"{m.group('hora')}:{m.group('minuto')}" if m else ""


def first_value(obj: dict, keys: list[str]) -> str:
    if not isinstance(obj, dict):
        return ""
    for k in keys:
        if k in obj and clean_text(obj[k]):
            return clean_text(obj[k])
    normalized = {norm(k): v for k, v in obj.items()}
    for wanted in keys:
        nw = norm(wanted)
        for nk, val in normalized.items():
            if nw == nk or nw in nk:
                txt = clean_text(val)
                if txt:
                    return txt
    return ""


def obj_to_partido(obj: dict, url: str, competicao_fallback: str) -> Partido | None:
    if not isinstance(obj, dict):
        return None

    mandante = first_value(obj, [
        "EquipoLocal", "NombreLocal", "Local", "ClubLocal", "TimeLocal", "HomeTeam",
    ])
    visitante = first_value(obj, [
        "EquipoVisitante", "NombreVisitante", "Visitante", "ClubVisitante", "AwayTeam",
    ])
    data_raw = first_value(obj, ["Fecha", "FechaPartido", "Date", "FechaFormateada"])
    hora_raw = first_value(obj, ["Hora", "HoraPartido", "Horario", "Time"])
    estadio = first_value(obj, ["Estadio", "Cancha", "Venue", "Sede"])
    cidade = first_value(obj, ["Ciudad", "Localidad", "City"])
    rodada = first_value(obj, ["Fecha_Numero", "Jornada", "Ronda", "Round", "Etapa"])

    data = parse_date(data_raw)
    hora = parse_time(hora_raw)

    if not data:
        joined = " ".join(clean_text(v) for v in obj.values() if isinstance(v, (str, int, float)))
        data = parse_date(joined)
        if not hora:
            hora = parse_time(joined)

    if not (mandante and visitante and data):
        return None
    if len(mandante) > 60 or len(visitante) > 60:
        return None

    extra_parts = []
    if cidade:
        extra_parts.append(f"cidade={cidade}")

    return Partido(
        fonte="AUF",
        competicao=competicao_fallback,
        data=data,
        hora=hora,
        mandante=mandante,
        visitante=visitante,
        estadio=estadio,
        rodada=rodada,
        url=url,
        extra="; ".join(extra_parts),
        cidade=cidade,
    )


def walk_json(data: Any, url: str, competicao_fallback: str) -> list[Partido]:
    out: list[Partido] = []
    if isinstance(data, dict):
        p = obj_to_partido(data, url, competicao_fallback)
        if p:
            out.append(p)
        for v in data.values():
            out.extend(walk_json(v, url, competicao_fallback))
    elif isinstance(data, list):
        for item in data:
            out.extend(walk_json(item, url, competicao_fallback))
    return out


def dedupe(rows: list[Partido]) -> list[Partido]:
    seen = set()
    out = []
    for p in rows:
        if p.id in seen:
            continue
        seen.add(p.id)
        out.append(p)
    return out


def collect_auf_json(start_urls: list[tuple[str, str]], wait_ms: int = 8000) -> tuple[list[dict], list[dict]]:
    json_payloads: list[dict] = []
    debug_urls: list[dict] = []
    seen_urls = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
            ),
            locale="es-UY",
        )

        def on_response(response):
            url = response.url
            if url in seen_urls:
                return
            seen_urls.add(url)
            low = url.lower()
            ct = ""
            try:
                ct = response.headers.get("content-type", "")
            except Exception:
                pass
            interesting = "json" in ct.lower() or any(
                x in low for x in ["fixture", "calendario", "partido", "jornada", "api", "ajax", ".ashx", ".json"]
            )
            if not interesting:
                return
            item = {"url": url, "status": response.status, "content_type": ct}
            try:
                data = response.json()
                item["json"] = True
                json_payloads.append({"url": url, "data": data})
            except Exception:
                item["json"] = False
            debug_urls.append(item)

        page.on("response", on_response)

        for competicao, url in start_urls:
            try:
                print(f"[INFO] Abrindo AUF: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(wait_ms)

                for selector in ["select", ".dropdown-toggle", "button", "a[href*='fixture']", "a[href*='calendario']"]:
                    try:
                        locs = page.locator(selector)
                        count = min(locs.count(), 5)
                        for i in range(count):
                            try:
                                locs.nth(i).click(timeout=1000)
                                page.wait_for_timeout(800)
                            except Exception:
                                pass
                    except Exception:
                        pass

                # FIX diagnóstico: a interceptação de rede não achou nenhuma
                # chamada de API com dados de jogos — pode ser que o AUF
                # renderize a tabela direto no HTML (server-side), sem uma
                # chamada JSON separada. Salva o texto renderizado para
                # inspecionar isso.
                try:
                    html = page.content()
                    slug = re.sub(r"[^a-z0-9]+", "_", competicao.lower()).strip("_")
                    (OUT_DIR / f"debug_auf_html_{slug}.html").write_text(html, encoding="utf-8")
                    text = page.evaluate("() => document.body ? document.body.innerText : ''")
                    (OUT_DIR / f"debug_auf_text_{slug}.txt").write_text(text, encoding="utf-8")
                except Exception as e:
                    print(f"[WARN] Falha ao salvar HTML/texto de {url}: {e}")
            except Exception as e:
                print(f"[WARN] Erro abrindo {url}: {e}")

        browser.close()

    return json_payloads, debug_urls


def in_window(p: Partido, desde: date, ate: date, incluir_passados: bool) -> bool:
    try:
        dt = date.fromisoformat(p.data)
    except Exception:
        return False
    return (incluir_passados or (desde <= dt <= ate)) and bool(p.hora)


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
        key=lambda r: (r.get("data", ""), r.get("hora", ""), r.get("competicao", ""), r.get("mandante", ""))
    )


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dias", type=int, default=180)
    parser.add_argument("--dias-atras", type=int, default=30)
    parser.add_argument("--incluir-passados", action="store_true")
    parser.add_argument("--wait-ms", type=int, default=8000)
    args = parser.parse_args()

    today = date.today()
    desde = today - timedelta(days=args.dias_atras)
    ate = today + timedelta(days=args.dias)

    payloads, debug_urls = collect_auf_json(START_URLS, wait_ms=args.wait_ms)

    (OUT_DIR / "debug_auf_urls.json").write_text(
        json.dumps(debug_urls, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    partidos: list[Partido] = []
    for payload in payloads:
        url = payload["url"]
        data = payload["data"]
        # tenta achar a competição pelo START_URLS mais provável (mesma origem)
        competicao_fallback = "Uruguay - AUF"
        for comp, u in START_URLS:
            if u.rstrip("/") in url or True:
                competicao_fallback = comp
                break
        found = walk_json(data, url, competicao_fallback)
        if found:
            print(f"[OK] AUF JSON {url} -> {len(found)} jogos")
        partidos.extend(found)

    partidos = dedupe([p for p in partidos if in_window(p, desde, ate, args.incluir_passados)])

    (OUT_DIR / "debug_auf_jogos_raw.json").write_text(
        json.dumps([p.to_row() for p in partidos], ensure_ascii=False, indent=2), encoding="utf-8"
    )

    rows_new = [p.to_row() for p in partidos]

    current_json = OUT_DIR / "jogos_programados.json"
    current_csv = OUT_DIR / "jogos_programados.csv"
    history_csv = OUT_DIR / "historico_jogos.csv"

    merged_current = merge_rows(load_json_rows(current_json), rows_new)
    current_json.write_text(json.dumps(merged_current, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(current_csv, merged_current)

    merged_history = merge_rows(load_csv_rows(history_csv), rows_new)
    write_csv(history_csv, merged_history)

    print(f"\nAUF (Uruguay) adicionados/atualizados: {len(rows_new)}")
    print(f"Total JSON atual: {len(merged_current)}")


if __name__ == "__main__":
    main()
