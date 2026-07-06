const DATA_URL = "data/jogos_programados.json";

const I18N = {
  pt: {
    locale: "pt-BR",
    htmlLang: "pt-BR",
    titleDoc: "Mapa de Jogos · Futebol Chileno",
    eyebrow: "Futebol chileno · agenda automática",
    title: "Mapa de jogos no Chile",
    subtitle: "Jogos programados por campeonato, time, cidade, região, estádio e data. A página lê automaticamente data/jogos_programados.json.",
    stat_games: "jogos filtrados",
    stat_map: "no mapa",
    stat_cities: "cidades",
    stat_updated: "última atualização",
    filters: "Filtros",
    clear: "Limpar",
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
  },
  es: {
    locale: "es-CL",
    htmlLang: "es-CL",
    titleDoc: "Mapa de Partidos · Fútbol Chileno",
    eyebrow: "Fútbol chileno · agenda automática",
    title: "Mapa de partidos en Chile",
    subtitle: "Partidos programados por campeonato, equipo, ciudad, región, estadio y fecha. La página lee automáticamente data/jogos_programados.json.",
    stat_games: "partidos filtrados",
    stat_map: "en el mapa",
    stat_cities: "ciudades",
    stat_updated: "última actualización",
    filters: "Filtros",
    clear: "Limpiar",
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
  },
};

let currentLang = localStorage.getItem("jogosChileLang") || "pt";
let activePeriodDays = null;
let showAllTeamMode = false;

const els = {
  totalJogos: document.getElementById("totalJogos"),
  totalNoMapa: document.getElementById("totalNoMapa"),
  totalCidades: document.getElementById("totalCidades"),
  ultimaAtualizacao: document.getElementById("ultimaAtualizacao"),
  filtroCompeticao: document.getElementById("filtroCompeticao"),
  filtroTime: document.getElementById("filtroTime"),
  filtroRegiao: document.getElementById("filtroRegiao"),
  filtroCidade: document.getElementById("filtroCidade"),
  filtroData: document.getElementById("filtroData"),
  busca: document.getElementById("busca"),
  hojeBtn: document.getElementById("hojeBtn"),
  proximos3Btn: document.getElementById("proximos3Btn"),
  proximos7Btn: document.getElementById("proximos7Btn"),
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

  els.ptBtn.classList.toggle("active", lang === "pt");
  els.esBtn.classList.toggle("active", lang === "es");

  setupFilters();
  renderAll();
}

function normalize(value) {
  return String(value || "")
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
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value.split("T")[0] || "—";
  return new Intl.DateTimeFormat(t("locale"), {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
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

function findStadiumInfo(estadioTexto) {
  const txt = normalize(estadioTexto);
  if (!txt) return null;

  const stadiums = window.ESTADIOS_CHILE || [];

  for (const s of stadiums) {
    const names = [s.nome, ...(s.aliases || [])];
    if (names.some(n => txt.includes(normalize(n)) || normalize(n).includes(txt))) {
      return s;
    }
  }

  const txtTokens = txt.split(/\s+/).filter(token => token.length >= 5);
  for (const s of stadiums) {
    const names = [s.nome, ...(s.aliases || [])].map(normalize).join(" ");
    const hits = txtTokens.filter(token => names.includes(token)).length;
    if (hits >= 2) return s;
  }

  return null;
}

function enrichGames(rawGames) {
  return rawGames.map((j, index) => {
    const stadium = findStadiumInfo(j.estadio || "");
    return {
      ...j,
      _idx: index,
      _stadiumInfo: stadium,
      cidade: j.cidade || stadium?.cidade || "",
      regiao: j.regiao || stadium?.regiao || "",
      lat: j.lat || stadium?.lat || null,
      lng: j.lng || stadium?.lng || null,
      temMapa: Boolean(j.lat && j.lng) || Boolean(stadium?.lat && stadium?.lng),
    };
  });
}

function populateSelect(select, values, allLabel) {
  const current = select.value;
  select.innerHTML = `<option value="">${allLabel}</option>` + values.map(optionHtml).join("");
  if (values.includes(current)) select.value = current;
}

function setupFilters() {
  const comps = uniqueSorted(jogosEnriquecidos.map(j => j.competicao));
  const times = uniqueSorted(jogosEnriquecidos.flatMap(j => [j.mandante, j.visitante]));
  const regioes = uniqueSorted(jogosEnriquecidos.map(j => j.regiao));
  const cidades = uniqueSorted(jogosEnriquecidos.map(j => j.cidade));

  populateSelect(els.filtroCompeticao, comps, t("all_m"));
  populateSelect(els.filtroTime, times, t("all_m"));
  populateSelect(els.filtroRegiao, regioes, t("all_f"));
  populateSelect(els.filtroCidade, cidades, t("all_f"));
  updateTeamButtonState();
}

function updateTeamButtonState() {
  const hasTeam = Boolean(els.filtroTime.value);
  els.todosDoTimeBtn.disabled = !hasTeam;
  els.todosDoTimeBtn.title = hasTeam ? "" : t("choose_team_first");
  els.todosDoTimeBtn.classList.toggle("isActive", showAllTeamMode && hasTeam);
}

function getFilteredGames() {
  const comp = els.filtroCompeticao.value;
  const time = els.filtroTime.value;
  const regiao = els.filtroRegiao.value;
  const cidade = els.filtroCidade.value;
  const data = els.filtroData.value;
  const q = normalize(els.busca.value);
  const start = todayISO();
  const end = activePeriodDays ? addDaysISO(activePeriodDays - 1) : "";

  let out = jogosEnriquecidos.filter(j => {
    const matchComp = !comp || j.competicao === comp;
    const matchTime = !time || j.mandante === time || j.visitante === time;
    const matchRegiao = showAllTeamMode ? true : (!regiao || j.regiao === regiao);
    const matchCidade = showAllTeamMode ? true : (!cidade || j.cidade === cidade);
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
    ].join(" "));

    return matchComp && matchTime && matchRegiao && matchCidade && matchData && matchPeriod && matchFutureDefault && matchMapa && (!q || text.includes(q));
  });

  out.sort((a, b) => parseDateTime(a) - parseDateTime(b));
  return out;
}

function updateDependentCityOptions() {
  const regiao = els.filtroRegiao.value;
  const cidades = uniqueSorted(
    jogosEnriquecidos
      .filter(j => !regiao || j.regiao === regiao)
      .map(j => j.cidade)
  );
  populateSelect(els.filtroCidade, cidades, t("all_f"));
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

  if (!activePeriodDays) {
    els.periodoAtivo.hidden = true;
    els.periodoAtivo.textContent = "";
  } else {
    const label = activePeriodDays === 3 ? t("period3") : t("period7");
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
        <span>🏟️ ${escapeHtml(j.estadio || t("stadium_confirm"))}</span>
        <span>📍 ${escapeHtml(j.cidade || t("city_confirm"))} ${j.regiao ? "· " + escapeHtml(j.regiao) : ""}</span>
        <span>🏆 ${escapeHtml(j.rodada || t("round_confirm"))}</span>
        ${j.extra ? `<span>ℹ️ ${escapeHtml(j.extra)}</span>` : ""}
      </div>

      <div class="badges">
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
      🏟️ ${escapeHtml(j.estadio || t("stadium_confirm"))}<br>
      📍 ${escapeHtml(j.cidade || "")}${j.regiao ? " · " + escapeHtml(j.regiao) : ""}<br>
      ${j.extra ? `ℹ️ ${escapeHtml(j.extra)}<br>` : ""}
      ${j.url ? `<a href="${escapeHtml(j.url)}" target="_blank" rel="noopener">${t("see_source")}</a>` : ""}
    </div>
  `;
}

function updateMap(games) {
  markersLayer.clearLayers();

  const withMap = games.filter(j => j.temMapa && j.lat && j.lng);

  for (const j of withMap) {
    L.marker([Number(j.lat), Number(j.lng)])
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
    updateDependentCityOptions();
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
    els.filtroCompeticao.value = "";
    els.filtroTime.value = "";
    els.filtroRegiao.value = "";
    els.filtroCidade.value = "";
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
