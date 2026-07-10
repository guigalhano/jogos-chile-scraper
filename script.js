const DATA_URL = "data/jogos_programados.json";

const I18N = {
  pt: {
    locale: "pt-BR",
    htmlLang: "pt-BR",
    titleDoc: "Mapa de Jogos · Futebol Sul-Americano",
    eyebrow: "Futebol sul-americano · agenda automática",
    title: "Mapa de jogos na América do Sul",
    subtitle: "Encontre seu próximo jogo na América do Sul. Explore partidas em um mapa interativo e filtre por país, campeonato, time, cidade, região, estádio ou data. A agenda é atualizada automaticamente com dados de sites oficiais de federações, competições e organizadores.",
    stat_games: "jogos filtrados",
    stat_map: "no mapa",
    stat_cities: "cidades",
    stat_updated: "última atualização",
    filters: "Filtros",
    clear: "Limpar",
    country: "País",
    championship: "Campeonato",
    team: "Time",
    region: "Região",
    city: "Cidade",
    date: "Data",
    search: "Buscar",
    search_placeholder: "Equipe, estádio, cidade, região...",
    today: "Hoje",
    next3: "Próximos 3 dias",
    next7: "Próximos 7 dias",
    next15: "Próximos 15 dias",
    next30: "Próximos 30 dias",
    next60: "Próximos 60 dias",
    radius_suffix: "km ao redor da cidade",
    no_coords: "Jogos sem coordenadas",
    show_all: "Mostrar todos",
    show_all_team: "Mostrar todos do time",
    choose_team_first: "Escolha um time primeiro",
    all_team_active: team => `Mostrando todos os jogos disponíveis de ${team}`,
    all_m: "Todos",
    all_f: "Todas",
    calendar: "Calendário",
    hint: "Para melhorar o mapa, edite estadios.js adicionando novos estádios com cidade, região, latitude e longitude.",
    footer_text: "Dados gerados pelo scraper do repositório",
    games: "jogos",
    game: "jogo",
    no_games_json: "Ainda não há jogos em data/jogos_programados.json. Rode o workflow ou verifique se o scraper encontrou partidas futuras.",
    no_results: "Nenhum jogo encontrado com esses filtros.",
    loading_map: "Carregando mapa...",
    no_json: "Não consegui carregar data/jogos_programados.json. Verifique se o arquivo existe e se o GitHub Pages está ativo.",
    map_json_error: "Erro ao carregar o JSON.",
    no_json_map: "Sem jogos no JSON. Rode o workflow para atualizar.",
    no_coords_filtered: "Nenhum jogo filtrado tem coordenadas de estádio. Complete o arquivo estadios.js.",
    map_count: (mapped, total) => `${mapped} de ${total} jogos filtrados aparecem no mapa.`,
    period3: "Filtro ativo: próximos 3 dias",
    period7: "Filtro ativo: próximos 7 dias",
    period15: "Filtro ativo: próximos 15 dias",
    period30: "Filtro ativo: próximos 30 dias",
    period60: "Filtro ativo: próximos 60 dias",
    futureDefault: "Mostrando jogos de hoje em diante",
    date_confirm: "Data a confirmar",
    time_confirm: "Hora a confirmar",
    stadium_confirm: "Estádio a confirmar",
    city_confirm: "Cidade a confirmar",
    round_confirm: "Rodada a confirmar",
    source: "Fonte",
    on_map: "No mapa",
    without_coords: "Sem coordenadas",
    championship_fallback: "Competição",
    home_fallback: "Mandante",
    away_fallback: "Visitante",
    see_source: "Ver fonte",
    estimated_venue: "estádio estimado",
  },
  es: {
    locale: "es-CL",
    htmlLang: "es-CL",
    titleDoc: "Mapa de Partidos · Fútbol Sudamericano",
    eyebrow: "Fútbol sudamericano · agenda automática",
    title: "Mapa de partidos en Sudamérica",
    subtitle: "Encuentra tu próximo partido en Sudamérica. Explora los encuentros en un mapa interactivo y filtra por país, campeonato, equipo, ciudad, región, estadio o fecha. La agenda se actualiza automáticamente con datos de sitios oficiales de federaciones, competiciones y organizadores.",
    stat_games: "partidos filtrados",
    stat_map: "en el mapa",
    stat_cities: "ciudades",
    stat_updated: "última actualización",
    filters: "Filtros",
    clear: "Limpiar",
    country: "País",
    championship: "Campeonato",
    team: "Equipo",
    region: "Región",
    city: "Ciudad",
    date: "Fecha",
    search: "Buscar",
    search_placeholder: "Equipo, estadio, ciudad, región...",
    today: "Hoy",
    next3: "Próximos 3 días",
    next7: "Próximos 7 días",
    next15: "Próximos 15 días",
    next30: "Próximos 30 días",
    next60: "Próximos 60 días",
    radius_suffix: "km alrededor de la ciudad",
    no_coords: "Partidos sin coordenadas",
    show_all: "Mostrar todos",
    show_all_team: "Mostrar todos del equipo",
    choose_team_first: "Elige un equipo primero",
    all_team_active: team => `Mostrando todos los partidos disponibles de ${team}`,
    all_m: "Todos",
    all_f: "Todas",
    calendar: "Calendario",
    hint: "Para mejorar el mapa, edita estadios.js agregando nuevos estadios con ciudad, región, latitud y longitud.",
    footer_text: "Datos generados por el scraper del repositorio",
    games: "partidos",
    game: "partido",
    no_games_json: "Todavía no hay partidos en data/jogos_programados.json. Ejecuta el workflow o revisa si el scraper encontró partidos futuros.",
    no_results: "No se encontraron partidos con esos filtros.",
    loading_map: "Cargando mapa...",
    no_json: "No pude cargar data/jogos_programados.json. Revisa si el archivo existe y si GitHub Pages está activo.",
    map_json_error: "Error al cargar el JSON.",
    no_json_map: "Sin partidos en el JSON. Ejecuta el workflow para actualizar.",
    no_coords_filtered: "Ningún partido filtrado tiene coordenadas de estadio. Completa el archivo estadios.js.",
    map_count: (mapped, total) => `${mapped} de ${total} partidos filtrados aparecen en el mapa.`,
    period3: "Filtro activo: próximos 3 días",
    period7: "Filtro activo: próximos 7 días",
    period15: "Filtro activo: próximos 15 días",
    period30: "Filtro activo: próximos 30 días",
    period60: "Filtro activo: próximos 60 días",
    futureDefault: "Mostrando partidos desde hoy en adelante",
    date_confirm: "Fecha por confirmar",
    time_confirm: "Hora por confirmar",
    stadium_confirm: "Estadio por confirmar",
    city_confirm: "Ciudad por confirmar",
    round_confirm: "Fecha/rueda por confirmar",
    source: "Fuente",
    on_map: "En el mapa",
    without_coords: "Sin coordenadas",
    championship_fallback: "Competición",
    home_fallback: "Local",
    away_fallback: "Visitante",
    see_source: "Ver fuente",
    estimated_venue: "estadio estimado",
  },
};

let currentLang = localStorage.getItem("jogosChileLang") || "pt";
let activePeriodDays = 3; // "Próximos 3 dias" selecionado por padrão ao carregar
let showAllTeamMode = false;

const els = {
  totalJogos: document.getElementById("totalJogos"),
  totalNoMapa: document.getElementById("totalNoMapa"),
  totalCidades: document.getElementById("totalCidades"),
  ultimaAtualizacao: document.getElementById("ultimaAtualizacao"),
  filtroPais: document.getElementById("filtroPais"),
  filtroCompeticao: document.getElementById("filtroCompeticao"),
  filtroTime: document.getElementById("filtroTime"),
  filtroRegiao: document.getElementById("filtroRegiao"),
  filtroCidade: document.getElementById("filtroCidade"),
  raioWrap: document.getElementById("raioWrap"),
  raioLabelTexto: document.getElementById("raioLabelTexto"),
  filtroRaio: document.getElementById("filtroRaio"),
  raioValorTexto: document.getElementById("raioValorTexto"),
  filtroData: document.getElementById("filtroData"),
  busca: document.getElementById("busca"),
  hojeBtn: document.getElementById("hojeBtn"),
  proximos3Btn: document.getElementById("proximos3Btn"),
  proximos7Btn: document.getElementById("proximos7Btn"),
  proximos15Btn: document.getElementById("proximos15Btn"),
  proximos30Btn: document.getElementById("proximos30Btn"),
  proximos60Btn: document.getElementById("proximos60Btn"),
  todosDoTimeBtn: document.getElementById("todosDoTimeBtn"),
  limparBtn: document.getElementById("limparBtn"),
  semMapaBtn: document.getElementById("semMapaBtn"),
  calendario: document.getElementById("calendario"),
  contadorLista: document.getElementById("contadorLista"),
  mapStatus: document.getElementById("mapStatus"),
  periodoAtivo: document.getElementById("periodoAtivo"),
  timeModoAtivo: document.getElementById("timeModoAtivo"),
  ptBtn: document.getElementById("ptBtn"),
  esBtn: document.getElementById("esBtn"),
};

let jogosOriginais = [];
let jogosEnriquecidos = [];
let markersLayer;
let semMapaAtivo = false;

const chileBounds = [
  [-56.0, -76.5],
  [-17.0, -66.0],
];

const map = L.map("map", {
  scrollWheelZoom: true,
  zoomControl: true,
}).fitBounds(chileBounds);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 18,
  attribution: "&copy; OpenStreetMap",
}).addTo(map);

markersLayer = L.layerGroup().addTo(map);

// O ponto do estádio cresce conforme o usuário dá zoom no mapa, para ficar
// proporcional (em zoom de continente um ponto grande polui o mapa; em
// zoom de rua um ponto pequeno fica difícil de clicar/ver).
const DOT_MIN_ZOOM = 3;
const DOT_MAX_ZOOM = 14;
const DOT_MIN_SIZE = 11;
const DOT_MAX_SIZE = 28;

function dotSizeForZoom(zoom) {
  const z = Math.max(DOT_MIN_ZOOM, Math.min(DOT_MAX_ZOOM, zoom));
  const progresso = (z - DOT_MIN_ZOOM) / (DOT_MAX_ZOOM - DOT_MIN_ZOOM);
  return Math.round(DOT_MIN_SIZE + progresso * (DOT_MAX_SIZE - DOT_MIN_SIZE));
}

function updateDotSize() {
  const size = dotSizeForZoom(map.getZoom());
  document.getElementById("map").style.setProperty("--dot-size", `${size}px`);
}

map.on("zoom", updateDotSize);
map.on("zoomend", updateDotSize);
updateDotSize();

function t(key, ...args) {
  const value = I18N[currentLang][key] ?? I18N.pt[key] ?? key;
  return typeof value === "function" ? value(...args) : value;
}

function applyLanguage(lang) {
  currentLang = lang;
  localStorage.setItem("jogosChileLang", lang);
  document.documentElement.lang = t("htmlLang");
  document.title = t("titleDoc");

  document.querySelectorAll("[data-i18n]").forEach(el => {
    el.textContent = t(el.dataset.i18n);
  });

  document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });

  updateRaioLabel();

  els.ptBtn.classList.toggle("active", lang === "pt");
  els.esBtn.classList.toggle("active", lang === "es");

  setupFilters();
  renderAll();
}

function normalize(value) {
  return String(value || "")
    .replace(/[’´`]/g, "'")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .trim();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function addDaysISO(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function formatDate(dataISO) {
  if (!dataISO) return t("date_confirm");
  const d = new Date(`${dataISO}T12:00:00`);
  if (Number.isNaN(d.getTime())) return dataISO;
  return new Intl.DateTimeFormat(t("locale"), {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(d);
}

function formatShortDate(dataISO) {
  if (!dataISO) return "";
  const d = new Date(`${dataISO}T12:00:00`);
  if (Number.isNaN(d.getTime())) return dataISO;
  return new Intl.DateTimeFormat(t("locale"), {
    day: "2-digit",
    month: "2-digit",
  }).format(d);
}

function formatUpdated(value) {
  if (!value) return "—";
  // Os timestamps são gerados nos runners do GitHub Actions com
  // datetime.now() (sem timezone explícito), cujo relógio é UTC.
  // Se não vier com "Z" ou offset explícito, tratamos como UTC.
  let iso = value;
  if (!/Z$|[+-]\d{2}:\d{2}$/.test(iso)) {
    iso = `${iso}Z`;
  }
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return value.split("T")[0] || "—";
  const formatted = new Intl.DateTimeFormat(t("locale"), {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Sao_Paulo",
  }).format(d);
  return `${formatted} (Brasília)`;
}

function parseDateTime(jogo) {
  return new Date(`${jogo.data || "2999-12-31"}T${jogo.hora || "00:00"}:00`);
}

function uniqueSorted(items) {
  return [...new Set(items.filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

function optionHtml(value) {
  return `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`;
}

const BANDEIRA_PAIS = {
  "Chile": "🇨🇱",
  "Brasil": "🇧🇷",
  "Argentina": "🇦🇷",
  "Uruguay": "🇺🇾",
  "Paraguay": "🇵🇾",
  "Peru": "🇵🇪",
  "Colombia": "🇨🇴",
  "Bolivia": "🇧🇴",
  "Ecuador": "🇪🇨",
  "Conmebol": "🏆",
};

function optionHtmlComBandeira(value) {
  const bandeira = BANDEIRA_PAIS[value] || "";
  const label = bandeira ? `${bandeira} ${value}` : value;
  return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
}

function populateSelectComBandeiras(select, values, allLabel) {
  const current = select.value;
  select.innerHTML = `<option value="">${allLabel}</option>` + values.map(optionHtmlComBandeira).join("");
  if (values.includes(current)) select.value = current;
}

function updateRaioLabel() {
  els.raioLabelTexto.innerHTML = `<span id="raioValorTexto">${els.filtroRaio.value}</span> ${t("radius_suffix")}`;
  els.raioValorTexto = document.getElementById("raioValorTexto");
}

function distanciaKm(lat1, lng1, lat2, lng2) {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLng / 2) *
      Math.sin(dLng / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

function coordenadasDaCidade(cidade) {
  const alvo = jogosEnriquecidos.find(j => j.cidade === cidade && j.lat && j.lng);
  return alvo ? { lat: alvo.lat, lng: alvo.lng } : null;
}

function findStadiumInfo(estadioTexto, pais) {
  const txt = normalize(estadioTexto);
  if (!txt) return null;

  const stadiums = pais === "Brasil" ? (window.ESTADIOS_BRASIL || [])
    : pais === "Argentina" ? (window.ESTADIOS_ARGENTINA || [])
    : pais === "Uruguay" ? (window.ESTADIOS_URUGUAY || [])
    : pais === "Paraguay" ? (window.ESTADIOS_PARAGUAY || [])
    : pais === "Peru" ? (window.ESTADIOS_PERU || [])
    : pais === "Colombia" ? (window.ESTADIOS_COLOMBIA || [])
    : pais === "Bolivia" ? (window.ESTADIOS_BOLIVIA || [])
    : pais === "Ecuador" ? (window.ESTADIOS_ECUADOR || [])
    : pais === "Conmebol" ? (window.ESTADIOS_CONMEBOL || [])
    : (window.ESTADIOS_CHILE || []);

  for (const s of stadiums) {
    const names = [s.nome, ...(s.aliases || [])];
    if (names.some(n => txt.includes(normalize(n)) || normalize(n).includes(txt))) {
      return s;
    }
  }

  const PALAVRAS_GENERICAS = new Set([
    "estadio", "municipal", "arena", "parque", "complexo", "campo",
    "centro", "cidade", "governador", "presidente", "doutor", "professor",
  ]);
  const txtTokens = txt.split(/\s+/).filter(token => token.length >= 5 && !PALAVRAS_GENERICAS.has(token));
  for (const s of stadiums) {
    const names = [s.nome, ...(s.aliases || [])].map(normalize).join(" ");
    const hits = txtTokens.filter(token => names.includes(token)).length;
    if (hits >= 2) return s;
  }

  return null;
}

// O scraper do Brasil às vezes só grava a cidade dentro do texto livre
// "extra" (ex.: "pais=Brasil; cidade=Rio de Janeiro"), em vez de um campo
// próprio. Extrai isso como último recurso, quando a base de estádios não
// tiver a cidade.
function extractCidadeFromExtra(extra) {
  const m = String(extra || "").match(/cidade\s*=\s*([^;]+)/i);
  return m ? m[1].trim() : "";
}

function extractEstadoFromExtra(extra) {
  const m = String(extra || "").match(/estado\s*=\s*([^;]+)/i);
  return m ? m[1].trim() : "";
}

// Fallback: quando o scraper não informa o estádio (comum em jogos em casa
// de alguns times, ex.: San Marcos de Arica), usamos o estádio mandante conhecido.
const ESTADIO_MANDANTE_PADRAO_CHILE = {
  "colo colo": "monumental david arellano",
  "universidad de chile": "estadio nacional",
  "universidad catolica": "claro arena",
  "union espanola": "santa laura",
  "palestino": "la cisterna",
  "audax italiano": "bicentenario de la florida",
  "magallanes": "luis navarro avilés",
  "everton": "sausalito",
  "santiago wanderers": "elías figueroa brander",
  "union la calera": "nicolás chahuán",
  "deportes la serena": "la portada",
  "coquimbo unido": "francisco sánchez rumoroso",
  "o'higgins": "el teniente",
  "rangers de talca": "fiscal de talca",
  "nublense": "bicentenario nelson oyarzún",
  "huachipato": "estadio huachipato",
  "universidad de concepcion": "ester roa rebolledo",
  "deportes concepcion": "ester roa rebolledo",
  "universidad de concepcion": "ester roa rebolledo",
  "u de concepcion": "ester roa rebolledo",
  "rangers": "fiscal de talca",
  "santiago morning": "la cisterna",
  "union san felipe": "municipal de san felipe",
  "deportes santa cruz": "municipal santa ana",
  "san luis": "lucio fariña",
  "deportes melipilla": "municipal de melipilla",
  "deportes limache": "gustavo ocaranza",
  "atletico colina": "manuel rojas del rio",
  "deportes temuco": "germán becker",
  "provincial osorno": "rubén marcos peralta",
  "deportes puerto montt": "chinquihue",
  "cobresal": "el cobre",
  "deportes copiapo": "luis valenzuela hermosilla",
  "deportes antofagasta": "regional calvo y bascuñán",
  "cobreloa": "zorros del desierto",
  "deportes iquique": "tierra de campeones",
  "san marcos de arica": "carlos dittborn",
  "curico unido": "la granja",
  "deportes recoleta": "leonel sanchez",
  "club deportes santa cruz": "joaquín muñoz garcía",
  "trasandino": "regional de los andes",

  // Tercera División A 2026 (14 equipes)
  "aguara": "municipal de san joaquin",
  "cdsc aguara": "municipal de san joaquin",
  "atletico oriente": "municipal de lo barnechea",
  "chimbarongo": "municipal de chimbarongo",
  "chimbarongo fc": "municipal de chimbarongo",
  "comunal cabrero": "luis figueroa",
  "constitucion unido": "enrique donn",
  "deportes rancagua": "municipal patricio mekis",
  "dep. rancagua": "municipal patricio mekis",
  "futuro": "municipal de penalolen",
  "futuro fc": "municipal de penalolen",
  "imperial unido": "el alto",
  "lautaro de buin": "lautaro de buin",
  "lautaro": "lautaro de buin",
  "malleco unido": "municipal alberto larraguibel",
  "municipal puente alto": "municipal de puente alto",
  "mun. puente alto": "municipal de puente alto",
  "naval": "el morro",
  "naval de talcahuano": "el morro",
  "quintero unido": "raul vargas",
  "rodelindo roman": "san gregorio",

  // Tercera División B 2026 — Zona Norte (14 equipes)
  "jardin del eden": "bicentenario de la florida",
  "union glorias navales": "olimpico gomez carreno",
  "glorias navales": "olimpico gomez carreno",
  "union companias": "la portada",
  "cultural maipu": "santiago bueras",
  "provincial talagante": "lucas pacheco",
  "prov. talagante": "lucas pacheco",
  "deportes vallenar": "nelson rojas",
  "dep. vallenar": "nelson rojas",
  "audax italiano de paipote": "luis valenzuela",
  "deportes ovalle": "diaguita",
  "municipal mejillones": "rolando cortes",
  "mun. mejillones": "rolando cortes",
  "julio covarrubias": "los jardines",
  "municipal ovalle": "diaguita",
  "mun. ovalle": "diaguita",
  "tricolor municipal": "municipal de paine",
  "tricolor de paine": "municipal de paine",
  "curacavi fc": "olimpico cuyuncavi",
  "ceff copiapo": "luis valenzuela",

  // Tercera División B 2026 — Zona Sur (14 equipes)
  "deportivo pumanque": "municipal de pumanque",
  "pumanque": "municipal de pumanque",
  "buenos aires": "nelson valenzuela",
  "deportes laja historico": "facela",
  "laja historico": "facela",
  "fernandez vial": "ester roa rebolledo",
  "vicente perez rosales": "chinquihue",
  "inter concepcion": "municipal de florida",
  "iberia": "municipal de los angeles",
  "cdsc iberia": "municipal de los angeles",
  "municipal paillaco": "municipal de paillaco",
  "mun. paillaco": "municipal de paillaco",
  "republica independiente": "municipal de hualqui",
  "rep. ind. de hualqui": "municipal de hualqui",
  "gasparin fc": "lo blanco",
  "efc conchali": "municipal de conchali",
  "nacimiento": "municipal de nacimiento",
  "nacimiento cdsc": "municipal de nacimiento",
  "deportes hualpen": "las golondrinas",
  "dep. hualpen": "las golondrinas",
};

const ESTADIO_MANDANTE_PADRAO_ARGENTINA = {
  "river": "monumental",
  "river plate": "monumental",
  "boca": "la bombonera",
  "boca jrs": "la bombonera",
  "boca juniors": "la bombonera",
  "racing": "cilindro",
  "racing club": "cilindro",
  "independiente": "libertadores de america",
  "san lorenzo": "nuevo gasometro",
  "san lorenzo de a": "nuevo gasometro",
  "huracan": "tomas duco",
  "velez": "jose amalfitani",
  "estudiantes": "estadio uno",
  "gimnasia": "estadio bosque",
  "gimnasia la plata": "estadio bosque",
  "all boys": "islas malvinas",
  "dep morón": "francisco urbano",
  "dep moron": "francisco urbano",
  "los andes": "eduardo gallardon",
  "san miguel": "cesar luis menotti",
  "g y tiro s": "gigante del norte",
  "g y esgrima j": "23 de agosto",
  "san martín t": "la ciudadela",
  "san martin t": "la ciudadela",
  "atlanta": "leon kolbowski",
  "racing cba": "presidente peron",
  "agropecuario arg": "ofelia rosenzuaig",
  "at de rafaela": "alfredo terrera",
  "godoy cruz mza": "malvinas argentinas",
  "san telmo": "osvaldo baletto",
  "t suarez": "20 de octubre",
  "colon": "brigadier general estanislao lopez",
  "fc midland": "ciudad de libertad",
  "guemes se": "arturo miranda",
  "talleres": "mario kempes",
  "belgrano": "gigante de alberdi",
  "rosario central": "gigante de arroyito",
  "newell's": "coloso del parque",
  "newells": "coloso del parque",
  "union": "15 de abril",
  "atletico tucuman": "jose fierro",
  "central cordoba": "madre de ciudades",
  "banfield": "florencio sola",
  "lanus": "ciudad de lanus",
  "platense": "ciudad de vicente lopez",
  "tigre": "la candela",
  "argentinos": "estadio maradona",
  "argentinos juniors": "estadio maradona",
  "sarmiento": "eva peron",
  "defensa y justicia": "norberto tomaghello",
  "aldosivi": "jose maria minella",
  "deportivo riestra": "guillermo laza",
  "independiente rivadavia": "bautista gargantini",
  "ind rivadavia mza": "bautista gargantini",
  "gimnasia mza": "victor legrotaglie",
  "gimnasia (mza)": "victor legrotaglie",
  "estudiantes rio cuarto": "antonio candini",
  "instituto": "estadio instituto atletico central cordoba",
  "barracas central": "claudio tapia",
};

const ESTADIO_MANDANTE_PADRAO_PERU = {
  "alianza lima": "alejandro villanueva",
  "universitario": "estadio monumental u",
  "universitario de deportes": "estadio monumental u",
  "sporting cristal": "alberto gallardo",
  "carlos a mannucci": "mansiche",
  "carlos a. mannucci": "mansiche",
  "carlos mannucci": "mansiche",
  "mannucci": "mansiche",
  "cienciano": "inca garcilaso de la vega",
  "melgar": "monumental de la unsa",
  "fbc melgar": "monumental de la unsa",
  "grau": "campeones del 36",
  "atletico grau": "campeones del 36",
  "atlético grau": "campeones del 36",
};

const SUFIXOS_REGIAO_CHILE = [
  "arica y parinacota", "tarapaca", "antofagasta", "atacama", "coquimbo",
  "valparaiso", "metropolitana", "o'higgins", "ohiggins", "maule", "nuble",
  "biobio", "la araucania", "araucania", "los rios", "los lagos", "aysen",
  "magallanes",
];

function stripSufixoRegiaoChile(nomeNormalizado) {
  for (const reg of SUFIXOS_REGIAO_CHILE) {
    if (nomeNormalizado.endsWith(" " + reg)) {
      return nomeNormalizado.slice(0, -(reg.length + 1)).trim();
    }
  }
  return nomeNormalizado;
}

// Categorias/divisões que o Chile as vezes anexa ao nome do time principal
// (ex.: "Universidad de Chile Juvenil Fem", "Ñublense Femenino"). O time
// base costuma jogar no mesmo estádio do time profissional, então vale a
// pena tentar de novo sem esse sufixo antes de desistir.
const SUFIXOS_CATEGORIA_CHILE = ["juvenil fem", "femenino"];

function stripSufixoCategoriaChile(nomeNormalizado) {
  for (const suf of SUFIXOS_CATEGORIA_CHILE) {
    if (nomeNormalizado.endsWith(" " + suf)) {
      return nomeNormalizado.slice(0, -(suf.length + 1)).trim();
    }
  }
  return nomeNormalizado;
}

// Estádio-mandante padrão da LigaPro Serie A (16 clubes 2026). Times de
// Ambato (Técnico Universitario) e Quito (Universidad Católica) marcados
// como incerteza — compartilham estádio com outro clube da mesma cidade
// e não há confirmação 100% de qual é a sede oficial de cada um.
const ESTADIO_MANDANTE_PADRAO_ECUADOR = {
  "liga de quito": "rodrigo paz delgado",
  "independiente del valle": "banco guayaquil",
  "barcelona sc": "banco pichincha",
  "emelec": "george capwell",
  "aucas": "gonzalo pozo ripalda",
  "guayaquil city fc": "christian benitez betancourt",
  "deportivo cuenca": "alejandro serrano aguilar",
  "orense": "9 de mayo",
  "macara": "bellavista",
  "mushuc runa": "coac mushuc runa",
  "libertad (ecuador)": "federativo reina del cisne",
  "delfin": "jocay",
  "manta f.c.": "jocay",
  "leones": "olimpico de ibarra",
  // incerteza — melhor palpite, sem confirmação
  "tecnico universitario": "bellavista",
  "universidad catolica (quito)": "gonzalo pozo ripalda",
};

// Torneo BetPlay (ascenso/reservas) — só os times que consegui confirmar
// com uma fonte real (não é a lista completa das 16 equipes: os que faltam
// ficaram de fora por falta de confirmação, em vez de arriscar um palpite
// errado).
const ESTADIO_MANDANTE_PADRAO_COLOMBIA = {
  "real cartagena": "jaime moron leon",
  "orsomarso sc": "raul miranda",
  "union magdalena": "sierra nevada",
  "inter palmira": "francisco rivera escobar",
  "deportes quindio": "centenario de armenia",
  "barranquilla fc": "romelio martinez",
  "patriotas": "la independencia",
  "envigado fc": "polideportivo sur",
  "itagui leones": "metropolitano ciudad de itagui",
  "bogota fc": "metropolitano de techo",
  "tigres fc": "metropolitano de techo",
  "boca juniors de cali": "pascual guerrero",
  "real cundinamarca": "municipal de mosquera",
  "real santander": "villa concha",
  "independiente santa fe": "el campin",
  "atletico nacional": "atanasio girardot",
};

function findDefaultHomeStadium(mandante, pais) {
  const mapa = pais === "Argentina" ? ESTADIO_MANDANTE_PADRAO_ARGENTINA
    : pais === "Peru" ? ESTADIO_MANDANTE_PADRAO_PERU
    : pais === "Ecuador" ? ESTADIO_MANDANTE_PADRAO_ECUADOR
    : pais === "Colombia" ? ESTADIO_MANDANTE_PADRAO_COLOMBIA
    : ESTADIO_MANDANTE_PADRAO_CHILE;
  const key = normalize(mandante);
  if (mapa[key]) return findStadiumInfo(mapa[key], pais);

  // Nomes argentinos às vezes vêm com pontuação/parênteses irregulares
  // (ex.: "San Lorenzo de A.", "Gimnasia (Mza.)"); tenta de novo sem elas.
  const keySemPontuacao = key.replace(/[().,]/g, "").replace(/\s+/g, " ").trim();
  if (mapa[keySemPontuacao]) return findStadiumInfo(mapa[keySemPontuacao], pais);

  if (pais === "Chile") {
    // anfaterceradivision.cl (Tercera A/B) grava o nome do time seguido da
    // região (ex.: "Quintero Unido Valparaíso", "Comunal Cabrero Biobío").
    const keySemRegiao = stripSufixoRegiaoChile(key);
    if (keySemRegiao !== key && mapa[keySemRegiao]) return findStadiumInfo(mapa[keySemRegiao], pais);

    // campeonatochileno.cl grava categorias femininas/juvenis anexadas ao
    // nome do time principal (ex.: "Universidad de Chile Juvenil Fem").
    const keySemCategoria = stripSufixoCategoriaChile(key);
    if (keySemCategoria !== key && mapa[keySemCategoria]) return findStadiumInfo(mapa[keySemCategoria], pais);
  }

  return null;
}

function derivePais(j) {
  if (j.pais) return j.pais;
  const extra = String(j.extra || "");
  if (/pais\s*=\s*brasil/i.test(extra)) return "Brasil";
  if (/pais\s*=\s*argentina/i.test(extra)) return "Argentina";
  if (/^brasil\s*-/i.test(j.competicao || "")) return "Brasil";
  if (/^argentina\s*-/i.test(j.competicao || "")) return "Argentina";
  return "Chile";
}

function enrichGames(rawGames) {
  return rawGames.map((j, index) => {
    const pais = derivePais(j);
    const estadioBruto = /^(estadio\s*)?por confirmar$|^a confirmar$/i.test(normalize(j.estadio || ""))
      ? ""
      : (j.estadio || "");
    // FIX: jogos da FMF (fonte === "FMF") são de estádios pequenos/locais de
    // Minas Gerais que não estão na base nacional (ESTADIOS_BRASIL só cobre
    // clubes de Série A/B/C/D + Copa do Brasil). Buscar nessa base para um
    // nome genérico tipo "Estádio Municipal Bezerrão" pode colidir por
    // engano com um estádio de OUTRO estado com nome parecido (ex.: bateu
    // com o "Bezerrão" de Gama/DF, ou "Arena Santa Cruz" bateu com o
    // "Estádio Santa Cruz" de Ribeirão Preto/SP). Para fonte FMF, pula essa
    // busca nacional e vai direto para o fallback por cidade de MG.
    const ehFMF = j.fonte === "FMF";
    let stadium = ehFMF ? null : findStadiumInfo(estadioBruto, pais);
    let estadioFallback = false;
    if (!stadium && !estadioBruto && pais !== "Brasil") {
      stadium = findDefaultHomeStadium(j.mandante, pais);
      estadioFallback = Boolean(stadium);
    }
    const cidadeResolvida = j.cidade || stadium?.cidade || extractCidadeFromExtra(j.extra) || "";
    let cidadeCoords = null;
    let regiaoPorCidade = "";
    if (!stadium?.lat && !j.lat && cidadeResolvida) {
      const chave = normalize(cidadeResolvida);
      if (window.CIDADES_MG && window.CIDADES_MG[chave]) {
        cidadeCoords = window.CIDADES_MG[chave];
        regiaoPorCidade = "Minas Gerais";
      } else if (window.CIDADES_SP && window.CIDADES_SP[chave]) {
        cidadeCoords = window.CIDADES_SP[chave];
        regiaoPorCidade = "São Paulo";
      }
    }
    return {
      ...j,
      _idx: index,
      _stadiumInfo: stadium,
      _estadioFallback: estadioFallback,
      pais,
      estadio: estadioBruto || (estadioFallback ? stadium.nome : ""),
      cidade: cidadeResolvida,
      regiao: j.regiao || stadium?.regiao || extractEstadoFromExtra(j.extra) || regiaoPorCidade,
      lat: j.lat || stadium?.lat || cidadeCoords?.lat || null,
      lng: j.lng || stadium?.lng || cidadeCoords?.lng || null,
      temMapa: Boolean(j.lat && j.lng) || Boolean(stadium?.lat && stadium?.lng) || Boolean(cidadeCoords),
    };
  });
}

function populateSelect(select, values, allLabel) {
  const current = select.value;
  select.innerHTML = `<option value="">${allLabel}</option>` + values.map(optionHtml).join("");
  if (values.includes(current)) select.value = current;
}

function setupFilters() {
  const paises = uniqueSorted(jogosEnriquecidos.map(j => j.pais));
  // "Conmebol" fica sempre em primeiro no filtro (competições continentais
  // em destaque), o resto segue em ordem alfabética normal.
  const idxConmebol = paises.indexOf("Conmebol");
  if (idxConmebol > 0) {
    paises.splice(idxConmebol, 1);
    paises.unshift("Conmebol");
  }
  populateSelectComBandeiras(els.filtroPais, paises, t("all_m"));

  const pais = els.filtroPais.value;
  const escopoPais = pais ? jogosEnriquecidos.filter(j => j.pais === pais) : jogosEnriquecidos;

  const regioes = uniqueSorted(escopoPais.map(j => j.regiao));
  populateSelect(els.filtroRegiao, regioes, t("all_f"));

  updateDependentCompTimeOptions();
  updateDependentCityOptions();
}

// Campeonato e Time dependem do País e da Região selecionados.
function updateDependentCompTimeOptions() {
  const pais = els.filtroPais.value;
  const regiao = els.filtroRegiao.value;
  const escopo = jogosEnriquecidos.filter(j =>
    (!pais || j.pais === pais) && (!regiao || j.regiao === regiao)
  );

  const comps = uniqueSorted(escopo.map(j => j.competicao));
  const times = uniqueSorted(escopo.flatMap(j => [j.mandante, j.visitante]));

  populateSelect(els.filtroCompeticao, comps, t("all_m"));
  populateSelect(els.filtroTime, times, t("all_m"));
  updateTeamButtonState();
}

function updateTeamButtonState() {
  const hasTeam = Boolean(els.filtroTime.value);
  els.todosDoTimeBtn.disabled = !hasTeam;
  els.todosDoTimeBtn.title = hasTeam ? "" : t("choose_team_first");
  els.todosDoTimeBtn.classList.toggle("isActive", showAllTeamMode && hasTeam);
}

function getFilteredGames() {
  const pais = els.filtroPais.value;
  const comp = els.filtroCompeticao.value;
  const time = els.filtroTime.value;
  const regiao = els.filtroRegiao.value;
  const cidade = els.filtroCidade.value;
  const raioKm = Number(els.filtroRaio.value) || 0;
  const cidadeCoords = cidade ? coordenadasDaCidade(cidade) : null;
  const data = els.filtroData.value;
  const q = normalize(els.busca.value);
  const start = todayISO();
  const end = activePeriodDays ? addDaysISO(activePeriodDays - 1) : "";

  let out = jogosEnriquecidos.filter(j => {
    const matchPais = !pais || j.pais === pais;
    const matchComp = !comp || j.competicao === comp;
    const matchTime = !time || j.mandante === time || j.visitante === time;
    const matchRegiao = showAllTeamMode ? true : (!regiao || j.regiao === regiao);
    const matchCidade = showAllTeamMode ? true : (!cidade || j.cidade === cidade ||
      (cidadeCoords && j.lat && j.lng && distanciaKm(cidadeCoords.lat, cidadeCoords.lng, j.lat, j.lng) <= raioKm));
    const matchData = showAllTeamMode ? true : (!data || j.data === data);
    const matchPeriod = showAllTeamMode ? true : (!activePeriodDays || (j.data >= start && j.data <= end));

    // Por padrão, a página mostra somente jogos de hoje em diante.
    // Jogos passados continuam no JSON/histórico, mas não aparecem na tela inicial.
    // Eles só aparecem quando:
    // - o usuário escolhe uma data específica;
    // - usa "Mostrar todos do time";
    // - ou algum filtro de período explícito está ativo.
    const defaultFutureOnly = !showAllTeamMode && !data && !activePeriodDays;
    const matchFutureDefault = defaultFutureOnly ? (!j.data || j.data >= start) : true;

    const matchMapa = !semMapaAtivo || !j.temMapa;

    const text = normalize([
      j.mandante,
      j.visitante,
      j.estadio,
      j.competicao,
      j.rodada,
      j.fonte,
      j.cidade,
      j.regiao,
      j.pais,
    ].join(" "));

    return matchPais && matchComp && matchTime && matchRegiao && matchCidade && matchData && matchPeriod && matchFutureDefault && matchMapa && (!q || text.includes(q));
  });

  out.sort((a, b) => parseDateTime(a) - parseDateTime(b));
  return out;
}

function updateDependentCityOptions() {
  const pais = els.filtroPais.value;
  const regiao = els.filtroRegiao.value;
  const cidades = uniqueSorted(
    jogosEnriquecidos
      .filter(j => (!pais || j.pais === pais) && (!regiao || j.regiao === regiao))
      .map(j => j.cidade)
  );
  populateSelect(els.filtroCidade, cidades, t("all_f"));
  els.raioWrap.hidden = !els.filtroCidade.value;
}

function groupedByDate(games) {
  return games.reduce((acc, j) => {
    const key = j.data || "sem-data";
    if (!acc[key]) acc[key] = [];
    acc[key].push(j);
    return acc;
  }, {});
}

function renderModeInfo() {
  els.proximos3Btn.classList.toggle("isActive", activePeriodDays === 3);
  els.proximos7Btn.classList.toggle("isActive", activePeriodDays === 7);
  els.proximos15Btn.classList.toggle("isActive", activePeriodDays === 15);
  els.proximos30Btn.classList.toggle("isActive", activePeriodDays === 30);
  els.proximos60Btn.classList.toggle("isActive", activePeriodDays === 60);

  if (!activePeriodDays) {
    els.periodoAtivo.hidden = true;
    els.periodoAtivo.textContent = "";
  } else {
    const PERIOD_LABEL_KEYS = { 3: "period3", 7: "period7", 15: "period15", 30: "period30", 60: "period60" };
    const label = t(PERIOD_LABEL_KEYS[activePeriodDays] || "period7");
    const range = `${formatShortDate(todayISO())} – ${formatShortDate(addDaysISO(activePeriodDays - 1))}`;
    els.periodoAtivo.hidden = false;
    els.periodoAtivo.textContent = `${label}: ${range}`;
  }

  const team = els.filtroTime.value;
  if (showAllTeamMode && team) {
    els.timeModoAtivo.hidden = false;
    els.timeModoAtivo.textContent = t("all_team_active", team);
  } else {
    els.timeModoAtivo.hidden = true;
    els.timeModoAtivo.textContent = "";
  }

  updateTeamButtonState();
}

function renderCalendar(games) {
  els.contadorLista.textContent = `${games.length} ${games.length === 1 ? t("game") : t("games")}`;

  if (!jogosEnriquecidos.length) {
    els.calendario.innerHTML = `<div class="empty">${t("no_games_json")}</div>`;
    return;
  }

  if (!games.length) {
    els.calendario.innerHTML = `<div class="empty">${t("no_results")}</div>`;
    return;
  }

  const groups = groupedByDate(games);
  const dates = Object.keys(groups).sort();

  els.calendario.innerHTML = dates.map(dateKey => `
    <div class="dayGroup">
      <h3 class="dayTitle">${escapeHtml(formatDate(dateKey))}</h3>
      ${groups[dateKey].map(j => renderMatchCard(j)).join("")}
    </div>
  `).join("");
}

function renderMatchCard(j) {
  return `
    <article class="matchCard" data-idx="${j._idx}">
      <div class="matchTop">
        <div class="competition">${escapeHtml(j.competicao || t("championship_fallback"))}</div>
        <div class="time">${escapeHtml(j.hora || t("time_confirm"))}</div>
      </div>

      <h4 class="teams">${escapeHtml(j.mandante || t("home_fallback"))} × ${escapeHtml(j.visitante || t("away_fallback"))}</h4>

      <div class="meta">
        <span>🏟️ ${escapeHtml(j.estadio || t("stadium_confirm"))}${j._estadioFallback ? ` <em class="estimated">(${t("estimated_venue")})</em>` : ""}</span>
        <span>📍 ${escapeHtml(j.cidade || t("city_confirm"))} ${j.regiao ? "· " + escapeHtml(j.regiao) : ""}</span>
        <span>🏆 ${escapeHtml(j.rodada || t("round_confirm"))}</span>
        ${j.extra ? `<span>ℹ️ ${escapeHtml(j.extra)}</span>` : ""}
      </div>

      <div class="badges">
        <span class="badge badge--pais">${BANDEIRA_PAIS[j.pais] || "🏳️"} ${escapeHtml(j.pais)}</span>
        ${j.temMapa ? `<span class="badge">${t("on_map")}</span>` : `<span class="badge noMap">${t("without_coords")}</span>`}
        ${j.url ? `<span class="badge"><a href="${escapeHtml(j.url)}" target="_blank" rel="noopener">${t("source")}</a></span>` : ""}
      </div>
    </article>
  `;
}

function markerPopup(j) {
  return `
    <div class="popupTitle">${escapeHtml(j.mandante || t("home_fallback"))} × ${escapeHtml(j.visitante || t("away_fallback"))}</div>
    <div class="popupMeta">
      <b>${escapeHtml(j.competicao || t("championship_fallback"))}</b><br>
      ${escapeHtml(formatDate(j.data))} · ${escapeHtml(j.hora || t("time_confirm"))}<br>
      🏟️ ${escapeHtml(j.estadio || t("stadium_confirm"))}${j._estadioFallback ? ` <em class="estimated">(${t("estimated_venue")})</em>` : ""}<br>
      📍 ${escapeHtml(j.cidade || "")}${j.regiao ? " · " + escapeHtml(j.regiao) : ""}<br>
      ${j.extra ? `ℹ️ ${escapeHtml(j.extra)}<br>` : ""}
      ${j.url ? `<a href="${escapeHtml(j.url)}" target="_blank" rel="noopener">${t("see_source")}</a>` : ""}
    </div>
  `;
}

const DOT_ICON = L.divIcon({
  className: "jogoDotIcon",
  html: '<span class="jogoDot"></span>',
  iconSize: [36, 36],
  iconAnchor: [18, 18],
  popupAnchor: [0, -14],
});

function updateMap(games) {
  markersLayer.clearLayers();

  const withMap = games.filter(j => j.temMapa && j.lat && j.lng);

  for (const j of withMap) {
    L.marker([Number(j.lat), Number(j.lng)], { icon: DOT_ICON })
      .bindPopup(markerPopup(j))
      .addTo(markersLayer);
  }

  els.totalJogos.textContent = games.length;
  els.totalNoMapa.textContent = withMap.length;
  els.totalCidades.textContent = uniqueSorted(games.map(j => j.cidade)).length;

  if (!jogosEnriquecidos.length) {
    els.mapStatus.textContent = t("no_json_map");
    map.fitBounds(chileBounds);
    return;
  }

  if (!withMap.length) {
    els.mapStatus.textContent = t("no_coords_filtered");
    map.fitBounds(chileBounds);
    return;
  }

  const bounds = L.latLngBounds(withMap.map(j => [Number(j.lat), Number(j.lng)]));
  map.fitBounds(bounds.pad(0.25), { maxZoom: 12 });
  els.mapStatus.textContent = t("map_count", withMap.length, games.length);
}

function renderAll() {
  renderModeInfo();
  const filtered = getFilteredGames();
  renderCalendar(filtered);
  updateMap(filtered);
}

function setPeriod(days) {
  activePeriodDays = activePeriodDays === days ? null : days;
  showAllTeamMode = false;
  els.filtroData.value = "";
  renderAll();
}

function setupEvents() {
  [
    els.filtroCompeticao,
    els.filtroTime,
    els.filtroCidade,
    els.filtroData,
    els.busca,
  ].forEach(el => {
    el.addEventListener("input", () => {
      if (el === els.filtroData && els.filtroData.value) {
        activePeriodDays = null;
        showAllTeamMode = false;
      }
      if (el === els.filtroTime && !els.filtroTime.value) showAllTeamMode = false;
      renderAll();
    });
    el.addEventListener("change", () => {
      if (el === els.filtroData && els.filtroData.value) {
        activePeriodDays = null;
        showAllTeamMode = false;
      }
      if (el === els.filtroTime && !els.filtroTime.value) showAllTeamMode = false;
      renderAll();
    });
  });

  els.filtroRegiao.addEventListener("change", () => {
    showAllTeamMode = false;
    els.filtroCompeticao.value = "";
    els.filtroTime.value = "";
    els.filtroCidade.value = "";
    els.raioWrap.hidden = true;
    updateDependentCompTimeOptions();
    updateDependentCityOptions();
    renderAll();
  });

  els.filtroCidade.addEventListener("change", () => {
    els.raioWrap.hidden = !els.filtroCidade.value;
    renderAll();
  });

  els.filtroRaio.addEventListener("input", () => {
    updateRaioLabel();
    renderAll();
  });

  els.filtroPais.addEventListener("change", () => {
    showAllTeamMode = false;
    els.filtroCompeticao.value = "";
    els.filtroTime.value = "";
    els.filtroRegiao.value = "";
    els.filtroCidade.value = "";
    els.raioWrap.hidden = true;
    setupFilters();
    renderAll();
  });

  els.hojeBtn.addEventListener("click", () => {
    activePeriodDays = null;
    showAllTeamMode = false;
    els.filtroData.value = todayISO();
    renderAll();
  });

  els.proximos3Btn.addEventListener("click", () => setPeriod(3));
  els.proximos7Btn.addEventListener("click", () => setPeriod(7));
  els.proximos15Btn.addEventListener("click", () => setPeriod(15));
  els.proximos30Btn.addEventListener("click", () => setPeriod(30));
  els.proximos60Btn.addEventListener("click", () => setPeriod(60));

  els.todosDoTimeBtn.addEventListener("click", () => {
    if (!els.filtroTime.value) {
      alert(t("choose_team_first"));
      return;
    }

    showAllTeamMode = !showAllTeamMode;

    if (showAllTeamMode) {
      activePeriodDays = null;
      els.filtroData.value = "";
      // Mantém campeonato se o usuário quiser ver só daquele campeonato.
      // Ignora cidade/região/data/período para listar todos os jogos disponíveis do time.
      els.filtroRegiao.value = "";
      els.filtroCidade.value = "";
      updateDependentCityOptions();
    }

    renderAll();
  });

  els.limparBtn.addEventListener("click", () => {
    els.filtroPais.value = "";
    els.filtroCompeticao.value = "";
    els.filtroTime.value = "";
    els.filtroRegiao.value = "";
    els.filtroCidade.value = "";
    els.filtroRaio.value = "50";
    updateRaioLabel();
    els.raioWrap.hidden = true;
    els.filtroData.value = "";
    els.busca.value = "";
    activePeriodDays = null;
    showAllTeamMode = false;
    semMapaAtivo = false;
    els.semMapaBtn.textContent = t("no_coords");
    setupFilters();
    renderAll();
  });

  els.semMapaBtn.addEventListener("click", () => {
    semMapaAtivo = !semMapaAtivo;
    els.semMapaBtn.textContent = semMapaAtivo ? t("show_all") : t("no_coords");
    renderAll();
  });

  els.ptBtn.addEventListener("click", () => applyLanguage("pt"));
  els.esBtn.addEventListener("click", () => applyLanguage("es"));

  els.calendario.addEventListener("click", event => {
    const card = event.target.closest(".matchCard");
    if (!card) return;
    const jogo = jogosEnriquecidos.find(j => String(j._idx) === card.dataset.idx);
    if (!jogo || !jogo.temMapa) return;
    map.setView([Number(jogo.lat), Number(jogo.lng)], 12);
  });
}

async function loadData() {
  try {
    const res = await fetch(`${DATA_URL}?v=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();
    jogosOriginais = Array.isArray(data) ? data : [];
    jogosEnriquecidos = enrichGames(jogosOriginais);

    const latest = jogosEnriquecidos.map(j => j.atualizado_em).filter(Boolean).sort().at(-1);
    els.ultimaAtualizacao.textContent = formatUpdated(latest);

    applyLanguage(currentLang);
  } catch (err) {
    console.error(err);
    els.calendario.innerHTML = `<div class="empty">${t("no_json")}</div>`;
    els.mapStatus.textContent = t("map_json_error");
    els.totalJogos.textContent = "0";
    els.totalNoMapa.textContent = "0";
    els.totalCidades.textContent = "0";
  }
}

els.mapStatus.textContent = t("loading_map");
setupEvents();
loadData();
