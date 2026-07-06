# Página com mapa, calendário e filtros

Suba estes arquivos na raiz do repositório:

- `index.html`
- `style.css`
- `script.js`
- `estadios.js`

A página lê automaticamente:

- `data/jogos_programados.json`

## Ativar GitHub Pages

No GitHub:

`Settings > Pages > Build and deployment > Deploy from a branch > main > /root > Save`

Depois a página abre em:

`https://guigalhano.github.io/jogos-chile-scraper/`

## Como completar cidades/regiões

Se um jogo aparecer como "Sem coordenadas", abra `estadios.js` e adicione o estádio:

```js
{
  nome: "Nome do Estádio",
  aliases: ["nome curto", "variação que aparece no JSON"],
  cidade: "Cidade",
  regiao: "Região",
  lat: -33.0000,
  lng: -70.0000
}
```

## Filtros incluídos

- Campeonato
- Time
- Região
- Cidade
- Data
- Busca livre
- Botão "Hoje"
- Botão "Jogos sem coordenadas"
