"""The one path every call takes: check limits, judge the task, send, record."""
import json
from dataclasses import dataclass, field

import anyio
import httpx

from . import config, costs, jev, rules, sse, store, upstream

# Statuses that mean the upstream refused the swapped model, not that the request was bad.
SWAP_REJECTED_STATUS = {400, 403, 404, 422}
SWAP_FAILED_REASON = "Anthropic rejected the recommended model, so the requested model ran."
DROPPED_REASON = "The stream ended before the reply finished. Tokens shown are what arrived."


@dataclass
class Context:
    """Where a call came from and what may be done to it."""

    source: str
    headers: dict[str, str] | None = None
    query: str = ""
    developer_id: int | None = None
    prompt_id: str = ""
    request_class: str = ""
    ok_status: str = "OK"
    rate: bool = True  # False for CaveDawg's own calls, such as Roast.
    may_swap: bool = False
    keep_model: bool = False


@dataclass
class Verdict:
    kind: str
    ideal: str
    decided_by: str
    note: str


@dataclass
class Plan:
    """A call that passed its limits and is ready to send."""

    requested: str
    model: str
    status: str
    reason: str
    content: bytes
    original: bytes
    snippet: str = ""
    kind: str = ""
    ideal: str = ""
    decided_by: str = ""
    simulated: bool = False


@dataclass
class Outcome:
    status: str
    row: dict
    http_status: int = 200
    content: bytes = b""
    headers: dict = field(default_factory=dict)
    message: str = ""

    @property
    def data(self) -> dict:
        try:
            return json.loads(self.content) if self.content else {}
        except ValueError:
            return {}


async def judge(tokens: int, has_tools: bool, text: str, level: int) -> Verdict:
    """Decide what a task is and which model suits it. Jev first, keyword rules as the fallback."""
    # Jev is a paid outside call, so simulated mode leaves it to the keyword rules.
    use_jev = not has_tools and not store.get_settings()["simulated"]
    kind = await jev.classify(text) if use_jev else None
    decided_by = "Jev" if kind else "Rules"
    kind = kind or rules.classify(tokens, has_tools, text)
    return Verdict(kind, rules.model_for(kind, level), decided_by, rules.note(kind, level))


def _fields(ctx: Context, requested: str, model: str, status: str, reason: str, plan=None) -> dict:
    return {
        "source": ctx.source,
        "requested_model": requested,
        "model": model,
        "status": status,
        "reason": reason,
        "developer_id": ctx.developer_id,
        "prompt_id": ctx.prompt_id,
        "request_class": ctx.request_class,
        "prompt_snippet": plan.snippet if plan else "",
        "task_kind": plan.kind if plan else "",
        "ideal_model": plan.ideal if plan else "",
        "decided_by": plan.decided_by if plan else "",
        "simulated": int(plan.simulated) if plan else 0,
    }


def _refuse(ctx: Context, model: str, status: str, reason: str, saved: float = 0.0) -> Outcome:
    row = store.add_call(**_fields(ctx, model, model, status, reason), saved_usd=saved)
    return Outcome(status=status, row=row, http_status=429, message=reason)


def _input_cost_estimate(model: str, tokens: int) -> float:
    return costs.call_cost(model, tokens, 0) or 0.0


def _check_limits(ctx: Context, model: str, body: dict, simulated: bool) -> Outcome | None:
    if not simulated and store.lifetime_spend() >= config.settings.hard_cap_usd:
        return _refuse(
            ctx, model, "Demo limit reached",
            f"This demo has reached its ${config.settings.hard_cap_usd:.2f} spending limit.",
        )
    totals, current = store.totals(), store.get_settings()
    if totals["spent"] >= current["budget_usd"]:
        return _refuse(
            ctx, model, "Blocked by budget",
            f"Spent ${totals['spent']:.4f} of the ${current['budget_usd']:.4f} budget. "
            "Raise the budget to continue.",
        )
    looping, count, tool = rules.is_loop(body.get("messages", []))
    if looping:
        saved = _input_cost_estimate(model, rules.estimate_tokens(body))
        return _refuse(
            ctx, model, "Loop stopped",
            f"{tool} failed {count} times with the same error, so this retry was stopped. "
            "Saved amount is an estimate of this call's input cost.",
            saved=saved,
        )
    return None


def _swap_model(body: dict, model: str) -> bytes:
    # Key order and every other field survive; only the model value differs.
    return json.dumps({**body, "model": model}, separators=(",", ":")).encode()


async def _verdict_for(ctx: Context, body: dict, text: str, level: int) -> Verdict | None:
    claude_code = ctx.request_class == "main"
    if claude_code and not text:
        return None
    if claude_code:
        # Tools and the system prompt are the same on every call, so only the ask is judged.
        return await judge(len(text) // 4, False, text, level)
    return await judge(rules.estimate_tokens(body), bool(body.get("tools")), text, level)


async def _prepare(content: bytes, body: dict, ctx: Context) -> Plan | Outcome:
    requested = str(body.get("model", "unknown"))
    # Read once, so the row always says where this call really went.
    simulated = store.get_settings()["simulated"]
    refused = _check_limits(ctx, requested, body, simulated)
    if refused:
        return refused

    text = rules.last_user_text(body.get("messages", []))
    plan = Plan(
        requested, requested, ctx.ok_status, "", content, content,
        snippet=rules.snippet(text), simulated=simulated,
    )
    # Background Claude Code calls aren't the developer's choice, so they run as sent and unrated.
    if not ctx.rate or ctx.request_class not in {"", "main"}:
        return plan

    prior = store.prompt_decision(ctx.prompt_id) if ctx.prompt_id else None
    if prior:
        # Tool rounds of one prompt stay on one model, and their text is only tool results.
        plan.kind, plan.ideal, plan.decided_by = (
            prior["task_kind"], prior["ideal_model"], prior["decided_by"]
        )
        plan.snippet = prior["prompt_snippet"]
        plan.status, plan.reason = _status_for(ctx, plan, swap=prior["model"] != requested)
        if prior["model"] != requested:
            plan.model = prior["model"]
            plan.content = _swap_model(body, prior["model"])
        return plan

    current = store.get_settings()
    verdict = await _verdict_for(ctx, body, text, current["level"])
    if verdict is None:
        return plan
    plan.kind, plan.ideal, plan.decided_by = verdict.kind, verdict.ideal, verdict.decided_by
    if ctx.source == "proxy" and ctx.request_class == "main":
        _live_roast(ctx, plan, verdict, text)

    swap = (
        ctx.may_swap
        and current["use_recommended"]
        and not ctx.keep_model
        and not rules.has_keep_tag(text)
        and requested in config.MODEL_RANK
        and requested != verdict.ideal
    )
    plan.status, plan.reason = _status_for(ctx, plan, swap)
    if swap:
        plan.model = verdict.ideal
        plan.content = _swap_model(body, verdict.ideal)
    return plan


def _live_roast(ctx: Context, plan: Plan, verdict: Verdict, text: str) -> None:
    """Score a Claude Code prompt with the Roast rules, once per prompt and with no model call."""
    from . import roast  # roast imports this module

    points, issues = roast.score(text, len(text) // 4)
    store.add_live_roast(
        developer_id=ctx.developer_id,
        prompt_id=ctx.prompt_id,
        snippet=plan.snippet,
        score=points,
        issues=issues,
        ideal_model=verdict.ideal,
        decided_by=verdict.decided_by,
        note=verdict.note,
    )


def _status_for(ctx: Context, plan: Plan, swap: bool) -> tuple[str, str]:
    ideal_label = config.MODEL_LABELS.get(plan.ideal, plan.ideal)
    if rules.runs_above(plan.requested, plan.ideal):
        if swap:
            return "Downshifted", (
                f"Moved to {ideal_label}, the ideal model. Saved amount uses this call's real tokens."
            )
        return "Overkill", f"{ideal_label} is the ideal model for this task at this routing level."
    if swap:
        return "Upshifted", f"Moved up to {ideal_label}, the ideal model. This costs more."
    return ctx.ok_status, ""


def _swap_was_rejected(plan: Plan, status: int) -> bool:
    return plan.model != plan.requested and status in SWAP_REJECTED_STATUS


def _fall_back(plan: Plan) -> None:
    plan.model, plan.content = plan.requested, plan.original
    plan.status, plan.reason = "Swap failed", SWAP_FAILED_REASON


def _record(ctx: Context, plan: Plan, status: str, reason: str, usage: dict | None = None) -> dict:
    usage = usage or {}
    cost = costs.usage_cost(plan.model, usage)
    if cost is None:
        cost, reason = 0.0, reason or f"No price is listed for {plan.model}, so its cost isn't counted."
    saved = 0.0
    if status == "Downshifted":
        saved = max((costs.usage_cost(plan.requested, usage) or cost) - cost, 0.0)
    return store.add_call(
        **_fields(ctx, plan.requested, plan.model, status, reason, plan),
        input_tokens=usage.get("input_tokens", 0) or 0,
        output_tokens=usage.get("output_tokens", 0) or 0,
        cache_read_tokens=usage.get("cache_read_input_tokens", 0) or 0,
        cache_write_tokens=usage.get("cache_creation_input_tokens", 0) or 0,
        cost_usd=cost,
        saved_usd=saved,
    )


def _refused_or(plan: Plan, stop_reason: str | None) -> tuple[str, str]:
    if stop_reason == "refusal":
        return "Refused", "Claude declined this request."
    return plan.status, plan.reason


def _unreachable(ctx: Context, plan: Plan, error: httpx.HTTPError) -> Outcome:
    reason = f"Could not reach the Anthropic API: {type(error).__name__}."
    row = _record(ctx, plan, "Error", reason)
    return Outcome("Error", row, http_status=502, message=reason)


async def _send(plan: Plan, ctx: Context) -> httpx.Response:
    return await upstream.post(plan.content, ctx.headers, ctx.query, simulated=plan.simulated)


async def run(content: bytes, body: dict, ctx: Context) -> Outcome:
    plan = await _prepare(content, body, ctx)
    if isinstance(plan, Outcome):
        return plan
    try:
        response = await _send(plan, ctx)
        if _swap_was_rejected(plan, response.status_code):
            _fall_back(plan)
            response = await _send(plan, ctx)
    except httpx.HTTPError as error:
        return _unreachable(ctx, plan, error)

    if response.status_code >= 400:
        reason = _error_message(response)
        row = _record(ctx, plan, "Error", reason)
        return Outcome(
            "Error", row, response.status_code, response.content, dict(response.headers), reason
        )

    data = response.json()
    status, reason = _refused_or(plan, data.get("stop_reason"))
    row = _record(ctx, plan, status, reason, data.get("usage") or {})
    return Outcome(status, row, response.status_code, response.content, dict(response.headers), reason)


@dataclass
class Stream:
    """An open upstream stream. Reading it forwards bytes and records the call at the end."""

    plan: Plan
    ctx: Context
    client: httpx.AsyncClient
    response: httpx.Response

    async def chunks(self):
        reader = sse.StreamReader()
        failure = ""
        try:
            async for chunk in self.response.aiter_raw():
                reader.feed(chunk)
                yield chunk
        except httpx.HTTPError as error:
            # Re-raised so the client sees a dropped connection, never a tidy ending.
            failure = f"The stream failed: {type(error).__name__}."
            raise
        finally:
            self._finish(reader, failure)
            with anyio.CancelScope(shield=True):
                await self.response.aclose()
                await self.client.aclose()

    def _finish(self, reader: sse.StreamReader, failure: str) -> None:
        if failure or reader.error:
            status, reason = "Error", failure or reader.error
        elif not reader.complete:
            status, reason = "Dropped", DROPPED_REASON
        else:
            status, reason = _refused_or(self.plan, reader.stop_reason)
        _record(self.ctx, self.plan, status, reason, reader.usage)


async def _open(plan: Plan, ctx: Context) -> tuple[httpx.AsyncClient, httpx.Response]:
    return await upstream.open_stream(
        plan.content, ctx.headers, ctx.query, simulated=plan.simulated
    )


async def stream(content: bytes, body: dict, ctx: Context) -> Stream | Outcome:
    """Run the checks, then open the stream. Limits and upstream errors still return an Outcome."""
    plan = await _prepare(content, body, ctx)
    if isinstance(plan, Outcome):
        return plan
    try:
        client, response = await _open(plan, ctx)
        if _swap_was_rejected(plan, response.status_code):
            await response.aclose()
            await client.aclose()
            _fall_back(plan)
            client, response = await _open(plan, ctx)
    except httpx.HTTPError as error:
        return _unreachable(ctx, plan, error)

    if response.status_code < 400:
        return Stream(plan, ctx, client, response)

    raw = await response.aread()
    failed = httpx.Response(response.status_code, content=raw)
    headers = dict(response.headers)
    await response.aclose()
    await client.aclose()
    reason = _error_message(failed)
    row = _record(ctx, plan, "Error", reason)
    return Outcome("Error", row, failed.status_code, raw, headers, reason)


def _error_message(response: httpx.Response) -> str:
    try:
        detail = response.json().get("error", {}).get("message", "")
    except ValueError:
        detail = ""
    return f"Anthropic API returned {response.status_code}. {detail}".strip()


def reply_text(data: dict) -> str:
    blocks = data.get("content") or []
    return "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
