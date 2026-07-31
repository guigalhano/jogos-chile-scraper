import json
import re

# Mapeamento de times para suas cidades/estádios principais
TIMES_CIDADES = {
    "Cruzeiro": "Belo Horizonte",
    "Atlético": "Belo Horizonte",
    "América": "Belo Horizonte",
    "Flamengo": "Rio de Janeiro",
    "Fluminense": "Rio de Janeiro",
    "Botafogo": "Rio de Janeiro",
    "Vasco": "Rio de Janeiro",
    "São Paulo": "São Paulo",
    "Corinthians": "São Paulo",
    "Palmeiras": "São Paulo",
    "Santos": "Santos",
    "Ponte Preta": "Campinas",
    "Guarani": "Campinas",
    "Ituano": "Itu",
    "Red Bull Bragantino": "Bragança Paulista",
    "Novorizontino": "Novo Horizonte",
    "Portuguesa": "São Paulo",
    "Inter": "Porto Alegre",
    "Grêmio": "Porto Alegre",
    "Cebolinha": "Porto Alegre",
    "Sport": "Recife",
    "Santa Cruz": "Recife",
    "Náutico": "Recife",
    "Ceará": "Fortaleza",
    "Fortaleza": "Fortaleza",
    "Caucaia": "Caucaia",
    "Bahia": "Salvador",
    "Vitória": "Salvador",
    "EC Bahia": "Salvador",
    "Goiás": "Goiânia",
    "Vila Nova": "Goiânia",
    "Crac": "Brasília",
    "Brasília": "Brasília",
    "Chapecoense": "Chapecó",
    "Avaí": "Florianópolis",
    "Figueirense": "Florianópolis",
    "Coritiba": "Curitiba",
    "Paraná": "Curitiba",
    "Athletico": "Curitiba",
    "Operário": "Ponta Grossa",
    "Londrina": "Londrina",
    "Fortaleza FC": "Fortaleza",
    "CSA": "Maceió",
    "CRB": "Maceió",
    "Remo": "Belém",
    "Paysandu": "Belém",
    "Manaus": "Manaus",
    "Nacional": "Brasília",
}

with open("data/jogos_programados.json", "r", encoding="utf-8") as f:
    jogos = json.load(f)

modificados = 0
for jogo in jogos:
    # Apenas para Série A
    if "Série A" not in jogo.get("competicao", ""):
        continue
    
    # Se a cidade está vazia ou é ruim, tentar extrair do time
    if not jogo.get("cidade") or jogo.get("cidade") in ["", "A definir"]:
        mandante = jogo.get("mandante", "")
        
        # Extrair nome do time (remover UF entre parênteses)
        mandante_clean = re.sub(r'\s*\([A-Z]{2}\)\s*$', '', mandante)
        
        # Procurar na lista
        for time_chave, cidade in TIMES_CIDADES.items():
            if time_chave.lower() in mandante_clean.lower():
                jogo["cidade"] = cidade
                modificados += 1
                break
    
    # Se data está "A definir" e tem abreviação de dia (sáb, qua, etc)
    if jogo.get("hora") and any(x in jogo.get("hora", "").lower() for x in ["sáb", "dom", "qua", "seg", "ter", "qui", "sex"]):
        jogo["data"] = ""  # Limpar data

with open("data/jogos_programados.json", "w", encoding="utf-8") as f:
    json.dump(jogos, f, indent=2, ensure_ascii=False)

print(f"OK: {modificados} cidades corrigidas")
