"""Local stand-in for the Anthropic API, for trying the UI with no key or spend.

python -m uvicorn tests.fake_upstream:app --port 9100
Then start CaveDawg with ANTHROPIC_UPSTREAM=http://127.0.0.1:9100.
Never point a deployed app at this: every reply and token count is made up.
The Simulated responses switch in the app does the same job without a second server.
"""
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from app import rules, simulated

app = FastAPI()


@app.post("/v1/messages")
async def messages(request: Request):
    body = await request.json()
    if body.get("stream"):
        return PlainTextResponse(simulated.events(body), media_type="text/event-stream")
    return simulated.message(body)


@app.post("/v1/messages/count_tokens")
async def count_tokens(request: Request):
    return {"input_tokens": rules.estimate_tokens(await request.json())}
