#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Partes comuns dos scrapers da Argentina que gravam em data/jogos_programados.json
(scrap_argentina_sofascore.py e scrap_liga_marplatense.py).

O problema que este arquivo resolve: as divisoes nacionais (LPF, Primera
Nacional, B, C, Federal A, Copa Argentina) vem de mais de uma fonte - a
agenda da AFA (scrap_afa_agenda.py), o ascensodelinterior (Federal A,
scrap_afa_federal_a.py) e o SofaScore (scrap_argentina_sofascore.py), que
traz a temporada inteira, com estadio e placar. Os nomes de time nao batem
entre elas ("River" x "River Plate", "G. Y TIRO (S.)" x "Gimnasia y Tiro"),
entao o merge normal por fonte+codigo nao junta as linhas e o jogo
apareceria duas ou tres vezes.

Regra: mesma competicao + mesmo dia + mandante parecido + visitante parecido
= mesmo jogo. Fica a linha da fonte de maior prioridade (PRIORIDADE_FONTE:
AFA > ascensodelinterior > SofaScore), que herda das outras o que estiver
vazio (estadio, cidade, coordenadas, categoria, rodada).

Nos workflows, depois do merge pos-reset:

  python argentina_comum.py --dedupe

Rodar isso nos workflows da AFA tambem (e nao so no do SofaScore) evita a
janela em que a AFA publica um jogo que o SofaScore ja tinha.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    FUSO_AR = ZoneInfo("America/Argentina/Buenos_Aires")
except Exception:  # noqa: BLE001 - Windows sem tzdata
    # A Argentina nao tem horario de verao desde 2009: UTC-3 fixo e exato.
    FUSO_AR = timezone(timedelta(hours=-3))

OUT_DIR = Path("data")
JOGOS_JSON = OUT_DIR / "jogos_programados.json"
JOGOS_CSV = OUT_DIR / "jogos_programados.csv"
HIST_CSV = OUT_DIR / "historico_jogos.csv"

FIELDS = [
    "id", "fonte", "competicao", "data", "hora",
    "pais", "cidade", "mandante", "visitante", "estadio", "rodada",
    "url", "extra", "atualizado_em",
]

FONTE_SOFASCORE = "SofaScore"
# Menor = vence. Fonte fora daqui nunca e removida pelo dedupe.
PRIORIDADE_FONTE = {"AFA": 0, "AFA-FederalA": 1, FONTE_SOFASCORE: 2}

# Palavras que nao identificam o clube (aparecem em metade dos nomes).
_STOP = {
    "club", "atletico", "at", "ca", "c", "a", "de", "del", "la", "las", "los",
    "el", "y", "fc", "f", "cs", "sc", "cd", "ad", "asoc", "asociacion",
    "deportivo", "dep", "social", "sportivo", "sp", "cultural", "sociedad",
    "futbol", "s", "m", "b", "reserva", "reserve", "reserves",
    # nao decidem sozinhos (San Martin x San Lorenzo, General Mitre x General Paz)
    "san", "santa", "general", "gral",
}


def norm(v) -> str:
    v = unicodedata.normalize("NFD", str(v or ""))
    v = "".join(c for c in v if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", v.lower()).strip()


# Siglas que uma fonte usa e a outra escreve por extenso.
_SIGLAS = {
    "fadep": "fundacion amigos por el deporte",
    "uai": "universidad abierta interamericana",
}


def tokens_time(nome: str) -> set[str]:
    palavras = " ".join(_SIGLAS.get(t, t) for t in norm(nome).split()).split()
    return {t for t in palavras if t not in _STOP and len(t) > 1}


def comparar_times(a: str, b: str) -> bool | None:
    """'River' ~ 'River Plate', 'G. Y TIRO (S.)' ~ 'Gimnasia y Tiro',
    'Def. de Belgrano (V.R.)' ~ 'Defensores de Belgrano Villa Ramallo'.
    Basta uma palavra significativa em comum (ou prefixo de 4+ letras).
    None = nao da para comparar (um dos nomes so tem palavras genericas,
    ex.: 'Sportivo Atletico')."""
    ta, tb = tokens_time(a), tokens_time(b)
    if not ta or not tb:
        return True if norm(a) == norm(b) else None
    for x in ta:
        for y in tb:
            if x == y or (min(len(x), len(y)) >= 4 and (x.startswith(y) or y.startswith(x))):
                return True
    return False


def mesmo_time(a: str, b: str) -> bool:
    return comparar_times(a, b) is True


def mesmo_jogo(o: dict, r: dict) -> bool:
    """Os dois times batem, ou um bate e o outro nao da para comparar."""
    m = comparar_times(o.get("mandante", ""), r.get("mandante", ""))
    v = comparar_times(o.get("visitante", ""), r.get("visitante", ""))
    return False not in (m, v) and True in (m, v)


def eh_argentina(r: dict) -> bool:
    return (r.get("pais") == "Argentina") or (r.get("competicao") or "").startswith("Argentina - ")


# Linhas antigas do scrap_afa_agenda.py: jogos do Torneo Proyeccion (Reserva)
# gravados como "Torneo Clausura" com a zona grudada no visitante
# ("Banfield (Zona A)") - bug corrigido em 14/10/2026. Saem na limpeza.
_PROYECCION_ERRADO_RE = re.compile(r"\(\s*Zona\s+[A-Z]\s*\)\s*$")


def proyeccion_mal_rotulado(r: dict) -> bool:
    return (r.get("fonte") == "AFA" and r.get("competicao") == "Argentina - Torneo Clausura"
            and bool(_PROYECCION_ERRADO_RE.search(r.get("visitante") or "")))


def codigo_sofascore(r: dict) -> int:
    m = re.search(r"codigo_sofascore=(\d+)", r.get("extra") or "")
    return int(m.group(1)) if m else 0


def _dias_vizinhos(data_iso: str) -> list[str]:
    try:
        d = datetime.strptime(data_iso, "%Y-%m-%d")
    except ValueError:
        return []
    return [(d + timedelta(days=k)).strftime("%Y-%m-%d") for k in (-1, 1)]


def _achar_vencedor(r: dict, por_dia: dict[str, list[dict]]) -> dict | None:
    # Os scrapers usam os mesmos rotulos de competicao ("Argentina - Primera
    # B", "Argentina - Torneo Proyeccion"...), entao competicao diferente =
    # jogo diferente.
    comp = norm(r.get("competicao"))
    mesmo_dia = [o for o in por_dia.get(r.get("data", ""), []) if norm(o.get("competicao")) == comp]
    achou = next((o for o in mesmo_dia if mesmo_jogo(o, r)), None)
    if achou:
        return achou
    # As fontes as vezes discordam da data em 1 dia (jogo remarcado que so
    # uma delas atualizou, ou data provisoria do SofaScore): ai exige os dois
    # times batendo de verdade.
    return next((
        o for dia in _dias_vizinhos(r.get("data", ""))
        for o in por_dia.get(dia, [])
        if norm(o.get("competicao")) == comp
        and mesmo_time(o.get("mandante", ""), r.get("mandante", ""))
        and mesmo_time(o.get("visitante", ""), r.get("visitante", ""))
    ), None)


def remover_duplicados(rows: list[dict]) -> tuple[list[dict], int]:
    """Tira (1) o mesmo jogo vindo de mais de uma fonte argentina (fica a de
    maior PRIORIDADE_FONTE), (2) eventos antigos de jogos remarcados no
    proprio SofaScore e (3) as linhas da Reserva que a AFA gravava como
    Torneo Clausura."""
    n_antes = len(rows)
    rows = [r for r in rows if not proyeccion_mal_rotulado(r)]

    # (2) remarcados: mesmo dia + mesmos times, fica o maior codigo_sofascore
    melhor: dict[tuple, int] = {}
    for r in rows:
        if r.get("fonte") == FONTE_SOFASCORE and eh_argentina(r):
            k = (r.get("data"), norm(r.get("mandante")), norm(r.get("visitante")))
            melhor[k] = max(melhor.get(k, 0), codigo_sofascore(r))
    rows = [
        r for r in rows
        if not (r.get("fonte") == FONTE_SOFASCORE and eh_argentina(r))
        or codigo_sofascore(r) == melhor[(r.get("data"), norm(r.get("mandante")), norm(r.get("visitante")))]
    ]

    # (1) por nivel de prioridade: cada linha so pode perder para uma linha
    # de nivel melhor que ja ficou (assim o ascensodelinterior perde para a
    # AFA antes de o SofaScore ser comparado, e o que ele herdou nao se perde).
    fora = {i for i, r in enumerate(rows) if not eh_argentina(r) or r.get("fonte") not in PRIORIDADE_FONTE}
    mantidos: set[int] = set()
    vencedores_por_dia: dict[str, list[dict]] = {}
    for nivel in sorted(set(PRIORIDADE_FONTE.values())):
        novos = []
        for i, r in enumerate(rows):
            if i in fora or PRIORIDADE_FONTE[r["fonte"]] != nivel:
                continue
            venc = _achar_vencedor(r, vencedores_por_dia)
            if venc is None:
                mantidos.add(i)
                novos.append(r)
                continue
            for campo in ("estadio", "cidade", "lat", "lng", "categoria", "rodada"):
                if not venc.get(campo) and r.get(campo):
                    venc[campo] = r[campo]
        for r in novos:
            vencedores_por_dia.setdefault(r.get("data", ""), []).append(r)

    out = [r for i, r in enumerate(rows) if i in fora or i in mantidos]
    return out, n_antes - len(out)


def _load_json(path: Path) -> list[dict]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def dedupe_arquivos() -> None:
    from merge_apos_reset import load_csv_rows, write_csv

    rows, n = remover_duplicados(_load_json(JOGOS_JSON))
    JOGOS_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(JOGOS_CSV, rows)

    hist, n_hist = remover_duplicados(load_csv_rows(HIST_CSV))
    write_csv(HIST_CSV, hist)
    print(f"[argentina] duplicados removidos: {n} em jogos_programados, {n_hist} no historico")


def para_local(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(FUSO_AR)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Remove duplicados AFA x SofaScore em data/jogos_programados.*")
    p.add_argument("--dedupe", action="store_true")
    a = p.parse_args()
    if not a.dedupe:
        p.error("use --dedupe")
    dedupe_arquivos()
