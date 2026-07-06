const DATA_URL = "data/jogos_programados.json";

const els = {
  lista: document.getElementById("listaJogos"),
  status: document.getElementById("status"),
  filtroCompeticao: document.getElementById("filtroCompeticao"),
  busca: document.getElementById("busca"),
  ordenar: document.getElementById("ordenar"),
  totalJogos: document.getElementById("totalJogos"),
  totalCompeticoes: document.getElementById("totalCompeticoes"),
  ultimaAtualizacao: document.getElementById("ultimaAtualizacao"),
};

let jogos = [];

function normalize(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

function parseDateTime(jogo) {
  return new Date(`${jogo.data || "2999-12-31"}T${jogo.hora || "00:00"}:00`);
}

function formatDate(dataISO) {
  if (!dataISO) return "Data a confirmar";
  const d = new Date(`${dataISO}T12:00:00`);
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

function uniqueCompetitions(items) {
  return [...new Set(items.map(j => j.competicao).filter(Boolean))].sort();
}

function setupFilters() {
  const comps = uniqueCompetitions(jogos);
  els.filtroCompeticao.innerHTML = `<option value="">Todas</option>` +
    comps.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");

  els.totalJogos.textContent = jogos.length;
  els.totalCompeticoes.textContent = comps.length;

  const latest = jogos
    .map(j => j.atualizado_em)
    .filter(Boolean)
    .sort()
    .at(-1);
  els.ultimaAtualizacao.textContent = formatUpdated(latest);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function filterAndSort() {
  const comp = els.filtroCompeticao.value;
  const q = normalize(els.busca.value);

  let out = jogos.filter(j => {
    const matchComp = !comp || j.competicao === comp;
    const text = normalize([
      j.mandante,
      j.visitante,
      j.estadio,
      j.competicao,
      j.rodada,
      j.fonte,
    ].join(" "));
    return matchComp && (!q || text.includes(q));
  });

  const order = els.ordenar.value;
  if (order === "data-desc") {
    out.sort((a, b) => parseDateTime(b) - parseDateTime(a));
  } else if (order === "competicao") {
    out.sort((a, b) =>
      String(a.competicao || "").localeCompare(String(b.competicao || "")) ||
      parseDateTime(a) - parseDateTime(b)
    );
  } else {
    out.sort((a, b) => parseDateTime(a) - parseDateTime(b));
  }

  render(out);
}

function render(items) {
  els.lista.innerHTML = "";

  if (!jogos.length) {
    els.status.hidden = false;
    els.status.textContent = "Ainda não há jogos no arquivo JSON. Rode o workflow para atualizar os dados ou verifique se o scraper encontrou partidas futuras.";
    return;
  }

  if (!items.length) {
    els.status.hidden = false;
    els.status.textContent = "Nenhum jogo encontrado com esses filtros.";
    return;
  }

  els.status.hidden = true;

  els.lista.innerHTML = items.map(j => `
    <article class="card">
      <div class="card__top">
        <div class="competition">${escapeHtml(j.competicao || "Competição")}</div>
        <div class="date">${escapeHtml(formatDate(j.data))}<br>${escapeHtml(j.hora || "Hora a confirmar")}</div>
      </div>

      <div class="match">
        <h2 class="teams">
          <span>${escapeHtml(j.mandante || "Mandante")}</span>
          <span class="vs">vs</span>
          <span>${escapeHtml(j.visitante || "Visitante")}</span>
        </h2>

        <div class="meta">
          <span>🏟️ <b>Estádio:</b> ${escapeHtml(j.estadio || "A confirmar")}</span>
          <span>🏆 <b>Rodada:</b> ${escapeHtml(j.rodada || "—")}</span>
          <span>🔗 <b>Fonte:</b> ${j.url ? `<a href="${escapeHtml(j.url)}" target="_blank" rel="noopener">${escapeHtml(j.fonte || "site")}</a>` : escapeHtml(j.fonte || "—")}</span>
        </div>
      </div>
    </article>
  `).join("");
}

async function loadData() {
  try {
    const res = await fetch(`${DATA_URL}?v=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    jogos = Array.isArray(data) ? data : [];
    setupFilters();
    filterAndSort();
  } catch (err) {
    console.error(err);
    els.status.hidden = false;
    els.status.classList.add("error");
    els.status.textContent = "Não consegui carregar data/jogos_programados.json. Verifique se o arquivo existe e se o GitHub Pages está ativo.";
  }
}

["change", "input"].forEach(evt => {
  els.filtroCompeticao.addEventListener(evt, filterAndSort);
  els.busca.addEventListener(evt, filterAndSort);
  els.ordenar.addEventListener(evt, filterAndSort);
});

loadData();
