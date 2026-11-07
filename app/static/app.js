const $ = (id) => document.getElementById(id);

const EXAMPLES = {
  simple: "Write a commit message for: fix typo in README",
  design:
    "Design a multi-region failover architecture for a payments ledger. " +
    "Compare consistency models and list the failure modes.",
};

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
let pickedModel = null;
let keepNext = false;
let levels = [];
let levelEditing = false;
let viewer = null;
let roastRuns = [];
let roastKey = "";
let selectedRoast = null;
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
    ? `Choose a username and a password of 8 or more characters. You get ${ACCESS_NAMES[demoAccess] ?? "Self"} access, and a token for Claude Code.`
    : "CaveDawg shows what your team's AI calls cost and stops the waste.";
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
  if (viewer?.can_manage) loadUsers();
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
      const created = await postJson("/api/signup", { name, password });
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
  if (call.roast) {
    const button = element("button", "roast-button scored", `${call.roast.score}/100`);
    button.type = "button";
    button.title = "Show this call's roast";
    button.addEventListener("click", () => selectRoast(call.roast.id));
    td.append(button);
  } else if (call.roast_call_id) {
    const button = element("button", "roast-button", "Roast");
    button.type = "button";
    button.title = "Score this call's prompt for wasted tokens";
    button.addEventListener("click", () => roastCall(call.roast_call_id, button));
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
      const prompt = cell(call.prompt || "None recorded", "prompt");
      prompt.title = call.prompt;
      if (call.calls > 1) prompt.append(element("span", "row-note", `${call.calls} calls`));
      const ideal = cell(call.ideal_label || "Not rated");
      if (call.decided_by) ideal.append(element("span", "row-note", `Judged by ${call.decided_by}`));
      row.append(
        cell(time),
        cell(call.developer),
        prompt,
        ideal,
        cell(call.used_label),
        cell(call.tokens ? call.tokens.toLocaleString() : "None", "num"),
        cell(call.cost_usd ? money(call.cost_usd) : "$0", "num"),
      );
      const status = cell("", "status");
      status.append(element("span", `stamp ${STAMPS[call.status] || "ok"}`, call.status));
      if (["Error", "Dropped", "Swap failed"].includes(call.status)) {
        status.append(element("span", "row-note", call.reason));
      }
      if (call.simulated) status.append(element("span", "row-note", "Simulated"));
      row.append(status, roastCell(call));
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

function renderBoard({ rows, minimum_prompts: minimum }) {
  $("board").hidden = rows.length === 0;
  $("board-rows").replaceChildren(
    ...rows.map((entry) => {
      const row = document.createElement("tr");
      const time = cell(duration(entry.dev_seconds), "num");
      time.append(element("span", "row-note", entry.dev_time_source));
      row.append(
        cell(entry.rank ?? "Unranked"),
        cell(entry.developer),
        cell(entry.prompts, "num"),
        cell(entry.tokens.toLocaleString(), "num"),
        cell(money(entry.cost_usd), "num"),
        time,
        cell(`${entry.overuse_percent.toFixed(1)}%`, "num"),
        cell(money(entry.overspend_usd), "num"),
      );
      return row;
    }),
  );
  $("board-note").textContent =
    "Overuse is the share of rated spend above each prompt's ideal model, lowest first. " +
    `A rank needs ${minimum} rated prompts. Ratings are judgments, not a performance measure.`;
}

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

function renderFlag(flag) {
  $("why").hidden = !flag;
  if (!flag) return;
  $("why-reason").textContent = flag.reason;
  $("why-math").textContent =
    flag.ideal_cost_usd === undefined
      ? ""
      : `Same call on ${flag.ideal_label}: ${money(flag.ideal_cost_usd)}. ` +
        `Projection at 100 calls a day: saves ${money(flag.projected_monthly_saving_usd, 2)} a month (estimate).`;
}

function renderLevel(value) {
  const current = levels.find(({ level }) => level === value);
  if (!current) return;
  $("level").setAttribute("aria-valuetext", current.name);
  $("level-note").textContent = current.summary;
  for (const tick of $("level-ticks").children) {
    tick.classList.toggle("current", tick.textContent === current.name);
  }
}

function renderSummary(summary) {
  $("spent").textContent = money(summary.spent);
  $("budget").textContent = money(summary.budget_usd);
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
  $("simulated").checked = summary.simulated;
  $("simulated-banner").hidden = !summary.simulated;
  renderFlag(summary.latest_flag);
  renderDevelopers(summary.developers);
  if (summary.viewer.access !== viewer?.access || summary.viewer.team !== viewer?.team) {
    applyViewer(summary.viewer);
  }

  if (!modelsLoaded) {
    $("model").replaceChildren(
      ...summary.models.map(({ id, label }) => new Option(label, id)),
    );
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

async function refresh() {
  const [summary, history, board, roasts] = await Promise.all([
    api("/api/summary"),
    api("/api/history"),
    api("/api/leaderboard"),
    api("/api/roasts"),
  ]);
  renderSummary(summary);
  renderCalls(history);
  renderBoard(board);
  updateRoasts(roasts);
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

// ---- Roast results, shared on the server with everyone who can see the call

function recommendationText({ label, reason, decided_by: decidedBy }) {
  const judged = decidedBy ? ` Judged by ${decidedBy}.` : "";
  return `${label}. ${reason}${judged}`;
}

function renderRun(run) {
  const details = element("details", "run");
  details.dataset.id = run.id;
  details.open = run.id === selectedRoast;
  details.classList.toggle("selected", run.id === selectedRoast);
  const score = element("span", "run-score", run.score);
  score.append(element("small", "", " out of 100"));
  const time = new Date(run.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const summary = element("summary");
  const tags = element("span", "run-tags");
  tags.append(run.source === "live" ? `Claude Code · ${run.developer}` : `Roasted by ${run.developer}`);
  if (run.simulated) tags.append(" · ", element("span", "sim", "Simulated"));
  summary.append(score, element("span", "run-prompt", run.prompt), element("span", "run-time", time), tags);
  details.addEventListener("toggle", () => {
    if (details.open) selectedRoast = run.id;
  });

  const issues = element("ul");
  for (const issue of run.issues.length ? run.issues : ["No issues found."]) {
    issues.append(element("li", "", issue));
  }
  const verdict = element("div", "verdict");
  verdict.append(element("h3", "", "Issues found"), issues);
  if (run.fix) verdict.append(element("h3", "", "Suggested fix"), element("p", "", run.fix));
  verdict.append(
    element("h3", "", "Recommended model"),
    element("p", "", recommendationText(run.recommendation)),
  );
  if (run.receipt) {
    const { model, cost_usd: cost, note } = run.receipt;
    verdict.append(element("h3", "", "Receipt"), element("p", "", `${model}, ${money(cost)}. ${note}`));
  } else {
    verdict.append(element("p", "hint", "Scored by rules as the prompt was sent, so no fix was written. Click Roast on the call for one."));
  }
  details.append(summary, verdict);
  return details;
}

function renderRoasts() {
  $("roast-count").textContent = roastRuns.length === 1 ? "1 run" : `${roastRuns.length} runs`;
  $("roasts-empty").hidden = roastRuns.length > 0;
  $("roast-runs").replaceChildren(...roastRuns.map(renderRun));
}

// Only redraw when the list changes, so a run someone opened stays open between polls.
function updateRoasts(rows) {
  const key = rows.map((row) => row.id).join(",");
  if (key === roastKey) return;
  const newest = rows[0]?.id;
  const grew = newest !== undefined && newest !== roastRuns[0]?.id;
  roastKey = key;
  roastRuns = rows;
  if (grew && selectedRoast === null) selectedRoast = newest;
  renderRoasts();
}

function selectRoast(id) {
  selectedRoast = id;
  renderRoasts();
  document.querySelector(`.run[data-id="${id}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

async function addRoast(result) {
  roastKey = "";
  roastRuns = [result, ...roastRuns.filter((run) => run.id !== result.id)];
  selectRoast(result.id);
}

function roastCall(callId, button) {
  withBusy(button, $("form-status"), "Roasting the call", async () => {
    const result = await api(`/api/calls/${callId}/roast`, { method: "POST" });
    await addRoast(result);
    setStatus($("form-status"), `Roast finished: ${result.score} out of 100.`);
  });
}

// ---- Composer

$("call-form").addEventListener("submit", (event) => {
  event.preventDefault();
  clearOffer();
  $("reply").hidden = true;
  const model = $("model").value;
  const keep_model = keepNext;
  keepNext = false;
  withBusy($("send"), $("form-status"), "Sending call", async () => {
    const payload = { model, prompt: $("prompt").value, keep_model };
    // Only all-access users choose who a call is for. Everyone else sends as themselves.
    if (viewer?.can_manage) {
      payload.developer_id = $("developer").value ? Number($("developer").value) : null;
    }
    const result = await api("/api/playground", { method: "POST", body: JSON.stringify(payload) });
    if (result.call.model !== model) offerOverride(model);
    const failed = ["Blocked by budget", "Demo limit reached", "Error"].includes(result.status);
    setStatus($("form-status"), failed ? result.message : `Call finished: ${result.status}`, failed);
    if (result.reply) {
      $("reply").textContent = result.reply;
      $("reply").hidden = false;
    }
  });
});

$("simple-task").addEventListener("click", () => {
  clearOffer();
  $("prompt").value = EXAMPLES.simple;
  $("prompt").focus();
});
$("real-design").addEventListener("click", () => {
  clearOffer();
  $("prompt").value = EXAMPLES.design;
  $("prompt").focus();
});

async function saveSetting(change, done) {
  await api("/api/settings", { method: "PUT", body: JSON.stringify(change) });
  if (done) setStatus($("form-status"), done);
}

$("simulated").addEventListener("change", async (event) => {
  const on = event.target.checked;
  try {
    await saveSetting({ simulated: on }, on ? "Simulated responses are on." : "Real Claude calls are on.");
    $("simulated-banner").hidden = !on;
  } catch (error) {
    event.target.checked = !on;
    setStatus($("form-status"), error.message, true);
  }
});

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
    clearOffer();
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
    clearOffer();
    roastRuns = [];
    roastKey = "";
    selectedRoast = null;
    renderRoasts();
    setStatus($("form-status"), "Demo reset.");
  });
});

$("edit-budget").addEventListener("click", () => {
  $("budget-input").value = $("budget").textContent.replace("$", "");
  setStatus($("budget-error"), "");
  $("budget-dialog").showModal();
});
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

function modelLabel(id) {
  return [...$("model").options].find((option) => option.value === id)?.text ?? id;
}

function clearOffer() {
  pickedModel = null;
  $("recommend").hidden = true;
  $("use-anyway").hidden = true;
}

function offerOverride(model) {
  pickedModel = model;
  $("use-anyway").textContent = `Use ${modelLabel(model)} anyway`;
  $("use-anyway").hidden = false;
}

function offerModel({ model, label, reason }) {
  // Roasting the same prompt twice must still remember the model the person chose.
  pickedModel ??= $("model").value;
  const differs = pickedModel !== model;
  $("model").value = model;
  $("recommend").textContent = differs
    ? `Recommended: ${label}. ${reason}`
    : `${label} is already the recommended model. ${reason}`;
  $("recommend").hidden = false;
  $("use-anyway").textContent = `Use ${modelLabel(pickedModel)} anyway`;
  $("use-anyway").hidden = !differs;
}

$("use-anyway").addEventListener("click", () => {
  $("model").value = pickedModel;
  keepNext = true;
  $("call-form").requestSubmit();
});

// The recommendation only applies to the prompt and model it was made for.
$("prompt").addEventListener("input", clearOffer);
$("model").addEventListener("change", clearOffer);

$("roast-send").addEventListener("click", () => {
  const text = $("prompt").value;
  $("reply").hidden = true;
  withBusy($("roast-send"), $("form-status"), "Roasting", async () => {
    const result = await api("/api/roast", { method: "POST", body: JSON.stringify({ text }) });
    await addRoast(result);
    offerModel(result.recommendation);
    setStatus($("form-status"), `Roast finished: ${result.score} out of 100.`);
  });
});

// ---- Users. Only all-access viewers see this section, and the server checks it too.

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
    await loadUsers();
  }
}

function showToken(issued, verb) {
  $("token-title").textContent = `${verb} token for ${issued.user.name}`;
  $("token-value").value = issued.token;
  $("token-settings").value = JSON.stringify(issued.claude_code_settings, null, 2);
  $("token-box").hidden = false;
  $("token-box").scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function renderUsers(users) {
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

      const tds = [name, team, level, swaps, password, regenerate].map((control) => {
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
    await loadUsers();
  } catch (error) {
    if (!(error instanceof SignedOut)) setStatus($("password-error"), error.message, true);
  }
});

async function loadUsers() {
  if (!viewer?.can_manage) return;
  try {
    renderUsers(await api("/api/users"));
  } catch (error) {
    if (!(error instanceof SignedOut)) setStatus($("users-status"), error.message, true);
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
      }),
    });
    $("new-name").value = "";
    $("new-password").value = "";
    showToken(issued, "First");
    setStatus($("users-status"), `Created ${issued.user.name}.`);
    await loadUsers();
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

renderRoasts();
loadSignInOptions();
start();
