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
];
