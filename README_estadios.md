# Estádios Chile: scraper + coordenadas melhoradas

Arquivos incluídos:

- `estadios.js`  
  Base melhorada de coordenadas e aliases para a página do mapa.

- `scrap_estadios_campeonato_chileno.py`  
  Script que extrai nomes de estádios do site campeonatochileno.cl e cruza com `estadios.js`.

## Importante

O site do Campeonato Chileno publica nomes e páginas de estádio, por exemplo:

- `/estadio/claro-arena/`
- `/estadio/estadio-el-cobre/`

Mas, pelo HTML público, ele não publica latitude/longitude. Por isso o scraper extrai nomes e gera pendências para você completar quando faltar coordenada.

## Como usar

1. Suba `estadios.js` na raiz do repositório para melhorar o mapa.

2. Opcionalmente suba também `scrap_estadios_campeonato_chileno.py`.

3. Rode localmente:

```bash
pip install requests beautifulsoup4 lxml
python scrap_estadios_campeonato_chileno.py
```

Ele gera:

```text
data/estadios_extraidos.csv
data/estadios_com_coordenadas.csv
data/estadios_pendentes.csv
```

## Como melhorar ainda mais

Quando aparecer pendente em `data/estadios_pendentes.csv`, adicione no `estadios.js`:

```js
{
  nome: "Nome do Estádio",
  aliases: ["variação 1", "variação 2"],
  cidade: "Cidade",
  regiao: "Região",
  lat: -33.0000,
  lng: -70.0000,
  fonte: "manual/osm-like"
}
```
