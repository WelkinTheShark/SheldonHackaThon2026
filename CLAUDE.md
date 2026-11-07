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
python -m app.devs add "Name"                      # developer token + Claude Code settings block
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

**Auth.** `_identify` accepts a developer token (stored as a SHA-256 hash) or the shared
`CAVEDAWG_GATEWAY_TOKEN`. The client's auth header is never forwarded. Upstream always gets the
server's `ANTHROPIC_API_KEY`, and only `anthropic-*` headers pass through.

**Simulated responses.** A setting (`store.get_settings()["simulated"]`) routes calls to
`app/simulated.py`, an in-process `httpx.MockTransport`, instead of Anthropic. The pipeline reads it
once per call into `Plan.simulated`, so each row records where the call really went. Simulated rows
count toward the budget but not the lifetime hard cap, and Jev is skipped. `tests/fake_upstream.py`
reuses the same canned replies as a standalone server.

**Views.** `app/team.py` groups rows by prompt ID into delivery history (the worst status wins via
`STATUS_ORDER`) and builds the leaderboard. Roast (`app/roast.py`) finds issues with rules and only
asks Claude for the suggested fix. Each new Claude Code prompt is also scored with the same rules in
`pipeline._live_roast` (no model call) and stored in `live_roasts`, which the page polls through
`/api/live-roasts` and merges into Roast My Stack.

**Store.** SQLite behind one lock. New `calls` columns go in `CALL_COLUMNS` so `_migrate` adds them
to existing databases. `store.reset` (Reset demo) clears calls, dev time, budget, the swap toggle and
the level. It keeps `lifetime_spend` and the simulated switch.

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
(Reset demo, Send call, Use recommended model, Edit budget, statuses) only with the use cases updated
to match.

## Known limits to keep in mind

The page has no login, so anyone with the URL can spend up to the hard cap, change settings or flip
Simulated responses. Only the first 80 characters of each prompt are stored. Saved amounts are
estimates.
