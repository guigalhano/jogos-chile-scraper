/*
  Base de estádios do futebol peruano. Ainda é um stub pequeno: o
  scraper de futbolperuano.com (Liga 1/2/3, Copa de la Liga, Copa Perú,
  Femenino) não traz o nome do estádio por partida na fonte usada, só
  data/hora/times, então por enquanto isso serve principalmente pros
  jogos do Peru que aparecem via CONMEBOL (Libertadores/Sudamericana),
  que já trazem estádio. Dá pra completar com mais clubes depois.
*/

window.ESTADIOS_PERU = [
  {
    nome: "Estadio Nacional de Lima",
    aliases: ["estadio nacional de lima", "estadio nacional del peru", "estadio nacional del perú", "nacional del peru"],
    cidade: "Lima",
    regiao: "Lima",
    lat: -12.0698,
    lng: -77.0378,
  },
  {
    nome: "Estadio Inca Garcilaso de la Vega",
    aliases: ["inca garcilaso de la vega", "estadio garcilaso"],
    cidade: "Cusco",
    regiao: "Cusco",
    lat: -13.5183,
    lng: -71.9714,
    fonte: "manual/aproximado (Cusco, Peru)",
  },
];
