"""
Estima datas para jogos sem data confirmada baseado na rodada.
"""

import json
import re
import unicodedata
from datetime import date, timedelta

def normalizar(text):
    """Remove acentos e converte para lowercase"""
    nfd = unicodedata.normalize('NFD', text)
    return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn').lower()

def estimar_data_rodada(numero_rodada, competicao):
    """Estima data para uma rodada específica"""
    try:
        rodada = int(numero_rodada)
    except:
        return None
    
    comp_norm = normalizar(competicao)
    
    # Série A: início maio, ~2 rodadas/semana (4 dias entre rodadas)
    if "serie a" in comp_norm:
        if 1 <= rodada <= 19:
            data_inicio = date(2026, 5, 24)
            dias = (rodada - 1) * 4
            return (data_inicio + timedelta(days=dias)).isoformat()
        elif 20 <= rodada <= 38:
            data_inicio = date(2026, 8, 29)
            dias = (rodada - 20) * 4
            return (data_inicio + timedelta(days=dias)).isoformat()
    
    # Série B
    elif "serie b" in comp_norm:
        if 1 <= rodada <= 19:
            data_inicio = date(2026, 5, 25)
            dias = (rodada - 1) * 4
            return (data_inicio + timedelta(days=dias)).isoformat()
        elif 20 <= rodada <= 38:
            data_inicio = date(2026, 8, 30)
            dias = (rodada - 20) * 4
            return (data_inicio + timedelta(days=dias)).isoformat()
    
    # Série C/D
    elif "serie c" in comp_norm or "serie d" in comp_norm:
        data_inicio = date(2026, 6, 1)
        dias = (rodada - 1) * 4
        return (data_inicio + timedelta(days=dias)).isoformat()
    
    # Campeonato Mineiro
    elif "mineiro" in comp_norm:
        data_inicio = date(2026, 9, 18)
        dias = (rodada - 1) * 4
        return (data_inicio + timedelta(days=dias)).isoformat()
    
    return None


def processar_jogos():
    with open("data/jogos_programados.json", "r", encoding="utf-8") as f:
        jogos = json.load(f)
    
    modificados = 0
    for jogo in jogos:
        # Se não tem data mas tem rodada
        if not jogo.get("data") and jogo.get("rodada"):
            # Extrair número da rodada
            match = re.search(r'(\d+)', jogo["rodada"])
            if match:
                rodada_str = match.group(1)
                comp = jogo.get("competicao", "")
                data_estimada = estimar_data_rodada(rodada_str, comp)
                
                if data_estimada:
                    jogo["data"] = data_estimada
                    # Marcar como estimada
                    extra = jogo.get("extra", "")
                    if "data_estimada=true" not in extra:
                        jogo["extra"] = f"{extra}; data_estimada=true" if extra else "data_estimada=true"
                    modificados += 1
    
    with open("data/jogos_programados.json", "w", encoding="utf-8") as f:
        json.dump(jogos, f, indent=2, ensure_ascii=False)
    
    print(f"OK: {modificados} datas estimadas adicionadas")

if __name__ == "__main__":
    processar_jogos()
