import gzip
import hmac
import json
import math
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, pipeline, roast, store, team, upstream

STATIC = Path(__file__).parent / "static"
FORWARDED_RESPONSE_HEADERS = {"request-id", "retry-after", "x-should-retry"}
BLOCKED_STATUSES = {"Blocked by budget", "Demo limit reached", "Loop stopped"}
FLAGGED_STATUSES = {
    "Overkill", "Downshifted", "Upshifted", "Swap failed", "Loop stopped", "Blocked by budget",
}
OTLP_CUMULATIVE = 2

LOOP_TASK = "Find this month's top 5 orders."
LOOP_TOOL = {
    "name": "run_sql",
    "description": "Run a SQL query against the orders database.",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}
LOOP_ATTEMPTS = 5


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.init()
    yield


app = FastAPI(title="ZeroDog", lifespan=lifespan)


def _api_error(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def _anthropic_error(kind: str, message: str, status: int, **headers) -> JSONResponse:
    return JSONResponse(
        {"type": "error", "error": {"type": kind, "message": message}},
        status_code=status,
        headers=headers,
    )


def _identify(request: Request) -> tuple[bool, dict | None]:
    """Return whether the caller is allowed in, and which developer they are if known."""
    bearer = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    supplied = request.headers.get("x-api-key") or bearer
    if not supplied:
        return False, None
    developer = store.developer_by_token(supplied)
    if developer:
        return True, developer
    shared = config.settings.gateway_token
    return bool(shared) and hmac.compare_digest(supplied.encode(), shared.encode()), None


def _forwarded_headers(request: Request) -> dict[str, str]:
    return {
        name: value for name, value in request.headers.items() if name.startswith("anthropic-")
    }


def _kept_headers(headers) -> dict[str, str]:
    return {
        name: value
        for name, value in headers.items()
        if name.lower() in FORWARDED_RESPONSE_HEADERS or name.lower().startswith("anthropic-")
    }


def _proxy_context(request: Request, developer: dict | None) -> pipeline.Context:
    prompt_id = request.headers.get("x-claude-code-prompt-id", "")
    request_class = request.headers.get("x-claude-code-request-class", "")
    swaps_allowed = developer is None or bool(developer["swaps_allowed"])
    return pipeline.Context(
        "proxy",
        headers=_forwarded_headers(request),
        query=request.url.query,
        developer_id=developer["id"] if developer else None,
        prompt_id=prompt_id,
        request_class=request_class,
        # Without a prompt ID, tool rounds can't be kept on one model, so nothing is swapped.
        may_swap=bool(prompt_id) and request_class == "main" and swaps_allowed,
    )


def _proxy_reply(outcome: pipeline.Outcome) -> Response:
    if outcome.status in BLOCKED_STATUSES:
        return _anthropic_error(
            "rate_limit_error", outcome.message, 429, **{"x-should-retry": "false"}
        )
    if not outcome.content:
        return _anthropic_error("api_error", outcome.message, outcome.http_status)
    return Response(
        outcome.content,
        outcome.http_status,
        headers=_kept_headers(outcome.headers),
        media_type="application/json",
    )


@app.post("/v1/messages")
async def proxy(request: Request):
    allowed, developer = _identify(request)
    if not allowed:
        return _anthropic_error("authentication_error", "Invalid gateway token.", 401)
    content = await request.body()
    try:
        body = json.loads(content)
    except ValueError:
        return _anthropic_error("invalid_request_error", "Body must be JSON.", 400)
    if not isinstance(body, dict):
        return _anthropic_error("invalid_request_error", "Body must be a JSON object.", 400)

    ctx = _proxy_context(request, developer)
    if not body.get("stream"):
        return _proxy_reply(await pipeline.run(content, body, ctx))

    result = await pipeline.stream(content, body, ctx)
    if isinstance(result, pipeline.Outcome):
        return _proxy_reply(result)
    return StreamingResponse(
        result.chunks(),
        status_code=result.response.status_code,
        headers={**_kept_headers(result.response.headers), "cache-control": "no-cache"},
        media_type="text/event-stream",
    )


@app.post("/v1/messages/count_tokens")
async def count_tokens(request: Request):
    allowed, _ = _identify(request)
    if not allowed:
        return _anthropic_error("authentication_error", "Invalid gateway token.", 401)
    try:
        response = await upstream.post(
            await request.body(),
            _forwarded_headers(request),
            request.url.query,
            path="/v1/messages/count_tokens",
        )
    except httpx.HTTPError as error:
        return _anthropic_error(
            "api_error", f"Could not reach the Anthropic API: {type(error).__name__}.", 502
        )
    return Response(
        response.content,
        response.status_code,
        headers=_kept_headers(response.headers),
        media_type="application/json",
    )


@app.api_route("/api/hello", methods=["GET", "HEAD"])
async def hello():
    """Claude Code probes this at startup."""
    return {"ok": True}


def _active_seconds(payload: dict) -> float:
    """Add up Claude Code's active time from an OTLP JSON metrics export."""
    total = 0.0
    for resource in payload.get("resourceMetrics") or []:
        for scope in resource.get("scopeMetrics") or []:
            for metric in scope.get("metrics") or []:
                if metric.get("name") != config.ACTIVE_TIME_METRIC:
                    continue
                reading = metric.get("sum") or {}
                # Cumulative points repeat the running total, so adding them would overcount.
                if reading.get("aggregationTemporality") == OTLP_CUMULATIVE:
                    continue
                for point in reading.get("dataPoints") or []:
                    total += float(point.get("asDouble") or point.get("asInt") or 0)
    return total


@app.post("/v1/metrics")
async def metrics(request: Request):
    allowed, developer = _identify(request)
    if not allowed:
        return _api_error("Invalid gateway token.", 401)
    content = await request.body()
    if request.headers.get("content-encoding") == "gzip":
        content = gzip.decompress(content)
    try:
        payload = json.loads(content)
    except ValueError:
        return _api_error("Send OTLP metrics as http/json.", 415)
    seconds = _active_seconds(payload) if isinstance(payload, dict) else 0.0
    if developer and seconds:
        store.add_dev_time(developer["id"], seconds)
    return {"partialSuccess": {}}


class PlaygroundCall(BaseModel):
    model: str
    prompt: str
    developer_id: int | None = None
    keep_model: bool = False


@app.post("/api/playground")
async def playground(call: PlaygroundCall):
    prompt = call.prompt.strip()
    if not prompt:
        return _api_error("Enter a prompt before sending.")
    if len(prompt) > config.PROMPT_MAX_CHARS:
        return _api_error(f"Shorten the prompt to {config.PROMPT_MAX_CHARS:,} characters or fewer.")
    if call.model not in config.PLAYGROUND_MODELS:
        return _api_error("Choose one of the listed models.")
    if call.developer_id is not None and not store.get_developer(call.developer_id):
        return _api_error("Choose one of the listed developers.")
    body = {
        "model": call.model,
        "max_tokens": config.PLAYGROUND_MAX_TOKENS,
        "output_config": {"effort": "low"},
        "messages": [{"role": "user", "content": prompt}],
    }
    outcome = await pipeline.run(
        json.dumps(body).encode(),
        body,
        pipeline.Context(
            "playground",
            developer_id=call.developer_id,
            may_swap=True,
            keep_model=call.keep_model,
        ),
    )
    return {
        "status": outcome.status,
        "message": outcome.message,
        "reply": pipeline.reply_text(outcome.data),
        "call": outcome.row,
    }


def _loop_messages(failures: int) -> list[dict]:
    messages = [{"role": "user", "content": LOOP_TASK}]
    for attempt in range(failures):
        tool_id = f"toolu_zerodog_{attempt}"
        messages.append({
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": tool_id, "name": "run_sql",
                "input": {"query": "SELEC * FROM orders"},
            }],
        })
        messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result", "tool_use_id": tool_id, "is_error": True,
                "content": 'syntax error at or near "SELEC"',
            }],
        })
    return messages


@app.post("/api/simulate-loop")
async def simulate_loop():
    """Replays a stuck agent with real Haiku calls until the proxy stops it."""
    statuses = []
    for failures in range(LOOP_ATTEMPTS):
        body = {
            "model": config.HAIKU,
            "max_tokens": 256,
            "output_config": {"effort": "low"},
            "tools": [LOOP_TOOL],
            "messages": _loop_messages(failures),
        }
        outcome = await pipeline.run(
            json.dumps(body).encode(), body, pipeline.Context("simulation", rate=False)
        )
        statuses.append(outcome.status)
        if outcome.status != "OK":
            break
    return {"statuses": statuses}


class RoastRequest(BaseModel):
    text: str


@app.post("/api/roast")
async def roast_stack(body: RoastRequest, request: Request):
    text = body.text.strip()
    if not text:
        return _api_error("Paste a prompt or tool definition to roast.")
    if len(text) > config.ROAST_MAX_CHARS:
        return _api_error(f"Shorten this to {config.ROAST_MAX_CHARS:,} characters or fewer.")
    # A token is optional here. It only attributes roasts sent from Claude Code.
    _, developer = _identify(request)
    return await roast.run(text, developer["id"] if developer else None)


class SettingsUpdate(BaseModel):
    budget_usd: float | None = None
    use_recommended: bool | None = None
    level: int | None = None


@app.put("/api/settings")
async def update_settings(update: SettingsUpdate):
    budget = update.budget_usd
    if budget is not None and (not math.isfinite(budget) or budget < 0):
        return _api_error("Enter a budget of $0 or more.")
    if update.level is not None and update.level not in config.LEVELS:
        return _api_error("Choose a level from 1 to 4.")
    store.update_settings(budget, update.use_recommended, update.level)
    return store.get_settings()


def _with_labels(call: dict) -> dict:
    return {**call, "model_label": team.label(call["model"])}


def _latest_flag(calls: list[dict]) -> dict | None:
    for call in calls:
        if call["status"] not in FLAGGED_STATUSES:
            continue
        flag = {"status": call["status"], "reason": call["reason"]}
        if call["status"] == "Overkill":
            ideal = team.ideal_cost(call) or 0.0
            flag["ideal_label"] = team.label(call["ideal_model"])
            flag["ideal_cost_usd"] = ideal
            flag["projected_monthly_saving_usd"] = max(call["cost_usd"] - ideal, 0.0) * (
                config.PROJECTION_CALLS_PER_DAY * config.DAYS_PER_MONTH
            )
        return flag
    return None


@app.get("/api/calls")
async def calls():
    return [_with_labels(call) for call in store.list_calls()]


@app.get("/api/history")
async def history():
    return team.history()


@app.get("/api/leaderboard")
async def leaderboard():
    return {"minimum_prompts": config.MIN_RATED_PROMPTS, "rows": team.leaderboard()}


@app.get("/api/summary")
async def summary():
    return {
        **store.totals(),
        **store.get_settings(),
        "latest_flag": _latest_flag(store.list_calls()),
        "models": [
            {"id": model, "label": config.MODEL_LABELS[model]}
            for model in config.PLAYGROUND_MODELS
        ],
        "levels": [
            {"level": level, "name": info["name"], "summary": info["summary"]}
            for level, info in config.LEVELS.items()
        ],
        "developers": [
            {"id": developer["id"], "name": developer["name"]}
            for developer in store.list_developers()
        ],
    }


@app.post("/api/reset")
async def reset():
    store.reset()
    return {"ok": True}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")
