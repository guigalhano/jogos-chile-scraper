/*
  Base de estádios do futebol brasileiro (CBF: Série A/B/C/D, Copa do Brasil).

  Mesmo formato de /estadios.js (Chile), usado pelo script.js para
  resolver cidade, estado (regiao) e coordenadas dos jogos do Brasil
  quando o campo "estadio" do scraper bate com um destes nomes.

  Campos:
  - nome: nome principal
  - aliases: variações do nome que podem aparecer no JSON
  - cidade
  - regiao: estado (UF por extenso)
  - lat/lng
*/

window.ESTADIOS_BRASIL = [
  {
    nome: "Allianz Parque",
    aliases: ["allianz parque", "arena palmeiras"],
    cidade: "São Paulo",
    regiao: "São Paulo",
    lat: -23.5273,
    lng: -46.6783,
  },
  {
    nome: "Arena Condá",
    aliases: ["arena conda", "arena condá"],
    cidade: "Chapecó",
    regiao: "Santa Catarina",
    lat: -27.0910,
    lng: -52.6222,
  },
  {
    nome: "Arena Fonte Nova",
    aliases: ["arena fonte nova", "fonte nova", "itaipava arena fonte nova"],
    cidade: "Salvador",
    regiao: "Bahia",
    lat: -12.9836,
    lng: -38.5054,
  },
  {
    nome: "Arena MRV",
    aliases: ["arena mrv"],
    cidade: "Belo Horizonte",
    regiao: "Minas Gerais",
    lat: -19.8657,
    lng: -44.0994,
  },
  {
    nome: "Arena da Baixada",
    aliases: ["arena da baixada", "ligga arena", "joaquim americo"],
    cidade: "Curitiba",
    regiao: "Paraná",
    lat: -25.4483,
    lng: -49.2731,
  },
  {
    nome: "Arena do Grêmio",
    aliases: ["arena do gremio", "arena do grêmio"],
    cidade: "Porto Alegre",
    regiao: "Rio Grande do Sul",
    lat: -29.9827,
    lng: -51.0680,
  },
  {
    nome: "Estádio Barradão",
    aliases: ["barradão", "barradao"],
    cidade: "Salvador",
    regiao: "Bahia",
    lat: -12.9481,
    lng: -38.4489,
  },
  {
    nome: "Estádio Beira-Rio",
    aliases: ["beira-rio", "beira rio"],
    cidade: "Porto Alegre",
    regiao: "Rio Grande do Sul",
    lat: -30.0653,
    lng: -51.2352,
  },
  {
    nome: "Estádio Couto Pereira",
    aliases: ["couto pereira"],
    cidade: "Curitiba",
    regiao: "Paraná",
    lat: -25.4406,
    lng: -49.2439,
  },
  {
    nome: "Estádio Municipal Cícero de Souza Marques",
    aliases: ["cícero s. marques", "cicero s. marques", "cícero de souza marques", "cicero de souza marques"],
    cidade: "Bragança Paulista",
    regiao: "São Paulo",
    lat: -22.9519,
    lng: -46.5419,
  },
  {
    nome: "Estádio José Maria de Campos Maia",
    aliases: ["josé m. c. maia", "jose m. c. maia", "josé maria de campos maia"],
    cidade: "Mirassol",
    regiao: "São Paulo",
    lat: -20.8181,
    lng: -49.5222,
  },
  {
    nome: "Estádio Olímpico do Pará (Mangueirão)",
    aliases: ["mangueirão", "mangueirao", "olimpico do para"],
    cidade: "Belém",
    regiao: "Pará",
    lat: -1.4108,
    lng: -48.4489,
  },
  {
    nome: "Maracanã",
    aliases: ["maracanã", "maracana", "estadio do maracana"],
    cidade: "Rio de Janeiro",
    regiao: "Rio de Janeiro",
    lat: -22.9121,
    lng: -43.2302,
  },
  {
    nome: "Mineirão",
    aliases: ["mineirão", "mineirao"],
    cidade: "Belo Horizonte",
    regiao: "Minas Gerais",
    lat: -19.8656,
    lng: -43.9695,
  },
  {
    nome: "MorumBIS",
    aliases: ["morumbis", "morumbi", "estadio cicero pompeu de toledo"],
    cidade: "São Paulo",
    regiao: "São Paulo",
    lat: -23.6003,
    lng: -46.7194,
  },
  {
    nome: "Neo Química Arena",
    aliases: ["neo quimica arena", "neo química arena", "arena corinthians"],
    cidade: "São Paulo",
    regiao: "São Paulo",
    lat: -23.5453,
    lng: -46.4742,
  },
  {
    nome: "Estádio Nilton Santos",
    aliases: ["nilton santos", "engenhão", "engenhao"],
    cidade: "Rio de Janeiro",
    regiao: "Rio de Janeiro",
    lat: -22.8925,
    lng: -43.2300,
  },
  {
    nome: "Estádio São Januário",
    aliases: ["são januário", "sao januario"],
    cidade: "Rio de Janeiro",
    regiao: "Rio de Janeiro",
    lat: -22.8917,
    lng: -43.2286,
  },
  {
    nome: "Estádio Urbano Caldeira (Vila Belmiro)",
    aliases: ["vila belmiro", "urbano caldeira"],
    cidade: "Santos",
    regiao: "São Paulo",
    lat: -23.9469,
    lng: -46.3353,
  },
];
