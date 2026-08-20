import {
  allowancePresentation,
  boundedPercent,
  cacheReuse,
  commaSeparated,
  evidenceSelectorForRow,
  humanColumnLabel,
  materializeTemplate,
  orderedColumns,
  pageRows,
  publicationKey,
  routeFromPath,
  sortRows,
} from "./model.js";

const API = "/api/kernel/v1";
const TABLE_PAGE_SIZE = 10;
const LIVE_CACHE_PREFIX = "kernel-live-v1:";
const LANGUAGE_STORAGE_KEY = "kernel-console-language";
const ZH_CN = Object.freeze({
  "Live kernel": "实时概览", "Usage as it lands": "本机用量概览",
  "Guided exploration": "引导查询", "Ask the fact store": "查询本机事实",
  "Exact evidence": "精确证据", "Follow the record": "追溯记录",
  "Allowance facts": "额度事实", "Capacity and limits": "容量与限制",
  "Local operation": "本机运行", "Settings": "设置",
  "Calls": "调用次数", "Total tokens": "总 Token", "Cache reuse": "缓存复用率",
  "Cost and credits": "成本与 credits", "Four-class token mix": "Token 构成",
  "Current committed view": "当前已提交视图", "Recent token bands": "近期每日 Token",
  "Highest-token threads": "Token 用量最高的任务", "Runtime": "运行状态",
  "Browser behavior": "浏览器行为", "Privacy boundary": "隐私边界",
  "Watch for committed generations": "监听新的数据代次", "Language": "语言",
  "English": "English", "Simplified Chinese": "简体中文",
  "Skip to workspace": "跳到主要内容", "Local evidence kernel": "本机数据内核",
  "Local data only": "仅本机数据", "Live": "实时概览", "Explore": "查询",
  "Limits": "额度", "Connecting…": "正在连接…", "Committed snapshot": "已提交快照",
  "Loading local index…": "正在读取本机索引…", "Checking freshness": "正在检查新鲜度",
  "Dataset": "数据集", "Operation": "操作", "Group by": "分组维度",
  "Measures": "统计指标", "Row limit": "行数上限", "Evidence": "证据",
  "Open": "查看", "Refresh data": "刷新数据", "Starting…": "正在启动…",
  "Uncached input": "未缓存输入", "Cached input": "缓存输入",
  "Reasoning": "推理", "Output": "输出",
  "No matching facts in this committed generation.": "当前已提交数据代次中没有匹配记录。",
  "Load detailed views": "加载详细视图", "Detailed views are loaded on demand to keep the initial summary fast.": "为加快首屏，趋势和任务排行改为按需加载。",
  "Live updates paused after a repeated snapshot gap; refresh the page after the next committed generation.": "连续两次快照间隙后已暂停实时监听；下次提交数据代次后请刷新页面。",
});

function t(value) {
  return state.language === "zh-CN" ? ZH_CN[value] || value : value;
}
const EXPLORE_DEFAULT_REQUESTS = Object.freeze([
  {
    dataset: "calls",
    operation: "share",
    dimensions: ["thread"],
    measures: [
      "calls",
      "uncached_input_tokens",
      "cached_input_tokens",
      "reasoning_tokens",
      "output_tokens",
      "total_tokens",
      "configured_cost_usd",
      "estimated_credits",
    ],
    order_by: "total_tokens",
    descending: true,
    limit: 25,
  },
  {
    dataset: "calls",
    operation: "rows",
    dimensions: ["event_at", "call", "thread"],
    measures: [
      "uncached_input_tokens",
      "cached_input_tokens",
      "reasoning_tokens",
      "output_tokens",
      "total_tokens",
      "configured_cost_usd",
      "estimated_credits",
    ],
    order_by: "event_at",
    descending: true,
    limit: 25,
  },
]);

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

const state = {
  status: null,
  route: "live",
  selector: "",
  eventSource: null,
  seenPublications: new Set(),
  language: localStorage.getItem(LANGUAGE_STORAGE_KEY) === "zh-CN" ? "zh-CN" : "en",
  snapshotRecoveryAttempted: false,
};
let tableSequence = 0;

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
    else if (key === "text") node.textContent = t(String(value));
    else if (key === "dataset") Object.assign(node.dataset, value);
    else node.setAttribute(key, String(value));
  }
  for (const child of children) node.append(child);
  return node;
}

function svgElement(tag, options = {}, children = []) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(options)) {
    if (key === "className") node.setAttribute("class", String(value));
    else if (key === "text") node.textContent = String(value);
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

function formatSmallFact(value, minimumFractionDigits = 0) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  if (number !== 0 && Math.abs(number) < 0.01) {
    return number.toLocaleString(undefined, {
      maximumSignificantDigits: 6,
      minimumSignificantDigits: 1,
    });
  }
  return number.toLocaleString(undefined, {
    maximumFractionDigits: 4,
    minimumFractionDigits,
  });
}

function timestampMillis(value) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 10_000_000_000 ? value : value * 1000;
  }
  const text = String(value);
  if (/^\d{9,12}$/.test(text)) return Number(text) * 1000;
  const parsed = new Date(text).getTime();
  return Number.isNaN(parsed) ? null : parsed;
}

function formatCell(column, value) {
  if (value === null || value === undefined || value === "") return "—";
  if (column === "event_at" || column === "observed_at" || column.endsWith("_at")) {
    const timestamp = timestampMillis(value);
    if (timestamp !== null) return new Date(timestamp).toLocaleString();
  }
  if (column.endsWith("_cost_usd")) {
    return `$${formatSmallFact(value, 2)}`;
  }
  if (column.includes("credits")) {
    return `${formatSmallFact(value)}${column === "estimated_credits" ? " credits" : ""}`;
  }
  if (column.startsWith("share_")) return formatPercent(value);
  if (column.endsWith("_percent")) return `${formatNumber(value)}%`;
  if (typeof value === "number") return formatNumber(value);
  return String(value);
}

function pricingCoverageSummary(results) {
  const resultList = (Array.isArray(results) ? results : [results]).filter(Boolean);
  const parts = [];
  for (const [measure, label] of [
    ["configured_cost_usd", "cost"],
    ["estimated_credits", "credits"],
  ]) {
    const entries = resultList
      .map((result) => result.coverage?.measures?.[measure])
      .filter(Boolean);
    if (!entries.length) continue;
    const observed = entries.reduce(
      (total, entry) => total + Number(entry.observed_count || 0),
      0,
    );
    const missing = entries.reduce(
      (total, entry) => total + Number(entry.missing_count || 0),
      0,
    );
    const denominator = observed + missing;
    const percent = denominator ? 100 * observed / denominator : 100;
    const confidence = entries.find((entry) => entry.confidence)?.confidence;
    const provenance = entries.find((entry) => entry.provenance)?.provenance;
    parts.push(
      `${label} ${percent.toFixed(1)}% rated · ${formatNumber(missing)} missing`
      + `${confidence ? ` · ${confidence} confidence` : ""}`
      + `${provenance ? ` · ${provenance}` : ""}`,
    );
  }
  const rateStatus = resultList
    .map((result) => result.coverage?.rate_card?.status)
    .find(Boolean);
  if (rateStatus) parts.push(`rate card ${rateStatus}`);
  return parts.join(" · ");
}

function tokenMixForRow(row, prefix = "") {
  const parts = [
    ["new", row[`${prefix}uncached_input_tokens`]],
    ["cached", row[`${prefix}cached_input_tokens`]],
    ["reasoning", row[`${prefix}reasoning_tokens`]],
    ["output", row[`${prefix}output_tokens`]],
  ];
  return parts.some(([, value]) => value !== null && value !== undefined)
    ? parts.map(([label, value]) => `${formatNumber(value)} ${label}`).join(" · ")
    : "—";
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

function tableFor(rows, includeEvidence = false, options = {}) {
  if (!rows.length) return element("div", { className: "empty", text: "No matching facts in this committed generation." });
  const technicalColumns = new Set(options.technicalColumns || []);
  const hiddenColumns = new Set(options.hiddenColumns || []);
  let discoveredColumns = [...new Set(rows.flatMap((row) => Object.keys(row)))]
    .filter((column) => !technicalColumns.has(column) && !hiddenColumns.has(column));
  if (options.compactTokens) {
    const tokenColumns = [
      "uncached_input_tokens",
      "cached_input_tokens",
      "reasoning_tokens",
      "output_tokens",
    ];
    const adjacentColumns = tokenColumns.map((column) => `adjacent_${column}`);
    if (tokenColumns.some((column) => discoveredColumns.includes(column))) {
      discoveredColumns = discoveredColumns.filter(
        (column) => !tokenColumns.includes(column),
      );
      discoveredColumns.push("token_mix");
    }
    if (adjacentColumns.some((column) => discoveredColumns.includes(column))) {
      discoveredColumns = discoveredColumns.filter(
        (column) => !adjacentColumns.includes(column),
      );
      discoveredColumns.push("adjacent_token_mix");
    }
  }
  const preferredColumns = options.columnOrder || [];
  const columns = [
    ...preferredColumns.filter((column) => discoveredColumns.includes(column)),
    ...orderedColumns(
      discoveredColumns.filter((column) => !preferredColumns.includes(column)),
    ),
  ];
  const rowSelectors = rows.map(evidenceSelectorForRow);
  const hasEvidence = includeEvidence && rowSelectors.some(Boolean);
  const hasDetails = technicalColumns.size > 0;
  /** @type {string|null} */
  let sortColumn = null;
  /** @type {"ascending"|"descending"} */
  let sortDirection = "descending";
  let currentPage = 1;
  let filterText = "";
  const wrapper = element("div", { className: "data-table" });
  tableSequence += 1;
  const filterId = `table-filter-${tableSequence}`;
  const filter = element("input", {
    id: filterId,
    type: "search",
    placeholder: "Filter visible rows",
    "aria-label": `Filter ${options.label || "table"} rows`,
  });
  const tableControls = element("div", { className: "table-controls" }, [
    element("label", { for: filterId, text: "Filter rows" }),
    filter,
  ]);
  const tableWrap = element("div", { className: "table-wrap" });
  const table = element("table");
  const head = element("tr");
  const body = element("tbody");
  const pager = element("div", { className: "table-pager" });
  const pageStatus = element("span", { className: "result-meta" });
  const previous = element("button", {
    className: "button ghost",
    type: "button",
    text: "Previous page",
  });
  const next = element("button", {
    className: "button ghost",
    type: "button",
    text: "Next page",
  });
  const headerControls = new Map();

  for (const column of columns) {
    const label = humanColumnLabel(column);
    const button = element("button", {
      className: "sort-button",
      type: "button",
      text: label,
      "aria-label": label,
    });
    const header = element("th", { scope: "col" }, [button]);
    button.addEventListener("click", () => {
      if (sortColumn === column) {
        sortDirection = sortDirection === "ascending" ? "descending" : "ascending";
      } else {
        sortColumn = column;
        sortDirection = "descending";
      }
      currentPage = 1;
      renderRows();
    });
    headerControls.set(column, { button, header });
    head.append(header);
  }
  if (hasEvidence) head.append(element("th", { scope: "col", text: "Evidence" }));
  if (hasDetails) head.append(element("th", { scope: "col", text: "Details" }));
  table.append(element("thead", {}, [head]), body);
  tableWrap.append(table);
  pager.append(pageStatus, previous, next);
  wrapper.append(tableControls, tableWrap, pager);

  const renderRows = () => {
    for (const [column, controls] of headerControls) {
      const active = sortColumn === column;
      controls.header.setAttribute("aria-sort", active ? sortDirection : "none");
    }
    const sortField = sortColumn === "token_mix"
      ? "total_tokens"
      : sortColumn === "adjacent_token_mix" ? "adjacent_total_tokens" : sortColumn;
    const ordered = sortField ? sortRows(rows, sortField, sortDirection) : [...rows];
    const filtered = filterText
      ? ordered.filter((row) => columns.some(
        (column) => {
          const value = column === "token_mix"
            ? tokenMixForRow(row)
            : column === "adjacent_token_mix"
              ? tokenMixForRow(row, "adjacent_")
              : row[column];
          return String(value ?? "").toLocaleLowerCase().includes(filterText);
        },
      ))
      : ordered;
    const page = pageRows(filtered, currentPage, options.pageSize || TABLE_PAGE_SIZE);
    currentPage = page.page;
    body.replaceChildren();
    page.rows.forEach((row) => {
      const sourceIndex = rows.indexOf(row);
      const tr = element("tr");
      columns.forEach((column) => {
        const value = column === "token_mix"
          ? tokenMixForRow(row)
          : column === "adjacent_token_mix"
            ? tokenMixForRow(row, "adjacent_")
            : row[column];
        tr.append(element("td", {
          className: typeof value === "number" ? "numeric" : "",
          text: formatCell(column, value),
        }));
      });
      if (hasEvidence) {
        const selector = rowSelectors[sourceIndex];
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
      if (hasDetails) {
        const details = Object.fromEntries(
          [...technicalColumns]
            .filter((column) => row[column] !== undefined)
            .map((column) => [humanColumnLabel(column), row[column]]),
        );
        const copyDetails = element("button", {
          className: "button ghost compact",
          type: "button",
          text: "Copy",
          "aria-label": "Copy technical details",
        });
        copyDetails.addEventListener("click", async () => {
          try {
            await navigator.clipboard.writeText(JSON.stringify(details, null, 2));
            toast("Technical details copied.");
          } catch (error) {
            toast(`Unable to copy technical details: ${error.message}`);
          }
        });
        tr.append(element("td", {}, [
          element("details", {}, [
            element("summary", { text: "Technical" }),
            element("code", { text: JSON.stringify(details) }),
            copyDetails,
          ]),
        ]));
      }
      body.append(tr);
    });
    pageStatus.textContent = `Rows ${page.start}–${page.end} of ${filtered.length}`;
    previous.disabled = page.page <= 1;
    next.disabled = page.page >= page.pageCount;
    pager.hidden = rows.length <= (options.pageSize || TABLE_PAGE_SIZE);
  };
  previous.addEventListener("click", () => {
    currentPage -= 1;
    renderRows();
  });
  next.addEventListener("click", () => {
    currentPage += 1;
    renderRows();
  });
  filter.addEventListener("input", () => {
    filterText = filter.value.trim().toLocaleLowerCase();
    currentPage = 1;
    renderRows();
  });
  renderRows();
  return wrapper;
}

function liveCacheKey() {
  return Number.isInteger(state.status?.generation)
    ? `${LIVE_CACHE_PREFIX}${state.status.generation}`
    : null;
}

function applyLanguage() {
  document.documentElement.lang = state.language;
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.getAttribute("data-i18n");
    if (key) node.textContent = t(key);
  });
}

function readLiveCache() {
  const key = liveCacheKey();
  if (!key) return null;
  try {
    const cached = JSON.parse(localStorage.getItem(key) || "null");
    return cached?.summary ? cached : null;
  } catch {
    localStorage.removeItem(key);
    return null;
  }
}

function writeLiveCache(payload) {
  const key = liveCacheKey();
  if (!key) return;
  try {
    localStorage.setItem(key, JSON.stringify(payload));
  } catch {
    // Keep the live view usable when browser storage is unavailable.
  }
}

async function requestLiveSummary() {
  const payload = await request("/query", {
    method: "POST",
    body: JSON.stringify({ requests: [{
      dataset: "calls", operation: "aggregate", dimensions: [],
      measures: ["calls", "uncached_input_tokens", "cached_input_tokens", "reasoning_tokens", "output_tokens", "total_tokens", "configured_cost_usd", "estimated_credits"],
      limit: 1,
    }] }),
  });
  return payload.results[0];
}

async function requestLiveDetails() {
  const payload = await request("/query", {
    method: "POST",
    body: JSON.stringify({ requests: [
      { dataset: "calls", operation: "aggregate", dimensions: [], measures: ["calls", "uncached_input_tokens", "cached_input_tokens", "reasoning_tokens", "output_tokens", "total_tokens", "configured_cost_usd", "estimated_credits"], limit: 1 },
      { dataset: "calls", operation: "share", dimensions: ["thread"], measures: ["calls", "uncached_input_tokens", "cached_input_tokens", "reasoning_tokens", "output_tokens", "total_tokens", "configured_cost_usd", "estimated_credits"], order_by: "total_tokens", descending: true, limit: 25 },
      { dataset: "calls", operation: "time_series", dimensions: ["time_day"], measures: ["uncached_input_tokens", "cached_input_tokens", "reasoning_tokens", "output_tokens", "total_tokens", "configured_cost_usd", "estimated_credits"], order_by: "time_day", descending: true, limit: 14 },
    ] }),
  });
  return { leaders: payload.results[1], timeline: payload.results[2] };
}

function liveDetailSections(leaders, timeline) {
  return [
    element("section", { className: "card", style: "margin-top:1rem" }, [
      element("h2", { text: "Recent token bands" }),
      element("p", { className: "result-meta", text: "Daily foundational facts by uncached input, cached input, reasoning, and output." }),
      tokenTimelineChart(timeline.rows),
      tableFor(timeline.rows, false, { label: "Recent token bands", compactTokens: true }),
      element("p", { className: "result-meta", text: pricingCoverageSummary(timeline) }),
    ]),
    element("section", { className: "card", style: "margin-top:1rem" }, [
      element("h2", { text: "Highest-token threads" }),
      element("p", { className: "result-meta", text: pricingCoverageSummary(leaders) }),
      tableFor(leaders.rows, true, {
        label: "Highest-token threads", compactTokens: true, technicalColumns: ["thread"],
        hiddenColumns: ["share_calls", "share_uncached_input_tokens", "share_cached_input_tokens", "share_reasoning_tokens", "share_output_tokens", "share_configured_cost_usd", "share_estimated_credits"],
      }),
    ]),
  ];
}

function renderLivePayload(payload) {
  const { summary, leaders, timeline } = payload;
  workspace.replaceChildren(heading("live"), metrics(summary.rows[0] || {}, summary));
  workspace.append(element("div", { className: "section-grid" }, [
    element("section", { className: "card", "aria-labelledby": "token-mix-title" }, [
      element("h2", { id: "token-mix-title", text: "Four-class token mix" }), tokenBars(summary.rows[0] || {}),
    ]),
    element("section", { className: "card" }, [
      element("h2", { text: "Current committed view" }),
      element("p", { text: "These cards read the existing index. Opening this page never starts or extends a refresh." }),
      element("div", { className: "result-meta", text: `Generation ${summary.generation} · ${formatNumber(summary.rows[0]?.calls)} calls · ${formatNumber(summary.elapsed_ms)} ms` }),
    ]),
  ]));
  if (leaders && timeline) {
    workspace.append(...liveDetailSections(leaders, timeline));
    return;
  }
  const button = element("button", { className: "button secondary", type: "button", text: "Load detailed views" });
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      const details = await requestLiveDetails();
      const complete = { summary, ...details };
      writeLiveCache(complete);
      renderLivePayload(complete);
    } catch (error) {
      button.disabled = false;
      toast(error.message);
    }
  });
  workspace.append(element("section", { className: "card", style: "margin-top:1rem" }, [
    element("h2", { text: "Load detailed views" }),
    element("p", { className: "result-meta", text: "Detailed views are loaded on demand to keep the initial summary fast." }),
    button,
  ]));
}

async function renderLive() {
  workspace.replaceChildren(heading("live"), loadingMetrics());
  if (!state.status?.generation) {
    workspace.append(element("div", { className: "card empty", text: "Build the first local generation with Refresh data. Existing sessions are not read until you ask." }));
    return;
  }
  const cached = readLiveCache();
  if (cached) return renderLivePayload(cached);
  try {
    const payload = { summary: await requestLiveSummary(), leaders: null, timeline: null };
    writeLiveCache(payload);
    renderLivePayload(payload);
  } catch (error) {
    workspace.replaceChildren(heading("live"), errorPanel(error, renderLive));
  }
}

function loadingMetrics() {
  const grid = element("div", { className: "metric-grid" });
  for (let index = 0; index < 4; index += 1) grid.append(element("div", { className: "card metric-card" }, [element("div", { className: "skeleton" })]));
  return grid;
}

function metrics(row, result) {
  const reuse = cacheReuse(row.cached_input_tokens, row.uncached_input_tokens);
  const cost = row.configured_cost_usd;
  const credits = row.estimated_credits;
  const coverage = pricingCoverageSummary(result);
  return element("div", { className: "metric-grid" }, [
    metricCard("Calls", formatNumber(row.calls), "Canonical model calls"),
    metricCard(
      "Total tokens",
      formatNumber(row.total_tokens),
      `${formatNumber(row.uncached_input_tokens)} new · ${formatNumber(row.cached_input_tokens)} cached · ${formatNumber(row.reasoning_tokens)} reasoning · ${formatNumber(row.output_tokens)} output`,
    ),
    metricCard(
      "Cache reuse",
      formatPercent(reuse),
      reuse === null ? "No input-token denominator" : "Share of input served from cache",
    ),
    metricCard(
      "Cost and credits",
      cost === null || cost === undefined ? "Unavailable" : formatCell("configured_cost_usd", cost),
      credits === null || credits === undefined
        ? "No configured credit estimate"
        : `${formatSmallFact(credits)} estimated credits${coverage ? ` · ${coverage}` : ""}`,
    ),
  ]);
}

function metricCard(label, value, detail) {
  return element("section", { className: "card metric-card" }, [
    element("span", { text: label }),
    element("strong", { text: value }),
    element("small", { text: detail }),
  ]);
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

function timePosition(timestamp, minimum, maximum, start, end) {
  if (maximum <= minimum) return (start + end) / 2;
  return start + ((end - start) * (timestamp - minimum) / (maximum - minimum));
}

function appendTimeAxis(
  svg,
  timestamps,
  width,
  height,
  left,
  right,
  mode = "date",
) {
  const minimum = Math.min(...timestamps);
  const maximum = Math.max(...timestamps);
  const showTime = mode === "auto" && maximum - minimum < 2 * 86_400_000;
  const label = (timestamp) => showTime
    ? new Date(timestamp).toLocaleTimeString(
      undefined,
      { hour: "numeric", minute: "2-digit", second: "2-digit" },
    )
    : new Date(timestamp).toLocaleDateString(
      undefined,
      { month: "short", day: "numeric", timeZone: "UTC" },
    );
  svg.append(
    svgElement("text", {
      className: "chart-label",
      x: left,
      y: height - 5,
      text: label(minimum),
    }),
  );
  if (maximum !== minimum) {
    svg.append(
      svgElement("text", {
        className: "chart-label chart-label-end",
        x: width - right,
        y: height - 5,
        text: label(maximum),
      }),
    );
  }
}

function tokenTimelineChart(rows) {
  const observations = rows
    .map((row) => ({ row, timestamp: timestampMillis(row.time_day) }))
    .filter((item) => item.timestamp !== null)
    .sort((left, right) => left.timestamp - right.timestamp);
  if (!observations.length) {
    return element("div", {
      className: "empty",
      text: "No daily token observations are available for this committed generation.",
    });
  }
  const width = 720;
  const height = 240;
  const left = 46;
  const right = 18;
  const top = 18;
  const bottom = 38;
  const timestamps = observations.map((item) => item.timestamp);
  const minimum = Math.min(...timestamps);
  const maximum = Math.max(...timestamps);
  const series = [
    ["total_tokens", "Total", "total"],
    ["uncached_input_tokens", "New input", "new"],
    ["cached_input_tokens", "Cached input", "cached"],
    ["reasoning_tokens", "Reasoning", "reasoning"],
    ["output_tokens", "Output", "output"],
  ];
  const maximumTokens = Math.max(
    1,
    ...observations.map((item) => Number(item.row.total_tokens || 0)),
  );
  const svg = svgElement("svg", {
    className: "allowance-chart token-timeline-chart",
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-label": `Daily token usage over time, ${observations.length} observations`,
  });
  for (const percent of [0, 25, 50, 75, 100]) {
    const y = height - bottom - ((height - top - bottom) * percent / 100);
    svg.append(svgElement("line", {
      className: "chart-grid",
      x1: left,
      x2: width - right,
      y1: y,
      y2: y,
    }));
  }
  svg.append(
    svgElement("text", {
      className: "chart-label",
      x: 2,
      y: top + 4,
      text: formatNumber(maximumTokens),
    }),
    svgElement("text", {
      className: "chart-label",
      x: 2,
      y: height - bottom + 4,
      text: "0 tokens",
    }),
  );
  for (const [measure, label, kind] of series) {
    const points = observations.map((item) => {
      const x = timePosition(item.timestamp, minimum, maximum, left, width - right);
      const y = height - bottom - (
        (height - top - bottom) * Number(item.row[measure] || 0) / maximumTokens
      );
      return `${x},${y}`;
    }).join(" ");
    svg.append(svgElement("polyline", {
      className: `chart-line ${kind}`,
      points,
      fill: "none",
      "aria-label": label,
    }));
  }
  appendTimeAxis(svg, timestamps, width, height, left, right);
  return element("div", { className: "chart-with-legend" }, [
    svg,
    element("div", { className: "chart-legend" }, series.map(([, label, kind]) =>
      element("span", { className: `chart-key ${kind}`, text: label })
    )),
  ]);
}

function allowanceChart(rows) {
  const observations = [...rows]
    .filter((row) => Number.isFinite(Number(row.used_percent)))
    .map((row) => ({ row, timestamp: timestampMillis(row.observed_at) }))
    .filter((item) => item.timestamp !== null)
    .sort((left, right) => left.timestamp - right.timestamp);
  if (!observations.length) {
    return element("div", {
      className: "empty",
      text: "No allowance observations are available for this committed generation.",
    });
  }
  const width = 720;
  const height = 240;
  const left = 32;
  const right = 18;
  const top = 18;
  const bottom = 38;
  const timestamps = observations.map((item) => item.timestamp);
  const minimum = Math.min(...timestamps);
  const maximum = Math.max(...timestamps);
  const points = observations.map((item) => {
    const x = timePosition(item.timestamp, minimum, maximum, left, width - right);
    const y = height - bottom - (
      (height - top - bottom) * Math.max(0, Math.min(100, Number(item.row.used_percent))) / 100
    );
    return `${x},${y}`;
  }).join(" ");
  const svg = svgElement("svg", {
    className: "allowance-chart",
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-label": `Allowance usage over time, ${observations.length} observations`,
  });
  for (const percent of [0, 25, 50, 75, 100]) {
    const y = height - bottom - ((height - top - bottom) * percent / 100);
    svg.append(
      svgElement("line", {
        className: "chart-grid",
        x1: left,
        x2: width - right,
        y1: y,
        y2: y,
      }),
      svgElement("text", {
        className: "chart-label",
        x: 2,
        y: y + 4,
        text: `${percent}%`,
      }),
    );
  }
  const resetTimestamps = [...new Set(observations
    .map((item) => timestampMillis(item.row.resets_at))
    .filter((timestamp) => (
      timestamp !== null && timestamp >= minimum && timestamp <= maximum
    )))];
  for (const timestamp of resetTimestamps) {
    const x = timePosition(timestamp, minimum, maximum, left, width - right);
    svg.append(
      svgElement("line", {
        className: "chart-reset",
        x1: x,
        x2: x,
        y1: top,
        y2: height - bottom,
      }),
      svgElement("text", {
        className: "chart-label",
        x: x + 4,
        y: top + 10,
        text: "reset",
      }),
    );
  }
  svg.append(svgElement("polyline", {
    className: "chart-line",
    points,
    fill: "none",
  }));
  observations.forEach((item, index) => {
    const [cx, cy] = points.split(" ")[index].split(",");
    svg.append(svgElement("circle", {
      className: "chart-point",
      cx,
      cy,
      r: 4,
    }, [
      svgElement("title", {
        text: `${formatCell("observed_at", item.row.observed_at)} · ${formatNumber(item.row.used_percent)}% used`,
      }),
    ]));
  });
  appendTimeAxis(svg, timestamps, width, height, left, right, "auto");
  return svg;
}

async function renderExplore() {
  workspace.replaceChildren(heading("explore"));
  let guidance;
  let initialResults;
  try {
    const initial = await request("/query", {
      method: "POST",
      body: JSON.stringify({
        requests: EXPLORE_DEFAULT_REQUESTS,
        include_guidance: true,
      }),
    });
    guidance = initial.guidance;
    initialResults = initial.results;
  } catch (error) {
    workspace.append(errorPanel(error, renderExplore));
    return;
  }
  const datasetNames = Object.keys(guidance.datasets).filter(
    (name) => guidance.datasets[name].default_request,
  );
  const templateNames = ["custom", ...Object.keys(guidance.templates)];
  const form = element("form", { className: "card form-grid", id: "query-form", "aria-label": "Custom bounded query" });
  const templateSelect = selectField(
    "Guided template",
    "guided-template",
    templateNames,
    "concentration",
  );
  const datasetSelect = selectField("Dataset", "dataset", datasetNames, "calls");
  const operationSelect = selectField(
    "Operation",
    "operation",
    guidance.datasets.calls.operations,
    "share",
  );
  const dimensionInput = inputField("Group by", "dimensions", "thread");
  const measureInput = inputField("Measures", "measures", "calls,total_tokens");
  const limitInput = inputField("Row limit", "limit", "25", "number");
  const now = new Date();
  const currentStart = new Date(now.getTime() - (7 * 86_400_000));
  const previousStart = new Date(currentStart.getTime() - (7 * 86_400_000));
  const previousStartInput = inputField(
    "Previous start",
    "previous-start",
    dateTimeValue(previousStart),
    "datetime-local",
  );
  const previousEndInput = inputField(
    "Previous end",
    "previous-end",
    dateTimeValue(currentStart),
    "datetime-local",
  );
  const currentStartInput = inputField(
    "Current start",
    "current-start",
    dateTimeValue(currentStart),
    "datetime-local",
  );
  const currentEndInput = inputField(
    "Current end",
    "current-end",
    dateTimeValue(now),
    "datetime-local",
  );
  form.append(
    templateSelect.wrapper,
    datasetSelect.wrapper,
    operationSelect.wrapper,
    dimensionInput.wrapper,
    measureInput.wrapper,
    limitInput.wrapper,
    previousStartInput.wrapper,
    previousEndInput.wrapper,
    currentStartInput.wrapper,
    currentEndInput.wrapper,
  );
  const saveButton = element("button", { className: "button ghost", type: "button", text: "Save locally" });
  const loadButton = element("button", {
    className: "button ghost",
    type: "button",
    text: "Load saved",
    ...(localStorage.getItem("kernel-saved-query") ? {} : { disabled: "" }),
  });
  const copyButton = element("button", {
    className: "button ghost",
    type: "button",
    text: "Copy typed request",
  });
  form.append(element("div", { className: "form-actions" }, [
    element("button", { className: "button primary", type: "submit", text: "Run bounded query" }),
    copyButton,
    saveButton,
    loadButton,
  ]));
  form.append(element("p", {
    className: "form-note",
    text: `${datasetNames.length} datasets · up to ${guidance.limits.max_batch_queries} requests · ${guidance.limits.max_rows_per_query} rows/request · ${formatNumber(guidance.limits.max_response_bytes)} bytes maximum`,
  }));
  form.append(element("p", {
    className: "form-note",
    text: "Context composition: Observed UTF-8 bytes and event counts are exact. Category token counts are optional tokenizer estimates with explicit coverage; they are not exact billed input-token shares.",
  }));
  const output = element("section", { className: "card", style: "margin-top:1rem" }, [
    queryResultPanel(initialResults[0], "Top threads"),
    queryResultPanel(initialResults[1], "Recent calls"),
  ]);
  workspace.append(output, form);

  let applyingTemplate = false;
  const comparisonParameters = () => {
    const controls = {
      previous_start: previousStartInput.control,
      previous_end: previousEndInput.control,
      current_start: currentStartInput.control,
      current_end: currentEndInput.control,
    };
    return Object.fromEntries(
      Object.entries(controls).map(([name, control]) => {
        if (!control.value) {
          throw new Error("All comparison dates are required.");
        }
        const parsed = new Date(control.value);
        if (Number.isNaN(parsed.getTime())) {
          throw new Error("Comparison dates must be valid timestamps.");
        }
        return [name, parsed.toISOString()];
      }),
    );
  };
  const selectedTemplateRequests = () => {
    const template = guidance.templates[templateSelect.control.value];
    const parameters = template.parameters?.length
      ? comparisonParameters()
      : {};
    return materializeTemplate(template, parameters);
  };
  const applyRequest = (requestSpec) => {
    applyingTemplate = true;
    datasetSelect.control.value = requestSpec.dataset;
    replaceOptions(
      operationSelect.control,
      guidance.datasets[requestSpec.dataset].operations,
      requestSpec.operation,
    );
    dimensionInput.control.value = requestSpec.dimensions.join(",");
    measureInput.control.value = requestSpec.measures.join(",");
    limitInput.control.value = String(requestSpec.limit);
    applyingTemplate = false;
  };
  const typedRequests = () => {
    if (templateSelect.control.value !== "custom") {
      return selectedTemplateRequests();
    }
    const requestSpec = {
      dataset: datasetSelect.control.value,
      operation: operationSelect.control.value,
      dimensions: commaSeparated(dimensionInput.control.value),
      measures: commaSeparated(measureInput.control.value),
      limit: Number(limitInput.control.value),
      descending: true,
      ...(operationSelect.control.value === "comparison"
        ? { comparison: comparisonParameters() }
        : {}),
    };
    return [requestSpec];
  };
  templateSelect.control.addEventListener("change", () => {
    if (templateSelect.control.value === "custom") return;
    try {
      applyRequest(selectedTemplateRequests()[0]);
    } catch (error) {
      toast(error.message);
    }
  });
  datasetSelect.control.addEventListener("change", () => {
    applyRequest(
      guidance.datasets[datasetSelect.control.value].default_request,
    );
  });
  for (const control of [
    datasetSelect.control,
    operationSelect.control,
    dimensionInput.control,
    measureInput.control,
    limitInput.control,
  ]) {
    control.addEventListener("input", () => {
      if (!applyingTemplate) templateSelect.control.value = "custom";
    });
  }
  const currentSpec = () => ({
    template: templateSelect.control.value,
    dataset: datasetSelect.control.value,
    operation: operationSelect.control.value,
    dimensions: dimensionInput.control.value,
    measures: measureInput.control.value,
    limit: limitInput.control.value,
    previousStart: previousStartInput.control.value,
    previousEnd: previousEndInput.control.value,
    currentStart: currentStartInput.control.value,
    currentEnd: currentEndInput.control.value,
  });
  saveButton.addEventListener("click", () => {
    localStorage.setItem("kernel-saved-query", JSON.stringify(currentSpec()));
    loadButton.disabled = false;
    toast("Query spec saved in this browser.");
  });
  loadButton.addEventListener("click", () => {
    const saved = JSON.parse(localStorage.getItem("kernel-saved-query") || "null");
    if (!saved) return;
    templateSelect.control.value = saved.template || "custom";
    datasetSelect.control.value = saved.dataset;
    replaceOptions(
      operationSelect.control,
      guidance.datasets[saved.dataset].operations,
      saved.operation,
    );
    operationSelect.control.value = saved.operation;
    dimensionInput.control.value = saved.dimensions;
    measureInput.control.value = saved.measures;
    limitInput.control.value = saved.limit;
    previousStartInput.control.value = saved.previousStart || previousStartInput.control.value;
    previousEndInput.control.value = saved.previousEnd || previousEndInput.control.value;
    currentStartInput.control.value = saved.currentStart || currentStartInput.control.value;
    currentEndInput.control.value = saved.currentEnd || currentEndInput.control.value;
    toast("Saved query loaded.");
  });
  copyButton.addEventListener("click", async () => {
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard access is unavailable.");
      }
      await navigator.clipboard.writeText(
        JSON.stringify({ requests: typedRequests() }, null, 2),
      );
      toast("Typed query request copied.");
    } catch (error) {
      toast(`Unable to copy typed request: ${error.message}`);
    }
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    output.replaceChildren(element("div", { className: "empty", text: "Reading committed facts…" }));
    try {
      const response = await request("/query", {
        method: "POST",
        body: JSON.stringify({ requests: typedRequests() }),
      });
      const generations = new Set(
        response.results.map((result) => result.generation),
      );
      if (generations.size > 1) {
        throw new Error("Batched query results crossed committed generations.");
      }
      output.replaceChildren(
        ...response.results.map((result) => queryResultPanel(result)),
      );
    } catch (error) {
      output.replaceChildren(errorPanel(error, () => form.requestSubmit()));
    }
  });
  applyRequest(selectedTemplateRequests()[0]);
}

function queryResultPanel(result, title = null) {
  const firstRow = result.rows[0] || {};
  const pricingCoverage = pricingCoverageSummary(result);
  const hiddenColumns = Object.keys(firstRow).filter(
    (column) => column.startsWith("share_") && column !== "share_total_tokens",
  );
  const technicalColumns = ["call", "thread", "turn", "tool_call"].filter(
    (column) => Object.hasOwn(firstRow, column),
  );
  return element("section", { className: "query-result" }, [
    element("h3", { text: title || `${result.dataset} · ${result.operation}` }),
    element("div", {
      className: "result-meta",
      text: `Generation ${result.generation} · ${result.returned_count} of ${result.matched_count} rows · ${formatNumber(result.elapsed_ms)} ms · ${result.grade}${pricingCoverage ? ` · ${pricingCoverage}` : ""}`,
    }),
    tableFor(result.rows, true, {
      label: title || `${result.dataset} ${result.operation}`,
      compactTokens: true,
      hiddenColumns,
      technicalColumns,
    }),
  ]);
}

function dateTimeValue(value) {
  const local = new Date(
    value.getTime() - (value.getTimezoneOffset() * 60_000),
  );
  return local.toISOString().slice(0, 16);
}

function selectField(labelText, name, options, selected) {
  const control = element("select", { name, id: name });
  options.forEach((option) => control.append(element("option", { value: option, text: option, ...(option === selected ? { selected: "" } : {}) })));
  return { control, wrapper: element("label", { for: name }, [document.createTextNode(t(labelText)), control]) };
}

function inputField(labelText, name, value, type = "text") {
  const control = element("input", { name, id: name, value, type });
  return { control, wrapper: element("label", { for: name }, [document.createTextNode(t(labelText)), control]) };
}

function replaceOptions(control, options, selected) {
  control.replaceChildren();
  options.forEach((option) => control.append(element("option", {
    value: option,
    text: option,
    ...(option === selected ? { selected: "" } : {}),
  })));
}

async function evidenceRowsWithCost(rows, generation) {
  const callIds = [...new Set(rows.flatMap((row) => {
    const selector = typeof row.selector === "string" ? row.selector : "";
    return selector.startsWith("call:") ? [selector.slice(5)] : [];
  }))];
  if (!callIds.length) return { rows, pricingCoverage: "" };
  const requests = [];
  for (let offset = 0; offset < callIds.length; offset += 25) {
    const chunk = callIds.slice(offset, offset + 25);
    requests.push({
      dataset: "calls",
      operation: "rows",
      dimensions: ["call"],
      measures: ["configured_cost_usd", "estimated_credits"],
      filters: [{ field: "call", operator: "in", value: chunk }],
      limit: chunk.length,
    });
  }
  const response = await request("/query", {
    method: "POST",
    body: JSON.stringify({ requests }),
  });
  if (response.results.some((result) => result.generation !== generation)) {
    throw new Error(
      "A newer committed generation arrived while evidence was loading. Reload this exact evidence view.",
    );
  }
  const costs = new Map(
    response.results.flatMap((result) => result.rows).map(
      (row) => [row.call, row],
    ),
  );
  return {
    pricingCoverage: pricingCoverageSummary(response.results),
    rows: rows.map((row) => {
    const selector = typeof row.selector === "string" ? row.selector : "";
    const cost = selector.startsWith("call:") ? costs.get(selector.slice(5)) : null;
    return cost ? {
      ...row,
      configured_cost_usd: cost.configured_cost_usd,
      estimated_credits: cost.estimated_credits,
    } : row;
    }),
  };
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
      const enriched = await evidenceRowsWithCost(result.rows, result.generation);
      output.replaceChildren(
        element("div", {
          className: "result-meta",
          text: `Generation ${result.generation} · ${result.returned_count} of ${result.matched_count} evidence rows · ${result.grade}${enriched.pricingCoverage ? ` · ${enriched.pricingCoverage}` : ""}`,
        }),
        tableFor(enriched.rows, false, {
          label: "Evidence",
          compactTokens: true,
          technicalColumns: [
            "event_id",
            "selector",
            "call",
            "thread",
            "turn",
            "tool_call",
            "allowance",
            "allowance_observation_id",
            "generation",
            "category",
          ],
        }),
        element("details", { className: "evidence-provenance" }, [
          element("summary", { text: "Evidence identity and provenance" }),
          definitionList({
            Selector: result.selector,
            Generation: result.generation,
            Grade: result.grade,
          }),
        ]),
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
        element("h2", { text: "Usage over time" }),
        allowanceChart(rows),
        element("div", {
          className: "result-meta",
          text: `${result.returned_count} observations · through ${formatCell("observed_at", result.observed_through)} · ${result.coverage?.pricing?.configured ? "rate card configured" : "rate card unavailable"} · ${formatPercent((result.coverage?.pricing?.coverage_percent || 0) / 100)} rated token coverage`,
        }),
      ]),
      element("section", { className: "card" }, [
        element("h2", { text: "Observed usage and local impact" }),
        element("div", { className: "result-meta", text: "Time comes first. Drain and credits-per-usage ratios appear only for adjacent observations inside one logical reset window." }),
        tableFor(rows, true, {
          label: "Observed usage and local impact",
          columnOrder: [
            "observed_at",
            "observed_drain_percent",
            "local_total_tokens",
            "estimated_credits",
            "estimated_credits_per_percentage_point",
            "local_tokens_per_percentage_point",
            "resets_at",
            "window",
            "used_percent",
            "remaining_percent",
            "estimated_cost_usd",
          ],
          technicalColumns: [
            "allowance_observation_id",
            "grade",
            "caveats",
            "local_calls",
            "local_turns",
            "local_calls_per_percentage_point",
            "local_turns_per_percentage_point",
            "percentage_points_per_hour",
            "pricing_coverage_percent",
            "used_percent",
            "remaining_percent",
            "estimated_cost_usd",
          ],
        }),
      ]),
      element("section", { className: "card" }, [
        element("h2", { text: "Coverage and caveats" }),
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
  const language = selectField("Language", "language", ["en", "zh-CN"], state.language);
  language.control.querySelector('option[value="en"]').textContent = t("English");
  language.control.querySelector('option[value="zh-CN"]').textContent = t("Simplified Chinese");
  language.control.addEventListener("change", () => {
    state.language = language.control.value;
    localStorage.setItem(LANGUAGE_STORAGE_KEY, state.language);
    applyLanguage();
    renderSettings();
  });
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
      language.wrapper,
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
    if (checkbox.checked) state.snapshotRecoveryAttempted = false;
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
    state.snapshotRecoveryAttempted = false;
    await refreshStatus();
    await renderCurrentRoute();
    toast(`Generation ${payload.generation} is ready.`);
  });
  source.addEventListener("snapshot_required", async () => {
    if (state.eventSource !== source) return;
    source.close();
    state.eventSource = null;
    await refreshStatus();
    if (state.snapshotRecoveryAttempted) {
      toast("Live updates paused after a repeated snapshot gap; refresh the page after the next committed generation.");
      return;
    }
    state.snapshotRecoveryAttempted = true;
    await renderCurrentRoute();
    if (!state.eventSource) connectLive();
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
  applyLanguage();
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
