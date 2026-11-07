"""Local stand-in for the Anthropic API, for trying the UI with no key or spend.

python -m uvicorn tests.fake_upstream:app --port 9100
Then start ZeroDog with ANTHROPIC_UPSTREAM=http://127.0.0.1:9100.
Never point a deployed app at this: every reply and token count is made up.
"""
import json

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()
REPLY = "Stub reply from the local test server."
USAGE = {"input_tokens": 40, "output_tokens": 60}


def _event(data: dict) -> str:
    return f"event: {data['type']}\ndata: {json.dumps(data)}\n\n"


async def _stream(model: str):
    message = {
        "id": "msg_stub", "type": "message", "role": "assistant", "model": model, "content": [],
        "stop_reason": None, "stop_sequence": None, "usage": {**USAGE, "output_tokens": 1},
    }
    yield _event({"type": "message_start", "message": message})
    yield _event({"type": "ping"})
    yield _event({
        "type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""},
    })
    yield _event({
        "type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": REPLY},
    })
    yield _event({"type": "content_block_stop", "index": 0})
    yield _event({
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
        "usage": {"output_tokens": USAGE["output_tokens"]},
    })
    yield _event({"type": "message_stop"})


@app.post("/v1/messages")
async def messages(request: Request):
    body = await request.json()
    if body.get("stream"):
        return StreamingResponse(_stream(body["model"]), media_type="text/event-stream")
    return {
        "id": "msg_stub",
        "type": "message",
        "role": "assistant",
        "model": body["model"],
        "content": [{"type": "text", "text": REPLY}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": USAGE,
    }


@app.post("/v1/messages/count_tokens")
async def count_tokens(request: Request):
    body = await request.json()
    return {"input_tokens": len(json.dumps(body)) // 4}
