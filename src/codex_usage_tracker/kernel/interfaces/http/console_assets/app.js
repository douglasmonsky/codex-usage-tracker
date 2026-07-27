import {
  allowancePresentation,
  boundedPercent,
  cacheReuse,
  commaSeparated,
  evidenceSelectorForRow,
  publicationKey,
  routeFromPath,
} from "./model.js";

const API = "/api/kernel/v1";

const COPY = Object.freeze({
  live: {
    eyebrow: "Live kernel",
    title: "Usage as it lands",
    description: "Committed facts first. New generations appear without rebuilding your existing index.",
  },
  explore: {
    eyebrow: "Guided exploration",
    title: "Ask the fact store",
    description: "Build one bounded query. The kernel returns facts and exact evidence selectors; you decide what they mean.",
  },
  evidence: {
    eyebrow: "Exact evidence",
    title: "Follow the record",
    description: "Resolve one stable selector into a generation-bound timeline, calls, tools, activities, or allowance observations.",
  },
  limits: {
    eyebrow: "Allowance facts",
    title: "Capacity and limits",
    description: "Observed allowance values remain distinct from calculations, estimates, and caveats.",
  },
  settings: {
    eyebrow: "Local operation",
    title: "Settings",
    description: "Control browser behavior and inspect cache, privacy, freshness, and rollback state.",
  },
});

const EXPLORE_PRESETS = Object.freeze({
  calls: { dimensions: ["thread"], measures: ["calls", "total_tokens"], order_by: "total_tokens" },
  threads: { dimensions: ["project"], measures: ["threads"], order_by: "threads" },
  turns: { dimensions: ["thread"], measures: ["turns", "duration_ms"], order_by: "duration_ms" },
  tools: { dimensions: ["tool"], measures: ["tools", "duration_ms"], order_by: "tools" },
});
const COMMON_OPERATIONS = Object.freeze(["aggregate", "rows", "distribution", "timeline"]);
const CALL_OPERATIONS = Object.freeze([...COMMON_OPERATIONS, "share", "time_series"]);

const state = {
  status: null,
  route: "live",
  selector: "",
  eventSource: null,
  seenPublications: new Set(),
};

const workspace = document.querySelector("#workspace");
const generationLabel = document.querySelector("#generation-label");
const freshnessChip = document.querySelector("#freshness-chip");
const connectionDot = document.querySelector("#connection-dot");
const connectionLabel = document.querySelector("#connection-label");
const refreshButton = /** @type {HTMLButtonElement} */ (document.querySelector("#refresh-button"));
const sidebar = document.querySelector(".sidebar");
const menuToggle = document.querySelector("#menu-toggle");

function element(tag, options = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(options)) {
    if (key === "className") node.className = value;
    else if (key === "text") node.textContent = String(value);
    else if (key === "dataset") Object.assign(node.dataset, value);
    else node.setAttribute(key, String(value));
  }
  for (const child of children) node.append(child);
  return node;
}

function formatNumber(value) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(Number(value));
}

function formatPercent(value) {
  if (value === null || value === undefined) return "—";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

function parseRoute() {
  const route = routeFromPath(location.pathname);
  state.route = route.area;
  state.selector = route.selector;
}

function setCurrentNavigation() {
  /** @type {NodeListOf<HTMLAnchorElement>} */ (document.querySelectorAll("nav a")).forEach((link) => {
    if (link.dataset.route === state.route) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
}

function heading(area) {
  const copy = COPY[area];
  return element("div", { className: "page-heading" }, [
    element("div", {}, [
      element("span", { className: "section-label", text: copy.eyebrow }),
      element("h1", { text: copy.title }),
      element("p", { text: copy.description }),
    ]),
  ]);
}

function setStatusPresentation(status) {
  state.status = status;
  const hasSnapshot = Number.isInteger(status.generation);
  const stale = status.state === "stale" || status.freshness?.stale === true;
  generationLabel.textContent = hasSnapshot
    ? `Generation ${status.generation} · committed`
    : "No committed generation";
  freshnessChip.className = `chip ${status.refresh || stale ? "warn" : hasSnapshot ? "good" : "neutral"}`;
  freshnessChip.textContent = status.refresh
    ? `Refresh ${status.refresh.progress_percent || 0}%`
    : stale ? "Stale snapshot" : hasSnapshot ? "Ready from cache" : "Refresh required";
  connectionDot.classList.toggle("online", true);
  connectionLabel.textContent = "Kernel connected";
}

function errorPanel(error, retry) {
  const children = [
    element("strong", { text: "This view could not load" }),
    element("span", { text: error.message }),
  ];
  if (typeof retry === "function") {
    const button = element("button", { className: "button ghost", type: "button", text: "Try again" });
    button.addEventListener("click", retry);
    children.push(element("div", { className: "form-actions" }, [button]));
  }
  return element("div", { className: "card error-state" }, children);
}

function tableFor(rows, includeEvidence = false) {
  if (!rows.length) return element("div", { className: "empty", text: "No matching facts in this committed generation." });
  const columns = Object.keys(rows[0]);
  const rowSelectors = rows.map(evidenceSelectorForRow);
  const hasEvidence = includeEvidence && rowSelectors.some(Boolean);
  const head = element("tr");
  for (const column of columns) head.append(element("th", { text: column.replaceAll("_", " ") }));
  if (hasEvidence) head.append(element("th", { text: "Evidence" }));
  const body = document.createDocumentFragment();
  rows.forEach((row, index) => {
    const tr = element("tr");
    columns.forEach((column) => {
      const value = row[column];
      const numeric = typeof value === "number";
      tr.append(element("td", { className: numeric ? "numeric" : "", text: numeric ? formatNumber(value) : value ?? "—" }));
    });
    if (hasEvidence) {
      const selector = rowSelectors[index];
      const cell = element("td");
      if (selector) {
        cell.append(element("a", {
          className: "evidence-link",
          href: `/evidence/${encodeURIComponent(selector)}?view=timeline`,
          text: "Open",
        }));
      }
      tr.append(cell);
    }
    body.append(tr);
  });
  const table = element("table", {}, [element("thead", {}, [head]), element("tbody", {}, [body])]);
  return element("div", { className: "table-wrap" }, [table]);
}

async function renderLive() {
  workspace.replaceChildren(heading("live"), loadingMetrics());
  if (!state.status?.generation) {
    workspace.append(element("div", { className: "card empty", text: "Build the first local generation with Refresh data. Existing sessions are not read until you ask." }));
    return;
  }
  try {
    const payload = await request("/query", {
      method: "POST",
      body: JSON.stringify({
        requests: [
          {
            dataset: "calls",
            operation: "aggregate",
            dimensions: [],
            measures: ["calls", "uncached_input_tokens", "cached_input_tokens", "reasoning_tokens", "output_tokens", "total_tokens"],
            limit: 1,
          },
          {
            dataset: "calls",
            operation: "aggregate",
            dimensions: ["thread"],
            measures: ["calls", "total_tokens"],
            order_by: "total_tokens",
            descending: true,
            limit: 12,
          },
          {
            dataset: "calls",
            operation: "time_series",
            dimensions: ["time_day"],
            measures: ["uncached_input_tokens", "cached_input_tokens", "reasoning_tokens", "output_tokens"],
            order_by: "time_day",
            descending: true,
            limit: 14,
          },
        ],
      }),
    });
    const summary = payload.results[0];
    const leaders = payload.results[1];
    const timeline = payload.results[2];
    workspace.replaceChildren(heading("live"), metrics(summary.rows[0] || {}));
    workspace.append(element("div", { className: "section-grid" }, [
      element("section", { className: "card", "aria-labelledby": "token-mix-title" }, [
        element("h2", { id: "token-mix-title", text: "Four-class token mix" }),
        tokenBars(summary.rows[0] || {}),
      ]),
      element("section", { className: "card" }, [
        element("h2", { text: "Snapshot truth" }),
        definitionList({
          Generation: summary.generation,
          Grade: summary.grade,
          "Matched calls": summary.matched_count,
          "Query time": `${formatNumber(summary.elapsed_ms)} ms`,
        }),
      ]),
    ]));
    workspace.append(element("section", { className: "card", style: "margin-top:1rem" }, [
      element("h2", { text: "Recent token bands" }),
      element("p", { className: "result-meta", text: "Daily foundational facts by uncached input, cached input, reasoning, and output." }),
      tableFor(timeline.rows),
    ]));
    workspace.append(element("section", { className: "card", style: "margin-top:1rem" }, [
      element("h2", { text: "Highest-token threads" }),
      tableFor(leaders.rows, true),
    ]));
  } catch (error) {
    workspace.replaceChildren(heading("live"), errorPanel(error, renderLive));
  }
}

function loadingMetrics() {
  const grid = element("div", { className: "metric-grid" });
  for (let index = 0; index < 4; index += 1) grid.append(element("div", { className: "card metric-card" }, [element("div", { className: "skeleton" })]));
  return grid;
}

function metrics(row) {
  const values = [
    ["Calls", row.calls],
    ["Total tokens", row.total_tokens],
    ["Cache reuse", cacheReuse(row.cached_input_tokens, row.uncached_input_tokens)],
    ["Tool-independent facts", state.status?.generation ? `Gen ${state.status.generation}` : "—"],
  ];
  return element("div", { className: "metric-grid" }, values.map(([label, value]) =>
    element("section", { className: "card metric-card" }, [
      element("span", { text: label }),
      element("strong", {
        text: label === "Cache reuse"
          ? formatPercent(value)
          : typeof value === "number" ? formatNumber(value) : value,
      }),
    ])
  ));
}

function tokenBars(row) {
  const values = [
    ["Uncached input", row.uncached_input_tokens || 0, ""],
    ["Cached input", row.cached_input_tokens || 0, "cached"],
    ["Reasoning", row.reasoning_tokens || 0, "reasoning"],
    ["Output", row.output_tokens || 0, "output"],
  ];
  const maximum = Math.max(...values.map((item) => Number(item[1])), 1);
  return element("div", { className: "token-bars" }, values.map(([label, value, kind]) =>
    element("div", { className: "token-row" }, [
      element("span", { text: label }),
      element("div", { className: "bar-track", role: "img", "aria-label": `${label}: ${formatNumber(value)} tokens` }, [
        element("div", { className: `bar-fill ${kind}`, style: `width:${boundedPercent(value, maximum)}%` }),
      ]),
      element("strong", { text: formatNumber(value) }),
    ])
  ));
}

async function renderExplore() {
  const dataset = "calls";
  workspace.replaceChildren(heading("explore"));
  const form = element("form", { className: "card form-grid", id: "query-form" });
  const datasetSelect = selectField("Dataset", "dataset", Object.keys(EXPLORE_PRESETS), dataset);
  const operationSelect = selectField("Operation", "operation", CALL_OPERATIONS, "aggregate");
  const dimensionInput = inputField("Group by", "dimensions", "thread");
  const measureInput = inputField("Measures", "measures", "calls,total_tokens");
  const limitInput = inputField("Row limit", "limit", "25", "number");
  form.append(datasetSelect.wrapper, operationSelect.wrapper, dimensionInput.wrapper, measureInput.wrapper, limitInput.wrapper);
  const saveButton = element("button", { className: "button ghost", type: "button", text: "Save locally" });
  const loadButton = element("button", {
    className: "button ghost",
    type: "button",
    text: "Load saved",
    ...(localStorage.getItem("kernel-saved-query") ? {} : { disabled: "" }),
  });
  form.append(element("div", { className: "form-actions" }, [
    element("button", { className: "button primary", type: "submit", text: "Run bounded query" }),
    saveButton,
    loadButton,
  ]));
  const output = element("section", { className: "card", style: "margin-top:1rem" }, [element("div", { className: "empty", text: "Choose the grain and measures, then run the query." })]);
  workspace.append(form, output);
  datasetSelect.control.addEventListener("change", () => {
    const preset = EXPLORE_PRESETS[datasetSelect.control.value];
    replaceOptions(
      operationSelect.control,
      datasetSelect.control.value === "calls" ? CALL_OPERATIONS : COMMON_OPERATIONS,
      "aggregate",
    );
    dimensionInput.control.value = preset.dimensions.join(",");
    measureInput.control.value = preset.measures.join(",");
  });
  const currentSpec = () => ({
    dataset: datasetSelect.control.value,
    operation: operationSelect.control.value,
    dimensions: dimensionInput.control.value,
    measures: measureInput.control.value,
    limit: limitInput.control.value,
  });
  saveButton.addEventListener("click", () => {
    localStorage.setItem("kernel-saved-query", JSON.stringify(currentSpec()));
    loadButton.disabled = false;
    toast("Query spec saved in this browser.");
  });
  loadButton.addEventListener("click", () => {
    const saved = JSON.parse(localStorage.getItem("kernel-saved-query") || "null");
    if (!saved) return;
    datasetSelect.control.value = saved.dataset;
    replaceOptions(
      operationSelect.control,
      saved.dataset === "calls" ? CALL_OPERATIONS : COMMON_OPERATIONS,
      saved.operation,
    );
    operationSelect.control.value = saved.operation;
    dimensionInput.control.value = saved.dimensions;
    measureInput.control.value = saved.measures;
    limitInput.control.value = saved.limit;
    toast("Saved query loaded.");
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    output.replaceChildren(element("div", { className: "empty", text: "Reading committed facts…" }));
    try {
      const result = (await request("/query", {
        method: "POST",
        body: JSON.stringify({ requests: [{
          dataset: datasetSelect.control.value,
          operation: operationSelect.control.value,
          dimensions: commaSeparated(dimensionInput.control.value),
          measures: commaSeparated(measureInput.control.value),
          limit: Number(limitInput.control.value),
          descending: true,
        }] }),
      })).results[0];
      output.replaceChildren(
        element("div", { className: "result-meta", text: `Generation ${result.generation} · ${result.returned_count} of ${result.matched_count} rows · ${formatNumber(result.elapsed_ms)} ms · ${result.grade}` }),
        tableFor(result.rows, true),
      );
    } catch (error) {
      output.replaceChildren(errorPanel(error, () => form.requestSubmit()));
    }
  });
}

function selectField(labelText, name, options, selected) {
  const control = element("select", { name, id: name });
  options.forEach((option) => control.append(element("option", { value: option, text: option, ...(option === selected ? { selected: "" } : {}) })));
  return { control, wrapper: element("label", { for: name }, [document.createTextNode(labelText), control]) };
}

function inputField(labelText, name, value, type = "text") {
  const control = element("input", { name, id: name, value, type });
  return { control, wrapper: element("label", { for: name }, [document.createTextNode(labelText), control]) };
}

function replaceOptions(control, options, selected) {
  control.replaceChildren();
  options.forEach((option) => control.append(element("option", {
    value: option,
    text: option,
    ...(option === selected ? { selected: "" } : {}),
  })));
}

async function renderEvidence() {
  workspace.replaceChildren(heading("evidence"));
  const form = element("form", { className: "card form-grid" });
  const selector = inputField("Evidence selector", "selector", state.selector);
  selector.control.placeholder = "thread:… or call:…";
  const params = new URLSearchParams(location.search);
  const view = selectField("View", "view", ["summary", "timeline", "calls", "tools", "activities", "allowance"], params.get("view") || "timeline");
  form.append(selector.wrapper, view.wrapper, element("div", { className: "form-actions" }, [
    element("button", { className: "button primary", type: "submit", text: "Open evidence" }),
  ]));
  const output = element("section", { className: "card", style: "margin-top:1rem" }, [element("div", { className: "empty", text: "Enter a selector or follow an evidence link from Live or Explore." })]);
  workspace.append(form, output);
  const load = async () => {
    if (!selector.control.value.trim()) return;
    output.replaceChildren(element("div", { className: "empty", text: "Resolving exact evidence…" }));
    try {
      const result = await request("/evidence", {
        method: "POST",
        body: JSON.stringify({ selector: selector.control.value.trim(), view: view.control.value, limit: 100, live: params.get("live") === "1" }),
      });
      output.replaceChildren(
        element("div", { className: "result-meta", text: `Generation ${result.generation} · ${result.selector} · ${result.grade} · ${result.returned_count} of ${result.matched_count}` }),
        tableFor(result.rows),
      );
    } catch (error) {
      output.replaceChildren(errorPanel(error, load));
    }
  };
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const next = `/evidence/${encodeURIComponent(selector.control.value.trim())}?view=${encodeURIComponent(view.control.value)}`;
    history.pushState({}, "", next);
    parseRoute();
    load();
  });
  if (state.selector) load();
}

async function renderLimits() {
  workspace.replaceChildren(heading("limits"), element("div", { className: "card empty", text: "Reading allowance observations…" }));
  try {
    const result = await request("/allowance?limit=100");
    const rows = allowancePresentation(result.intervals || result.rows || []);
    const caveats = [...new Set(rows.flatMap((row) => row.caveats ? row.caveats.split(", ") : []))];
    workspace.replaceChildren(
      heading("limits"),
      element("div", { className: "callout", text: "Allowance percentages are exact observations. Interval ratios are deterministic local comparisons, not causal billing attribution. Cost and credit values appear only as source-stamped estimates." }),
      element("section", { className: "card" }, [
        element("h2", { text: "Measurement coverage" }),
        definitionList({
          Generation: result.generation,
          Grade: result.grade,
          "Observed through": result.observed_through || "none",
          "Returned observations": result.returned_count,
          "Rate card": result.coverage?.pricing?.configured ? "configured" : "not configured",
          "Rated token coverage": formatPercent((result.coverage?.pricing?.coverage_percent || 0) / 100),
        }),
      ]),
      element("section", { className: "card" }, [
        element("h2", { text: "Observed windows and local intervals" }),
        element("div", { className: "result-meta", text: "A ratio is shown only when two adjacent observations share one logical reset window and usage increased." }),
        tableFor(rows, true),
      ]),
      element("section", { className: "card" }, [
        element("h2", { text: "Caveats" }),
        caveats.length
          ? element("ul", {}, caveats.map((item) => element("li", { text: item.replaceAll("_", " ") })))
          : element("p", { text: "No additional caveats in this page." }),
      ]),
    );
  } catch (error) {
    workspace.replaceChildren(heading("limits"), errorPanel(error, renderLimits));
  }
}

function renderSettings() {
  workspace.replaceChildren(
    heading("settings"),
    element("section", { className: "card" }, [
      element("h2", { text: "Runtime" }),
      definitionList({
        Version: state.status?.version || "—",
        "Cache state": state.status?.state || "absent",
        Generation: state.status?.generation ?? "none",
        Publication: state.status?.publication_id || "none",
        "Active refresh": state.status?.refresh ? `${state.status.refresh.stage} · ${state.status.refresh.progress_percent}%` : "none",
        Watcher: localStorage.getItem("kernel-live-enabled") === "false" ? "paused in this browser" : "watching committed generations",
        "Rate card": state.status?.rate_card?.configured
          ? `${state.status.rate_card.source?.name || "configured"} · effective ${state.status.rate_card.source?.effective_at || "unknown"}`
          : `${state.status?.rate_card?.status || "absent"} · no estimates shown`,
        Rollback: "available through the operational CLI",
        "Optional content indexing": "off · foundational facts only",
      }),
    ]),
    element("section", { className: "card", style: "margin-top:1rem" }, [
      element("h2", { text: "Browser behavior" }),
      toggleRow(),
      element("p", { className: "callout", text: "Refresh is explicit. Opening or reopening this console only reads the last committed snapshot; it never rebuilds the database." }),
    ]),
    element("section", { className: "card", style: "margin-top:1rem" }, [
      element("h2", { text: "Privacy boundary" }),
      element("p", { text: "The console reads normalized local facts from the loopback kernel API. Prompts, reasoning text, raw tool arguments, raw tool output, shell bodies, secrets, and full source paths are not part of this product surface." }),
    ]),
  );
}

function definitionList(values) {
  const list = element("dl", { className: "definition-list" });
  Object.entries(values).forEach(([term, value]) => list.append(element("div", {}, [
    element("dt", { text: term }),
    element("dd", { text: value }),
  ])));
  return list;
}

function toggleRow() {
  const enabled = localStorage.getItem("kernel-live-enabled") !== "false";
  const checkbox = element("input", { type: "checkbox", id: "live-toggle", ...(enabled ? { checked: "" } : {}) });
  checkbox.addEventListener("change", () => {
    localStorage.setItem("kernel-live-enabled", String(checkbox.checked));
    connectLive();
  });
  return element("label", { for: "live-toggle" }, [
    element("span", { text: "Watch for committed generations" }),
    checkbox,
  ]);
}

async function renderCurrentRoute() {
  setCurrentNavigation();
  sidebar.classList.remove("open");
  menuToggle.setAttribute("aria-expanded", "false");
  if (state.route === "live") await renderLive();
  else if (state.route === "explore") await renderExplore();
  else if (state.route === "evidence") await renderEvidence();
  else if (state.route === "limits") await renderLimits();
  else renderSettings();
}

async function refreshStatus() {
  const status = await request("/status");
  setStatusPresentation(status);
  return status;
}

async function startRefresh() {
  refreshButton.disabled = true;
  refreshButton.textContent = "Starting…";
  try {
    const started = await request("/refresh", { method: "POST", body: "{}" });
    const job = started.job;
    toast(started.disposition === "joined" ? "Joined the active refresh." : "Refresh started.");
    const terminal = await request(`/jobs/${encodeURIComponent(job.job_id)}?wait_seconds=30&include_result=1`);
    if (terminal.terminal && terminal.state === "completed") {
      await refreshStatus();
      await renderCurrentRoute();
      toast(`Generation ${terminal.output_generation} committed.`);
    } else {
      await refreshStatus();
      toast(`Refresh is ${terminal.stage}. The committed snapshot remains available.`);
    }
  } catch (error) {
    toast(error.message);
  } finally {
    refreshButton.disabled = false;
    refreshButton.textContent = "Refresh data";
  }
}

function connectLive() {
  if (state.eventSource) state.eventSource.close();
  state.eventSource = null;
  if (localStorage.getItem("kernel-live-enabled") === "false" || !state.status?.generation) return;
  if (state.status.publication_id) state.seenPublications.add(state.status.publication_id);
  const source = new EventSource(`${API}/events?limit=100`);
  state.eventSource = source;
  source.addEventListener("generation_committed", async (event) => {
    const payload = JSON.parse(event.data);
    const key = publicationKey(payload);
    if (state.seenPublications.has(key)) return;
    state.seenPublications.add(key);
    await refreshStatus();
    await renderCurrentRoute();
    toast(`Generation ${payload.generation} is ready.`);
  });
  source.addEventListener("snapshot_required", async () => {
    await refreshStatus();
    await renderCurrentRoute();
  });
}

function toast(message) {
  const region = document.querySelector("#toast-region");
  const item = element("div", { className: "toast", text: message });
  region.append(item);
  setTimeout(() => item.remove(), 5000);
}

document.addEventListener("click", (event) => {
  if (!(event.target instanceof Element)) return;
  const link = event.target.closest("a[href^='/']");
  if (!(link instanceof HTMLAnchorElement) || link.hasAttribute("download")) return;
  const url = new URL(link.href);
  if (url.origin !== location.origin) return;
  event.preventDefault();
  history.pushState({}, "", url.pathname + url.search);
  parseRoute();
  renderCurrentRoute();
});

window.addEventListener("popstate", () => {
  parseRoute();
  renderCurrentRoute();
});

menuToggle.addEventListener("click", () => {
  const open = sidebar.classList.toggle("open");
  menuToggle.setAttribute("aria-expanded", String(open));
});
refreshButton.addEventListener("click", startRefresh);

async function boot() {
  parseRoute();
  setCurrentNavigation();
  try {
    await refreshStatus();
    await renderCurrentRoute();
    connectLive();
  } catch (error) {
    connectionLabel.textContent = "Kernel unavailable";
    freshnessChip.className = "chip warn";
    freshnessChip.textContent = "Unavailable";
    workspace.replaceChildren(heading(state.route), errorPanel(error, boot));
  }
}

boot();
