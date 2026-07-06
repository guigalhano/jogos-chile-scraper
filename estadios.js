/*
  Base melhorada de estádios do futebol chileno.

  Importante:
  - O site campeonatochileno.cl expõe nomes/páginas de estádio, mas não latitude/longitude no HTML público.
  - Este arquivo cruza os nomes extraídos do site com coordenadas aproximadas.
  - Quando aparecer um estádio novo, adicione um objeto nesta lista ou rode o scraper de estádios para gerar pendências.

  Campos:
  - nome: nome principal
  - aliases: variações do nome que podem aparecer no JSON
  - cidade
  - regiao
  - lat/lng
  - fonte: "manual/osm-like" = coordenada aproximada validada manualmente
*/

window.ESTADIOS_CHILE = [
  {
    nome: "Estadio Nacional Julio Martínez Prádanos",
    aliases: ["estadio nacional", "nacional julio martínez", "nacional julio martinez", "nacional"],
    cidade: "Santiago",
    regiao: "Región Metropolitana",
    lat: -33.4649,
    lng: -70.6107,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Monumental David Arellano",
    aliases: ["estadio monumental", "monumental david arellano", "monumental", "estadio de colo colo"],
    cidade: "Santiago",
    regiao: "Región Metropolitana",
    lat: -33.5065,
    lng: -70.6055,
    fonte: "manual/osm-like"
  },
  {
    nome: "Claro Arena / San Carlos de Apoquindo",
    aliases: ["claro arena", "san carlos de apoquindo", "estadio san carlos de apoquindo"],
    cidade: "Santiago",
    regiao: "Región Metropolitana",
    lat: -33.3960,
    lng: -70.5018,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Santa Laura Universidad SEK",
    aliases: ["santa laura", "estadio santa laura", "santa laura universidad sek"],
    cidade: "Santiago",
    regiao: "Región Metropolitana",
    lat: -33.4055,
    lng: -70.6623,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Municipal de La Cisterna",
    aliases: ["la cisterna", "municipal de la cisterna", "estadio municipal de la cisterna"],
    cidade: "Santiago",
    regiao: "Región Metropolitana",
    lat: -33.5210,
    lng: -70.6730,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Bicentenario de La Florida",
    aliases: ["bicentenario de la florida", "la florida", "estadio bicentenario la florida", "estadio bicentenario de la florida", "municipal de la florida"],
    cidade: "Santiago",
    regiao: "Región Metropolitana",
    lat: -33.5408,
    lng: -70.5783,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Municipal de La Pintana",
    aliases: ["la pintana", "municipal de la pintana", "estadio municipal de la pintana"],
    cidade: "Santiago",
    regiao: "Región Metropolitana",
    lat: -33.5852,
    lng: -70.6346,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Santiago Bueras",
    aliases: ["santiago bueras", "estadio santiago bueras", "municipal santiago bueras"],
    cidade: "Maipú",
    regiao: "Región Metropolitana",
    lat: -33.5098,
    lng: -70.7583,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Municipal Luis Navarro Avilés",
    aliases: ["municipal de san bernardo", "san bernardo", "estadio municipal san bernardo", "luis navarro avilés", "luis navarro aviles", "san bernardo luis navarro", "alcalde luis navarro avilés"],
    cidade: "San Bernardo",
    regiao: "Región Metropolitana",
    lat: -33.5945,
    lng: -70.6903,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Municipal de Lo Barnechea",
    aliases: ["lo barnechea", "municipal de lo barnechea", "estadio municipal de lo barnechea"],
    cidade: "Lo Barnechea",
    regiao: "Región Metropolitana",
    lat: -33.3506,
    lng: -70.5184,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Sausalito",
    aliases: ["sausalito", "estadio sausalito"],
    cidade: "Viña del Mar",
    regiao: "Valparaíso",
    lat: -33.0145,
    lng: -71.5355,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Elías Figueroa Brander",
    aliases: ["elías figueroa", "elias figueroa", "playa ancha", "estadio playa ancha", "estadio elías figueroa brander"],
    cidade: "Valparaíso",
    regiao: "Valparaíso",
    lat: -33.0223,
    lng: -71.6400,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Lucio Fariña Fernández",
    aliases: ["lucio fariña", "lucio farina", "municipal lucio fariña fernández", "municipal lucio farina fernandez", "estadio lucio fariña"],
    cidade: "Quillota",
    regiao: "Valparaíso",
    lat: -32.8836,
    lng: -71.2481,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Nicolás Chahuán Nazar",
    aliases: ["nicolás chahuán", "nicolas chahuan", "estadio nicolás chahuán", "estadio nicolas chahuan"],
    cidade: "La Calera",
    regiao: "Valparaíso",
    lat: -32.7931,
    lng: -71.2087,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Regional de Los Andes",
    aliases: ["regional de los andes", "estadio regional de los andes", "los andes"],
    cidade: "Los Andes",
    regiao: "Valparaíso",
    lat: -32.8353,
    lng: -70.5983,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Municipal de Cartagena",
    aliases: ["municipal de cartagena", "cartagena", "estadio municipal cartagena"],
    cidade: "Cartagena",
    regiao: "Valparaíso",
    lat: -33.5527,
    lng: -71.6059,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Municipal de Concón",
    aliases: ["municipal de concón", "municipal de concon", "concon", "concón"],
    cidade: "Concón",
    regiao: "Valparaíso",
    lat: -32.9306,
    lng: -71.5186,
    fonte: "manual/osm-like"
  },

  {
    nome: "Estadio Francisco Sánchez Rumoroso",
    aliases: ["francisco sánchez rumoroso", "francisco sanchez rumoroso", "sánchez rumoroso", "sanchez rumoroso", "estadio municipal francisco sánchez rumoroso", "estadio municipal francisco sanchez rumoroso"],
    cidade: "Coquimbo",
    regiao: "Coquimbo",
    lat: -29.9647,
    lng: -71.3387,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio La Portada",
    aliases: ["la portada", "estadio la portada"],
    cidade: "La Serena",
    regiao: "Coquimbo",
    lat: -29.9078,
    lng: -71.2520,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Diaguita",
    aliases: ["diaguita", "estadio diaguita", "estadio municipal diaguita"],
    cidade: "Ovalle",
    regiao: "Coquimbo",
    lat: -30.6030,
    lng: -71.2055,
    fonte: "manual/osm-like"
  },

  {
    nome: "Estadio El Teniente / Codelco El Teniente",
    aliases: ["el teniente", "estadio el teniente", "estadio codelco el teniente", "codelco el teniente"],
    cidade: "Rancagua",
    regiao: "O'Higgins",
    lat: -34.1744,
    lng: -70.7397,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Municipal Jorge Silva Valenzuela",
    aliases: ["jorge silva valenzuela", "san fernando", "estadio municipal jorge silva valenzuela"],
    cidade: "San Fernando",
    regiao: "O'Higgins",
    lat: -34.5847,
    lng: -70.9901,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Municipal Joaquín Muñoz García",
    aliases: ["joaquín muñoz garcía", "joaquin munoz garcia", "santa cruz", "estadio municipal de santa cruz"],
    cidade: "Santa Cruz",
    regiao: "O'Higgins",
    lat: -34.6381,
    lng: -71.3619,
    fonte: "manual/osm-like"
  },

  {
    nome: "Estadio Fiscal de Talca",
    aliases: ["fiscal de talca", "estadio fiscal de talca"],
    cidade: "Talca",
    regiao: "Maule",
    lat: -35.4264,
    lng: -71.6669,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Municipal Tucapel Bustamante Lastra",
    aliases: ["tucapel bustamante", "municipal de linares", "linares", "estadio municipal de linares"],
    cidade: "Linares",
    regiao: "Maule",
    lat: -35.8463,
    lng: -71.5919,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Fiscal Manuel Moya Medel",
    aliases: ["manuel moya medel", "cauquenes", "fiscal manuel moya medel"],
    cidade: "Cauquenes",
    regiao: "Maule",
    lat: -35.9697,
    lng: -72.3220,
    fonte: "manual/osm-like"
  },

  {
    nome: "Estadio Bicentenario Nelson Oyarzún Arenas",
    aliases: ["nelson oyarzún", "nelson oyarzun", "bicentenario nelson oyarzún", "bicentenario nelson oyarzun", "estadio bicentenario nelson oyarzún"],
    cidade: "Chillán",
    regiao: "Ñuble",
    lat: -36.6183,
    lng: -72.1078,
    fonte: "manual/osm-like"
  },

  {
    nome: "Estadio Ester Roa Rebolledo",
    aliases: ["ester roa", "ester roa rebolledo", "ester roa de concepción", "ester roa de concepcion", "estadio ester roa rebolledo"],
    cidade: "Concepción",
    regiao: "Biobío",
    lat: -36.8372,
    lng: -73.0428,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Huachipato / CAP Acero",
    aliases: ["estadio huachipato", "huachipato", "estadio cap", "cap acero", "estadio cap acero"],
    cidade: "Talcahuano",
    regiao: "Biobío",
    lat: -36.7542,
    lng: -73.1079,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Municipal de Los Ángeles",
    aliases: ["municipal de los ángeles", "municipal de los angeles", "los ángeles", "los angeles", "estadio municipal de los ángeles"],
    cidade: "Los Ángeles",
    regiao: "Biobío",
    lat: -37.4666,
    lng: -72.3522,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Federico Schwager",
    aliases: ["federico schwager", "coronel", "estadio federico schwager"],
    cidade: "Coronel",
    regiao: "Biobío",
    lat: -37.0286,
    lng: -73.1447,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio El Morro",
    aliases: ["el morro", "estadio el morro"],
    cidade: "Talcahuano",
    regiao: "Biobío",
    lat: -36.7214,
    lng: -73.1161,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Municipal Alcaldesa Ester Roa Rebolledo / Las Golondrinas",
    aliases: ["las golondrinas", "municipal las golondrinas", "hualpén", "hualpen"],
    cidade: "Hualpén",
    regiao: "Biobío",
    lat: -36.7817,
    lng: -73.1080,
    fonte: "manual/osm-like"
  },

  {
    nome: "Estadio Germán Becker",
    aliases: ["germán becker", "german becker", "estadio germán becker"],
    cidade: "Temuco",
    regiao: "La Araucanía",
    lat: -38.7485,
    lng: -72.6208,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Municipal de Villarrica",
    aliases: ["municipal de villarrica", "villarrica"],
    cidade: "Villarrica",
    regiao: "La Araucanía",
    lat: -39.2796,
    lng: -72.2273,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Parque Municipal de Valdivia",
    aliases: ["parque municipal de valdivia", "municipal de valdivia", "valdivia"],
    cidade: "Valdivia",
    regiao: "Los Ríos",
    lat: -39.8194,
    lng: -73.2442,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Chinquihue",
    aliases: ["chinquihue", "estadio chinquihue"],
    cidade: "Puerto Montt",
    regiao: "Los Lagos",
    lat: -41.4752,
    lng: -72.9396,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Rubén Marcos Peralta",
    aliases: ["rubén marcos", "ruben marcos", "estadio rubén marcos peralta", "estadio ruben marcos peralta"],
    cidade: "Osorno",
    regiao: "Los Lagos",
    lat: -40.5747,
    lng: -73.1335,
    fonte: "manual/osm-like"
  },

  {
    nome: "Estadio Zorros del Desierto",
    aliases: ["zorros del desierto", "municipal de calama", "estadio zorros del desierto"],
    cidade: "Calama",
    regiao: "Antofagasta",
    lat: -22.4567,
    lng: -68.9241,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Regional Calvo y Bascuñán",
    aliases: ["calvo y bascuñán", "calvo y bascunan", "regional calvo y bascuñán", "regional de antofagasta", "estadio regional calvo y bascuñán"],
    cidade: "Antofagasta",
    regiao: "Antofagasta",
    lat: -23.6700,
    lng: -70.4087,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio El Cobre",
    aliases: ["el cobre", "estadio el cobre"],
    cidade: "El Salvador",
    regiao: "Atacama",
    lat: -26.3403,
    lng: -70.6247,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Luis Valenzuela Hermosilla",
    aliases: ["luis valenzuela hermosilla", "estadio luis valenzuela hermosilla"],
    cidade: "Copiapó",
    regiao: "Atacama",
    lat: -27.3662,
    lng: -70.3323,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Tierra de Campeones Ramón Estay Saavedra",
    aliases: ["tierra de campeones", "estadio tierra de campeones"],
    cidade: "Iquique",
    regiao: "Tarapacá",
    lat: -20.2441,
    lng: -70.1350,
    fonte: "manual/osm-like"
  },
  {
    nome: "Estadio Carlos Dittborn",
    aliases: ["carlos dittborn", "estadio carlos dittborn", "dittborn", "estadio regional de arica", "regional de arica"],
    cidade: "Arica",
    regiao: "Arica y Parinacota",
    lat: -18.4876,
    lng: -70.2991,
    fonte: "manual/osm-like"
  }
];
