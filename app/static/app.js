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

// Full roast results stay in this browser. The server keeps only a short snippet.
const ROAST_KEY = "cavedawg.roasts";
const ROAST_LIMIT = 20;
const ROAST_PROMPT_CHARS = 80;

let newestSeen = 0;
let modelsLoaded = false;
let roastRuns = loadRoasts();
let liveRuns = [];
let liveKey = "";
let pickedModel = null;
let keepNext = false;
let levels = [];
let levelEditing = false;

function loadRoasts() {
  try {
    const runs = JSON.parse(localStorage.getItem(ROAST_KEY));
    return Array.isArray(runs) ? runs : [];
  } catch {
    return [];
  }
}

function saveRoasts() {
  try {
    localStorage.setItem(ROAST_KEY, JSON.stringify(roastRuns));
  } catch {
    // History still works until the page reloads.
  }
}

function money(value, places = 4) {
  const amount = Number(value || 0);
  // Tiny calls would otherwise display as $0.0000.
  if (amount > 0 && amount < 0.0001) return `$${amount.toFixed(6)}`;
  return `$${amount.toFixed(places)}`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "The request failed. Try again.");
  return data;
}

function setStatus(element, text, bad = false) {
  element.textContent = text;
  element.classList.toggle("bad", bad);
}

function cell(text, className) {
  const td = document.createElement("td");
  td.textContent = text;
  if (className) td.className = className;
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
      row.append(status);
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
  const options = [...$("developer").options].slice(1);
  const known = options.map((option) => option.text).join();
  if (known === developers.map(({ name }) => name).join()) return;
  const selected = $("developer").value;
  $("developer").replaceChildren(
    new Option("Unattributed", ""),
    ...developers.map(({ id, name }) => new Option(name, id)),
  );
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
  const [summary, history, board, live] = await Promise.all([
    api("/api/summary"),
    api("/api/history"),
    api("/api/leaderboard"),
    api("/api/live-roasts"),
  ]);
  renderSummary(summary);
  renderCalls(history);
  renderBoard(board);
  updateLiveRuns(live);
}

async function refreshQuietly() {
  try {
    await refresh();
  } catch {
    setStatus($("form-status"), "Live updates paused. Check your connection.", true);
  }
}

async function withBusy(button, statusElement, busyText, work) {
  button.disabled = true;
  setStatus(statusElement, busyText);
  try {
    await work();
  } catch (error) {
    setStatus(statusElement, error.message, true);
  } finally {
    button.disabled = false;
    await refreshQuietly();
  }
}

$("call-form").addEventListener("submit", (event) => {
  event.preventDefault();
  clearOffer();
  $("reply").hidden = true;
  const model = $("model").value;
  const keep_model = keepNext;
  keepNext = false;
  withBusy($("send"), $("form-status"), "Sending call", async () => {
    const developer_id = $("developer").value ? Number($("developer").value) : null;
    const result = await api("/api/playground", {
      method: "POST",
      body: JSON.stringify({ model, prompt: $("prompt").value, developer_id, keep_model }),
    });
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

$("simulated").addEventListener("change", async (event) => {
  const on = event.target.checked;
  try {
    await api("/api/settings", { method: "PUT", body: JSON.stringify({ simulated: on }) });
    $("simulated-banner").hidden = !on;
    setStatus($("form-status"), on ? "Simulated responses are on." : "Real Claude calls are on.");
  } catch (error) {
    event.target.checked = !on;
    setStatus($("form-status"), error.message, true);
  }
});

$("use-recommended").addEventListener("change", async (event) => {
  try {
    await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ use_recommended: event.target.checked }),
    });
    setStatus(
      $("form-status"),
      `Use recommended model is ${event.target.checked ? "on" : "off"}.`,
    );
  } catch (error) {
    event.target.checked = !event.target.checked;
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
    await api("/api/settings", { method: "PUT", body: JSON.stringify({ level: value }) });
    clearOffer();
    const { name } = levels.find(({ level }) => level === value);
    setStatus($("form-status"), `Routing level set to ${name}.`);
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
    saveRoasts();
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
    await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ budget_usd: Number($("budget-input").value) }),
    });
    $("budget-dialog").close();
    setStatus($("form-status"), "Budget saved.");
    await refreshQuietly();
  } catch (error) {
    setStatus($("budget-error"), error.message, true);
  }
});

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function recommendationText({ label, reason, decided_by: decidedBy }) {
  const judged = decidedBy ? ` Judged by ${decidedBy}.` : "";
  return `${label}. ${reason}${judged}`;
}

function renderRun(run, open) {
  const details = element("details", "run");
  details.open = open;
  const score = element("span", "run-score", run.score);
  score.append(element("small", "", " out of 100"));
  const time = new Date(run.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const summary = element("summary");
  const prompt = element("span", "run-prompt", run.prompt);
  if (run.live) prompt.prepend(element("span", "run-source", `Claude Code · ${run.developer}`));
  summary.append(score, prompt, element("span", "run-time", time));

  const issues = element("ul");
  for (const issue of run.issues.length ? run.issues : ["No issues found."]) {
    issues.append(element("li", "", issue));
  }
  const verdict = element("div", "verdict");
  verdict.append(element("h3", "", "Issues found"), issues);
  if (run.live) {
    verdict.append(
      element("h3", "", "Recommended model"),
      element("p", "", recommendationText(run.recommendation)),
      element("p", "hint", "Scored by rules as the prompt was sent, so no fix was written."),
    );
  } else {
    const { model, cost_usd: cost, note } = run.receipt;
    verdict.append(
      element("h3", "", "Suggested fix"),
      element("p", "", run.fix),
      element("h3", "", "Recommended model"),
      element("p", "", recommendationText(run.recommendation)),
      element("h3", "", "Receipt"),
      element("p", "", `${model}, ${money(cost)}. ${note}`),
    );
  }
  details.append(summary, verdict);
  return details;
}

// Claude Code prompts are roasted on the server as they arrive. Only redraw when that list
// changes, so a run someone opened stays open between polls.
function updateLiveRuns(rows) {
  const key = rows.map((row) => row.id).join(",");
  if (key === liveKey) return;
  const grew = rows.length > 0 && !liveKey.startsWith(String(rows[0].id));
  liveKey = key;
  liveRuns = rows.map((row) => ({
    live: true,
    ts: row.ts,
    prompt: row.snippet,
    developer: row.developer,
    score: row.score,
    issues: row.issues,
    recommendation: { label: row.ideal_label, reason: row.note, decided_by: row.decided_by },
  }));
  renderRoasts();
  if (grew) $("roasts").open = true;
}

function renderRoasts() {
  const runs = [...liveRuns, ...roastRuns].sort((a, b) => b.ts.localeCompare(a.ts));
  $("roasts").hidden = runs.length === 0;
  $("roast-count").textContent = runs.length === 1 ? "1 run" : `${runs.length} runs`;
  $("roast-runs").replaceChildren(...runs.map((run, index) => renderRun(run, index === 0)));
}

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
    const prompt = text.trim().replace(/\s+/g, " ").slice(0, ROAST_PROMPT_CHARS);
    roastRuns = [{ ...result, prompt, ts: new Date().toISOString() }, ...roastRuns].slice(0, ROAST_LIMIT);
    saveRoasts();
    renderRoasts();
    $("roasts").open = true;
    offerModel(result.recommendation);
    setStatus($("form-status"), `Roast finished: ${result.score} out of 100.`);
  });
});

renderRoasts();
$("roasts").open = roastRuns.length > 0;
refreshQuietly();
setInterval(refreshQuietly, 2000);
