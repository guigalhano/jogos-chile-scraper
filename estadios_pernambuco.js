/*
  Base de estádios de Pernambuco (fonte="FPF-PE" no scrap_fpf_pe.py).

  Cobre os 8 clubes do Campeonato Pernambucano Série A1 2026 (confirmado
  via Wikipedia em 17/07/2026): Decisão, Jaguar, Maguary, Náutico, Retrô,
  Santa Cruz, Sport, Vitória das Tabocas.
*/
window.ESTADIOS_PERNAMBUCO = [
  {
    nome: "Estádio Ilha do Retiro",
    aliases: ["ilha do retiro"],
    cidade: "Recife",
    regiao: "Pernambuco",
    lat: -8.0630,
    lng: -34.9051,
    fonte: "Wikipedia (2021/2018 Campeonato Pernambucano) - casa do Sport",
  },
  {
    nome: "Estádio do Arruda",
    aliases: ["arruda"],
    cidade: "Recife",
    regiao: "Pernambuco",
    lat: -8.0267,
    lng: -34.8933,
    fonte: "Wikipedia (2021/2018 Campeonato Pernambucano) - casa do Santa Cruz",
  },
  {
    nome: "Estádio dos Aflitos",
    aliases: ["aflitos"],
    cidade: "Recife",
    regiao: "Pernambuco",
    lat: -8.0406,
    lng: -34.8990,
    fonte: "Wikipedia (2021 Campeonato Pernambucano) - casa do Náutico",
  },
  {
    nome: "Arena de Pernambuco",
    aliases: ["arena pernambuco", "arena de pernambuco", "arena são lourenço da mata"],
    cidade: "São Lourenço da Mata",
    regiao: "Pernambuco",
    lat: -8.0407,
    lng: -35.0104,
    fonte: "Wikipedia (2021 Campeonato Pernambucano) - casa do Retrô, Jaguar, Santa Cruz e Vitória das Tabocas em 2026",
  },
  {
    nome: "Estádio Arthur Tavares de Melo",
    aliases: ["arthur tavares de melo", "arthur tavares melo"],
    cidade: "Bonito",
    regiao: "Pernambuco",
    lat: -8.4700,
    lng: -35.7289,
    fonte: "aproximado (centro de Bonito/PE, ogol.com.br confirma ser a casa do Maguary) - casa do Maguary",
  },
  {
    nome: "Estádio José Dionísio do Carmo (SESC Goiana)",
    aliases: ["jose dionisio do carmo", "josé dionísio do carmo", "sesc goiana"],
    cidade: "Goiana",
    regiao: "Pernambuco",
    lat: -7.5608,
    lng: -35.0028,
    fonte: "aproximado (centro de Goiana/PE, fotmob/ogol confirmam ser a casa do Decisão) - casa do Decisão",
  },
  {
    nome: "Estádio Lacerdão",
    aliases: ["lacerdao", "lacerdão"],
    cidade: "Caruaru",
    regiao: "Pernambuco",
    lat: -8.2784,
    lng: -35.9752,
    fonte: "Wikipedia (2021 Campeonato Pernambucano) - casa do Central (Caruaru)",
  },
];

// Fallback por mandante (usado só quando o jogo não vem com nome de
// estádio - a maioria dos jogos da FPF-PE já traz o estádio no widget,
// então esse mapa é reforço/exceção, não o caminho principal).
window.ESTADIO_MANDANTE_PADRAO_FPFPE = {
  "sport": "ilha do retiro",
  "santa cruz": "arruda",
  "nautico": "aflitos",
  "náutico": "aflitos",
  "retro": "arena pernambuco",
  "retrô": "arena pernambuco",
  "jaguar": "arena pernambuco",
  "vitoria": "arena pernambuco",
  "vitória": "arena pernambuco",
  "vitoria das tabocas": "arena pernambuco",
  "vitória das tabocas": "arena pernambuco",
  "maguary": "arthur tavares de melo",
  "decisao": "jose dionisio do carmo",
  "decisão": "jose dionisio do carmo",
  "central": "lacerdao",
};
