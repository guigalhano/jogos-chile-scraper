#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CBF PDFs v2 - documentos da competição

Corrige o problema da versão anterior:
- A página também expõe PDFs de súmulas (/sumulas/2026/...) e links de jogos.
- Por padrão, esta versão baixa SOMENTE documentos da competição:
  Manual de Competições, PGA, REC/Regulamento e Tabela Detalhada.

Página padrão:
https://www.cbf.com.br/futebol-brasileiro/tabelas/campeonato-brasileiro/serie-a/2026

Instalação:
    py -m pip install requests beautifulsoup4 playwright
    py -m playwright install chromium

Listar documentos:
    py atualizar_pdfs_cbf_pagina_v2.py --playwright --buscar-web --somente-listar

Baixar documentos da competição:
    py atualizar_pdfs_cbf_pagina_v2.py --playwright --buscar-web

Incluir também súmulas:
    py atualizar_pdfs_cbf_pagina_v2.py --playwright --incluir-sumulas

Forçar baixar:
    py atualizar_pdfs_cbf_pagina_v2.py --playwright --buscar-web --forcar

Saídas:
- data/cbf_pdfs/serie-a-2026/
- data/cbf_pdfs_manifest.json
- data/cbf_pdfs_manifest.csv
- data/debug_cbf_pdf_links.json
- data/debug_cbf_page_resources.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
import unicodedata
import urllib3
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, unquote, parse_qs

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None


DEFAULT_URL = "https://www.cbf.com.br/futebol-brasileiro/tabelas/campeonato-brasileiro/serie-a/2026"

# Páginas de tabela de cada série/competição nacional, usadas pelo modo
# --todas-competicoes. A descoberta diária original só visitava a Série A
# (DEFAULT_URL); isso deixava Série B/C/D e as copas sem NENHUMA atualização
# automática de PDF, dependendo pra sempre do link fixo (seed) mantido à mão
# em adicionar_brasil_jogos.py -- exatamente o que causou o jogo do Athletic
# x CRB (Série B, 20/08) sumir por semanas até alguém notar e reclamar.
PAGINAS_CBF_COMPETICOES = [
    DEFAULT_URL,
    "https://www.cbf.com.br/futebol-brasileiro/tabelas/campeonato-brasileiro/serie-b/2026",
    "https://www.cbf.com.br/futebol-brasileiro/tabelas/campeonato-brasileiro/serie-c/2026",
    "https://www.cbf.com.br/futebol-brasileiro/tabelas/campeonato-brasileiro/serie-d/2026",
    "https://www.cbf.com.br/futebol-brasileiro/tabelas/copa-do-brasil/masculino/2026",
    "https://www.cbf.com.br/futebol-brasileiro/tabelas/copa-do-brasil/feminino/2026",
]

OUT_DIR = Path("data")
BASE_PDF_DIR = OUT_DIR / "cbf_pdfs"
MANIFEST_JSON = OUT_DIR / "cbf_pdfs_manifest.json"
MANIFEST_CSV = OUT_DIR / "cbf_pdfs_manifest.csv"
DEBUG_LINKS_JSON = OUT_DIR / "debug_cbf_pdf_links.json"
DEBUG_RESOURCES_JSON = OUT_DIR / "debug_cbf_page_resources.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,es;q=0.8,en;q=0.7",
    "Referer": "https://www.cbf.com.br/",
}

PDF_RE = re.compile(r"""(?P<url>https?://[^"' <>()]+?\.pdf(?:\?[^"' <>()]*)?|/[^"' <>()]+?\.pdf(?:\?[^"' <>()]*)?)""", re.I)
DOC_HINT_RE = re.compile(r"(pdf|documento|documentos|tabela|pga|imt|manual|regulamento|rec_|rec-|competição|competicao|download|arquivo)", re.I)

FIELDS = [
    "id", "tipo", "competicao_slug", "page_url", "title", "url", "filename",
    "local_path", "status", "content_type", "bytes", "sha256",
    "etag", "last_modified", "origem", "baixado_em", "atualizado",
]


@dataclass
class PdfCandidate:
    url: str
    title: str = ""
    origem: str = ""

    @property
    def id(self) -> str:
        return hashlib.sha1(self.url.encode("utf-8")).hexdigest()[:16]


def clean_text(x: Any) -> str:
    x = "" if x is None else str(x)
    x = x.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", x).strip()


def norm_filename(x: str) -> str:
    x = unquote(clean_text(x))
    x = unicodedata.normalize("NFD", x)
    x = "".join(c for c in x if unicodedata.category(c) != "Mn")
    x = re.sub(r"[^A-Za-z0-9._-]+", "_", x)
    x = re.sub(r"_+", "_", x).strip("._")
    return x[:180] or "arquivo.pdf"


def infer_slug_from_url(url: str) -> str:
    parts = [p for p in urlparse(url).path.split("/") if p]
    if len(parts) >= 2:
        return norm_filename("-".join(parts[-2:]).lower())
    return "cbf-pdfs"


def unwrap_redirect(raw: str) -> str:
    raw = clean_text(raw).replace("&amp;", "&").replace("\\/", "/")
    if not raw:
        return ""

    # DuckDuckGo / Bing redirect with uddg=...
    try:
        parsed = urlparse(raw)
        qs = parse_qs(parsed.query)
        for key in ["uddg", "url", "u", "file", "arquivo", "download"]:
            if key in qs and qs[key]:
                val = unquote(qs[key][0])
                if ".pdf" in val.lower():
                    return val
    except Exception:
        pass

    return raw


def normalize_url(raw: str, base_url: str) -> str:
    raw = unwrap_redirect(raw)
    if not raw:
        return ""
    if raw.startswith("//"):
        raw = "https:" + raw
    return urljoin(base_url, raw)


def filename_from_url(url: str, title: str = "") -> str:
    path_name = unquote(Path(urlparse(url).path).name)
    if path_name and "." in path_name:
        name = norm_filename(path_name)
    else:
        base = norm_filename(title) or hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        name = base + ".pdf"
    if ".pdf" in url.lower() and not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name


def is_pdf_url(url: str) -> bool:
    return ".pdf" in urlparse(url).path.lower() or ".pdf" in url.lower()


def likely_doc_url(url: str, text: str = "") -> bool:
    return bool(DOC_HINT_RE.search(f"{url} {text}"))


def classify_candidate(url: str, title: str = "") -> str:
    filename = filename_from_url(url, title).lower()
    hay = f"{url} {title} {filename}".lower()

    if "/sumulas/" in hay:
        return "sumula"
    if "/futebol-brasileiro/jogos/" in hay:
        return "pagina_jogo"
    if any(x in hay for x in ["manual_de_competicoes", "manual-de-competicoes", "manual de competicoes", "manual de competições"]):
        return "manual"
    if "pga_" in hay or "pga-" in hay or "pga brasileiro" in hay:
        return "pga"
    if "rec_" in hay or "rec-" in hay or "regulamento" in hay:
        return "regulamento"
    if "tabela_detalhada" in hay or "tabela-detalhada" in hay:
        return "tabela_detalhada"
    if "imt" in hay:
        return "imt"
    if is_pdf_url(url):
        return "pdf_outro"
    return "link_outro"


def competition_doc_allowed(c: PdfCandidate, incluir_sumulas: bool = False, incluir_outros: bool = False) -> bool:
    tipo = classify_candidate(c.url, c.title)
    if tipo in {"manual", "pga", "regulamento", "tabela_detalhada", "imt"}:
        return True
    if incluir_sumulas and tipo == "sumula":
        return True
    if incluir_outros and tipo == "pdf_outro":
        return True
    return False


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_manifest() -> dict:
    if not MANIFEST_JSON.exists():
        return {}
    try:
        data = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {row.get("url", ""): row for row in data if row.get("url")}
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def write_manifest(rows_by_url: dict) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    rows = sorted(rows_by_url.values(), key=lambda r: (r.get("competicao_slug", ""), r.get("tipo", ""), r.get("filename", "")))
    MANIFEST_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with MANIFEST_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in FIELDS})


def extract_candidates_from_html(html: str, base_url: str, origem: str) -> list[PdfCandidate]:
    out: list[PdfCandidate] = []
    soup = BeautifulSoup(html or "", "html.parser")

    for tag in soup.find_all(["a", "iframe", "embed", "object", "link", "script"]):
        text = clean_text(tag.get_text(" ", strip=True))
        for attr in ["href", "src", "data"]:
            href = tag.get(attr)
            if not href:
                continue
            url = normalize_url(href, base_url)
            if is_pdf_url(url) or likely_doc_url(url, text):
                out.append(PdfCandidate(url=url, title=text, origem=f"{origem}:{tag.name}.{attr}"))

    for m in PDF_RE.finditer(html or ""):
        url = normalize_url(m.group("url"), base_url)
        if url:
            out.append(PdfCandidate(url=url, title="", origem=f"{origem}:regex_pdf"))

    return out


def fetch_text(url: str, verify_ssl: bool = True) -> tuple[str, dict]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=60, allow_redirects=True, verify=verify_ssl)
        ct = r.headers.get("content-type", "")
        info = {
            "url": r.url,
            "status": r.status_code,
            "content_type": ct,
            "bytes": len(r.content or b""),
            "sample": clean_text((r.text or "")[:400]) if any(x in ct.lower() for x in ["text", "html", "json", "javascript"]) else "",
        }
        if any(x in ct.lower() for x in ["text", "html", "json", "javascript"]):
            return r.text, info
        return "", info
    except Exception as e:
        return "", {"url": url, "error": str(e)}


def discover_with_requests(page_url: str, verify_ssl: bool = True) -> tuple[list[PdfCandidate], list[dict]]:
    debug = []
    html, info = fetch_text(page_url, verify_ssl=verify_ssl)
    debug.append({"tipo": "page_requests", **info})
    candidates = extract_candidates_from_html(html, info.get("url", page_url), "requests_page") if html else []

    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup.find_all(["script", "link"]):
        href = tag.get("src") or tag.get("href")
        if not href:
            continue
        url = normalize_url(href, info.get("url", page_url))
        if not any(k in url.lower() for k in ["cbf", "assets", "js", "document", "tabela", "competicao", "_next"]):
            continue
        text, jsinfo = fetch_text(url, verify_ssl=verify_ssl)
        debug.append({"tipo": "asset_requests", **jsinfo})
        if text:
            candidates.extend(extract_candidates_from_html(text, url, "requests_asset"))

    return candidates, debug


def discover_with_playwright(page_url: str, wait_ms: int = 9000) -> tuple[list[PdfCandidate], list[dict]]:
    if sync_playwright is None:
        return [], [{"error": "playwright não instalado"}]

    candidates: list[PdfCandidate] = []
    resources: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=HEADERS["User-Agent"], locale="pt-BR", ignore_https_errors=True)
        page = context.new_page()

        def on_response(response):
            url = response.url
            ct = response.headers.get("content-type", "")
            row = {
                "url": url,
                "status": response.status,
                "content_type": ct,
                "interessante": is_pdf_url(url) or likely_doc_url(url),
            }
            resources.append(row)

            if is_pdf_url(url):
                candidates.append(PdfCandidate(url=url, title="", origem="playwright_response_pdf"))

            if likely_doc_url(url) or any(k in ct.lower() for k in ["html", "json", "javascript", "text"]):
                try:
                    if any(k in ct.lower() for k in ["html", "json", "javascript", "text"]):
                        txt = response.text()
                        row["sample"] = clean_text(txt[:400])
                        candidates.extend(extract_candidates_from_html(txt, url, "playwright_response_body"))
                except Exception as e:
                    row["read_error"] = str(e)

        page.on("response", on_response)
        page.goto(page_url, wait_until="domcontentloaded", timeout=70000)
        page.wait_for_timeout(wait_ms)

        # clica somente áreas de documentos, não links de jogos
        for selector in ["a", "button", ".btn", "[role=button]"]:
            try:
                locs = page.locator(selector)
                count = min(locs.count(), 100)
                for i in range(count):
                    try:
                        txt = clean_text(locs.nth(i).inner_text(timeout=300))
                        ntx = txt.lower()
                        if any(k in ntx for k in ["document", "pga", "imt", "manual", "regulamento", "tabela", "baixar", "download", "pdf"]):
                            if "documentos do jogo" in ntx:
                                continue
                            locs.nth(i).click(timeout=1200)
                            page.wait_for_timeout(1200)
                    except Exception:
                        pass
            except Exception:
                pass

        html = page.content()
        candidates.extend(extract_candidates_from_html(html, page.url, "playwright_page_content"))

        try:
            perf = page.evaluate("() => performance.getEntriesByType('resource').map(r => r.name)")
            for url in perf:
                if isinstance(url, str):
                    resources.append({"url": url, "status": "", "content_type": "", "interessante": is_pdf_url(url) or likely_doc_url(url), "tipo": "performance"})
                    if is_pdf_url(url):
                        candidates.append(PdfCandidate(url=url, title="", origem="playwright_performance_pdf"))
        except Exception:
            pass

        browser.close()

    return candidates, resources


def search_engine_candidates(page_url: str) -> tuple[list[PdfCandidate], list[dict]]:
    queries = [
        'site:stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn filetype:pdf "Brasileiro_Serie_A_2026"',
        'site:stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn filetype:pdf "Tabela_Detalhada" "Serie_A_2026"',
        'site:stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn filetype:pdf "PGA_Brasileiro_Serie_A_2026"',
        'site:stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn filetype:pdf "REC_Brasileiro_Serie_A_2026"',
    ]

    candidates = []
    debug = []
    for q in queries:
        try:
            r = requests.get("https://html.duckduckgo.com/html/", params={"q": q}, headers=HEADERS, timeout=45)
            debug.append({"tipo": "duckduckgo", "query": q, "status": r.status_code, "bytes": len(r.content or b"")})
            candidates.extend(extract_candidates_from_html(r.text, "https://duckduckgo.com/", "duckduckgo"))
        except Exception as e:
            debug.append({"tipo": "duckduckgo", "query": q, "error": str(e)})

        try:
            r = requests.get("https://www.bing.com/search", params={"q": q}, headers=HEADERS, timeout=45)
            debug.append({"tipo": "bing", "query": q, "status": r.status_code, "bytes": len(r.content or b"")})
            candidates.extend(extract_candidates_from_html(r.text, "https://www.bing.com/", "bing"))
        except Exception as e:
            debug.append({"tipo": "bing", "query": q, "error": str(e)})

    return candidates, debug


def dedupe_candidates(candidates: list[PdfCandidate]) -> list[PdfCandidate]:
    by_url: dict[str, PdfCandidate] = {}
    for c in candidates:
        if not c.url:
            continue
        # unwrap again
        c.url = normalize_url(c.url, c.url)

        low_path = urlparse(c.url).path.lower()
        if any(low_path.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".svg", ".css", ".js", ".woff", ".woff2", ".ttf", ".webp"]):
            continue

        if not (is_pdf_url(c.url) or likely_doc_url(c.url, c.title)):
            continue

        key = c.url.split("#")[0]
        if key not in by_url:
            by_url[key] = c
        else:
            old = by_url[key]
            if c.title and c.title not in old.title:
                old.title = clean_text((old.title + " | " + c.title).strip(" |"))
            if c.origem and c.origem not in old.origem:
                old.origem = clean_text(old.origem + ";" + c.origem)

    return sorted(by_url.values(), key=lambda x: (classify_candidate(x.url, x.title), x.url))


def download_candidate(
    c: PdfCandidate,
    page_url: str,
    slug: str,
    out_pdf_dir: Path,
    old_manifest: dict,
    forcar: bool = False,
    verify_ssl: bool = True,
) -> dict:
    out_pdf_dir.mkdir(parents=True, exist_ok=True)
    tipo = classify_candidate(c.url, c.title)
    filename = filename_from_url(c.url, c.title)
    local_path = out_pdf_dir / filename

    old = old_manifest.get(c.url, {})
    row = {
        "id": c.id,
        "tipo": tipo,
        "competicao_slug": slug,
        "page_url": page_url,
        "title": c.title,
        "url": c.url,
        "filename": filename,
        "local_path": str(local_path).replace("\\", "/"),
        "status": "",
        "content_type": "",
        "bytes": 0,
        "sha256": "",
        "etag": "",
        "last_modified": "",
        "origem": c.origem,
        "baixado_em": "",
        "atualizado": False,
    }

    try:
        h = requests.head(c.url, headers=HEADERS, timeout=45, allow_redirects=True, verify=verify_ssl)
        row["status"] = str(h.status_code)
        row["content_type"] = h.headers.get("content-type", "")
        row["etag"] = h.headers.get("etag", "")
        row["last_modified"] = h.headers.get("last-modified", "")

        if not forcar and local_path.exists() and old:
            same_etag = row["etag"] and row["etag"] == old.get("etag")
            same_lastmod = row["last_modified"] and row["last_modified"] == old.get("last_modified")
            if same_etag or same_lastmod:
                row.update(old)
                row["atualizado"] = False
                return row
    except Exception:
        pass

    try:
        r = requests.get(c.url, headers=HEADERS, timeout=120, allow_redirects=True, verify=verify_ssl)
        row["status"] = str(r.status_code)
        row["content_type"] = r.headers.get("content-type", "")
        row["etag"] = r.headers.get("etag", row.get("etag", ""))
        row["last_modified"] = r.headers.get("last-modified", row.get("last_modified", ""))
        row["bytes"] = len(r.content or b"")

        if r.status_code == 200 and r.content:
            content = r.content
            row["sha256"] = sha256_bytes(content)

            if not forcar and local_path.exists() and old and old.get("sha256") == row["sha256"]:
                row["baixado_em"] = old.get("baixado_em", "")
                row["atualizado"] = False
                return row

            if b"%PDF" not in content[:20] and "pdf" not in row["content_type"].lower():
                row["status"] = f"{row['status']} NAO_PDF"
                row["atualizado"] = False
                return row

            local_path.write_bytes(content)
            row["baixado_em"] = datetime.now().isoformat(timespec="seconds")
            row["atualizado"] = True

    except Exception as e:
        row["status"] = f"ERRO: {e}"

    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--slug", default="")
    parser.add_argument("--playwright", action="store_true")
    parser.add_argument("--wait-ms", type=int, default=9000)
    parser.add_argument("--buscar-web", action="store_true")
    parser.add_argument("--forcar", action="store_true")
    parser.add_argument("--somente-listar", action="store_true")
    parser.add_argument("--incluir-sumulas", action="store_true")
    parser.add_argument("--incluir-outros-pdfs", action="store_true")
    parser.add_argument("--insecure", action="store_true", help="Desativa verificação SSL para requests, útil se houver CERTIFICATE_VERIFY_FAILED.")
    parser.add_argument(
        "--todas-competicoes", action="store_true",
        help=(
            "Em vez de checar só --url (Série A por padrão), percorre a página de "
            "tabelas de cada série/competição da CBF (A, B, C, D, Copa do Brasil e "
            "Copa do Brasil Feminina) e acumula os PDFs encontrados de todas elas "
            "em debug_cbf_pdf_links.json. Corrige o problema de a descoberta diária "
            "só cobrir a Série A por padrão, deixando as demais séries dependentes "
            "só do link fixo (seed) manual em adicionar_brasil_jogos.py, que não é "
            "atualizado automaticamente e por isso fica velho sem ninguém perceber."
        ),
    )
    args = parser.parse_args()

    if args.insecure:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    verify_ssl = not args.insecure

    paginas = PAGINAS_CBF_COMPETICOES if args.todas_competicoes else [args.url]

    all_candidates: list[PdfCandidate] = []
    debug: list[dict] = []
    resources: list[dict] = []

    for page_url in paginas:
        slug = infer_slug_from_url(page_url)
        print(f"[INFO] Página CBF: {page_url}")
        print(f"[INFO] Slug: {slug}")

        req_candidates, req_debug = discover_with_requests(page_url, verify_ssl=verify_ssl)
        all_candidates.extend(req_candidates)
        debug.extend(req_debug)
        print(f"[INFO] Candidatos via requests: {len(req_candidates)}")

        if args.playwright:
            pw_candidates, pw_resources = discover_with_playwright(page_url, wait_ms=args.wait_ms)
            all_candidates.extend(pw_candidates)
            resources.extend(pw_resources)
            print(f"[INFO] Candidatos via Playwright: {len(pw_candidates)}")

        if args.buscar_web:
            se_candidates, se_debug = search_engine_candidates(page_url)
            all_candidates.extend(se_candidates)
            debug.extend(se_debug)
            print(f"[INFO] Candidatos via busca web: {len(se_candidates)}")

    # slug/out_pdf_dir do download (modo --somente-listar não usa isso; no modo
    # de download com --todas-competicoes, cada PDF ainda cai na pasta correta
    # porque download_candidate já deriva o slug a partir da própria URL do PDF).
    slug = args.slug or infer_slug_from_url(args.url)
    out_pdf_dir = BASE_PDF_DIR / slug
    OUT_DIR.mkdir(exist_ok=True)

    all_unique = dedupe_candidates(all_candidates)
    candidates = [
        c for c in all_unique
        if competition_doc_allowed(c, incluir_sumulas=args.incluir_sumulas, incluir_outros=args.incluir_outros_pdfs)
    ]

    DEBUG_LINKS_JSON.write_text(
        json.dumps([asdict(c) | {"id": c.id, "tipo": classify_candidate(c.url, c.title)} for c in candidates], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    DEBUG_RESOURCES_JSON.write_text(
        json.dumps({"debug": debug, "resources": resources, "all_candidates_count": len(all_unique)}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"[INFO] Candidatos únicos brutos: {len(all_unique)}")
    print(f"[INFO] Documentos aceitos para download: {len(candidates)}")

    if args.somente_listar:
        for c in candidates:
            print(f"- [{classify_candidate(c.url, c.title)}] {filename_from_url(c.url, c.title)} | {c.url}")
        print(f"[OK] Lista salva em {DEBUG_LINKS_JSON}")
        return

    old_manifest = load_manifest()
    rows_by_url = dict(old_manifest)

    processed = 0
    updated = 0
    for c in candidates:
        row = download_candidate(c, args.url, slug, out_pdf_dir, old_manifest, forcar=args.forcar, verify_ssl=verify_ssl)
        rows_by_url[c.url] = row
        processed += 1
        if row.get("atualizado"):
            updated += 1
            print(f"[PDF] atualizado: [{row['tipo']}] {row['filename']} ({row.get('bytes', 0)} bytes)")
        else:
            print(f"[--] sem mudança/não pdf: [{row['tipo']}] {row['filename']} | {row.get('status', '')}")
        time.sleep(0.2)

    write_manifest(rows_by_url)

    print("")
    print(f"Documentos processados: {processed}")
    print(f"PDFs novos/atualizados: {updated}")
    print(f"Pasta PDFs: {out_pdf_dir}")
    print(f"Manifesto JSON: {MANIFEST_JSON}")
    print(f"Manifesto CSV: {MANIFEST_CSV}")
    print(f"Debug links filtrados: {DEBUG_LINKS_JSON}")
    print(f"Debug recursos: {DEBUG_RESOURCES_JSON}")


if __name__ == "__main__":
    main()
