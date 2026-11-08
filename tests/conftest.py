import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config, jev, main, store, upstream

USAGE = {"input_tokens": 30, "output_tokens": 60}


def sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def stream_events(model: str, stop_reason: str = "end_turn") -> list[bytes]:
    return [
        sse("message_start", {
            "type": "message_start",
            "message": {
                "id": "msg_1", "role": "user", "model": model, "content": [],
                "usage": {
                    "input_tokens": 30, "output_tokens": 1,
                    "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 200,
                },
            },
        }),
        sse("ping", {"type": "ping"}),
        sse("content_block_start", {
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "text", "text": ""},
        }),
        sse("content_block_delta", {
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "text_delta", "text": "stub reply"},
        }),
        sse("content_block_stop", {"type": "content_block_stop", "index": 0}),
        sse("message_delta", {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason},
            "usage": {"output_tokens": 60},
        }),
        sse("message_stop", {"type": "message_stop"}),
    ]


class FakeAnthropic:
    """Stands in for the Anthropic API and records what it was sent."""

    def __init__(self):
        self.requests = []
        self.status = 200
        self.reply_text = "stub reply"
        self.error = None
        self.stop_reason = "end_turn"
        self.rejected_models = set()
        self.events = None  # Replaces the normal event list for one scenario.
        self.chunk_size = None
        self.fail_after = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error:
            raise self.error
        if self.status >= 400:
            return httpx.Response(
                self.status, json={"type": "error", "error": {"message": "Overloaded"}}
            )
        if request.url.path.endswith("/count_tokens"):
            return httpx.Response(200, json={"input_tokens": 12})
        body = json.loads(request.content)
        if body["model"] in self.rejected_models:
            return httpx.Response(
                400, json={"type": "error", "error": {"message": "Unsupported parameter"}}
            )
        if body.get("stream"):
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream", "request-id": "req_1"},
                content=self._stream(body["model"]),
            )
        return httpx.Response(
            200,
            json={
                "model": body["model"],
                "content": [{"type": "text", "text": self.reply_text}],
                "stop_reason": self.stop_reason,
                "usage": USAGE,
            },
        )

    async def _stream(self, model: str):
        raw = b"".join(
            self.events if self.events is not None else stream_events(model, self.stop_reason)
        )
        size = self.chunk_size or len(raw) or 1
        for start in range(0, len(raw), size):
            if self.fail_after is not None and start >= self.fail_after:
                raise httpx.ReadError("connection lost")
            yield raw[start:start + size]

    @property
    def message_requests(self):
        return [r for r in self.requests if r.url.path == "/v1/messages"]

    @property
    def models(self):
        return [json.loads(r.content)["model"] for r in self.message_requests]


class FakeJev:
    """Stands in for Jev. The default answer is a confident mechanical task."""

    def __init__(self):
        self.requests = []
        self.answers = jev_answers("mechanical")
        self.status = 200
        self.error = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        if self.error:
            raise self.error
        return httpx.Response(self.status, json={"answers": self.answers})


def jev_answers(kind="unclear", probability=0.9, investigate=0.1, score_confidence=0.8) -> dict:
    return {
        "task_kind": {
            "type": "choice", "choice": kind, "confidence": probability,
            "probabilities": {kind: probability},
        },
        "complexity": {"type": "score", "score": 1.0, "confidence": score_confidence},
        "needs_investigation": {"type": "noul", "noul": investigate},
    }


@pytest.fixture
def anthropic(monkeypatch):
    fake = FakeAnthropic()
    monkeypatch.setattr(upstream, "transport", httpx.MockTransport(fake))
    return fake


@pytest.fixture
def client(tmp_path, monkeypatch, anthropic):
    monkeypatch.setattr(config.settings, "db_path", str(tmp_path / "test.db"))
    monkeypatch.setattr(config.settings, "gateway_token", "gateway-secret")
    monkeypatch.setattr(config.settings, "api_key", "upstream-secret")
    monkeypatch.setattr(config.settings, "typesafe_api_key", "")
    monkeypatch.setattr(config.settings, "hard_cap_usd", 5.0)
    # The page signs in with a token. Tests act as the gateway Admin unless they say otherwise.
    with TestClient(main.app, headers={"x-cavedawg-token": "gateway-secret"}) as test_client:
        yield test_client
    store._db.close()
    store._db = None


@pytest.fixture
def fake_jev(client, monkeypatch):
    fake = FakeJev()
    monkeypatch.setattr(jev, "transport", httpx.MockTransport(fake))
    monkeypatch.setattr(config.settings, "typesafe_api_key", "jev-secret")
    return fake


@pytest.fixture
def developer(client):
    """A registered developer's auth headers and record."""
    record, token = store.add_developer("Ada")
    return {"authorization": f"Bearer {token}"}, record
