const $ = (id) => document.getElementById(id);

// The page has no model menu. Calls go out on Opus, and Use recommended model moves them.
const SEND_MODEL = "claude-opus-5-5";

const STAMPS = {
  OK: "ok",
  Overkill: "overkill",
  Refused: "refused",
  Upshifted: "refused",
  "Swap failed": "refused",
  Downshifted: "downshifted",
  Roast: "roast",
  Dropped: "error",
  "Blocked by budget": "blocked",
  "Demo limit reached": "blocked",
  "Loop stopped": "stopped",
  Error: "error",
};

const ACCESS_NAMES = { self: "Self", team: "Team", all: "All" };

// The token is a per-viewer convenience. Everything it unlocks lives on the server.
const TOKEN_KEY = "cavedawg.token";

let newestSeen = 0;
let modelsLoaded = false;
let modelLabels = {};
let recommendedModel = null;
let levels = [];
let levelEditing = false;
let viewer = null;
let roastRuns = [];
let settingsVersion = 0;
let pollTimer = null;

function storedToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

let token = storedToken();

function rememberToken(value) {
  token = value;
  try {
    if (value) localStorage.setItem(TOKEN_KEY, value);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Signing in still works until the page reloads.
  }
}

class SignedOut extends Error {}

function money(value, places = 4) {
  const amount = Number(value || 0);
  // Tiny calls would otherwise display as $0.0000.
  if (amount > 0 && amount < 0.0001) return `$${amount.toFixed(6)}`;
  return `$${amount.toFixed(places)}`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "content-type": "application/json", "x-cavedawg-token": token },
  });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) {
    signOut(data.error);
    throw new SignedOut(data.error || "Sign in to continue.");
  }
  if (!response.ok) throw new Error(data.error || "The request failed. Try again.");
  return data;
}

function setStatus(element, text, bad = false) {
  element.textContent = text;
  element.classList.toggle("bad", bad);
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function cell(text, className) {
  const td = document.createElement("td");
  td.textContent = text;
  if (className) td.className = className;
  return td;
}

// ---- Sign-in

let demoMode = false;
let demoAccess = null;

function showSignIn(message = "") {
  setStatus($("signin-error"), message, Boolean(message));
  if (!$("signin-dialog").open) $("signin-dialog").showModal();
  $("signin-name").focus();
}

function setDemoMode(on) {
  demoMode = on;
  $("signin-title").textContent = on ? "Create a demo login" : "Sign in to CaveDawg";
  $("signin-hint").textContent = on
    ? "Choose a username, a password of 8 or more characters, your team and your access. You also get a token for Claude Code."
    : "CaveDawg shows what your team's AI calls cost and stops the waste.";
  $("demo-fields").hidden = !on;
  if (on) {
    $("signin-team").value = "";
    $("signin-access").value = demoAccess ?? "self";
  }
  $("signin-password").autocomplete = on ? "new-password" : "current-password";
  $("signin-submit").textContent = on ? "Create login and token" : "Sign in";
  $("demo-toggle").textContent = on ? "Back to sign in" : "Demo, create new token";
  $("token-signin").hidden = on;
  setStatus($("signin-error"), "");
  $("signin-name").focus();
}

async function loadSignInOptions() {
  try {
    const options = await (await fetch("/api/signin-options")).json();
    demoAccess = options.demo_access;
    $("demo-toggle").hidden = !options.demo;
  } catch {
    $("demo-toggle").hidden = true;
  }
}

async function postJson(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "That didn't work. Try again.");
  return data;
}

function signOut(message = "") {
  if (token && viewer) {
    // Ends a password session on the server. A pasted token simply stops being remembered.
    fetch("/api/logout", { method: "POST", headers: { "x-cavedawg-token": token } }).catch(() => {});
  }
  rememberToken("");
  viewer = null;
  document.body.classList.remove("can-manage");
  $("who").textContent = "";
  $("sign-out").hidden = true;
  $("users-link").hidden = true;
  $("simulated-on").hidden = true;
  $("simulated-banner").hidden = true;
  clearInterval(pollTimer);
  pollTimer = null;
  showSignIn(message && message !== "Sign in to CaveDawg." ? message : "");
}

function applyViewer(me) {
  viewer = me;
  document.body.classList.toggle("can-manage", me.can_manage);
  const team = me.team ? `, team ${me.team}` : "";
  $("who").textContent = `Signed in as ${me.name}${team}, ${ACCESS_NAMES[me.access]} access`;
  $("sign-out").hidden = false;
  $("users-link").hidden = false;
  // Everyone sees the routing controls. Only all-access users can change them.
  $("level").disabled = !me.can_manage;
  $("use-recommended").disabled = !me.can_manage;
}

async function start() {
  if (!token) {
    showSignIn();
    return;
  }
  try {
    applyViewer(await api("/api/me"));
  } catch {
    return;
  }
  if ($("signin-dialog").open) $("signin-dialog").close();
  await refreshQuietly();
  showView();
  clearInterval(pollTimer);
  pollTimer = setInterval(refreshQuietly, 2000);
}

$("signin-dialog").addEventListener("cancel", (event) => event.preventDefault());

$("signin-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = $("signin-name").value.trim();
  const password = $("signin-password").value;
  $("signin-submit").disabled = true;
  setStatus($("signin-error"), demoMode ? "Creating your login" : "Signing in");
  try {
    if (demoMode) {
      const created = await postJson("/api/signup", {
        name,
        password,
        team: $("signin-team").value.trim(),
        access: $("signin-access").value,
      });
      rememberToken(created.session);
      $("signin-dialog").close();
      $("welcome-token").value = created.token;
      $("welcome-settings").value = JSON.stringify(created.claude_code_settings, null, 2);
      $("welcome-dialog").showModal();
    } else {
      rememberToken((await postJson("/api/login", { name, password })).session);
      await start();
    }
    $("signin-password").value = "";
    setDemoMode(false);
  } catch (error) {
    setStatus($("signin-error"), error.message, true);
  } finally {
    $("signin-submit").disabled = false;
  }
});

$("demo-toggle").addEventListener("click", () => setDemoMode(!demoMode));

$("token-submit").addEventListener("click", async () => {
  rememberToken($("signin-token").value.trim());
  $("signin-token").value = "";
  setStatus($("signin-error"), "Checking token");
  await start();
  if (!viewer) setStatus($("signin-error"), "That token didn't work. Check it and try again.", true);
});

$("welcome-dialog").addEventListener("cancel", (event) => event.preventDefault());
$("welcome-continue").addEventListener("click", async () => {
  $("welcome-dialog").close();
  $("welcome-token").value = "";
  await start();
});
$("welcome-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("welcome-token").value);
    $("welcome-copy").textContent = "Copied";
  } catch {
    $("welcome-token").select();
  }
});

$("sign-out").addEventListener("click", () => signOut());

// ---- Live calls

function roastCell(call) {
  const td = cell("", "roast-cell");
  const run = call.roast && roastRuns.find((item) => item.id === call.roast.id);
  if (run?.roasted) {
    const button = element("button", "roast-button scored", "View roast");
    button.type = "button";
    button.title = "Show this call's roast";
    button.addEventListener("click", () => showRoast(run));
    td.append(button);
  } else if (call.roast || call.roast_call_id) {
    const button = element("button", "roast-button", "Roast");
    button.type = "button";
    button.title = "Have Haiku 5.5 read this call's prompt for wasted tokens";
    button.addEventListener("click", () =>
      call.roast ? roastRun(call.roast.id, button) : roastCall(call.roast_call_id, button, call.prompt),
    );
    td.append(button);
  }
  return td;
}

function renderCalls(rows) {
  const body = $("calls");
  body.replaceChildren(
    ...rows.map((call) => {
      const row = document.createElement("tr");
      if (call.id > newestSeen) row.className = "new";
      const time = new Date(call.ts).toLocaleTimeString([], {
        hour: "numeric",
        minute: "2-digit",
      });
      const recommended = cell(call.ideal_label || "Not rated");
      if (call.decided_by) recommended.append(element("span", "row-note", `Judged by ${call.decided_by}`));
      const results = cell("", "status");
      results.title = call.prompt || "";
      results.append(element("span", `stamp ${STAMPS[call.status] || "ok"}`, call.status));
      if (["Error", "Dropped", "Swap failed"].includes(call.status)) {
        results.append(element("span", "row-note", call.reason));
      }
      const tokens = call.tokens ? `${call.tokens.toLocaleString()} tokens` : "No tokens";
      const calls = call.calls > 1 ? ` · ${call.calls} calls` : "";
      results.append(
        element("span", "row-note", `${call.cost_usd ? money(call.cost_usd) : "$0"} · ${tokens}${calls}`),
      );
      if (call.simulated) results.append(element("span", "row-note sim", "Simulated"));
      row.append(cell(time), cell(call.developer), cell(call.used_label), recommended, results, roastCell(call));
      return row;
    }),
  );
  newestSeen = rows.reduce((max, call) => Math.max(max, call.id), newestSeen);
  $("empty").hidden = rows.length > 0;
}

function duration(seconds) {
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

// ---- Developer leaderboard. Compact: team summary and the top two. Expanded: every column,
// sortable by its header and filterable by the box under it.

// Efficiency is the share of rated spend that was not above each prompt's ideal model.
function efficiency(entry) {
  return entry.prompts ? Math.max(0, 100 - entry.overuse_percent) : null;
}

function rating(entry) {
  const value = efficiency(entry);
  if (value === null) return null;
  if (value >= 90) return "A";
  if (value >= 75) return "B";
  if (value >= 50) return "C";
  return "D";
}

const BOARD_COLUMNS = [
  { key: "rank", label: "Rank", num: true, value: (r) => r.rank, show: (r) => r.rank ?? "Unranked" },
  { key: "developer", label: "Developer", value: (r) => r.developer },
  { key: "rating", label: "Rating", value: rating, show: (r) => rating(r) ?? "–" },
  {
    key: "efficiency", label: "Efficiency", num: true, value: efficiency,
    show: (r) => (efficiency(r) === null ? "–" : `${efficiency(r).toFixed(1)}%`),
  },
  { key: "prompts", label: "Prompts", num: true, value: (r) => r.prompts },
  { key: "tokens", label: "Tokens", num: true, value: (r) => r.tokens, show: (r) => r.tokens.toLocaleString() },
  { key: "cost", label: "Cost", num: true, value: (r) => r.cost_usd, show: (r) => money(r.cost_usd) },
  { key: "time", label: "Dev time (min)", num: true, value: (r) => r.dev_seconds / 60 },
  {
    key: "overuse", label: "Overuse", num: true, value: (r) => r.overuse_percent,
    show: (r) => `${r.overuse_percent.toFixed(1)}%`,
  },
  { key: "overspend", label: "Overspend", num: true, value: (r) => r.overspend_usd, show: (r) => money(r.overspend_usd) },
];

let boardRows = [];
let boardOrder = { key: "rank", dir: 1 };
const boardFilters = {};

// Text columns match any part of the text. Number columns take "5" (at least 5), or >, <, >=,
// <=, = before the number. A $ or % is ignored.
function numberFilter(text) {
  const match = text.trim().match(/^(<=|>=|<|>|=)?\s*\$?(-?\d*\.?\d+)%?$/);
  if (!match) return null;
  const [, op = ">=", raw] = match;
  const target = Number(raw);
  return (value) => {
    if (value === null || value === undefined) return false;
    if (op === "<") return value < target;
    if (op === ">") return value > target;
    if (op === "<=") return value <= target;
    if (op === "=") return Math.abs(value - target) < 1e-9;
    return value >= target;
  };
}

function boardMatches(entry) {
  return BOARD_COLUMNS.every((column) => {
    const text = (boardFilters[column.key] || "").trim();
    if (!text) return true;
    if (column.num) {
      const test = numberFilter(text);
      return test ? test(column.value(entry)) : true; // an unreadable filter is marked and ignored
    }
    const shown = column.show ? column.show(entry) : column.value(entry);
    return String(shown ?? "").toLowerCase().includes(text.toLowerCase());
  });
}

function compareBy(column, dir) {
  return (a, b) => {
    const x = column.value(a);
    const y = column.value(b);
    // Empty values sort last whichever way the column runs.
    const xEmpty = x === null || x === undefined;
    const yEmpty = y === null || y === undefined;
    if (xEmpty || yEmpty) return xEmpty === yEmpty ? a.developer.localeCompare(b.developer) : xEmpty ? 1 : -1;
    const order = typeof x === "string" ? x.localeCompare(y) : x - y;
    return order * dir || a.developer.localeCompare(b.developer);
  };
}

function buildBoardHead() {
  $("board-head-row").replaceChildren(
    ...BOARD_COLUMNS.map((column) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.dataset.key = column.key;
      if (column.num) th.className = "num";
      const button = element("button", "sort", column.label);
      button.type = "button";
      button.addEventListener("click", () => {
        // A first click puts the best or biggest on top; a second click flips it.
        boardOrder = boardOrder.key === column.key
          ? { key: column.key, dir: -boardOrder.dir }
          : { key: column.key, dir: column.num && column.key !== "rank" ? -1 : 1 };
        renderBoardTable();
      });
      th.append(button);
      return th;
    }),
  );
  $("board-filter-row").replaceChildren(
    ...BOARD_COLUMNS.map((column) => {
      const td = document.createElement("td");
      const input = element("input");
      input.type = "text";
      input.placeholder = column.num ? "e.g. >5" : "Filter";
      input.setAttribute("aria-label", `Filter ${column.label}`);
      input.addEventListener("input", () => {
        boardFilters[column.key] = input.value;
        const bad = Boolean(column.num && input.value.trim() && !numberFilter(input.value));
        input.setAttribute("aria-invalid", String(bad));
        renderBoardTable();
      });
      td.append(input);
      return td;
    }),
  );
}

function renderBoardTable() {
  const column = BOARD_COLUMNS.find((c) => c.key === boardOrder.key);
  for (const th of $("board-head-row").children) {
    const active = th.dataset.key === boardOrder.key;
    th.setAttribute("aria-sort", active ? (boardOrder.dir > 0 ? "ascending" : "descending") : "none");
    th.firstChild.dataset.arrow = active ? (boardOrder.dir > 0 ? "▲" : "▼") : "";
  }
  const shown = boardRows.filter(boardMatches).sort(compareBy(column, boardOrder.dir));
  $("board-rows").replaceChildren(
    ...shown.map((entry) => {
      const row = document.createElement("tr");
      for (const c of BOARD_COLUMNS) {
        if (c.key === "time") {
          const time = cell(duration(entry.dev_seconds), "num");
          time.append(element("span", "row-note", entry.dev_time_source));
          row.append(time);
        } else {
          row.append(cell(c.show ? c.show(entry) : c.value(entry), c.num ? "num" : ""));
        }
      }
      return row;
    }),
  );
  $("board-nomatch").hidden = !boardRows.length || shown.length > 0;
}

const COMPACT_ORDER = {
  efficiency: { column: "efficiency", note: "most efficient first" },
  cost: { column: "cost", note: "highest spend first" },
  prompts: { column: "prompts", note: "most prompts first" },
};

function renderBoardCompact() {
  const order = COMPACT_ORDER[$("board-sort").value];
  const column = BOARD_COLUMNS.find((c) => c.key === order.column);
  const active = boardRows.filter((r) => r.prompts || r.cost_usd);
  const top = [...active].sort(compareBy(column, -1)).slice(0, 2);
  $("board-top").replaceChildren(
    ...top.map((entry, index) => {
      const item = element("li", "board-card");
      const grade = rating(entry);
      const eff = efficiency(entry);
      item.append(
        element("span", "board-place", `#${index + 1}`),
        element("span", "board-name", entry.developer),
        element("span", `board-grade grade-${(grade || "none").toLowerCase()}`, grade ?? "–"),
        element("span", "board-stats",
          `${eff === null ? "No rated prompts" : `${eff.toFixed(0)}% efficient`} · ${money(entry.cost_usd, 2)}`),
      );
      item.title = `Rating ${grade ?? "none"}: A is 90% efficient or better, B 75%, C 50%, D below.`;
      return item;
    }),
  );
  const cost = active.reduce((sum, r) => sum + r.cost_usd, 0);
  const rated = active.filter((r) => r.prompts);
  const ratedCost = rated.reduce((sum, r) => sum + r.cost_usd, 0);
  // Rough: each developer's efficiency weighted by what they spent.
  const teamEfficiency = ratedCost
    ? rated.reduce((sum, r) => sum + efficiency(r) * r.cost_usd, 0) / ratedCost
    : null;
  $("board-summary").textContent = active.length
    ? `Team: about ${money(cost, 2)} across ${active.length} developer${active.length === 1 ? "" : "s"}` +
      (teamEfficiency === null ? "" : `, ${teamEfficiency.toFixed(0)}% efficient`) +
      `. Ranked ${order.note}.`
    : "";
}

function renderBoard({ rows }) {
  boardRows = rows;
  $("board-empty").hidden = rows.length > 0;
  renderBoardCompact();
  if (!$("board-full").hidden) renderBoardTable();
}

buildBoardHead();
$("board-sort").addEventListener("change", renderBoardCompact);
$("board-toggle").addEventListener("click", () => {
  const open = $("board-full").hidden;
  $("board-full").hidden = !open;
  $("board-toggle").textContent = open ? "Collapse" : "Expand";
  $("board-toggle").setAttribute("aria-expanded", String(open));
  if (open) renderBoardTable();
});

function renderDevelopers(developers) {
  const wanted = [
    ["", "Unattributed"],
    ...developers.map(({ id, name }) => [String(id), name]),
  ];
  const known = [...$("developer").options].map((o) => `${o.value}:${o.text}`).join();
  if (known === wanted.map(([id, name]) => `${id}:${name}`).join()) return;
  const selected = $("developer").options.length ? $("developer").value : String(viewer?.id ?? "");
  $("developer").replaceChildren(...wanted.map(([id, name]) => new Option(name, id)));
  $("developer").value = selected;
}

function renderLevel(value) {
  const current = levels.find(({ level }) => level === value);
  if (!current) return;
  $("level").setAttribute("aria-valuetext", current.name);
  $("level").title = current.summary;
  for (const tick of $("level-ticks").children) {
    tick.classList.toggle("current", tick.textContent === current.name);
  }
}

// The server's Python build when this page loaded. See _build_stamp in app/main.py.
const PAGE_BUILD = Number(document.querySelector('meta[name="cavedawg-build"]')?.content || 0);

function renderBuild(serverBuild) {
  // A server from before build stamps sends none, and it also serves the page without one.
  const serverOld = !serverBuild || (PAGE_BUILD && PAGE_BUILD > serverBuild);
  if (!serverOld && (!PAGE_BUILD || serverBuild === PAGE_BUILD)) {
    $("stale-banner").hidden = true;
    return;
  }
  $("stale-text").textContent = serverOld
    ? "The server is running older code than the files on disk. Restart it (.\serve.ps1), then reload."
    : "The server was updated. Reload the page.";
  $("stale-banner").hidden = false;
}

function renderSummary(summary) {
  renderBuild(summary.build);
  $("spent").textContent = money(summary.spent);
  $("budget").textContent = money(summary.budget_usd);
  $("team-spent").textContent = money(summary.spent);
  $("team-budget").textContent = money(summary.budget_usd);
  $("saved").textContent = money(summary.saved);
  $("count").textContent = summary.calls;
  $("blocked").textContent = summary.blocked;
  const percent = summary.budget_usd
    ? Math.min((summary.spent / summary.budget_usd) * 100, 100)
    : 100;
  $("meter-fill").style.width = `${percent}%`;
  $("meter-bar").setAttribute("aria-valuenow", Math.round(percent));
  document.querySelector(".meter").classList.toggle("over", percent >= 100);
  $("use-recommended").checked = summary.use_recommended;
  renderDevelopers(summary.developers);
  if (summary.viewer.access !== viewer?.access || summary.viewer.team !== viewer?.team) {
    applyViewer(summary.viewer);
  }

  if (!modelsLoaded) {
    modelLabels = Object.fromEntries(summary.models.map(({ id, label }) => [id, label]));
    $("run-model").replaceChildren(...summary.models.map(({ id, label }) => new Option(label, id)));
    $("run-model").value = SEND_MODEL;
    levels = summary.levels;
    $("level-ticks").replaceChildren(
      ...levels.map(({ name }) => {
        const tick = document.createElement("span");
        tick.textContent = name;
        return tick;
      }),
    );
    modelsLoaded = true;
  }

  if (!levelEditing) {
    $("level").value = summary.level;
    renderLevel(summary.level);
  }
}

function renderSimulated(on) {
  $("simulated-banner").hidden = !on;
  $("simulated-on").hidden = on || !viewer;
}

async function refresh() {
  const version = settingsVersion;
  const [summary, history, board, roasts] = await Promise.all([
    api("/api/summary"),
    api("/api/history"),
    api("/api/leaderboard"),
    api("/api/roasts"),
  ]);
  renderSummary(summary);
  // A poll that started before a toggle carries the old value, so it must not undo the click.
  if (version === settingsVersion) renderSimulated(summary.simulated);
  roastRuns = roasts;
  renderCalls(history);
  renderBoard(board);
  // Keep the user list current, so users made elsewhere (such as a demo signup) show up. Skip it
  // while someone is typing in the table, so a redraw can't wipe an edit in progress.
  if (!$("users-view").hidden && !$("user-rows").contains(document.activeElement)) await loadUsers();
}

async function refreshQuietly() {
  if (!token) return;
  try {
    await refresh();
  } catch (error) {
    if (!(error instanceof SignedOut)) {
      setStatus($("form-status"), "Live updates paused. Check your connection.", true);
    }
  }
}

async function withBusy(button, statusElement, busyText, work) {
  button.disabled = true;
  setStatus(statusElement, busyText);
  try {
    await work();
  } catch (error) {
    if (!(error instanceof SignedOut)) setStatus(statusElement, error.message, true);
  } finally {
    button.disabled = false;
    await refreshQuietly();
  }
}

// ---- Roast modal. Roasts are shared on the server with everyone who can see the call

function recommendationWhy({ reason, decided_by: decidedBy }) {
  return decidedBy ? `${reason} Judged by ${decidedBy}.` : reason;
}

function roastTime(ts) {
  return new Date(ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function openRoastDialog(prompt, busyText) {
  $("roast-meta").textContent = "";
  $("roast-prompt").textContent = prompt || "";
  $("roast-prompt").hidden = !prompt;
  $("roast-body").replaceChildren();
  setStatus($("roast-status"), busyText);
  if (!$("roast-dialog").open) $("roast-dialog").showModal();
}

function showRoast(run) {
  openRoastDialog(run.prompt, "");
  const source = run.source === "live" ? `Claude Code · ${run.developer}` : `Roasted by ${run.developer}`;
  $("roast-meta").textContent = `${source} · ${roastTime(run.ts)}${run.simulated ? " · Simulated" : ""}`;
  const body = $("roast-body");
  body.append(
    element("h3", "", "Recommended model"),
    element("p", "", `${run.recommendation.label}. ${recommendationWhy(run.recommendation)}`),
    element("h3", "", "Issues found"),
  );
  const issues = element("ul");
  for (const issue of run.issues.length ? run.issues : ["No issues found."]) {
    issues.append(element("li", "", issue));
  }
  body.append(issues);
  if (run.fix) body.append(element("h3", "", "Suggested fix"), element("p", "", run.fix));
  if (run.receipt) {
    const { model, cost_usd: cost, note } = run.receipt;
    body.append(element("h3", "", "Receipt"), element("p", "", `${model}, ${money(cost)}. ${note}`));
  }
}

// Opens the modal at once, then fills it when Haiku answers.
async function roastInModal(button, prompt, request) {
  button.disabled = true;
  openRoastDialog(prompt, "Roasting with Haiku 5.5");
  try {
    const result = await request();
    roastRuns = [result, ...roastRuns.filter((run) => run.id !== result.id)];
    if ($("roast-dialog").open) showRoast(result);
    return result;
  } catch (error) {
    if (!(error instanceof SignedOut)) setStatus($("roast-status"), error.message, true);
    return null;
  } finally {
    button.disabled = false;
    await refreshQuietly();
  }
}

function roastCall(callId, button, prompt) {
  roastInModal(button, prompt, () => api(`/api/calls/${callId}/roast`, { method: "POST" }));
}

function roastRun(roastId, button) {
  const run = roastRuns.find((item) => item.id === roastId);
  roastInModal(button, run?.prompt, () => api(`/api/roasts/${roastId}/roast`, { method: "POST" }));
}

$("roast-close").addEventListener("click", () => $("roast-dialog").close());
$("roast-dialog").addEventListener("click", (event) => {
  // A click on the backdrop lands on the dialog itself.
  if (event.target === $("roast-dialog")) $("roast-dialog").close();
});

// ---- Composer

// Before a roast, Run this prompt sends Opus and Use recommended model may move it. After a roast,
// the menu beside it picks the model, and that pick is kept.
function runPrompt(button, model, keep_model) {
  $("reply").hidden = true;
  withBusy(button, $("form-status"), "Running prompt", async () => {
    const payload = { model, prompt: $("prompt").value, keep_model };
    // Only all-access users choose who a call is for. Everyone else sends as themselves.
    if (viewer?.can_manage) {
      payload.developer_id = $("developer").value ? Number($("developer").value) : null;
    }
    const result = await api("/api/playground", { method: "POST", body: JSON.stringify(payload) });
    const failed = ["Blocked by budget", "Demo limit reached", "Error"].includes(result.status);
    setStatus($("form-status"), failed ? result.message : `Call finished: ${result.status}`, failed);
    if (result.reply) {
      $("reply").textContent = result.reply;
      $("reply").hidden = false;
    }
  });
}

async function saveSetting(change, done) {
  await api("/api/settings", { method: "PUT", body: JSON.stringify(change) });
  if (done) setStatus($("form-status"), done);
}

async function setSimulated(on, button) {
  settingsVersion += 1;
  button.disabled = true;
  try {
    await saveSetting({ simulated: on }, on ? "Simulated responses are on." : "Real Claude calls are on.");
    renderSimulated(on);
  } catch (error) {
    if (!(error instanceof SignedOut)) setStatus($("form-status"), error.message, true);
  } finally {
    button.disabled = false;
    settingsVersion += 1;
  }
}

$("simulated-on").addEventListener("click", () => setSimulated(true, $("simulated-on")));
$("simulated-off").addEventListener("click", () => setSimulated(false, $("simulated-off")));

$("use-recommended").addEventListener("change", async (event) => {
  const on = event.target.checked;
  try {
    await saveSetting({ use_recommended: on }, `Use recommended model is ${on ? "on" : "off"}.`);
  } catch (error) {
    event.target.checked = !on;
    setStatus($("form-status"), error.message, true);
  }
});

$("level").addEventListener("input", (event) => {
  levelEditing = true;
  renderLevel(Number(event.target.value));
});

$("level").addEventListener("change", async (event) => {
  const value = Number(event.target.value);
  try {
    const { name } = levels.find(({ level }) => level === value);
    await saveSetting({ level: value }, `Routing level set to ${name}.`);
    clearRecommendation();
  } catch (error) {
    setStatus($("form-status"), error.message, true);
  } finally {
    levelEditing = false;
    await refreshQuietly();
  }
});

$("simulate").addEventListener("click", () => {
  withBusy($("simulate"), $("form-status"), "Running the retry loop", async () => {
    const { statuses } = await api("/api/simulate-loop", { method: "POST" });
    const last = statuses[statuses.length - 1];
    setStatus($("form-status"), `Retry loop finished: ${last}`, last === "Error");
  });
});

$("reset").addEventListener("click", () => {
  withBusy($("reset"), $("form-status"), "Resetting", async () => {
    await api("/api/reset", { method: "POST" });
    newestSeen = 0;
    $("prompt").value = "";
    $("reply").hidden = true;
    clearRecommendation();
    roastRuns = [];
    setStatus($("form-status"), "Demo reset.");
  });
});

function openBudgetDialog() {
  $("budget-input").value = $("budget").textContent.replace("$", "");
  setStatus($("budget-error"), "");
  $("budget-dialog").showModal();
}

$("edit-budget").addEventListener("click", openBudgetDialog);
$("team-edit-budget").addEventListener("click", openBudgetDialog);
$("stale-reload").addEventListener("click", () => location.reload());
$("budget-cancel").addEventListener("click", () => $("budget-dialog").close());

$("budget-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await saveSetting({ budget_usd: Number($("budget-input").value) }, "Budget saved.");
    $("budget-dialog").close();
    await refreshQuietly();
  } catch (error) {
    setStatus($("budget-error"), error.message, true);
  }
});

// After a roast, the Roast button becomes Run on recommended model, and Run this prompt gets a
// model menu. Editing the prompt puts both back, since a roast only fits the prompt it read.
function showRecommendation({ model, label, reason, decided_by: decidedBy }) {
  recommendedModel = model;
  $("roast-send").textContent = "Run on recommended model";
  $("roast-send").title = `${label}. ${recommendationWhy({ reason, decided_by: decidedBy })}`;
  $("run-model").hidden = false;
}

function clearRecommendation() {
  recommendedModel = null;
  $("roast-send").textContent = "Roast this prompt";
  $("roast-send").title = "";
  $("run-model").hidden = true;
  $("run-model").value = SEND_MODEL;
}

$("prompt").addEventListener("input", () => {
  if (recommendedModel) clearRecommendation();
});

$("call-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const picked = !$("run-model").hidden;
  runPrompt($("send"), picked ? $("run-model").value : SEND_MODEL, picked);
});

$("roast-send").addEventListener("click", () => {
  if (recommendedModel) {
    runPrompt($("roast-send"), recommendedModel, true);
    return;
  }
  const text = $("prompt").value;
  $("reply").hidden = true;
  roastInModal($("roast-send"), text, () =>
    api("/api/roast", { method: "POST", body: JSON.stringify({ text }) }),
  ).then((result) => {
    if (result) showRecommendation(result.recommendation);
  });
});

// ---- Users. For the demo, anyone signed in can manage users on the User management view.

function accessSelect(value) {
  const select = element("select");
  for (const [level, name] of Object.entries(ACCESS_NAMES)) select.append(new Option(name, level));
  select.value = value;
  return select;
}

async function updateUser(user, change, describe) {
  try {
    const saved = await api(`/api/users/${user.id}`, { method: "PATCH", body: JSON.stringify(change) });
    Object.assign(user, saved);
    setStatus($("users-status"), describe(saved));
    await refreshQuietly();
  } catch (error) {
    if (!(error instanceof SignedOut)) setStatus($("users-status"), error.message, true);
    await loadUsers(true);
  }
}

function showToken(issued, verb) {
  $("token-title").textContent = `${verb} token for ${issued.user.name}`;
  $("token-value").value = issued.token;
  $("token-settings").value = JSON.stringify(issued.claude_code_settings, null, 2);
  $("token-box").hidden = false;
  $("token-box").scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function usersMessage(text, bad = false) {
  const td = cell(text, bad ? "empty bad" : "empty");
  td.colSpan = 7;
  const row = document.createElement("tr");
  row.append(td);
  $("user-rows").replaceChildren(row);
}

function renderUsers(users) {
  if (!users.length) {
    usersMessage("No users yet. Add one below.");
    return;
  }
  $("user-rows").replaceChildren(
    ...users.map((user) => {
      const row = document.createElement("tr");
      const name = element("input");
      name.type = "text";
      name.value = user.name;
      name.setAttribute("aria-label", `Username for ${user.name}`);
      name.addEventListener("change", () =>
        updateUser(user, { name: name.value }, (saved) => `Renamed to ${saved.name}.`));

      const team = element("input");
      team.type = "text";
      team.value = user.team;
      team.placeholder = "No team";
      team.setAttribute("aria-label", `Team for ${user.name}`);
      team.addEventListener("change", () =>
        updateUser(user, { team: team.value }, (saved) =>
          `${saved.name} is on ${saved.team ? `team ${saved.team}` : "no team"}.`));

      const level = accessSelect(user.access);
      level.setAttribute("aria-label", `Access for ${user.name}`);
      level.addEventListener("change", () =>
        updateUser(user, { access: level.value }, (saved) =>
          `${saved.name} now has ${ACCESS_NAMES[saved.access]} access.`));

      const budget = element("span", "user-budget");
      const budgetInput = element("input");
      budgetInput.type = "number";
      budgetInput.min = "0";
      budgetInput.step = "0.01";
      budgetInput.inputMode = "decimal";
      budgetInput.placeholder = "No limit";
      budgetInput.value = user.budget_usd ?? "";
      budgetInput.setAttribute("aria-label", `Budget in dollars for ${user.name}`);
      budgetInput.addEventListener("change", () => {
        const value = budgetInput.value.trim() === "" ? null : Number(budgetInput.value);
        updateUser(user, { budget_usd: value }, (saved) =>
          saved.budget_usd === null
            ? `${saved.name} has no budget of their own.`
            : `${saved.name}'s budget is ${money(saved.budget_usd)}.`);
      });
      budget.append(budgetInput, element("small", "hint", `${money(user.spent_usd)} spent`));

      const swaps = element("input");
      swaps.type = "checkbox";
      swaps.checked = Boolean(user.swaps_allowed);
      swaps.setAttribute("aria-label", `Model swaps for ${user.name}`);
      swaps.addEventListener("change", () =>
        updateUser(user, { swaps_allowed: swaps.checked }, (saved) =>
          `Model swaps are ${saved.swaps_allowed ? "on" : "off"} for ${saved.name}.`));

      const password = element("span", "user-password");
      password.append(user.has_password ? "Set " : "Not set ");
      const setPassword = element("button", "roast-button", user.has_password ? "Change" : "Set");
      setPassword.type = "button";
      setPassword.addEventListener("click", () => openPasswordDialog(user));
      password.append(setPassword);

      const regenerate = element("button", "roast-button", "New token");
      regenerate.type = "button";
      regenerate.addEventListener("click", async () => {
        if (!confirm(`Make a new token for ${user.name}? Their old token stops working at once.`)) return;
        try {
          showToken(await api(`/api/users/${user.id}/token`, { method: "POST" }), "New");
          setStatus($("users-status"), `${user.name} has a new token. Update their Claude Code settings.`);
        } catch (error) {
          if (!(error instanceof SignedOut)) setStatus($("users-status"), error.message, true);
        }
      });

      const tds = [name, team, level, budget, swaps, password, regenerate].map((control) => {
        const td = cell("");
        td.append(control);
        return td;
      });
      row.append(...tds);
      return row;
    }),
  );
}

let passwordUser = null;

function openPasswordDialog(user) {
  passwordUser = user;
  $("password-title").textContent = `Set password for ${user.name}`;
  $("password-input").value = "";
  setStatus($("password-error"), "");
  $("password-dialog").showModal();
}

$("password-cancel").addEventListener("click", () => $("password-dialog").close());

$("password-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api(`/api/users/${passwordUser.id}`, {
      method: "PATCH",
      body: JSON.stringify({ password: $("password-input").value }),
    });
    $("password-dialog").close();
    setStatus($("users-status"), `Password set for ${passwordUser.name}.`);
    await loadUsers(true);
  } catch (error) {
    if (!(error instanceof SignedOut)) setStatus($("password-error"), error.message, true);
  }
});

// User management is its own view at #users. For the demo, anyone signed in can use it.
function showView() {
  const users = location.hash === "#users";
  $("users-view").hidden = !users;
  $("dashboard").hidden = users;
  $("users-link").classList.toggle("current", users);
  if (users && viewer) loadUsers(true);
}

window.addEventListener("hashchange", showView);

$("roast-info").addEventListener("click", () => {
  const open = $("roast-help").hidden;
  $("roast-help").hidden = !open;
  $("roast-info").setAttribute("aria-expanded", String(open));
});

let shownUsers = "";

async function loadUsers(force = false) {
  if (!viewer) return;
  try {
    const users = await api("/api/users");
    // Redraw only on a change, so the 2-second poll leaves open menus and buttons alone.
    const key = JSON.stringify(users);
    if (!force && key === shownUsers && $("user-rows").children.length) return;
    shownUsers = key;
    renderUsers(users);
  } catch (error) {
    if (error instanceof SignedOut) return;
    // Say it in the table, so a failed load never looks like an empty list.
    shownUsers = "";
    usersMessage(`Couldn't load users: ${error.message}`, true);
  }
}

$("user-form").addEventListener("submit", (event) => {
  event.preventDefault();
  withBusy($("add-user"), $("users-status"), "Creating user", async () => {
    const issued = await api("/api/users", {
      method: "POST",
      body: JSON.stringify({
        name: $("new-name").value,
        team: $("new-team").value,
        access: $("new-access").value,
        password: $("new-password").value,
        budget_usd: $("new-budget").value.trim() === "" ? null : Number($("new-budget").value),
      }),
    });
    $("new-name").value = "";
    $("new-password").value = "";
    $("new-budget").value = "";
    showToken(issued, "First");
    setStatus($("users-status"), `Created ${issued.user.name}.`);
    await loadUsers(true);
  });
});

$("token-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("token-value").value);
    setStatus($("users-status"), "Token copied.");
  } catch {
    $("token-value").select();
    setStatus($("users-status"), "Press Ctrl+C to copy the selected token.");
  }
});

loadSignInOptions();
start();
