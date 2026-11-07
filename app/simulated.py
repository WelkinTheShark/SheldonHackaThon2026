"""Canned Anthropic replies, so the whole app can run with no key and no spend.

The Simulated responses switch sends calls here instead of to Anthropic. Everything else in the
pipeline still runs. Tokens are estimated from the request, so amounts are never real spend.
"""
import json

import httpx

from . import rules

REPLY = "Simulated reply. CaveDawg sent nothing to Anthropic, so this did not come from Claude."
OUTPUT_TOKENS = 60


def usage(body: dict) -> dict:
    return {"input_tokens": max(rules.estimate_tokens(body), 1), "output_tokens": OUTPUT_TOKENS}


def message(body: dict) -> dict:
    return {
        "id": "msg_simulated",
        "type": "message",
        "role": "assistant",
        "model": body.get("model", ""),
        "content": [{"type": "text", "text": REPLY}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": usage(body),
    }


def _event(data: dict) -> str:
    return f"event: {data['type']}\ndata: {json.dumps(data)}\n\n"


def events(body: dict) -> str:
    """The same reply as a complete event stream."""
    start = {
        **message(body), "content": [], "stop_reason": None,
        "usage": {**usage(body), "output_tokens": 1},
    }
    return "".join(_event(item) for item in [
        {"type": "message_start", "message": start},
        {"type": "ping"},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": REPLY}},
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": OUTPUT_TOKENS},
        },
        {"type": "message_stop"},
    ])


async def _handle(request: httpx.Request) -> httpx.Response:
    try:
        body = json.loads(request.content)
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return httpx.Response(400, json={
            "type": "error",
            "error": {"type": "invalid_request_error", "message": "Body must be a JSON object."},
        })
    headers = {"request-id": "req_simulated"}
    if request.url.path.endswith("/count_tokens"):
        return httpx.Response(200, json={"input_tokens": usage(body)["input_tokens"]}, headers=headers)
    if body.get("stream"):
        return httpx.Response(
            200,
            stream=httpx.ByteStream(events(body).encode()),
            headers={**headers, "content-type": "text/event-stream"},
        )
    return httpx.Response(200, json=message(body), headers=headers)


transport = httpx.MockTransport(_handle)
