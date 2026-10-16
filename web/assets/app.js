// D25–D28 — front estático: lê o JSON pré-computado de dist/data, nada de cálculo estatístico
// aqui (só formatação e um lookup). Contrato de cache: toda requisição de dados carrega
// ?v=<version> do meta.json. Cada página declara `data-page` no <body>; o módulo dela roda no load.

"use strict";

const DATA = "data/";
let META = null;

// --- dados ---------------------------------------------------------------------------------------

async function loadMeta() {
  if (META) return META;
  const res = await fetch(`${DATA}meta.json`, { cache: "no-cache" });
  if (!res.ok) throw new Error(`meta.json: ${res.status}`);
  META = await res.json();
  return META;
}

async function loadJSON(path) {
  const meta = await loadMeta();
  const res = await fetch(`${DATA}${path}?v=${meta.version}`);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

// --- recorte (Análises e Meta) -------------------------------------------------------------------
// A janela (`full`, a de análise, ou `recent`, a visão recente) e o tier (`all`, `vct`, `vcl`). Cada
// combinação tem os próprios JSONs em data/analyses/{recorte}/ e data/meta/{recorte}/
// (site_artifacts.py). O recorte vem da URL (?w=recent&tier=vct), senão do último escolhido na aba
// (sessionStorage: acompanha a navegação entre as análises), senão o padrão.

const SCOPE_VALUES = { window: ["full", "recent"], tier: ["all", "vct", "vcl"] };
const SCOPE_PARAMS = { window: "w", tier: "tier" };
const SCOPE_DEFAULT = { window: "full", tier: "all" };
const scopeKey = (s) => `${s.window}-${s.tier}`;

function readStore(key) {
  try {
    return JSON.parse(sessionStorage.getItem(key) ?? "null");
  } catch (_) {
    return null; // armazenamento indisponível: vale a URL ou o padrão
  }
}
function writeStore(key, value) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch (_) {
    /* armazenamento indisponível: o recorte vale só para esta página */
  }
}

function getScope() {
  const saved = readStore("scope") ?? {};
  const pick = (k) => [param(SCOPE_PARAMS[k]), saved[k]].find((v) => SCOPE_VALUES[k].includes(v)) ?? SCOPE_DEFAULT[k];
  return { window: pick("window"), tier: pick("tier") };
}

// A query string do recorte (só o que difere do padrão), para a página somar os próprios filtros.
function scopeParams(scope) {
  const qs = new URLSearchParams();
  for (const k of Object.keys(SCOPE_PARAMS)) if (scope[k] !== SCOPE_DEFAULT[k]) qs.set(SCOPE_PARAMS[k], scope[k]);
  return qs;
}
function replaceQuery(qs) {
  const q = qs.toString();
  history.replaceState(null, "", q ? `?${q}` : location.pathname);
}

// Liga os botões de #scope; `onChange` recebe o recorte novo. Devolve o recorte inicial. Sem o
// seletor de janela (tese da janela), a janela fica como estava: os JSONs do drift são iguais nas
// duas.
function bindScope(onChange) {
  const scope = getScope();
  const bar = $("#scope");
  const period = $("#scope-period");
  const sync = () => {
    bar?.querySelectorAll(".segmented[data-scope]").forEach((g) =>
      g.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.value === scope[g.dataset.scope])))
    );
    if (period?.dataset[scope.window]) period.textContent = period.dataset[scope.window];
    // cabeçalho do Meta: "VCT · últimos 3 meses"
    const context = $("#scope-context");
    const months = bar?.querySelector(`[data-scope="window"] [data-value="${scope.window}"]`)?.textContent;
    if (context && months) {
      const tier = scope.tier === "all" ? "VCT + VCL" : scope.tier.toUpperCase();
      context.textContent = `${tier} · ${scope.window === "full" ? "janela de" : "últimos"} ${months}`;
    }
  };
  bar?.querySelectorAll(".segmented[data-scope] button").forEach((b) =>
    b.addEventListener("click", () => {
      const k = b.closest(".segmented").dataset.scope;
      if (scope[k] === b.dataset.value) return;
      scope[k] = b.dataset.value;
      writeStore("scope", scope);
      sync();
      onChange({ ...scope });
    })
  );
  sync();
  return { ...scope };
}

// Uma troca de recorte por vez, na ordem dos cliques: cada uma limpa e redesenha a página inteira,
// e duas intercaladas desenhariam dois gráficos no mesmo lugar.
function serial(fn) {
  let queue = Promise.resolve();
  return (...args) => (queue = queue.then(() => fn(...args)));
}

// --- formatação (pt-BR) --------------------------------------------------------------------------

const formats = {};
function nf(digits) {
  formats[digits] ??= new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return formats[digits];
}
const num = (x, d = 3) => (x == null ? "—" : nf(d).format(x));
const pct = (x, d = 1) => (x == null ? "—" : `${nf(d).format(x * 100)}%`);
const pp = (x, d = 1) => (x == null ? "—" : `${x > 0 ? "+" : ""}${nf(d).format(x * 100)} p.p.`);
const signed = (x, d = 3) => (x == null ? "—" : `${x > 0 ? "+" : ""}${nf(d).format(x)}`);
const date = (s) => (s ? new Date(`${s.slice(0, 10)}T12:00:00`).toLocaleDateString("pt-BR") : "—");

// "51,2% (IC 50,8–51,5%)"
function estText(e, { percent = false, digits = 3 } = {}) {
  if (!e || e.value == null) return "amostra insuficiente";
  const f = percent ? (x) => nf(Math.max(digits - 2, 0)).format(x * 100) : (x) => num(x, digits);
  const unit = percent ? "%" : "";
  const sep = e.low < 0 ? " a " : "–";
  return `${f(e.value)}${unit} <span class="faint">(IC ${f(e.low)}${sep}${f(e.high)}${unit})</span>`;
}

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const param = (name) => new URLSearchParams(location.search).get(name);
const $ = (sel, root = document) => root.querySelector(sel);

const VERDICT_CLASS = {
  ataque: "attack",
  defesa: "defense",
  "acima do Elo": "positive",
  "abaixo do Elo": "negative",
  "vantagem de quem escolhe": "positive",
  "desvantagem de quem escolhe": "negative",
};
const verdictTag = (v) => `<span class="tag ${VERDICT_CLASS[v] ?? "muted"}">${esc(v ?? "—")}</span>`;
const regionDot = (r) => `<span class="region-dot ${esc(r)}">${esc(r ?? "—")}</span>`;
const tierChip = (tier) => `<span class="tier ${esc(tier)}">${esc((tier ?? "—").toUpperCase())}</span>`;
const two = (n) => String(n).padStart(2, "0");
// Selo do ranking Elo: poucas séries do próprio tier na janela (ex.: promovido da VCL ao VCT); o
// rating é o mesmo, só ainda está assentando (mart_team_ratings.is_provisional).
const tierSeries = (t) => `${t.tier_matches} ${t.tier_matches === 1 ? "série" : "séries"} de ${esc((t.tier ?? "").toUpperCase())}`;
// Ao lado do nome; no ranking, o nome encolhe (reticências) para o selo caber sem alargar a coluna.
const provisionalTag = (t) =>
  t?.provisional ? `<span class="tag muted" title="${tierSeries(t)} na janela: o rating ainda está assentando">provisório</span>` : "";

// Badge do time: o logo sobre as iniciais na cor da região; sem logo, ou se ele falhar ao carregar
// (onerror remove a imagem), ficam as iniciais. Par do macro `badge` dos templates.
function teamBadge(t, size = "") {
  const code = (t?.tag || t?.name || "?").toUpperCase().slice(0, 2);
  const logo = t?.logo ? `<img src="${esc(t.logo)}" alt="" loading="lazy" onerror="this.remove()">` : "";
  return `<span class="team-badge ${esc(t?.region ?? "")} ${size}" aria-hidden="true"><span class="code">${esc(code)}</span>${logo}</span>`;
}

// Ícone do agente: o do vlr.gg (ou de imgs/agentsV) sobre as iniciais; sem ícone, ou se ele falhar
// ao carregar, ficam as iniciais. `AGENTS` vem de agents.json, carregado uma vez por `loadAgents`.
let AGENTS = null;
async function loadAgents() {
  if (AGENTS) return AGENTS;
  try {
    AGENTS = await loadJSON("agents.json");
  } catch (err) {
    console.warn("agents.json indisponível; os agentes ficam só com as iniciais", err);
    AGENTS = {};
  }
  return AGENTS;
}
function agentIcon(name, size = "") {
  const src = AGENTS?.[name];
  const img = src ? `<img src="${esc(src)}" alt="" loading="lazy" onerror="this.remove()">` : "";
  return `<span class="agent-icon ${size}" title="${esc(name)}" aria-hidden="true"><span class="code">${esc((name ?? "?").slice(0, 2))}</span>${img}</span>`;
}
const agentChip = (name) => `<span class="agent-chip">${agentIcon(name, "sm")}${esc(name)}</span>`;
const agentChips = (names) => names.map(agentChip).join("");

// Sparkline SVG: a série inteira normalizada na própria altura; verde se subiu, vermelho se caiu.
function sparkline(values) {
  if (!values || values.length < 2) return "";
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || 1;
  const points = values.map((v, i) => `${(i * 100) / (values.length - 1)},${28 - ((v - lo) / span) * 24}`).join(" ");
  const trend = values.at(-1) > values[0] ? "up" : values.at(-1) < values[0] ? "down" : "";
  return `<svg class="sparkline ${trend}" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true"><polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
}

// Barra de IC inline: trilho [min, max], linha do nulo, faixa do IC e ponto. Com `verdict`, a cor
// segue o veredito (que já tem a correção de Holm), não o IC cru: os dois podem divergir.
function ciBar(e, { min = 0, max = 1, nullValue = 0.5, verdict } = {}) {
  if (!e || e.value == null) return "";
  const x = (v) => `${(100 * (Math.min(Math.max(v, min), max) - min)) / (max - min)}%`;
  const raw = e.low > nullValue ? "positive" : e.high < nullValue ? "negative" : "";
  const cls = verdict === undefined ? raw : verdict === "inconclusivo" ? "" : raw;
  const width = `calc(${x(e.high)} - ${x(e.low)})`;
  return `<span class="ci ${cls}" aria-hidden="true"><span class="null" style="left:${x(nullValue)}"></span><span class="range" style="left:${x(e.low)};width:${width}"></span><span class="point" style="left:${x(e.value)}"></span></span>`;
}

function showState(el, message, error = false) {
  if (el.classList.contains("chart")) el.style.height = "auto"; // sem gráfico, sem o espaço dele
  el.innerHTML = `<div class="state${error ? " error" : ""}">${message}</div>`;
}
function fail(el, err) {
  console.error(err);
  showState(el, `Não foi possível carregar os dados (${esc(err.message)}).`, true);
}

// --- tabela ordenável ----------------------------------------------------------------------------

// columns: [{key, label, num?, render?(row), sort?(row)}]
function renderTable(el, rows, columns, { sortKey = null, desc = true, empty = "Nada a mostrar." } = {}) {
  let key = sortKey;
  let descending = desc;
  const draw = () => {
    const col = columns.find((c) => c.key === key);
    const sorted = col
      ? [...rows].sort((a, b) => {
          const va = col.sort ? col.sort(a) : a[col.key];
          const vb = col.sort ? col.sort(b) : b[col.key];
          if (va == null) return 1;
          if (vb == null) return -1;
          return (va < vb ? -1 : va > vb ? 1 : 0) * (descending ? -1 : 1);
        })
      : rows;
    if (!sorted.length) return showState(el, empty);
    const head = columns
      .map((c) => {
        const aria = c.key === key ? ` aria-sort="${descending ? "descending" : "ascending"}"` : "";
        const sortable = c.nosort ? "" : ` data-sort="${c.key}"`;
        return `<th class="${c.num ? "num" : ""}"${sortable}${aria}>${c.label}</th>`;
      })
      .join("");
    const body = sorted
      .map(
        (r, i) =>
          `<tr>${columns
            .map((c) => `<td class="${c.cls ?? (c.num ? "num" : "")}">${c.render ? c.render(r, i) : esc(r[c.key])}</td>`)
            .join("")}</tr>`,
      )
      .join("");
    el.innerHTML = `<div class="table-wrap"><table class="dense"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
    el.querySelectorAll("th[data-sort]").forEach((th) =>
      th.addEventListener("click", () => {
        descending = th.dataset.sort === key ? !descending : true;
        key = th.dataset.sort;
        draw();
      }),
    );
  };
  draw();
}

// --- gráficos ------------------------------------------------------------------------------------

const charts = [];
function chart(el) {
  const c = echarts.init(el, "metascope", { renderer: "svg" });
  charts.push(c);
  return c;
}
window.addEventListener("resize", () => charts.forEach((c) => c.resize()));

// Libera os gráficos dentro de `root` (troca de recorte): o elemento volta à altura do CSS.
function disposeCharts(root = document) {
  for (let i = charts.length - 1; i >= 0; i--) {
    const el = charts[i].getDom();
    if (root === el || root.contains(el)) {
      charts[i].dispose();
      charts.splice(i, 1);
      el.style.height = "";
    }
  }
}
const tokens = () => metascopeTheme().tokens;

// Floresta: categoria no eixo y, estimativa e IC no x, linha do nulo.
function forest(el, rows, { nullValue = null, format = (v) => num(v, 2), xName = "", tooltip } = {}) {
  const t = tokens();
  const c = chart(el);
  el.style.height = `${Math.max(rows.length * 30 + 60, 160)}px`;
  c.resize();
  c.setOption({
    grid: { left: 8, right: 24, top: 8, bottom: 36, containLabel: true },
    xAxis: { type: "value", scale: true, name: xName, nameLocation: "middle", nameGap: 26, axisLabel: { formatter: format } },
    yAxis: { type: "category", inverse: true, data: rows.map((r) => r.label), axisLabel: { fontFamily: t.sans } },
    tooltip: { trigger: "item", formatter: (p) => tooltip?.(rows[p.dataIndex]) ?? rows[p.dataIndex].label },
    series: [
      {
        type: "custom",
        encode: { x: [1, 2, 3], y: 0 },
        data: rows.map((r, i) => [i, r.low, r.high, r.value]),
        renderItem: (params, api) => {
          const lo = api.coord([api.value(1), api.value(0)]);
          const hi = api.coord([api.value(2), api.value(0)]);
          const mid = api.coord([api.value(3), api.value(0)]);
          const color = rows[params.dataIndex].color ?? t.text;
          return {
            type: "group",
            children: [
              { type: "line", shape: { x1: lo[0], y1: lo[1], x2: hi[0], y2: hi[1] }, style: { stroke: color, lineWidth: 3 } },
              { type: "circle", shape: { cx: mid[0], cy: mid[1], r: 4.5 }, style: { fill: color } },
            ],
          };
        },
        markLine:
          nullValue == null
            ? undefined
            : { silent: true, symbol: "none", data: [{ xAxis: nullValue }], lineStyle: { type: "dashed", color: t.faint }, label: { show: false } },
      },
    ],
  });
  return c;
}

// Pontos com barra de IC vertical, para eixo x de categoria ou de valor.
function intervalSeries(name, points, color, { offset = 0, dx: px = 0 } = {}) {
  return {
    name,
    type: "custom",
    encode: { x: 0, y: [1, 2, 3] },
    data: points.map((p) => [p.x, p.low, p.high, p.value]),
    itemStyle: { color },
    renderItem: (params, api) => {
      const lo = api.coord([api.value(0), api.value(1)]);
      const hi = api.coord([api.value(0), api.value(2)]);
      const mid = api.coord([api.value(0), api.value(3)]);
      // offset: fração da banda (eixo de categoria); px: deslocamento fixo (eixo de valor)
      const dx = px + (offset ? offset * api.size([1, 0])[0] : 0);
      return {
        type: "group",
        children: [
          { type: "line", shape: { x1: lo[0] + dx, y1: lo[1], x2: hi[0] + dx, y2: hi[1] }, style: { stroke: color, lineWidth: 2 } },
          { type: "circle", shape: { cx: mid[0] + dx, cy: mid[1], r: 4.5 }, style: { fill: color } },
        ],
      };
    },
  };
}

// --- busca de times ------------------------------------------------------------------------------

function teamSearch(input, list, teams, onPick) {
  let active = -1;
  const norm = (s) => (s ?? "").normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
  const indexed = teams.map((t) => ({ t, key: `${norm(t.name)} ${norm(t.tag)}` }));
  const close = () => {
    list.hidden = true;
    active = -1;
  };
  const render = () => {
    const q = norm(input.value.trim());
    if (!q) return close();
    const hits = indexed.filter((x) => x.key.includes(q)).slice(0, 12);
    list.innerHTML = hits.length
      ? hits
          .map(
            ({ t }, i) =>
              `<li><button type="button" data-i="${i}" data-id="${esc(t.id)}"><span>${esc(t.name)} <span class="faint">${esc(t.tag ?? "")}</span></span><span class="faint">${esc(t.tier)} · ${esc(t.region ?? "—")} · ${num(t.rating, 0)}</span></button></li>`,
          )
          .join("")
      : `<li><span class="faint" style="display:block;padding:.5rem .75rem">Nenhum time ativo na janela com esse nome.</span></li>`;
    list.hidden = false;
    list.querySelectorAll("button").forEach((b) =>
      b.addEventListener("mousedown", (ev) => {
        ev.preventDefault();
        pick(b.dataset.id);
      }),
    );
  };
  const pick = (id) => {
    const team = teams.find((t) => t.id === id);
    close();
    if (team) onPick(team);
  };
  input.addEventListener("input", render);
  input.addEventListener("focus", render);
  input.addEventListener("blur", () => setTimeout(close, 100));
  input.addEventListener("keydown", (ev) => {
    const buttons = [...list.querySelectorAll("button")];
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      ev.preventDefault();
      active = (active + (ev.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length;
      buttons.forEach((b, i) => b.setAttribute("aria-selected", String(i === active)));
    } else if (ev.key === "Enter" && buttons.length) {
      ev.preventDefault();
      pick(buttons[Math.max(active, 0)].dataset.id);
    } else if (ev.key === "Escape") close();
  });
}

// --- páginas -------------------------------------------------------------------------------------

const pages = {};

pages.home = async () => {
  const input = $("#team-search");
  try {
    const teams = await loadJSON("teams/index.json");
    teamSearch(input, $("#team-search-list"), teams, (t) => (location.href = `team.html?id=${encodeURIComponent(t.id)}`));
  } catch (err) {
    input.disabled = true;
    input.placeholder = "busca indisponível";
    console.error(err);
  }
  // o gráfico do hero: a tese da janela (o mesmo dado da análise 01)
  const el = $("#hero-chart");
  try {
    const drift = await loadJSON(`analyses/${scopeKey(SCOPE_DEFAULT)}/drift.json`);
    if (!drift.meta_by_age.length) return showState(el, "Histórico curto demais para o drift.");
    const t = tokens();
    const byMap = {};
    drift.meta_by_quarter.filter((r) => r.quarters_before > 0).forEach((r) => (byMap[r.map_name] ??= []).push([r.quarters_before * 3, r.distance]));
    chart(el).setOption({
      grid: { left: 4, right: 12, top: 12, bottom: 4, containLabel: true },
      xAxis: { type: "value", min: 0, interval: 3, axisLabel: { formatter: (v) => `${v}m` } },
      yAxis: { type: "value", min: 0, axisLabel: { formatter: (v) => num(v, 1) } },
      tooltip: { trigger: "item", formatter: (p) => `${esc(p.seriesName)}: ${num(p.value[1], 2)} a ${p.value[0]} meses` },
      series: [
        ...Object.entries(byMap).map(([m, pts]) => ({
          name: m,
          type: "line",
          data: pts.sort((x, y) => x[0] - y[0]),
          lineStyle: { color: t.neutral, width: 1, opacity: 0.4 },
          itemStyle: { color: t.neutral, opacity: 0.4 },
          symbolSize: 2,
        })),
        {
          name: "média entre mapas",
          type: "line",
          data: drift.meta_by_age.map((r) => [r.quarters_before * 3, r.distance]),
          lineStyle: { color: cssVar("--accent"), width: 3 },
          itemStyle: { color: cssVar("--accent") },
          symbolSize: 7,
          z: 3,
        },
        {
          name: "piso de ruído",
          type: "line",
          data: drift.meta_by_age.map((r) => [r.quarters_before * 3, r.noise_floor]),
          lineStyle: { color: t.text, width: 1, type: "dashed" },
          showSymbol: false,
        },
      ],
    });
  } catch (err) {
    fail(el, err);
  }
};

pages.rankings = async () => {
  const out = $("#ranking");
  let teams;
  try {
    teams = await loadJSON("teams/index.json");
  } catch (err) {
    return fail(out, err);
  }
  const state = {
    region: param("region") ?? "",
    tier: param("tier") ?? "vct",
    min: Number(param("min") ?? 10),
    q: "",
  };
  const region = $("#f-region");
  const tier = $("#f-tier");
  const min = $("#f-min");
  const q = $("#f-q");
  region.value = state.region;
  min.value = state.min;
  tier.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.value === state.tier)));

  const norm = (s) => (s ?? "").normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
  const draw = () => {
    const rows = teams.filter(
      (t) =>
        (!state.region || t.region === state.region) &&
        (!state.tier || t.tier === state.tier) &&
        t.matches >= state.min &&
        (!state.q || norm(`${t.name} ${t.tag}`).includes(norm(state.q))),
    );
    $("#ranking-count").textContent = `${rows.length} ${rows.length === 1 ? "time" : "times"}`;
    renderTable(
      out,
      rows,
      [
        { key: "rating_pos", label: "#", num: true, nosort: true, cls: "rank num", render: (_, i) => `<span${i === 0 ? ' class="lead"' : ""}>${two(i + 1)}</span>` },
        { key: "name", label: "Time", cls: "team", render: (t) => `<a class="team-cell" href="team.html?id=${encodeURIComponent(t.id)}" title="${esc(t.name)}">${teamBadge(t)}<b>${esc(t.name)}</b>${provisionalTag(t)}</a>` },
        { key: "tag", label: "Tag", render: (t) => `<span class="faint">${esc(t.tag ?? "")}</span>` },
        { key: "region", label: "Região", render: (t) => regionDot(t.region) },
        { key: "tier", label: "Tier", render: (t) => tierChip(t.tier) },
        { key: "trend", label: "Tendência", nosort: true, render: (t) => sparkline(t.trend) },
        { key: "rating", label: "Elo", num: true, render: (t) => `<b>${num(t.rating, 0)}</b>` },
        { key: "peak", label: '<span title="maior Elo na janela">Pico</span>', num: true, render: (t) => num(t.peak, 0) },
        { key: "matches", label: "Séries", num: true, render: (t) => t.matches },
        { key: "win_rate", label: "Vitórias", num: true, render: (t) => pct(t.win_rate, 0) },
        { key: "rank_region_tier", label: '<span title="posição na região × tier do time">No circuito</span>', num: true, render: (t) => t.rank_region_tier },
        { key: "last_match", label: '<span title="última série na janela">Última</span>', num: true, render: (t) => date(t.last_match) },
      ],
      { sortKey: "rating", empty: "Nenhum time com esses filtros." },
    );
    const qs = new URLSearchParams();
    if (state.region) qs.set("region", state.region);
    qs.set("tier", state.tier);
    qs.set("min", state.min);
    history.replaceState(null, "", `?${qs}`);
  };
  region.addEventListener("change", () => ((state.region = region.value), draw()));
  min.addEventListener("input", () => ((state.min = Number(min.value) || 0), draw()));
  q.addEventListener("input", () => ((state.q = q.value), draw()));
  tier.querySelectorAll("button").forEach((b) =>
    b.addEventListener("click", () => {
      state.tier = b.dataset.value;
      tier.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      draw();
    }),
  );
  draw();
};

pages.team = async () => {
  const root = $("#team");
  const id = param("id");
  if (!id) return showState(root, `Nenhum time escolhido. Procure um time na <a href="rankings.html">tabela de rankings</a>.`);
  let data;
  try {
    data = await loadJSON(`teams/${encodeURIComponent(id)}.json`);
  } catch (err) {
    return showState(root, `Time <code>${esc(id)}</code> não encontrado na janela de análise. Veja os <a href="rankings.html">rankings</a>.`, true);
  }
  await loadAgents();
  const t = data.team;
  document.title = `${t.name} — MetaScope VAL`;
  $(".topbar h1").textContent = t.name;
  const form = data.form
    .map((r) => (r === 1 ? '<span class="w">V</span>' : r === 0 ? '<span class="l">D</span>' : '<span class="d">E</span>'))
    .join("");
  const fav = data.maps[0]; // mapas vêm ordenados por jogados
  root.innerHTML = `
    <section class="team-hero">
      <div class="team-identity">
        ${teamBadge(t, "lg")}
        <div>
          <span class="context">${esc(t.region ?? "—")} · ${esc(t.tier.toUpperCase())} · ${t.rank_region_tier}º no circuito</span>
          <h2>${esc(t.name)}</h2>
          <span class="sub">${esc(t.tag ?? "")} · última série em ${date(t.last_match)}${document.body.dataset.predictions === "off" ? "" : ` · <a href="previsoes.html?a=${encodeURIComponent(t.id)}">prever um confronto</a>`}</span>
        </div>
      </div>
      <div class="team-rating"><span>Elo</span><b>${num(t.rating, 0)}</b><small>pico na janela ${num(t.peak, 0)} · ${t.rank}º geral</small>${t.provisional ? `<small title="o rating ainda está assentando">provisório: ${tierSeries(t)} na janela</small>` : ""}</div>
    </section>
    <section class="grid-hair metric-grid">
      <article><span>Séries na janela</span><b>${t.matches}</b><small>${pct(t.win_rate, 0)} de vitórias</small></article>
      <article><span>Forma (10 últimas)</span><b><span class="form" title="mais recente à esquerda">${form || "—"}</span></b><small>mais recente à esquerda</small></article>
      <article><span>Mapa mais jogado</span><b>${fav ? esc(fav.map) : "—"}</b><small>${fav ? `${fav.played} mapas · ${estText(fav.win_rate, { percent: true })}` : "sem mapas na janela"}</small></article>
      <article><span>Rank geral</span><b>${t.rank}º</b><small>${t.rank_region_tier}º em ${esc(t.region ?? "—")} · ${esc(t.tier.toUpperCase())}</small></article>
    </section>
    <section class="panel">
      <div class="panel-head"><h2>Elo na janela</h2><small>rating depois de cada série</small></div>
      <div class="panel-body"><div id="elo-chart" class="chart short"></div></div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2>Mapas</h2><small>win rate com IC de Wilson</small></div>
      <div id="maps"></div>
    </section>
    <section class="grid-hair split-panel">
      <div><h2>Elenco</h2><div id="roster"></div></div>
      <div><h2>Partidas</h2><div id="matches"></div></div>
    </section>`;

  const accent = cssVar("--accent");
  const c = chart($("#elo-chart"));
  c.setOption({
    grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
    xAxis: { type: "time" },
    yAxis: { type: "value", scale: true, axisLabel: { formatter: (v) => num(v, 0) } },
    tooltip: { trigger: "axis", valueFormatter: (v) => num(v, 0) },
    series: [
      {
        name: "Elo",
        type: "line",
        step: "end",
        showSymbol: false,
        data: data.elo,
        lineStyle: { color: accent },
        itemStyle: { color: accent },
        areaStyle: { color: accent, opacity: 0.08 },
      },
    ],
  });

  renderTable(
    $("#maps"),
    data.maps,
    [
      { key: "map", label: "Mapa" },
      { key: "played", label: "Jogados", num: true },
      { key: "won", label: "Vencidos", num: true },
      { key: "rate", label: "Win rate (IC 95%)", num: true, sort: (m) => m.win_rate.value, render: (m) => `${estText(m.win_rate, { percent: true })}${ciBar(m.win_rate)}` },
    ],
    { sortKey: "played", empty: "Sem mapas na janela." },
  );
  renderTable(
    $("#roster"),
    data.roster,
    [
      { key: "name", label: "Jogador", render: (p) => `${esc(p.name)}${p.current ? "" : ' <span class="faint">(saiu)</span>'}` },
      { key: "agent", label: "Agente principal", render: (p) => (p.agent ? agentChip(p.agent) : "—") },
      { key: "maps", label: "Mapas", num: true },
      { key: "last_played", label: "Último mapa", num: true, render: (p) => date(p.last_played) },
    ],
    { sortKey: "last_played", empty: "Sem elenco na janela." },
  );
  renderTable(
    $("#matches"),
    data.matches,
    [
      { key: "date", label: "Data", num: true, render: (m) => date(m.date) },
      { key: "opponent", label: "Adversário", render: (m) => `<a href="team.html?id=${encodeURIComponent(m.opponent_id)}">${esc(m.opponent)}</a>` },
      { key: "score", label: "Placar", num: true, nosort: true, render: (m) => `<span style="color:var(${m.result === 1 ? "--win" : m.result === 0 ? "--loss" : "--draw"})">${esc(m.score)}</span>` },
      { key: "expected", label: "Elo dava", num: true, render: (m) => pct(m.expected, 0) },
      { key: "event", label: "Evento", render: (m) => `<span class="faint">${esc(m.event)}</span>` },
    ],
    { sortKey: "date", empty: "Sem partidas na janela." },
  );
};

// Veto: matriz mapa × passo, o elemento de ousadia visual do site (D27). Cada mapa sofre uma ação
// por veto em que está no pool, então a linha soma 100%: em cada célula, a fração dos vetos daquele
// mapa decidida naquele passo, em barra empilhada por ação (ban, pick, decider). Lê-se "quem é o
// primeiro ban", "quem é escolhido" e "quem sobra de decider" de uma vez.
function vetoMatrix(el, ladder, selected, onSelect) {
  const t = tokens();
  const maps = Object.keys(ladder).sort();
  const steps = Math.max(...Object.values(ladder).flat().map((s) => s.step));
  const data = [];
  let max = 0;
  maps.forEach((m, y) => {
    const rowTotal = ladder[m].reduce((acc, s) => acc + s.ban + s.pick + s.decider, 0);
    ladder[m].forEach((s) => {
      const total = s.ban + s.pick + s.decider;
      const share = total / rowTotal;
      max = Math.max(max, share);
      data.push([s.step - 1, y, s.ban / rowTotal, s.pick / rowTotal, s.decider / rowTotal, share, total, rowTotal]);
    });
  });
  el.style.height = `${maps.length * 34 + 60}px`;
  const c = chart(el);
  c.setOption({
    grid: { left: 8, right: 8, top: 28, bottom: 8, containLabel: true },
    xAxis: {
      type: "category",
      position: "top",
      data: Array.from({ length: steps }, (_, i) => `${i + 1}º passo`),
      axisLine: { show: false },
      splitLine: { show: true, lineStyle: { color: t.border } },
      axisLabel: { color: t.muted, fontFamily: t.sans },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: maps,
      axisLine: { show: false },
      splitLine: { show: false },
      axisLabel: {
        fontFamily: t.sans,
        fontSize: 12,
        color: t.muted,
        rich: { sel: { color: t.text, fontWeight: 700, fontFamily: t.sans, fontSize: 12 } },
        formatter: (m) => (m === selected ? `{sel|${m}}` : m),
      },
    },
    tooltip: {
      trigger: "item",
      formatter: (p) => {
        const [x, y, ban, pick, dec, share, total, rowTotal] = p.data;
        const parts = [["ban", ban], ["pick", pick], ["decider", dec]].filter(([, v]) => v > 0).map(([a, v]) => `${a} ${pct(v, 0)}`);
        return `<b>${esc(maps[y])}</b> no ${x + 1}º passo: ${pct(share, 0)} dos vetos<br>${parts.join(" · ")}<br><span style="color:${t.faint}">${total} de ${rowTotal} vetos com o mapa no pool</span>`;
      },
    },
    series: [
      {
        type: "custom",
        data,
        encode: { x: 0, y: 1 },
        renderItem: (params, api) => {
          const [cx, cy] = api.coord([api.value(0), api.value(1)]);
          const [w, h] = api.size([1, 1]);
          const share = api.value(5);
          const full = w - 34; // espaço para o rótulo
          const height = Math.min(h * 0.56, 16);
          let x = cx - w / 2 + 6;
          const children = [];
          if (maps[api.value(1)] === selected && api.value(0) === 0) {
            children.push({ type: "rect", shape: { x: params.coordSys.x, y: cy - h / 2, width: params.coordSys.width, height: h }, style: { fill: t.surface2 }, z2: -1, silent: true });
          }
          [
            [api.value(2), t.neutral],
            [api.value(3), t.attack],
            [api.value(4), t.gold],
          ].forEach(([v, color]) => {
            if (!v) return;
            const seg = (full * v) / max;
            children.push({ type: "rect", shape: { x, y: cy - height / 2, width: seg, height }, style: { fill: color } });
            x += seg;
          });
          if (share >= 0.05) {
            children.push({
              type: "text",
              style: { x: x + 4, y: cy, text: nf(0).format(share * 100), fill: share >= 0.2 ? t.text : t.faint, font: `600 11px ${t.sans}`, verticalAlign: "middle" },
            });
          }
          return { type: "group", children };
        },
      },
    ],
  });
  c.on("click", (p) => onSelect?.(maps[p.data[1]]));
  return c;
}

// O Meta segue o recorte (janela × tier): as fatias mapa × patch, o veto, os KPIs e as composições
// vêm de data/meta/{recorte}/ e data/analyses/{recorte}/veto.json. Trocar o recorte mantém o mapa e
// o patch quando eles existem no recorte novo.
pages.meta = async () => {
  const body = $("#meta-body");
  const empty = $("#meta-empty");
  const mapSel = $("#f-map");
  const patchSel = $("#f-patch");
  const vetoEl = $("#veto-chart");
  const state = { map: param("map"), patch: param("patch"), scope: null };
  let slices = [];
  let veto = null;

  const syncUrl = () => {
    const qs = scopeParams(state.scope);
    if (state.map) qs.set("map", state.map.toLowerCase());
    if (state.patch) qs.set("patch", state.patch);
    replaceQuery(qs);
  };

  const drawVeto = () => {
    disposeCharts(vetoEl);
    vetoEl.style.height = "";
    if (!Object.keys(veto.ladder).length) return showState(vetoEl, "Sem vetos nesta janela e tier.");
    vetoMatrix(vetoEl, veto.ladder, state.map, (m) => {
      state.map = m;
      state.patch = null;
      update();
    });
  };

  const update = serial(async () => {
    mapSel.value = state.map;
    const options = slices.filter((s) => s.map === state.map).sort((a, b) => b.patch.localeCompare(a.patch, "pt", { numeric: true }));
    if (!options.some((s) => s.patch === state.patch)) state.patch = options[0].patch;
    patchSel.innerHTML = options.map((s) => `<option value="${esc(s.patch)}">${esc(s.patch)} (${s.compositions} comps)</option>`).join("");
    patchSel.value = state.patch;
    syncUrl();
    drawVeto();
    const slice = options.find((s) => s.patch === state.patch);
    const detail = $("#slice");
    let d;
    try {
      d = await loadJSON(`meta/${scopeKey(state.scope)}/${slice.file}.json`);
    } catch (err) {
      return fail(detail, err);
    }
    const vetoRow = veto.maps.find((m) => m.map_name === state.map);
    const top = d.agents[0];
    // banner do mapa: a foto de imgs/maps (quando o usuário a puser) atrás do nome; sem ela, o
    // fundo com o brilho do acento
    const banner = $("#map-banner");
    banner.classList.toggle("has-image", Boolean(d.image));
    banner.style.backgroundImage = d.image ? `url("${d.image}")` : "";
    banner.innerHTML = `<h2>${esc(d.map)}</h2><span>patch ${esc(d.patch)} · ${d.compositions} composições</span>`;
    $("#map-kpis").innerHTML = `
      <article><span>Composições no recorte</span><b>${d.compositions}</b><small>${esc(d.map)} · patch ${esc(d.patch)}</small></article>
      <article><span>Agente mais escolhido</span><b class="with-icon">${top ? `${agentIcon(top.agent, "kpi")}${esc(top.agent)}` : "—"}</b><small>${top ? `em ${pct(top.pick_rate, 0)} das composições` : "sem composições"}</small></article>
      <article><span>Ataque vence (janela)</span><b>${d.side ? pct(d.side.attack.value, 1) : "—"}</b><small>${d.side ? `IC ${pct(d.side.attack.low, 1)}–${pct(d.side.attack.high, 1)} · ${esc(d.side.verdict)}` : "sem histórico de lado"}</small></article>
      <article><span>Quem escolhe vence</span><b>${vetoRow ? pct(vetoRow.picker_win_rate.value, 1) : "—"}</b><small>${vetoRow ? `IC ${pct(vetoRow.picker_win_rate.low, 1)}–${pct(vetoRow.picker_win_rate.high, 1)} · ${vetoRow.picks} picks` : "sem picks na janela"}</small></article>`;
    $("#map-facts").innerHTML = `
      <dl class="facts">
        <dt>Patches no recorte</dt><dd>${esc(d.patches.join(", "))}</dd>
        <dt>Ataque vence</dt><dd>${d.side ? `${estText(d.side.attack, { percent: true })} ${verdictTag(d.side.verdict)}` : "sem histórico de lado"}</dd>
        <dt>Quem escolhe vence</dt><dd>${vetoRow ? estText(vetoRow.picker_win_rate, { percent: true }) : "—"}</dd>
        <dt>Acima do Elo ao escolher</dt><dd>${vetoRow ? `${estText(vetoRow.excess_over_elo)} ${verdictTag(vetoRow.verdict)}` : "—"}</dd>
      </dl>`;
    const agents = d.agents.slice(0, 15);
    $("#agents").innerHTML = agents.length
      ? agents
          .map(
            (a) => `<div class="agent-row">${agentIcon(a.agent)}<b>${esc(a.agent)}</b><span class="bar"><i style="width:${a.pick_rate * 100}%"></i></span><em>${pct(a.pick_rate, 0)}</em></div>`,
          )
          .join("")
      : '<div class="state">Sem composições neste recorte.</div>';
    renderTable(
      $("#comps"),
      d.comps,
      [
        { key: "key", label: "Composição", cls: "wrap comp", render: (r) => agentChips(r.agents) },
        {
          key: "top_team",
          label: "Time que mais usou",
          sort: (r) => r.top_team?.name ?? "",
          render: (r) =>
            r.top_team
              ? `<a class="team-cell" href="team.html?id=${encodeURIComponent(r.top_team.id)}">${teamBadge(r.top_team)}<b>${esc(r.top_team.name)}</b></a><small class="team-sub">${r.top_team.maps} ${r.top_team.maps === 1 ? "mapa" : "mapas"} com ela</small>`
              : "—",
        },
        { key: "maps", label: "Mapas", num: true },
        { key: "win_rate", label: "Win rate bruto", num: true, render: (r) => pct(r.win_rate, 0) },
        {
          key: "above",
          label: "Acima do Elo (IC 95%)",
          num: true,
          sort: (r) => r.above_elo.value,
          render: (r) => `${pp(r.above_elo.value)} <span class="faint">(${pp(r.above_elo.low)} a ${pp(r.above_elo.high)})</span>${ciBar(r.above_elo, { min: -0.5, max: 0.5, nullValue: 0 })}`,
        },
      ],
      { sortKey: "maps", empty: "Nenhuma composição com 3 mapas ou mais neste recorte." },
    );
  });

  // troca de recorte: relê as fatias e o veto; mapa e patch ficam se existirem no recorte novo
  const load = serial(async (scope) => {
    state.scope = scope;
    try {
      [slices, veto] = await Promise.all([loadJSON(`meta/${scopeKey(scope)}/index.json`), loadJSON(`analyses/${scopeKey(scope)}/veto.json`), loadAgents()]);
    } catch (err) {
      body.hidden = true;
      empty.hidden = false;
      return fail(empty, err);
    }
    body.hidden = !slices.length;
    empty.hidden = Boolean(slices.length);
    mapSel.disabled = patchSel.disabled = !slices.length;
    if (!slices.length) {
      disposeCharts(body);
      mapSel.innerHTML = patchSel.innerHTML = "";
      syncUrl();
      return showState(empty, "Nenhum mapa × patch com amostra suficiente nesta janela e tier. Troque o recorte acima.");
    }
    const maps = [...new Set(slices.map((s) => s.map))].sort();
    mapSel.innerHTML = maps.map((m) => `<option>${esc(m)}</option>`).join("");
    const latest = [...slices].sort((x, y) => y.patch.localeCompare(x.patch, "pt", { numeric: true }) || y.compositions - x.compositions)[0];
    state.map = maps.find((m) => m.toLowerCase() === (state.map ?? "").toLowerCase()) ?? latest.map;
    await update();
  });

  mapSel.addEventListener("change", () => ((state.map = mapSel.value), (state.patch = null), update()));
  patchSel.addEventListener("change", () => ((state.patch = patchSel.value), update()));
  load(bindScope(load));
};

pages.predictions = async () => {
  const out = $("#prediction");
  let teams;
  try {
    teams = await loadJSON("teams/index.json");
  } catch (err) {
    return fail(out, err);
  }
  const byId = Object.fromEntries(teams.map((t) => [t.id, t]));
  const state = { a: byId[param("a")] ?? null, b: byId[param("b")] ?? null };
  const inputs = { a: $("#team-a"), b: $("#team-b") };
  const prob = $("#probability");
  const cross = $("#cross");

  const side = (t) =>
    t
      ? `${teamBadge(t, "lg")}<h2><a href="team.html?id=${encodeURIComponent(t.id)}">${esc(t.name)}</a></h2><span class="sub">${esc(t.region ?? "—")} · ${esc(t.tier.toUpperCase())} · ${t.rank_region_tier}º no circuito</span>`
      : `<span class="team-badge empty lg" aria-hidden="true">?</span><span class="sub">escolha um time</span>`;

  // linha do comparativo: os dois valores, a barra de proporção e o líder em destaque
  const row = (label, va, vb, fmt, higherIsBetter = true) => {
    const total = Math.abs(va) + Math.abs(vb) || 1;
    const leadA = higherIsBetter ? va > vb : va < vb;
    const leadB = higherIsBetter ? vb > va : vb < va;
    return `<div class="compare-row"><b class="${leadA ? "lead" : ""}">${fmt(va)}</b><span><small>${label}</small><span class="duel"><i style="width:${(Math.abs(va) / total) * 100}%"></i><i style="width:${(Math.abs(vb) / total) * 100}%"></i></span></span><b class="${leadB ? "lead" : ""}">${fmt(vb)}</b></div>`;
  };

  const render = async () => {
    Object.entries(inputs).forEach(([k, el]) => (el.value = state[k] ? state[k].name : ""));
    $("#pick-a").innerHTML = side(state.a);
    $("#pick-b").innerHTML = side(state.b);
    prob.innerHTML = "";
    cross.innerHTML = "";
    const qs = new URLSearchParams();
    if (state.a) qs.set("a", state.a.id);
    if (state.b) qs.set("b", state.b.id);
    history.replaceState(null, "", qs.toString() ? `?${qs}` : location.pathname);
    if (!state.a || !state.b) return showState(out, "Escolha dois times para ver a probabilidade de cada um vencer a série.");
    if (state.a.id === state.b.id) return showState(out, "Escolha dois times diferentes.");
    let pred;
    try {
      pred = await loadJSON(`predictions/${encodeURIComponent(state.a.id)}.json`);
    } catch (err) {
      return fail(out, err);
    }
    const p = pred.p[state.b.id];
    if (p == null) return showState(out, "Sem previsão para esse par: um dos times não está ativo na janela.", true);
    const a = state.a;
    const b = state.b;
    const code = (t) => esc((t.tag || t.name).toUpperCase());
    prob.innerHTML = `
      <div><b>${pct(p, 0)}</b><span>${code(a)}</span></div>
      <div class="prob-bar" role="img" aria-label="${esc(a.name)} ${pct(p, 0)}, ${esc(b.name)} ${pct(1 - p, 0)}"><i style="width:${p * 100}%"></i><i style="width:${(1 - p) * 100}%"></i></div>
      <div><b>${pct(1 - p, 0)}</b><span>${code(b)}</span></div>`;
    out.innerHTML = `<div class="compare">${[
      row("Elo", a.rating, b.rating, (v) => num(v, 0)),
      row("Pico na janela", a.peak, b.peak, (v) => num(v, 0)),
      row("Séries na janela", a.matches, b.matches, (v) => v),
      row("Vitórias na janela", a.win_rate, b.win_rate, (v) => pct(v, 0)),
      row("Rank no circuito", a.rank_region_tier, b.rank_region_tier, (v) => `${v}º`, false),
    ].join("")}</div>`;
    if (a.region !== b.region || a.tier !== b.tier) {
      cross.innerHTML = `<div class="notice"><b>Circuitos diferentes.</b> As ligas quase não se cruzam: só os confrontos internacionais ligam as escalas, e nelas há região rendendo abaixo do Elo (<a href="analise-regioes.html">análise de regiões</a>). Esta comparação vale menos que uma dentro do mesmo circuito.</div>`;
    }
  };
  Object.entries(inputs).forEach(([k, el]) =>
    teamSearch(el, $(`#team-${k}-list`), teams, (t) => {
      state[k] = t;
      render();
    }),
  );
  $("#swap").addEventListener("click", () => {
    [state.a, state.b] = [state.b, state.a];
    render();
  });
  render();
};

// --- análises ------------------------------------------------------------------------------------

const analyses = {};

analyses.janela = async (data) => {
  const t = tokens();
  const months = META?.window?.months ?? 12;
  const past = data.meta_by_quarter.filter((r) => r.quarters_before > 0);
  const byMap = {};
  past.forEach((r) => (byMap[r.map_name] ??= []).push([r.quarters_before * 3, r.distance]));
  const c = chart($("#chart-main"));
  c.setOption({
    grid: { left: 8, right: 24, top: 24, bottom: 36, containLabel: true },
    xAxis: { type: "value", name: "meses antes do trimestre de referência", nameLocation: "middle", nameGap: 26, interval: 3, min: 0 },
    yAxis: { type: "value", name: "distância ao meta atual", nameLocation: "middle", nameGap: 40, min: 0, axisLabel: { formatter: (v) => num(v, 1) } },
    tooltip: { trigger: "item", formatter: (p) => `${esc(p.seriesName)}: ${num(p.value[1], 2)} a ${p.value[0]} meses` },
    legend: { top: 0, right: 0, data: ["média entre mapas", "piso de ruído"] },
    series: [
      ...Object.entries(byMap).map(([m, pts]) => ({
        name: m,
        type: "line",
        data: pts.sort((x, y) => x[0] - y[0]),
        lineStyle: { color: t.neutral, width: 1, opacity: 0.45 },
        itemStyle: { color: t.neutral, opacity: 0.45 },
        symbolSize: 3,
        z: 1,
      })),
      {
        name: "média entre mapas",
        type: "line",
        data: data.meta_by_age.map((r) => [r.quarters_before * 3, r.distance]),
        lineStyle: { color: t.attack, width: 3 },
        itemStyle: { color: t.attack },
        symbolSize: 7,
        z: 3,
        markArea: { silent: true, itemStyle: { color: t.gold, opacity: 0.07 }, label: { color: t.gold, position: "insideBottomLeft", fontSize: 10 }, data: [[{ xAxis: 0, name: `janela de análise (${months} meses)` }, { xAxis: months }]] },
      },
      {
        name: "piso de ruído",
        type: "line",
        data: data.meta_by_age.map((r) => [r.quarters_before * 3, r.noise_floor]),
        lineStyle: { color: t.text, width: 1, type: "dashed" },
        itemStyle: { color: t.text },
        showSymbol: false,
        z: 2,
      },
    ],
  });
  renderTable(
    $("#table-main"),
    data.homogeneity,
    [
      { key: "map_name", label: "Mapa" },
      { key: "quarters", label: "Trimestres", num: true },
      { key: "chi2", label: "Qui-quadrado", num: true, render: (r) => num(r.chi2, 2) },
      { key: "p_adj", label: "p (Holm)", num: true, render: (r) => num(r.p_adj, 3) },
      { key: "changes", label: "Lado muda?", render: (r) => (r.changes ? '<span class="tag gold">muda</span>' : verdictTag("inconclusivo")) },
    ],
    { sortKey: "p_adj", desc: false, empty: "Sem mapas com dois trimestres ou mais." },
  );
};

analyses.lados = async (data) => {
  const t = tokens();
  const color = { ataque: t.attack, defesa: t.defense };
  if (!data.maps.length) {
    showState($("#chart-main"), "Sem mapas com histórico de lado nesta janela e tier.");
  } else {
    forest(
      $("#chart-main"),
      data.maps.map((m) => ({ label: `${m.map_name} (${m.maps})`, ...m.estimate, color: color[m.verdict] ?? t.neutral, m })),
      { nullValue: 0.5, format: (v) => pct(v, 0), xName: "rounds vencidos pelo ataque (1–24), IC 95%", tooltip: (r) => `<b>${esc(r.m.map_name)}</b><br>${estText(r.m.estimate, { percent: true })}<br>${r.m.rounds} rounds · ${esc(r.m.verdict)}` },
    );
  }
  renderTable(
    $("#table-main"),
    data.maps,
    [
      { key: "map_name", label: "Mapa" },
      { key: "maps", label: "Mapas", num: true },
      { key: "rounds", label: "Rounds", num: true },
      { key: "estimate", label: "Ataque vence (IC 95%)", num: true, sort: (m) => m.estimate.value, render: (m) => `${estText(m.estimate, { percent: true })}${ciBar(m.estimate, { min: 0.42, max: 0.58, verdict: m.verdict })}` },
      { key: "p_adj", label: "p (Holm)", num: true, render: (m) => num(m.p_adj, 4) },
      { key: "verdict", label: "Veredito", render: (m) => verdictTag(m.verdict) },
    ],
    { sortKey: "estimate" },
  );
};

analyses.pistol = async (data) => {
  const el = $("#chart-main");
  if (!data.equal_elo) {
    showState(el, "Amostra insuficiente para a regressão.");
    return showState($("#table-main"), "Nada a mostrar.");
  }
  const t = tokens();
  const pts = (obj) => [0, 1, 2].map((k) => ({ x: k, ...obj[k] }));
  const c = chart(el);
  c.setOption({
    grid: { left: 8, right: 24, top: 32, bottom: 8, containLabel: true },
    legend: { top: 0, right: 0 },
    xAxis: { type: "category", data: ["0 pistols", "1 pistol", "2 pistols"], axisLabel: { fontFamily: t.sans } },
    yAxis: { type: "value", min: 0, max: 1, axisLabel: { formatter: (v) => pct(v, 0) } },
    tooltip: { trigger: "item", formatter: (p) => `${esc(p.seriesName)}: ${pct(p.value[3], 1)} (IC ${pct(p.value[1], 1)}–${pct(p.value[2], 1)})` },
    series: [
      intervalSeries("bruto", pts(data.raw), t.neutral, { offset: -0.12 }),
      intervalSeries("com Elo igual (logística)", pts(data.equal_elo), t.attack, { offset: 0.12 }),
    ],
  });
  const or = data.odds_ratios;
  renderTable(
    $("#table-main"),
    [
      { term: "1 pistol (vs 0)", e: or["C(pistols)[T.1]"] },
      { term: "2 pistols (vs 0)", e: or["C(pistols)[T.2]"] },
      { term: "+100 de Elo", e: or.diff },
    ],
    [
      { key: "term", label: "Termo", nosort: true },
      { key: "e", label: "Razão de chances (IC 95%)", num: true, nosort: true, render: (r) => estText(r.e, { digits: 2 }) },
    ],
  );
};

analyses.veto = async (data) => {
  const t = tokens();
  if (!data.maps.length) {
    showState($("#chart-main"), "Sem picks jogados nesta janela e tier.");
  } else {
    forest(
      $("#chart-main"),
      data.maps.map((m) => ({ label: `${m.map_name} (${m.picks})`, ...m.excess_over_elo, color: m.verdict === "inconclusivo" ? t.neutral : t.attack, m })),
      { nullValue: 0, format: (v) => pp(v, 0), xName: "vitória de quem escolheu − esperado pelo Elo (IC 95%)", tooltip: (r) => `<b>${esc(r.m.map_name)}</b><br>${estText(r.m.excess_over_elo)}<br>quem escolheu venceu ${estText(r.m.picker_win_rate, { percent: true })}` },
    );
  }
  renderTable(
    $("#table-main"),
    data.maps,
    [
      { key: "map_name", label: "Mapa" },
      { key: "picks", label: "Picks jogados", num: true },
      { key: "picker_win_rate", label: "Quem escolheu venceu", num: true, sort: (m) => m.picker_win_rate.value, render: (m) => estText(m.picker_win_rate, { percent: true }) },
      { key: "excess_over_elo", label: "Acima do Elo", num: true, sort: (m) => m.excess_over_elo.value, render: (m) => `${estText(m.excess_over_elo)}${ciBar(m.excess_over_elo, { min: -0.2, max: 0.2, nullValue: 0, verdict: m.verdict })}` },
      { key: "p_adj", label: "p (Holm)", num: true, render: (m) => num(m.p_adj, 3) },
      { key: "verdict", label: "Veredito", render: (m) => verdictTag(m.verdict) },
    ],
    { sortKey: "picks" },
  );
};

analyses.regioes = async (data) => {
  const t = tokens();
  if (!data.regions.length) {
    showState($("#chart-main"), "Sem confrontos internacionais entre regiões nesta janela e tier.");
    return showState($("#table-main"), "Nada a mostrar.");
  }
  forest(
    $("#chart-main"),
    data.regions.map((r) => ({ label: `${r.region} (${r.matches})`, ...r.excess_over_elo, color: cssVar(`--${r.region}`) || t.neutral, r })),
    { nullValue: 0, format: (v) => signed(v, 2), xName: "resultado − esperado pelo Elo (IC 95%)", tooltip: (x) => `<b>${esc(x.r.region)}</b><br>${estText(x.r.excess_over_elo)}<br>venceu ${estText(x.r.win_rate, { percent: true })} de ${x.r.matches} séries` },
  );
  renderTable(
    $("#table-main"),
    data.matrix,
    [
      { key: "region", label: "Região", render: (r) => regionDot(r.region) },
      { key: "opponent_region", label: "Contra", render: (r) => regionDot(r.opponent_region) },
      { key: "matches", label: "Séries", num: true },
      { key: "wins", label: "Vitórias", num: true, render: (r) => num(r.wins, 1).replace(",0", "") },
      { key: "rate", label: "Taxa", num: true, sort: (r) => r.wins / r.matches, render: (r) => pct(r.wins / r.matches, 0) },
    ],
    { sortKey: "matches" },
  );
};

analyses.composicoes = async (data) => {
  await loadAgents();
  renderTable(
    $("#table-main"),
    data.top,
    [
      { key: "map", label: "Mapa" },
      { key: "patch", label: "Patch" },
      { key: "key", label: "Composição", cls: "wrap", render: (r) => agentChips(r.key.split("+")) },
      { key: "maps", label: "Mapas", num: true },
      { key: "win_rate", label: "Win rate bruto", num: true, render: (r) => pct(r.win_rate, 0) },
      { key: "above", label: "Acima do Elo, com shrinkage (IC 95%)", num: true, sort: (r) => r.above_elo.value, render: (r) => `${pp(r.above_elo.value)} <span class="faint">(${pp(r.above_elo.low)} a ${pp(r.above_elo.high)})</span>${ciBar(r.above_elo, { min: -0.5, max: 0.5, nullValue: 0 })}` },
    ],
    { sortKey: "above", empty: "Nenhuma composição com 5 mapas ou mais." },
  );
};

analyses.calibracao = async (data, scope) => {
  const t = tokens();
  if (!data.all?.n) {
    showState($("#chart-main"), "Sem séries nesta janela e tier.");
    return showState($("#table-main"), "Nada a mostrar.");
  }
  const curve = (key) => data[key]?.curve.map((b) => ({ x: b.predicted, ...b.observed })) ?? [];
  // com um tier escolhido, o JSON só tem "all" (o próprio tier): a série leva o nome e a cor dele
  const tier = scope?.tier && scope.tier !== "all" ? scope.tier : null;
  const label = { all: tier ? tier.toUpperCase() : "todas", vct: "VCT", vcl: "VCL" };
  const allColor = { vct: t.attack, vcl: t.defense }[tier] ?? t.text;
  const c = chart($("#chart-main"));
  c.setOption({
    grid: { left: 8, right: 24, top: 32, bottom: 36, containLabel: true },
    legend: { top: 0, right: 0, data: ["all", "vct", "vcl"].filter((k) => data[k]).map((k) => label[k]) },
    xAxis: { type: "value", min: 0, max: 1, name: "probabilidade prevista pelo Elo", nameLocation: "middle", nameGap: 26, axisLabel: { formatter: (v) => pct(v, 0) } },
    yAxis: { type: "value", min: 0, max: 1, name: "frequência observada", nameLocation: "middle", nameGap: 44, axisLabel: { formatter: (v) => pct(v, 0) } },
    tooltip: { trigger: "item", formatter: (p) => `${esc(p.seriesName)}: previsto ${pct(p.value[0], 0)}, observado ${pct(p.value[3], 0)} (IC ${pct(p.value[1], 0)}–${pct(p.value[2], 0)})` },
    series: [
      { name: "calibração perfeita", type: "line", data: [[0, 0], [1, 1]], showSymbol: false, lineStyle: { type: "dashed", color: t.faint, width: 1 }, silent: true },
      intervalSeries(label.all, curve("all"), allColor),
      intervalSeries("VCT", curve("vct"), t.attack, { dx: -7 }),
      intervalSeries("VCL", curve("vcl"), t.defense, { dx: 7 }),
    ],
  });
  const rows = ["all", "vct", "vcl"].filter((k) => data[k]).map((k) => ({ k, ...data[k] }));
  renderTable(
    $("#table-main"),
    rows,
    [
      { key: "k", label: "Recorte", render: (r) => label[r.k] },
      { key: "n", label: "Séries", num: true },
      { key: "log_loss", label: "Log loss (IC 95%)", num: true, nosort: true, render: (r) => estText(r.log_loss, { digits: 4 }) },
      { key: "brier", label: "Brier (IC 95%)", num: true, nosort: true, render: (r) => estText(r.brier, { digits: 4 }) },
      { key: "coin", label: "Moeda", num: true, nosort: true, render: (r) => `${num(r.coin_log_loss, 4)} · ${num(r.coin_brier, 2)}` },
    ],
  );
};

analyses.velocidade = async (data) => {
  const t = tokens();
  const sp = data.speed;
  if (!sp.length) {
    ["#chart-main", "#chart-second"].forEach((sel) => showState($(sel), "Menos de dois meses com composições nesta janela e tier."));
    return showState($("#table-main"), "Nada a mostrar.");
  }
  const c = chart($("#chart-main"));
  c.setOption({
    grid: { left: 8, right: 24, top: 32, bottom: 8, containLabel: true },
    legend: { top: 0, right: 0, data: ["mudança no mês", "piso de ruído"] },
    xAxis: { type: "time" },
    yAxis: { type: "value", min: 0, name: "distância ao mês anterior", nameLocation: "middle", nameGap: 44, axisLabel: { formatter: (v) => num(v, 2) } },
    tooltip: { trigger: "axis", valueFormatter: (v) => num(v, 3) },
    series: [
      { name: "ic-base", type: "line", stack: "ic", data: sp.map((r) => [r.month, r.low]), lineStyle: { opacity: 0 }, showSymbol: false, silent: true, tooltip: { show: false } },
      { name: "ic", type: "line", stack: "ic", data: sp.map((r) => [r.month, r.high - r.low]), lineStyle: { opacity: 0 }, areaStyle: { color: t.attack, opacity: 0.15 }, showSymbol: false, silent: true, tooltip: { show: false } },
      {
        name: "mudança no mês",
        type: "line",
        data: sp.map((r) => [r.month, r.distance]),
        lineStyle: { color: t.attack },
        itemStyle: { color: t.attack },
        markLine: {
          silent: true,
          symbol: "none",
          data: data.patches.map((p) => ({ xAxis: p.release_date, lineStyle: { color: t.gold, opacity: p.patch.endsWith(".00") ? 0.9 : 0.25, width: p.patch.endsWith(".00") ? 1.5 : 1, type: "solid" }, label: { show: p.patch.endsWith(".00"), formatter: p.patch, color: t.gold } })),
        },
      },
      { name: "piso de ruído", type: "line", data: sp.map((r) => [r.month, r.noise_floor]), lineStyle: { color: t.text, type: "dashed", width: 1 }, itemStyle: { color: t.text }, showSymbol: false },
    ],
  });
  const agents = Object.keys(data.pick_rate);
  await loadAgents();
  // um estilo rich por agente com o ícone de fundo; sem ícone, só o nome
  const rich = Object.fromEntries(
    agents.filter((a) => AGENTS[a]).map((a, i) => [`a${agents.indexOf(a)}`, { width: 16, height: 16, backgroundColor: { image: AGENTS[a] } }]),
  );
  const months = data.months.map((m) => m.slice(0, 7));
  const heat = [];
  agents.forEach((a, y) => data.pick_rate[a].forEach((v, x) => heat.push([x, y, v])));
  const h = chart($("#chart-second"));
  $("#chart-second").style.height = `${agents.length * 22 + 60}px`;
  h.resize();
  h.setOption({
    grid: { left: 8, right: 8, top: 8, bottom: 8, containLabel: true },
    xAxis: { type: "category", data: months, splitLine: { show: false }, axisLine: { show: false } },
    yAxis: {
      type: "category",
      data: agents,
      inverse: true,
      axisLine: { show: false },
      axisLabel: { fontFamily: t.sans, rich, formatter: (a) => (rich[`a${agents.indexOf(a)}`] ? `${a}  {a${agents.indexOf(a)}|}` : a) },
    },
    visualMap: { show: false, min: 0, max: 1, inRange: { color: [t.surface, t.defense] } },
    tooltip: { formatter: (p) => `${esc(agents[p.value[1]])}, ${months[p.value[0]]}: ${pct(p.value[2], 0)}` },
    series: [{ type: "heatmap", data: heat, label: { show: true, fontSize: 9, color: t.text, formatter: (p) => (p.value[2] >= 0.05 ? nf(0).format(p.value[2] * 100) : "") } }],
  });
  renderTable(
    $("#table-main"),
    sp,
    [
      { key: "month", label: "Mês", num: true, render: (r) => r.month.slice(0, 7) },
      { key: "compositions", label: "Composições", num: true },
      { key: "distance", label: "Mudança (IC 95%)", num: true, render: (r) => estText({ value: r.distance, low: r.low, high: r.high }) },
      { key: "noise_floor", label: "Piso de ruído", num: true, render: (r) => num(r.noise_floor, 3) },
      { key: "real", label: "Acima do ruído?", nosort: true, render: (r) => (r.low > r.noise_floor ? '<span class="tag gold">sim</span>' : verdictTag("inconclusivo")) },
    ],
    { sortKey: "month", desc: false },
  );
};

// Cada troca de recorte limpa os gráficos e as tabelas, carrega o JSON do recorte e roda o mesmo
// desenho; a resposta (escrita no HTML pelo build_site.py, uma por recorte) só troca de visível.
pages.analysis = async () => {
  const name = document.body.dataset.analysis;
  const file = document.body.dataset.file;
  const targets = ["#chart-main", "#chart-second", "#table-main"].map((sel) => $(sel)).filter(Boolean);
  const render = serial(async (scope) => {
    const key = scopeKey(scope);
    document.querySelectorAll(".answer[data-scope]").forEach((p) => (p.hidden = p.dataset.scope !== key));
    replaceQuery(scopeParams(scope));
    targets.forEach((el) => {
      disposeCharts(el);
      el.innerHTML = "";
      el.style.height = ""; // a altura do CSS (ou a que o desenho definir)
    });
    try {
      const data = await loadJSON(`analyses/${key}/${file}.json`);
      await analyses[name]?.(data, scope);
    } catch (err) {
      fail($("#chart-main") ?? $("#table-main") ?? $("main"), err);
    }
  });
  render(bindScope(render));
};

// --- tema e partida ------------------------------------------------------------------------------

function setupThemeToggle() {
  const btn = $("#theme-toggle");
  if (!btn) return;
  const current = () => document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  btn.textContent = current() === "light" ? "◐" : "☼";
  btn.title = current() === "light" ? "tema escuro" : "tema claro";
  btn.addEventListener("click", () => {
    const next = current() === "light" ? "dark" : "light";
    try {
      localStorage.setItem("theme", next);
    } catch (_) {
      /* armazenamento indisponível: o tema vale só para esta página */
    }
    document.documentElement.dataset.theme = next;
    location.reload(); // os gráficos releem os tokens
  });
}

// Menu lateral no celular: o botão ≡ abre e fecha; clicar fora fecha.
function setupNav() {
  const btn = $("#mobile-menu");
  const bar = $("#sidebar");
  if (!btn || !bar) return;
  const toggle = (open) => {
    bar.classList.toggle("open", open);
    btn.setAttribute("aria-expanded", String(open));
  };
  btn.addEventListener("click", (ev) => {
    ev.stopPropagation();
    toggle(!bar.classList.contains("open"));
  });
  document.addEventListener("click", (ev) => {
    if (bar.classList.contains("open") && !bar.contains(ev.target)) toggle(false);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  setupThemeToggle();
  setupNav();
  pages[document.body.dataset.page]?.();
});
