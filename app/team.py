"""Delivery history and the leaderboard, both built from recorded calls."""
from datetime import datetime

from . import config, costs, store

# When one prompt has many calls, its row shows the most important status.
STATUS_ORDER = [
    "Error", "Dropped", "Loop stopped", "Blocked by budget", "Demo limit reached", "Refused",
    "Swap failed", "Downshifted", "Upshifted", "Overkill", "Roast", "OK",
]
UNATTRIBUTED = "Unattributed"


def label(model: str) -> str:
    return config.MODEL_LABELS.get(model, model)


def total_tokens(call: dict) -> int:
    return (
        call["input_tokens"] + call["output_tokens"]
        + call["cache_read_tokens"] + call["cache_write_tokens"]
    )


def ideal_cost(call: dict) -> float | None:
    """What this call's real tokens would have cost on its ideal model."""
    return costs.call_cost(
        call["ideal_model"], call["input_tokens"], call["output_tokens"],
        call["cache_read_tokens"], call["cache_write_tokens"],
    )


def overspend(call: dict) -> float:
    """Dollars above ideal. Calls on or below their ideal model count as zero."""
    rank = config.MODEL_RANK
    if rank.get(call["model"], -1) <= rank.get(call["ideal_model"], 99):
        return 0.0
    return max(call["cost_usd"] - (ideal_cost(call) or 0.0), 0.0)


def _names() -> dict:
    return {developer["id"]: developer["name"] for developer in store.list_developers()}


def _prompt_key(call: dict) -> str:
    return call["prompt_id"] or f"call-{call['id']}"


def _worst_status(calls: list[dict]) -> dict:
    return min(
        calls,
        key=lambda c: STATUS_ORDER.index(c["status"]) if c["status"] in STATUS_ORDER else 99,
    )


def history(limit: int = config.HISTORY_LIMIT) -> list[dict]:
    """One row per prompt, newest first. A Claude Code prompt can span many calls."""
    names = _names()
    groups: dict[str, list[dict]] = {}
    for call in reversed(store.list_calls(limit * 20)):
        groups.setdefault(_prompt_key(call), []).append(call)

    rows = []
    for calls in groups.values():
        first, shown = calls[0], _worst_status(calls)
        ideal = next((c["ideal_model"] for c in calls if c["ideal_model"]), "")
        rows.append({
            "id": calls[-1]["id"],
            "ts": first["ts"],
            "developer": names.get(first["developer_id"], UNATTRIBUTED),
            "prompt": next((c["prompt_snippet"] for c in calls if c["prompt_snippet"]), ""),
            "kind": first["task_kind"],
            "ideal_label": label(ideal) if ideal else "",
            "used_label": label(calls[-1]["model"]),
            "requested_label": label(first["requested_model"]),
            "decided_by": first["decided_by"],
            "calls": len(calls),
            "tokens": sum(total_tokens(c) for c in calls),
            "cost_usd": sum(c["cost_usd"] for c in calls),
            "status": shown["status"],
            "reason": shown["reason"],
        })
    rows.sort(key=lambda row: row["id"], reverse=True)
    return rows[:limit]


def active_seconds(timestamps: list[str]) -> float:
    """Time between calls, treating any gap over the idle limit as time away."""
    moments = sorted(datetime.fromisoformat(ts) for ts in timestamps)
    gaps = ((later - earlier).total_seconds() for earlier, later in zip(moments, moments[1:]))
    return sum(gap for gap in gaps if gap <= config.IDLE_GAP_SECONDS)


def leaderboard() -> list[dict]:
    names = _names()
    measured = store.measured_dev_time()
    by_developer: dict[int | None, list[dict]] = {developer: [] for developer in names}
    for call in store.list_calls(-1):
        by_developer.setdefault(call["developer_id"], []).append(call)

    rows = []
    for developer, calls in by_developer.items():
        known = developer in names
        if not known and not calls:
            continue
        rated = [c for c in calls if c["ideal_model"]]
        rated_cost = sum(c["cost_usd"] for c in rated)
        over = sum(overspend(c) for c in rated)
        prompts = len({_prompt_key(c) for c in rated})
        has_time = developer in measured
        rows.append({
            "developer": names.get(developer, UNATTRIBUTED),
            "prompts": prompts,
            "tokens": sum(total_tokens(c) for c in calls),
            "cost_usd": sum(c["cost_usd"] for c in calls),
            "dev_seconds": measured[developer] if has_time else active_seconds(
                [c["ts"] for c in calls]
            ),
            "dev_time_source": "Measured" if has_time else "Estimate",
            "overuse_percent": over / rated_cost * 100 if rated_cost else 0.0,
            "overspend_usd": over,
            "rankable": known and prompts >= config.MIN_RATED_PROMPTS,
        })

    ranked = sorted(
        (r for r in rows if r["rankable"]), key=lambda r: (r["overuse_percent"], -r["prompts"])
    )
    for position, row in enumerate(ranked, start=1):
        row["rank"] = position
    unranked = sorted(
        (r for r in rows if not r["rankable"]), key=lambda r: r["developer"] == UNATTRIBUTED
    )
    for row in unranked:
        row["rank"] = None
    return [{k: v for k, v in row.items() if k != "rankable"} for row in ranked + unranked]
