const DATA_URL = "data/jogos_programados.json";

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
  limparBtn: document.getElementById("limparBtn"),
  semMapaBtn: document.getElementById("semMapaBtn"),
  calendario: document.getElementById("calendario"),
  contadorLista: document.getElementById("contadorLista"),
  mapStatus: document.getElementById("mapStatus"),
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

function formatDate(dataISO) {
  if (!dataISO) return "Data a confirmar";
  const d = new Date(`${dataISO}T12:00:00`);
  if (Number.isNaN(d.getTime())) return dataISO;
  return new Intl.DateTimeFormat("pt-BR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(d);
}

function formatUpdated(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value.split("T")[0] || "—";
  return new Intl.DateTimeFormat("pt-BR", {
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

  // 1) match exato/alias contido no texto
  for (const s of stadiums) {
    const names = [s.nome, ...(s.aliases || [])];
    if (names.some(n => txt.includes(normalize(n)) || normalize(n).includes(txt))) {
      return s;
    }
  }

  // 2) match parcial por tokens relevantes
  const txtTokens = txt.split(/\s+/).filter(t => t.length >= 5);
  for (const s of stadiums) {
    const names = [s.nome, ...(s.aliases || [])].map(normalize).join(" ");
    const hits = txtTokens.filter(t => names.includes(t)).length;
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

  populateSelect(els.filtroCompeticao, comps, "Todos");
  populateSelect(els.filtroTime, times, "Todos");
  populateSelect(els.filtroRegiao, regioes, "Todas");
  populateSelect(els.filtroCidade, cidades, "Todas");
}

function getFilteredGames() {
  const comp = els.filtroCompeticao.value;
  const time = els.filtroTime.value;
  const regiao = els.filtroRegiao.value;
  const cidade = els.filtroCidade.value;
  const data = els.filtroData.value;
  const q = normalize(els.busca.value);

  let out = jogosEnriquecidos.filter(j => {
    const matchComp = !comp || j.competicao === comp;
    const matchTime = !time || j.mandante === time || j.visitante === time;
    const matchRegiao = !regiao || j.regiao === regiao;
    const matchCidade = !cidade || j.cidade === cidade;
    const matchData = !data || j.data === data;
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

    return matchComp && matchTime && matchRegiao && matchCidade && matchData && matchMapa && (!q || text.includes(q));
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
  populateSelect(els.filtroCidade, cidades, "Todas");
}

function groupedByDate(games) {
  return games.reduce((acc, j) => {
    const key = j.data || "sem-data";
    if (!acc[key]) acc[key] = [];
    acc[key].push(j);
    return acc;
  }, {});
}

function renderCalendar(games) {
  els.contadorLista.textContent = `${games.length} jogo${games.length === 1 ? "" : "s"}`;

  if (!jogosEnriquecidos.length) {
    els.calendario.innerHTML = `
      <div class="empty">
        Ainda não há jogos em <code>data/jogos_programados.json</code>.
        Rode o workflow ou verifique se o scraper encontrou partidas futuras.
      </div>
    `;
    return;
  }

  if (!games.length) {
    els.calendario.innerHTML = `<div class="empty">Nenhum jogo encontrado com esses filtros.</div>`;
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
        <div class="competition">${escapeHtml(j.competicao || "Competição")}</div>
        <div class="time">${escapeHtml(j.hora || "Hora a confirmar")}</div>
      </div>

      <h4 class="teams">${escapeHtml(j.mandante || "Mandante")} × ${escapeHtml(j.visitante || "Visitante")}</h4>

      <div class="meta">
        <span>🏟️ ${escapeHtml(j.estadio || "Estádio a confirmar")}</span>
        <span>📍 ${escapeHtml(j.cidade || "Cidade a confirmar")} ${j.regiao ? "· " + escapeHtml(j.regiao) : ""}</span>
        <span>🏆 ${escapeHtml(j.rodada || "Rodada a confirmar")}</span>
      </div>

      <div class="badges">
        ${j.temMapa ? `<span class="badge">No mapa</span>` : `<span class="badge noMap">Sem coordenadas</span>`}
        ${j.url ? `<span class="badge"><a href="${escapeHtml(j.url)}" target="_blank" rel="noopener">Fonte</a></span>` : ""}
      </div>
    </article>
  `;
}

function markerPopup(j) {
  return `
    <div class="popupTitle">${escapeHtml(j.mandante || "Mandante")} × ${escapeHtml(j.visitante || "Visitante")}</div>
    <div class="popupMeta">
      <b>${escapeHtml(j.competicao || "Competição")}</b><br>
      ${escapeHtml(formatDate(j.data))} · ${escapeHtml(j.hora || "Hora a confirmar")}<br>
      🏟️ ${escapeHtml(j.estadio || "Estádio a confirmar")}<br>
      📍 ${escapeHtml(j.cidade || "")}${j.regiao ? " · " + escapeHtml(j.regiao) : ""}<br>
      ${j.url ? `<a href="${escapeHtml(j.url)}" target="_blank" rel="noopener">Ver fonte</a>` : ""}
    </div>
  `;
}

function updateMap(games) {
  markersLayer.clearLayers();

  const withMap = games.filter(j => j.temMapa && j.lat && j.lng);

  for (const j of withMap) {
    const marker = L.marker([Number(j.lat), Number(j.lng)])
      .bindPopup(markerPopup(j));
    marker.addTo(markersLayer);
  }

  els.totalJogos.textContent = games.length;
  els.totalNoMapa.textContent = withMap.length;
  els.totalCidades.textContent = uniqueSorted(games.map(j => j.cidade)).length;

  if (!jogosEnriquecidos.length) {
    els.mapStatus.textContent = "Sem jogos no JSON. Rode o workflow para atualizar.";
    map.fitBounds(chileBounds);
    return;
  }

  if (!withMap.length) {
    els.mapStatus.textContent = "Nenhum jogo filtrado tem coordenadas de estádio. Complete o arquivo estadios.js.";
    map.fitBounds(chileBounds);
    return;
  }

  const bounds = L.latLngBounds(withMap.map(j => [Number(j.lat), Number(j.lng)]));
  map.fitBounds(bounds.pad(0.25), { maxZoom: 12 });
  els.mapStatus.textContent = `${withMap.length} de ${games.length} jogos filtrados aparecem no mapa.`;
}

function renderAll() {
  const filtered = getFilteredGames();
  renderCalendar(filtered);
  updateMap(filtered);
}

function setupEvents() {
  [
    els.filtroCompeticao,
    els.filtroTime,
    els.filtroCidade,
    els.filtroData,
    els.busca,
  ].forEach(el => {
    el.addEventListener("input", renderAll);
    el.addEventListener("change", renderAll);
  });

  els.filtroRegiao.addEventListener("change", () => {
    updateDependentCityOptions();
    renderAll();
  });

  els.hojeBtn.addEventListener("click", () => {
    els.filtroData.value = new Date().toISOString().slice(0, 10);
    renderAll();
  });

  els.limparBtn.addEventListener("click", () => {
    els.filtroCompeticao.value = "";
    els.filtroTime.value = "";
    els.filtroRegiao.value = "";
    els.filtroCidade.value = "";
    els.filtroData.value = "";
    els.busca.value = "";
    semMapaAtivo = false;
    els.semMapaBtn.textContent = "Jogos sem coordenadas";
    setupFilters();
    renderAll();
  });

  els.semMapaBtn.addEventListener("click", () => {
    semMapaAtivo = !semMapaAtivo;
    els.semMapaBtn.textContent = semMapaAtivo ? "Mostrar todos" : "Jogos sem coordenadas";
    renderAll();
  });

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

    setupFilters();
    renderAll();
  } catch (err) {
    console.error(err);
    els.calendario.innerHTML = `
      <div class="empty">
        Não consegui carregar <code>data/jogos_programados.json</code>.
        Verifique se o arquivo existe e se o GitHub Pages está ativo.
      </div>
    `;
    els.mapStatus.textContent = "Erro ao carregar o JSON.";
    els.totalJogos.textContent = "0";
    els.totalNoMapa.textContent = "0";
    els.totalCidades.textContent = "0";
  }
}

setupEvents();
loadData();
