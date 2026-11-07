# CaveDawg

See what your AI calls cost, and stop the waste before you pay for it.

CaveDawg is a small proxy for the Claude API and Claude Code. It logs real spend per developer,
compares each prompt's ideal model with the one used, stops agent retry loops, and blocks calls at
a budget. Built for Ship Happens.
It replaces the cost-control slice of Datadog, not Datadog.

## Run it

```powershell
python -m pip install -r requirements.txt
$env:ANTHROPIC_API_KEY = "<your key>"
$env:CAVEDAWG_GATEWAY_TOKEN = "<a long random string>"
python -m uvicorn app.main:app --port 8000
```

Open http://127.0.0.1:8000.

For Wren, run `.\serve.ps1` instead. It reads `.env` (copy `.env.example`), starts the app and opens a
Cloudflare quick tunnel, then prints the public URL to paste into Wren. `.\serve.ps1 -Stub` runs
with the fake upstream for a dry run.

To test with no token cost, turn on Simulated responses at the top of the page. Calls get canned
replies, nothing reaches Anthropic or Jev, and each row is marked Simulated. Amounts are estimates
that count toward the budget but never the hard cap. Reset demo clears them and leaves the switch as
it is. The switch covers proxy traffic too, so Claude Code can't do real work while it's on. Never
use simulated runs for Wren evidence.

To run the same canned replies as a separate server, start the stub in a second terminal:

```powershell
python -m uvicorn tests.fake_upstream:app --port 9100
$env:ANTHROPIC_UPSTREAM = "http://127.0.0.1:9100"
```

Stub replies and token counts are made up, so never use it for Wren evidence or a deployed app.

## Routing levels

The Routing level bar sets which model each kind of task should use. It drives each prompt's
ideal model, the Overkill label, Use recommended model and Roast's recommendation.

| Task | Fastest | Balanced | Thorough | Full power |
|---|---|---|---|---|
| Commit, push, single-fact lookup | Haiku | Haiku | Haiku | Haiku |
| Mechanical (format, regex, rename, JSON) | Haiku | Haiku | Sonnet | Opus |
| Unclear | Haiku | Sonnet | Opus | Opus |
| Tools or a long setup | Sonnet | Sonnet | Opus | Opus |
| Investigation or design | Sonnet | Opus | Opus | Opus |

Any sign of investigation outranks a lookup or a push.

With `TYPESAFE_API_KEY` set, [Jev](https://docs.typesafe.ai) judges each prompt. If it has no key,
fails, or takes over 1.5 seconds, keyword rules decide instead. Each call shows which one judged it.
Turning Jev on sends prompts (up to 8,000 characters) to TypeSafe. Zero retention is enterprise-only.

Use recommended model runs calls on their ideal model, up or down, so it can cost more at Thorough
and Full power. It's off by default. Use {model} anyway overrides it for one call.

## Claude Code

Create a token for each developer. It prints the settings to add to their
`~/.claude/settings.json`:

```powershell
$env:CAVEDAWG_PUBLIC_URL = "https://your-app.example.com"
python -m app.devs add "Name"
```

Needs Claude Code 2.1.283 or later. Those settings replace a developer's subscription login, so usage
bills to CaveDawg's API key.

| What | How it works in Claude Code |
|---|---|
| Delivery history | Every call is tied to the token. A prompt with many tool rounds is one row. |
| Ideal and used model | Judged once on the developer's own words, then kept for that prompt's tool rounds. |
| Use recommended model | Swaps the `model` field on main-conversation calls. Background calls are left alone. |
| Override | Add `#keep` to a prompt, or run `python -m app.devs swaps "Name" off`. |
| Rejected swap | If Anthropic refuses the swapped model, the original request is resent once and marked Swap failed. |
| Dev time | Claude Code telemetry, shown as Measured. Without it, an Estimate from gaps between calls. |
| Live roast | Each prompt is scored by the Roast rules as it arrives and shows in Roast My Stack, with no extra Claude call. |
| Roast | Copy `claude-code/roast.md` to `~/.claude/commands/` and `claude-code/cavedawg_roast.py` to `~/.claude/`, then run `/roast <prompt>`. |

Anthropic doesn't document swapping models behind Claude Code as safe, so test it with real calls
before relying on it. Each model has its own prompt cache, so a swap can raise input costs.

## Use the proxy

Point any client that speaks the Anthropic Messages format at CaveDawg, and use the gateway token
as its API key:

```powershell
$env:ANTHROPIC_BASE_URL = "https://your-app.example.com"
$env:ANTHROPIC_API_KEY = "<gateway token>"
```

Streaming and non-streaming calls both work. Clients that don't send Claude Code's hint headers are
labelled but never swapped.

## Test it

```powershell
python -m pytest
```

Browser use cases for Wren are in `wren/use-cases.md`.

## Deploy it

Any Docker host works. Set these environment variables:

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Upstream key. Use a dedicated key with a Console spend limit. |
| `CAVEDAWG_GATEWAY_TOKEN` | Required for `/v1/messages`. With none set, the proxy refuses every call. |
| `CAVEDAWG_HARD_CAP_USD` | Lifetime spend ceiling, default 5. Reset demo doesn't clear it. |
| `TYPESAFE_API_KEY` | Optional. Turns on Jev. |
| `CAVEDAWG_PUBLIC_URL` | The URL `app.devs add` puts in Claude Code settings. |
| `CAVEDAWG_DB` | Database path, default `data/cavedawg.db`. Keep it on a persistent disk. |

## Known limits

- The page has no login, so anyone with the URL can spend up to the hard cap, read prompt snippets
  and the leaderboard, change settings, and clear history with Reset demo. Treat a public deployment
  as a demo with no real team data, and rely on the Console spend limit as the backstop.
- The first 80 characters of each prompt are stored, along with call metadata. Full prompts and
  replies aren't.
- The default $5 hard cap and $1 budget are for demos. Real Claude Code sessions will reach them fast.
- Leaderboard ratings are judgments from Jev or keywords. Don't use them as a performance measure.
- A budget blocks the call after spend reaches the cap, so the last call can go slightly over.
- Saved amounts are estimates. A move down prices the same token counts on the original model,
  and a stopped loop prices the blocked call's estimated input.
- The keyword rules can miss cases or misjudge a short, hard task that mentions a keyword.
- Full Roast results live in the browser's local storage, up to 20 runs per browser.
