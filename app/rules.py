"""Plain rules for sorting tasks and spotting loops. Jev goes first when it is configured."""
import json
import re

from . import config

SIMPLE_TASK = re.compile(r"\b(commit message|format|formatting|regex|rename|json)\b", re.I)
DEEP_TASK = re.compile(
    r"\b(architecture|design|failover|trade-?offs?|failure modes?|threat model|root cause"
    r"|investigate|investigation|debug|debugging|diagnose|troubleshoot|figure out|trace"
    r"|why|wrong|broken|failing|fails|failed|not working|bug|compare|audit|analy[sz]e)\b",
    re.I,
)
# Anchored to the start, so "Refactor auth, then commit and push" isn't treated as routine.
COMMIT_MESSAGE = re.compile(
    r"^\s*(please\s+)?(write|draft|generate|create|suggest|give me)\b[^.?!\n]{0,30}\bcommit message",
    re.I,
)
COMMIT_OR_PUSH = re.compile(r"^\s*(please\s+)?(git\s+)?(commit|push)\b", re.I)
LOOKUP = re.compile(r"^\s*(what('s| is| are)|who|when|where|which|define|look up|how many)\b", re.I)
REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
KEEP_TAG = re.compile(r"(?<!\S)#keep\b", re.I)
TASK_NOTES = {
    "routine": "Commit, push or single-fact lookup",
    "simple": "Mechanical task",
    "grey": "Unclear task",
    "heavy": "Tools or a long setup",
    "deep": "Investigation or design work",
}


def estimate_tokens(body: dict) -> int:
    """Rough pre-call size: about 4 characters per token."""
    parts = [body.get("system"), body.get("messages"), body.get("tools")]
    return sum(len(json.dumps(p, ensure_ascii=False)) for p in parts if p) // 4


def last_user_text(messages: list) -> str:
    """The human's latest words, without Claude Code's injected reminders or tool results."""
    for message in reversed(messages or []):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, list):
            content = " ".join(
                block.get("text", "") for block in content if block.get("type") == "text"
            )
        return REMINDER.sub("", content).strip() if isinstance(content, str) else ""
    return ""


def snippet(text: str) -> str:
    return " ".join(text.split())[: config.SNIPPET_CHARS]


def has_keep_tag(text: str) -> bool:
    return KEEP_TAG.search(text or "") is not None


def classify(estimated_tokens: int, has_tools: bool, text: str) -> str:
    """Sort a task into a kind. Anything needing investigation outranks the cheap kinds."""
    text = text or ""
    long_or_tooled = has_tools or estimated_tokens >= config.OVERKILL_MAX_TOKENS
    # The words after "commit message for:" describe the change, not the task.
    if not long_or_tooled and COMMIT_MESSAGE.search(text):
        return "routine"
    if DEEP_TASK.search(text):
        return "deep"
    if long_or_tooled:
        return "heavy"
    if estimated_tokens < config.ROUTINE_MAX_TOKENS and (
        COMMIT_OR_PUSH.search(text) or LOOKUP.search(text)
    ):
        return "routine"
    return "simple" if SIMPLE_TASK.search(text) else "grey"


def model_for(kind: str, level: int) -> str:
    return config.LEVELS[level]["routes"][kind]


def note(kind: str, level: int) -> str:
    return f"{TASK_NOTES[kind]} at the {config.LEVELS[level]['name']} level."


def runs_above(requested: str, ideal: str) -> bool:
    """True when a call asks for a costlier model than its task needs. Unknown models never match."""
    rank = config.MODEL_RANK
    return requested in rank and ideal in rank and rank[requested] > rank[ideal]


def _error_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
    return ""


def repeated_tool_errors(messages: list) -> tuple[int, str]:
    """Count the identical tool errors at the end of a conversation.

    Agents resend their history on every call, so the request itself holds the
    evidence and the proxy needs no per-session state.
    """
    tool_names: dict[str, str] = {}
    count, last_signature, tool = 0, None, ""
    for message in messages or []:
        content = message.get("content")
        blocks = content if isinstance(content, list) else []
        if message.get("role") == "assistant":
            for block in blocks:
                if block.get("type") == "tool_use":
                    tool_names[block.get("id", "")] = block.get("name", "")
            continue
        results = [b for b in blocks if b.get("type") == "tool_result"]
        if not results:
            count, last_signature = 0, None
            continue
        for block in results:
            if not block.get("is_error"):
                count, last_signature = 0, None
                continue
            name = tool_names.get(block.get("tool_use_id", ""), "unknown tool")
            signature = (name, _error_text(block))
            count = count + 1 if signature == last_signature else 1
            last_signature, tool = signature, name
    return count, tool


def is_loop(messages: list) -> tuple[bool, int, str]:
    count, tool = repeated_tool_errors(messages)
    return count >= config.LOOP_LIMIT, count, tool
