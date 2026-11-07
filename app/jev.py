"""Asks Jev what a prompt is. Any failure returns None, and the keyword rules take over.

Raw HTTP on purpose: the SDK is young and has had breaking changes between minor versions.
"""
import asyncio

import httpx

from . import config

# Tests replace this with httpx.MockTransport.
transport: httpx.AsyncBaseTransport | None = None

KINDS = {
    "routine": "routine",
    "mechanical": "simple",
    "unclear": "grey",
    "agent_setup": "heavy",
    "investigation": "deep",
    "design": "deep",
}
QUESTIONS = {
    "task_kind": {
        "type": "choice",
        "instructions": "What kind of software task does this developer prompt ask for?",
        "criteria": {
            "routine": "A git commit, a git push, a commit message, or one fact that can be looked up.",
            "mechanical": "A fixed transformation with one right answer, such as formatting or renaming.",
            "unclear": "Too vague to tell, or a task that fits none of the other options.",
            "agent_setup": "A long system prompt, tool setup, or multi-step agent configuration.",
            "investigation": "Finding a cause: debugging, tracing a failure, or explaining odd behaviour.",
            "design": "Weighing options: architecture, trade-offs, security, or a plan across systems.",
        },
    },
    "complexity": {
        "type": "score",
        "instructions": "How much reasoning does this prompt need to be done well?",
        "criteria": [
            "None: the answer is immediate or mechanical.",
            "Low: one straightforward step.",
            "Medium: several steps within one area of the code.",
            "High: unknown causes, or decisions across several systems.",
        ],
    },
    "needs_investigation": {
        "type": "noul",
        "instructions": "Completing this prompt requires investigating something unknown.",
        "criteria": {
            "true": "The cause, location, or right approach must be found before acting.",
            "false": "The task is fully stated, and it could be done without exploring anything.",
        },
    },
}


def kind_from(answers: dict) -> str:
    """Turn Jev's answers into a task kind, using the thresholds from its confidence guide."""
    investigate = answers["needs_investigation"]["noul"]
    if investigate > config.JEV_YES:
        return "deep"

    choice = answers["task_kind"]
    picked = choice["choice"]
    if choice["probabilities"][picked] < config.JEV_MIN_CHOICE:
        return "grey"
    if answers["complexity"]["confidence"] < config.JEV_MIN_SCORE_CONFIDENCE:
        return "grey"

    kind = KINDS[picked]
    # A real chance of investigation rules out the two cheapest kinds.
    if investigate >= config.JEV_NO and kind in {"routine", "simple"}:
        return "grey"
    return kind


async def _ask(text: str) -> dict:
    async with httpx.AsyncClient(
        transport=transport, timeout=config.JEV_TIMEOUT_SECONDS
    ) as client:
        response = await client.post(
            config.settings.jev_url,
            headers={"authorization": f"Bearer {config.settings.typesafe_api_key}"},
            json={
                "model": config.JEV_MODEL,
                "state": text[: config.JEV_MAX_STATE_CHARS],
                "questions": QUESTIONS,
            },
        )
    response.raise_for_status()
    return response.json()["answers"]


async def classify(text: str) -> str | None:
    if not config.settings.typesafe_api_key or not text.strip():
        return None
    try:
        answers = await asyncio.wait_for(_ask(text), config.JEV_TIMEOUT_SECONDS)
        return kind_from(answers)
    except (httpx.HTTPError, asyncio.TimeoutError, ValueError, KeyError, TypeError):
        return None
