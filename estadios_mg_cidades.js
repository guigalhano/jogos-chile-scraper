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

  // Adicionadas para cobrir cidades da FMF que ainda ficavam sem coordenadas
  // (fonte: IBGE, via alanwillms/geoinfo).
  "abaete": { lat: -19.1551, lng: -45.4444 },
  "araxa": { lat: -19.5902, lng: -46.9438 },
  "belmiro braga": { lat: -21.9440, lng: -43.4084 },
  "bom despacho": { lat: -19.7386, lng: -45.2622 },
  "brumadinho": { lat: -20.1510, lng: -44.2007 },
  "caete": { lat: -19.8826, lng: -43.6704 },
  "carmo da mata": { lat: -20.5575, lng: -44.8735 },
  "carmo do cajuru": { lat: -20.1912, lng: -44.7664 },
  "esmeraldas": { lat: -19.7640, lng: -44.3065 },
  "itabira": { lat: -19.6239, lng: -43.2312 },
  "ituiutaba": { lat: -18.9772, lng: -49.4639 },
  "joao monlevade": { lat: -19.8126, lng: -43.1735 },
  "mario campos": { lat: -20.0582, lng: -44.1883 },
  "mateus leme": { lat: -19.9794, lng: -44.4318 },
  "ouro preto": { lat: -20.3796, lng: -43.5120 },
  "para de minas": { lat: -19.8534, lng: -44.6114 },
  "pocos de caldas": { lat: -21.7800, lng: -46.5692 },
  "prudente de morais": { lat: -19.4742, lng: -44.1591 },
  "raposos": { lat: -19.9636, lng: -43.8079 },
  "rio acima": { lat: -20.0876, lng: -43.7878 },
  "sao gotardo": { lat: -19.3087, lng: -46.0465 },
  "sao joaquim de bicas": { lat: -20.0480, lng: -44.2749 },
  "sao jose da lapa": { lat: -19.6971, lng: -43.9586 },
  "vicosa": { lat: -20.7559, lng: -42.8742 },
};
