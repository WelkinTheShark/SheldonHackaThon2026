# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

CaveDawg is a FastAPI proxy for the Claude API and Claude Code, built for the Ship Happens hackathon.
It logs spend per developer, compares each prompt's ideal model with the one used, can swap to the
ideal model, stops agent retry loops, and blocks calls at a budget. It replaces the cost-control
slice of Datadog, not Datadog. One page (`app/static/`, plain JS, no build step) sits on the same
SQLite database.

## Commands

```powershell
python -m pip install -r requirements.txt
python -m pytest                                   # full suite, all upstream calls mocked
python -m pytest tests/test_rules.py::test_name    # one test
python -m uvicorn app.main:app --port 8000         # needs ANTHROPIC_API_KEY, CAVEDAWG_GATEWAY_TOKEN
.\serve.ps1                                        # loads .env, starts app + Cloudflare quick tunnel
.\serve.ps1 -Stub                                  # same, against tests/fake_upstream on :9100
python -m app.devs add "Name" --team Core --access team   # token + Claude Code settings block
python -m app.devs access "Name" all                # also: team, token (rotate), password, list
python -m app.devs swaps "Name" off                # per-developer model-swap kill switch
```

There is no linter or formatter configured. All settings come from env vars read in `app/config.py`
(`Settings`). Prices, model IDs, routing levels and limits also live there.

## Architecture

**Every call takes one path: `app/pipeline.py`.** The playground (`/api/playground`), the proxy
(`/v1/messages`), the retry-loop demo and Roast all build a `pipeline.Context` and call
`pipeline.run` (JSON) or `pipeline.stream` (SSE). The order is fixed:
1. `_check_limits`: hard cap, then budget, then `rules.is_loop`. A refusal still records a row.
2. `_prepare` builds a `Plan`: the user's text is judged, which gives a kind, an ideal model and a
   status (OK, Overkill, Downshifted, Upshifted). The model is swapped if allowed.
3. `upstream.post` / `open_stream` sends raw bytes. If Anthropic rejects a swapped model, the
   original bytes are resent once and the row says Swap failed.
4. `_record` prices usage (`app/costs.py`) and writes one row to `calls` (`app/store.py`).

**Judging.** `pipeline.judge` asks Jev (`app/jev.py`, TypeSafe API, 1.5 s timeout) when
`TYPESAFE_API_KEY` is set, and otherwise uses the keyword rules in `app/rules.py`. A kind maps to a
model through the routing level in `config.LEVELS`. For Claude Code (`request_class == "main"`),
only the human's latest words are judged, with `<system-reminder>` blocks stripped.

**Claude Code specifics.** `_proxy_context` in `app/main.py` reads Claude Code's hint headers
`x-claude-code-prompt-id` and `x-claude-code-request-class`. The client needs
`CLAUDE_CODE_GATEWAY_HINT_HEADERS=1`. Rules that depend on them:
- Only `main` or headerless calls are rated. Subagent, compaction and other background classes pass
  through untouched.
- Swaps need a prompt ID. Later tool rounds reuse the first decision via `store.prompt_decision`,
  so one prompt never changes model mid-turn.
- `#keep` in a prompt, or `devs swaps off`, blocks the swap.
- `/v1/metrics` takes OTLP http/json and turns `claude_code.active_time.total` into Dev time.

**Auth.** The proxy's `_identify` accepts a developer token (stored as a SHA-256 hash) or the
shared `CAVEDAWG_GATEWAY_TOKEN`. The client's auth header is never forwarded. Upstream always gets
the server's `ANTHROPIC_API_KEY`, and only `anthropic-*` headers pass through.

**Page access** (`app/access.py`). Every `/api/*` route except `/api/hello` takes
`Depends(access.require_viewer)` or `require_manager`. The page sends `x-cavedawg-token`; Claude
Code's roast script sends `x-api-key`. A developer row carries `team` and `access` (`self`, `team`,
`all`). `access.scope(viewer)` returns the visible developer IDs, or None for everything, and
`team.history` / `team.leaderboard` / `/api/roasts` filter by it. Only `all` can change settings (except
the Simulate responses switch (a red banner with Turn off when on), which anyone signed in may flip, since it blocks real work), Reset demo and the retry-loop demo. For the demo, the `/api/users` routes take `require_viewer`, so anyone signed in can create, edit and delete users (including granting `all`) from the User management view (`#users`). New users default to `config.DEFAULT_ACCESS` (`team`) and `config.DEFAULT_USER_BUDGET_USD` ($1000). `store.delete_developer` keeps the user's calls and roasts (their `developer_id` becomes NULL, shown as Unattributed) and drops their sessions and dev time; deleting yourself signs you out. The gateway token signs in as Admin with all access.
Password login (`/api/login`, scrypt hashes in `developers.password_hash`) and the Demo signup
(`/api/signup`, where the person picks team and access; blank means team Demo and access from `CAVEDAWG_DEMO_ACCESS`, which also turns Demo off when invalid) issue page sessions (`sessions` table, `cs_`
prefix). `access.viewer_for` accepts a developer token or a session. The proxy's `_identify`
accepts tokens only, so a session can't spend through `/v1/messages`. Setting a password ends that
user's sessions.
HTTPExceptions are turned into the page's `{"error": ...}` shape. Tests sign in as Admin through a
default header on the `client` fixture; pass `headers={"x-cavedawg-token": token}` to act as a user.

**Simulated responses.** A setting (`store.get_settings()["simulated"]`) routes calls to
`app/simulated.py`, an in-process `httpx.MockTransport`, instead of Anthropic. The pipeline reads it
once per call into `Plan.simulated`, so each row records where the call really went. Simulated rows
count toward the budget but not the lifetime hard cap, and Jev is skipped. `tests/fake_upstream.py`
reuses the same canned replies as a standalone server.

**Views.** `app/team.py` groups rows by prompt ID into delivery history (the worst status wins via
`STATUS_ORDER`) and builds the leaderboard. Roast (`app/roast.py`) asks Haiku for the issues and fix
as JSON, and falls back to the rules' issues when the reply isn't JSON or the call fails. Roasts live in the `roasts` table and are shared. Each one stores
`prompt_hash` (`rules.prompt_hash` of the stripped words), and a history row shows the newest roast
whose hash matches its call's `prompt_hash`, so a roast follows a prompt that was sent unchanged.
Calls keep the person's words in `prompt_text` (never for background Claude Code classes), which
`POST /api/calls/{id}/roast` uses. Each new Claude Code prompt is also scored with the rules in
`pipeline._live_roast` (source `live`, no model call). The page shows such a roast's recommended
model only (`roasted` is false) until someone clicks Roast, and `POST /api/roasts/{id}/roast` then
fills it in place with Haiku. The page shows no scores. The playground sends Opus unless Use recommended
model swaps it. After Roast this prompt, that button becomes Run on recommended model (sent with
`keep_model`), and a model menu appears beside Run this prompt. `/api/playground` accepts any model
in `config.MODEL_LABELS`. The page has no Developer menu and no retry-loop button: playground calls
count for whoever is signed in. `developer_id` on `/api/playground` and `/api/simulate-loop` remain
as APIs (tests use them), but the page no longer sends or calls them.

**Store.** SQLite behind one lock. New `calls` columns go in `CALL_COLUMNS` so `_migrate` adds them
to existing databases. `store.reset` (Reset demo) clears calls, roasts, dev time, budget, the swap
toggle and the level. It keeps `lifetime_spend`, the simulated switch and users. New `developers`
columns go in `DEVELOPER_COLUMNS`.

## Tests

`tests/conftest.py` swaps `upstream.transport` for `FakeAnthropic` and `jev.transport` for `FakeJev`,
and gives each test its own temp database. The useful fixtures are `client`, `anthropic` (inspect
`.requests`), `fake_jev` and `developer` (Bearer auth headers plus the row).
`tests/test_claude_code.py` has helpers that build Claude Code-shaped requests (`first_body`,
`tool_round`, `hints`).

## Wren (hackathon QA)

`wren/use-cases.md` holds plain-English browser tests for Seldon's Wren agent, pointed at the
deployed URL. W1 and W2 are required for prizes and must run against the final build with real
Claude calls and Simulated responses off. Expected results check status labels and amounts, never
Claude's wording. Each Wren run past the first 10 costs $3, so change UI labels those tests name
(Reset demo, Run this prompt, Run on recommended model, Use recommended model, Edit budget, User management, statuses) only with the use cases updated
to match.

## Known limits to keep in mind

Login has no rate limit and no audit log, and the Demo button is open to anyone with the URL. Anyone signed in (including a Demo login) can
manage users and give themselves all access. Spend, budget and settings are global, not
per team. The person's prompt words are stored so calls can be roasted later. Saved amounts are
estimates. Wren tests now need a sign-in step with a demo all-access token.
