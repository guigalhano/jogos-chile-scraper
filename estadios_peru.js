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
  {
    nome: "Estadio Alejandro Villanueva (Matute)",
    aliases: ["alejandro villanueva", "matute", "estadio alianza lima"],
    cidade: "Lima",
    regiao: "Lima",
    lat: -12.0672,
    lng: -77.0117,
    fonte: "manual/aproximado (La Victoria, Lima)",
  },
  {
    nome: "Estadio Monumental \"U\"",
    aliases: ["estadio monumental u", "monumental u", "estadio monumental \"u\"", "monumental de universitario"],
    cidade: "Lima",
    regiao: "Lima",
    lat: -12.0089,
    lng: -76.8567,
    fonte: "manual/aproximado (Ate, Lima)",
  },
  {
    nome: "Estadio Alberto Gallardo (La Florida)",
    aliases: ["alberto gallardo", "la florida sporting cristal"],
    cidade: "Lima",
    regiao: "Lima",
    lat: -12.0755,
    lng: -77.0011,
    fonte: "manual/aproximado (San Luis, Lima)",
  },
  {
    nome: "Estadio Mansiche",
    aliases: ["mansiche", "estadio mansiche"],
    cidade: "Trujillo",
    regiao: "La Libertad",
    lat: -8.1116,
    lng: -79.0287,
    fonte: "manual/aproximado (Trujillo, Peru)",
  },
  {
    nome: "Estadio Monumental de la UNSA",
    aliases: ["monumental de la unsa", "estadio unsa", "monumental unsa"],
    cidade: "Arequipa",
    regiao: "Arequipa",
    lat: -16.4090,
    lng: -71.5375,
    fonte: "manual/aproximado (Arequipa, Peru)",
  },
  {
    nome: "Estadio Campeones del 36",
    aliases: ["campeones del 36"],
    cidade: "Piura",
    regiao: "Piura",
    lat: -5.1945,
    lng: -80.6328,
    fonte: "manual/aproximado (Piura, Peru)",
  },
];
