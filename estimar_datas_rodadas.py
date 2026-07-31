"""
Estima datas para jogos sem data confirmada baseado na rodada.

Quando um jogo tem a rodada mas não tem data (ex: "A definir" na CBF),
estima a data baseada em um calendário típico de cada competição.
"""

import json
import re
from datetime import date, timedelta

CALENDARIOS = {
    # Série A/B: ~2 rodadas por semana
    "Serie A": {
        "turno": (date(2026, 5, 24), 19),  # Inicio, num rodadas
        "returno": (date(2026, 8, 29), 19),
    },
    "Serie B": {
        "turno": (date(2026, 5, 25), 19),
        "returno": (date(2026, 8, 30), 19),
    },
    "Mineiro": {
        "unico": (date(2026, 9, 18), 30),  # Mineiro tem até 30 rodadas
    },
    "Paulista": {
        "unico": (date(2026, 3, 7), 32),
    },
}

def estimar_data_rodada(numero_rodada_str, competicao):
    """Estima data para uma rodada específica"""
    try:
        rodada_num = int(numero_rodada_str.strip())
    except:
        return None
    
    # Identificar competição
    comp_lower = competicao.lower()
    
    for comp_chave, calendario in CALENDARIOS.items():
        if comp_chave.lower() in comp_lower:
            if "turno" in calendario and "returno" in calendario:
                if rodada_num <= calendario["turno"][1]:
                    data_inicio, _ = calendario["turno"]
                    dias = (rodada_num - 1) * 4  # ~2 rodadas/semana
                    return (data_inicio + timedelta(days=dias)).isoformat()
                else:
                    data_inicio, _ = calendario["returno"]
                    dias = (rodada_num - calendario["turno"][1] - 1) * 4
                    return (data_inicio + timedelta(days=dias)).isoformat()
            elif "unico" in calendario:
                data_inicio, _ = calendario["unico"]
                dias = (rodada_num - 1) * 4
                return (data_inicio + timedelta(days=dias)).isoformat()
    
    return None

def processar_jogos():
    with open("data/jogos_programados.json", "r", encoding="utf-8") as f:
        jogos = json.load(f)
    
    modificados = 0
    for jogo in jogos:
        # Se não tem data mas tem rodada, tentar estimar
        if not jogo.get("data") and jogo.get("rodada"):
            # Extrair número da rodada
            match = re.search(r'(\d+)', jogo["rodada"])
            if match:
                rodada_str = match.group(1)
                data_estimada = estimar_data_rodada(rodada_str, jogo.get("competicao", ""))
                
                if data_estimada:
                    jogo["data"] = data_estimada
                    # Marcar como estimada
                    extra = jogo.get("extra", "")
                    if "data_estimada=true" not in extra:
                        jogo["extra"] = f"{extra}; data_estimada=true" if extra else "data_estimada=true"
                    modificados += 1
    
    with open("data/jogos_programados.json", "w", encoding="utf-8") as f:
        json.dump(jogos, f, indent=2, ensure_ascii=False)
    
    print(f"OK: {modificados} datas estimadas")

if __name__ == "__main__":
    processar_jogos()
