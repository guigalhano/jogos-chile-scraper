/*
  Coordenadas de cidades de Minas Gerais (fallback por cidade).

  Os jogos da FMF acontecem em dezenas de cidades pequenas do interior de
  MG que não têm um estádio "profissional" na base estadios_brasil.js
  (essa cobre só clubes de Série A/B/C/D + Copa do Brasil). Quando não há
  correspondência de estádio, usamos o centro da cidade como aproximação
  razoável — melhor que não aparecer no mapa.
*/

window.CIDADES_MG = {
  "belo horizonte": { lat: -19.9167, lng: -43.9345 },
  "vespasiano": { lat: -19.6889, lng: -43.9236 },
  "contagem": { lat: -19.9317, lng: -44.0536 },
  "sete lagoas": { lat: -19.4658, lng: -44.2468 },
  "itauna": { lat: -20.0742, lng: -44.5828 },
  "juiz de fora": { lat: -21.7642, lng: -43.3503 },
  "sao joao del rei": { lat: -21.1355, lng: -44.2615 },
  "santa luzia": { lat: -19.7697, lng: -43.8514 },
  "muriae": { lat: -21.1306, lng: -42.3664 },
  "betim": { lat: -19.9678, lng: -44.1983 },
  "manhuacu": { lat: -20.2583, lng: -42.0281 },
  "divinopolis": { lat: -20.1389, lng: -44.8839 },
  "oliveira": { lat: -20.6975, lng: -44.8281 },
  "ipatinga": { lat: -19.4683, lng: -42.5367 },
  "nova lima": { lat: -19.9856, lng: -43.8467 },
  "uba": { lat: -21.1200, lng: -42.9425 },
  "montes claros": { lat: -16.7350, lng: -43.8617 },
  "eloi mendes": { lat: -21.5911, lng: -45.5981 },
  "patrocinio": { lat: -18.9439, lng: -46.9928 },
  "patos de minas": { lat: -18.5789, lng: -46.5183 },
  "matozinhos": { lat: -19.5522, lng: -44.0794 },
  "ibirite": { lat: -20.0233, lng: -44.0589 },
  "uberaba": { lat: -19.7483, lng: -47.9319 },
  "formiga": { lat: -20.4650, lng: -45.4267 },
  "coronel fabriciano": { lat: -19.5186, lng: -42.6289 },
  "governador valadares": { lat: -18.8511, lng: -41.9494 },
  "visconde do rio branco": { lat: -21.0100, lng: -42.8386 },
  "itabirinha": { lat: -18.6389, lng: -41.6858 },
  "uberlandia": { lat: -18.9186, lng: -48.2772 },
  "crucilandia": { lat: -20.4494, lng: -44.4867 },
};
