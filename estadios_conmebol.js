/*
  Base de estádios para jogos classificados como pais="Conmebol"
  (CONMEBOL Libertadores / Sudamericana - competições continentais de
  clubes). Como os times vêm de vários países, reaproveitamos aqui as
  bases de estádios já existentes (Chile, Brasil, Argentina, Uruguai,
  Paraguai) — a maioria dos estádios de mandantes dessas competições já
  está mapeada nelas.

  Limitação conhecida: clubes de Colômbia, Equador, Peru, Bolívia e
  Venezuela ainda não têm base de estádios própria neste projeto, então
  jogos mandados por times desses países aparecem sem coordenadas (o
  card mostra o selo "sem coordenadas", mesmo comportamento já usado
  pra qualquer estádio não mapeado). Dá pra completar depois.

  Este arquivo precisa ser carregado DEPOIS de estadios.js,
  estadios_brasil.js, estadios_argentina.js, estadios_uruguay.js e
  estadios_paraguay.js no index.html.
*/

window.ESTADIOS_CONMEBOL = [
  ...(window.ESTADIOS_CHILE || []),
  ...(window.ESTADIOS_BRASIL || []),
  ...(window.ESTADIOS_ARGENTINA || []),
  ...(window.ESTADIOS_URUGUAY || []),
  ...(window.ESTADIOS_PARAGUAY || []),
  // Colômbia e Equador ainda não têm base própria no projeto; jogos de
  // clubes desses países em competições CONMEBOL entram aqui direto.
  {
    nome: "Estadio Manuel Murillo Toro",
    aliases: ["manuel murillo toro"],
    cidade: "Ibagué",
    regiao: "Tolima",
    lat: 4.4389,
    lng: -75.2322,
    fonte: "manual/aproximado (cidade de Ibagué, Colômbia)",
  },
  {
    nome: "Estadio Rodrigo Paz Delgado (Casa Blanca)",
    aliases: ["rodrigo paz delgado", "casa blanca"],
    cidade: "Quito",
    regiao: "Pichincha",
    lat: -0.1858,
    lng: -78.4783,
    fonte: "manual/aproximado (Quito, Equador)",
  },
  {
    nome: "Estadio Banco Guayaquil",
    aliases: ["banco guayaquil", "estadio idv", "estadio independiente del valle"],
    cidade: "Quito",
    regiao: "Pichincha",
    lat: -0.4014,
    lng: -78.4517,
    fonte: "manual/aproximado (Sangolquí/Amaguaña, Equador)",
  },
  {
    nome: "Estadio Olímpico de la UCV",
    aliases: ["olimpico de la ucv", "olímpico de la ucv", "estadio olimpico ucv"],
    cidade: "Caracas",
    regiao: "Distrito Capital",
    lat: 10.4880,
    lng: -66.8890,
    fonte: "manual/aproximado (Ciudad Universitaria de Caracas, Venezuela)",
  },
  {
    nome: "Estadio Atanasio Girardot",
    aliases: ["atanasio girardot"],
    cidade: "Medellín",
    regiao: "Antioquia",
    lat: 6.2506,
    lng: -75.5783,
    fonte: "manual/aproximado (Medellín, Colômbia)",
  },
  {
    nome: "Estadio Hernando Siles",
    aliases: ["hernando siles"],
    cidade: "La Paz",
    regiao: "La Paz",
    lat: -16.5309,
    lng: -68.1193,
    fonte: "manual/aproximado (La Paz, Bolívia)",
  },
  {
    nome: "Estadio Nemesio Camacho El Campín",
    aliases: ["nemesio camacho el campin", "nemesio camacho el campín", "el campin", "el campín"],
    cidade: "Bogotá",
    regiao: "Cundinamarca",
    lat: 4.6486,
    lng: -74.0776,
    fonte: "manual/aproximado (Bogotá, Colômbia)",
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
    nome: "Estadio Polideportivo Misael Delgado",
    aliases: ["polideportivo misael delgado", "misael delgado"],
    cidade: "Valencia",
    regiao: "Carabobo",
    lat: 10.2234,
    lng: -68.0115,
    fonte: "manual/confirmado (Valencia, Estado Carabobo, Venezuela)",
  },
];
