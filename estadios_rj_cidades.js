/*
  Coordenadas de cidades do Rio de Janeiro (fallback por cidade).

  Muitos jogos da FFERJ (categorias de base e divisões amadoras) não têm
  o nome do estádio informado no card da FERJ, só a cidade - e a maioria
  vem com "Rio de Janeiro" genérico (não o bairro/clube específico).
  Quando não há correspondência de estádio, usamos o centro da cidade
  como aproximação razoável - melhor que não aparecer no mapa.
*/

window.CIDADES_RJ = {
  "rio de janeiro": { lat: -22.9068, lng: -43.1729 },
  "niteroi": { lat: -22.8833, lng: -43.1036 },
  "duque de caxias": { lat: -22.7856, lng: -43.3117 },
  "nova iguacu": { lat: -22.7556, lng: -43.4603 },
  "sao goncalo": { lat: -22.8268, lng: -43.0539 },
  "petropolis": { lat: -22.5050, lng: -43.1786 },
  "volta redonda": { lat: -22.5231, lng: -44.1042 },
  "campos dos goytacazes": { lat: -21.7522, lng: -41.3244 },
  "cabo frio": { lat: -22.8894, lng: -42.0286 },
  "angra dos reis": { lat: -23.0067, lng: -44.3181 },
  "barra mansa": { lat: -22.5439, lng: -44.1739 },
  "resende": { lat: -22.4703, lng: -44.4475 },
  "teresopolis": { lat: -22.4131, lng: -42.9661 },
  "nova friburgo": { lat: -22.2819, lng: -42.5311 },
  "itaborai": { lat: -22.7439, lng: -42.8592 },
  "magé": { lat: -22.6553, lng: -43.0419 },
  "mage": { lat: -22.6553, lng: -43.0419 },
  "macae": { lat: -22.3708, lng: -41.7869 },
  "araruama": { lat: -22.8722, lng: -42.3436 },
  "buzios": { lat: -22.7469, lng: -41.8817 },
  "saquarema": { lat: -22.9200, lng: -42.5100 },
  "carapebus": { lat: -22.1889, lng: -41.6825 },
  "santo antonio de padua": { lat: -21.5361, lng: -42.1758 },
  "belford roxo": { lat: -22.7642, lng: -43.3994 },
  "campos dos goytacazes": { lat: -21.7545, lng: -41.3244 },
};
