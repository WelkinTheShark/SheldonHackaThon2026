"""Forwards requests to the Anthropic API.

This uses raw HTTP rather than the SDK on purpose: a proxy has to pass request
bytes and anthropic-* headers through unchanged.
"""
import httpx

from . import config, simulated as simulator

API_VERSION = "2023-06-01"
TIMEOUT_SECONDS = 300.0
STREAM_TIMEOUT = httpx.Timeout(600.0, connect=10.0)

# Tests replace this with httpx.MockTransport.
transport: httpx.AsyncBaseTransport | None = None


def _transport(simulated: bool) -> httpx.AsyncBaseTransport | None:
    return simulator.transport if simulated else transport


def _url(path: str, query: str) -> str:
    base = f"{config.settings.upstream.rstrip('/')}{path}"
    return f"{base}?{query}" if query else base


def _headers(headers: dict[str, str] | None) -> dict[str, str]:
    return {
        "content-type": "application/json",
        "anthropic-version": API_VERSION,
        # Compressed event streams couldn't be read for usage.
        "accept-encoding": "identity",
        **(headers or {}),
        "x-api-key": config.settings.api_key,
    }


async def post(
    content: bytes,
    headers: dict[str, str] | None = None,
    query: str = "",
    path: str = "/v1/messages",
    simulated: bool = False,
) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=_transport(simulated), timeout=TIMEOUT_SECONDS
    ) as client:
        return await client.post(_url(path, query), content=content, headers=_headers(headers))


async def open_stream(
    content: bytes,
    headers: dict[str, str] | None = None,
    query: str = "",
    simulated: bool = False,
) -> tuple[httpx.AsyncClient, httpx.Response]:
    """Start a streaming request. The caller must close both the response and the client."""
    client = httpx.AsyncClient(transport=_transport(simulated), timeout=STREAM_TIMEOUT)
    try:
        request = client.build_request(
            "POST", _url("/v1/messages", query), content=content, headers=_headers(headers)
        )
        return client, await client.send(request, stream=True)
    except BaseException:
        await client.aclose()
        raise
