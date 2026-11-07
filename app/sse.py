"""Reads usage from a copy of an Anthropic event stream. The bytes themselves are never changed."""
import json


class StreamReader:
    def __init__(self) -> None:
        self.usage: dict = {}
        self.stop_reason: str | None = None
        self.complete = False
        self.error = ""
        self._buffer = b""

    def feed(self, chunk: bytes) -> None:
        # Network chunks can split a line anywhere, so only whole lines are read.
        self._buffer += chunk
        *lines, self._buffer = self._buffer.split(b"\n")
        for line in lines:
            self._read_line(line.strip())

    def _read_line(self, line: bytes) -> None:
        # Text deltas are most of the stream and hold nothing this class needs.
        if not line.startswith(b"data:") or b"content_block" in line[:60]:
            return
        try:
            event = json.loads(line[5:])
        except ValueError:
            return
        kind = event.get("type") if isinstance(event, dict) else None
        if kind == "message_start":
            self._merge((event.get("message") or {}).get("usage"))
        elif kind == "message_delta":
            self._merge(event.get("usage"))
            self.stop_reason = (event.get("delta") or {}).get("stop_reason") or self.stop_reason
        elif kind == "message_stop":
            self.complete = True
        elif kind == "error":
            self.error = (event.get("error") or {}).get("message", "") or "Upstream stream error."

    def _merge(self, usage: dict | None) -> None:
        # message_delta can repeat fields, so the latest non-empty value wins.
        for name, value in (usage or {}).items():
            if value is not None:
                self.usage[name] = value
