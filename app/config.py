"""All tunable values live here. Prices are USD per million tokens."""
import os
from dataclasses import dataclass, field

OPUS = "claude-opus-5-5"
SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"
FABLE = "claude-fable-5-1"

# https://platform.claude.com/docs/en/about-claude/pricing (checked 2026-11-05)
PRICES = {
    FABLE: {"input": 10.0, "output": 50.0, "cache_write": 12.5, "cache_read": 0.25},
    OPUS: {"input": 4.0, "output": 20.0, "cache_write": 5.0, "cache_read": 0.20},
    SONNET: {"input": 2.0, "output": 10.0, "cache_write": 2.5, "cache_read": 0.10},
    HAIKU: {"input": 0.10, "output": 0.50, "cache_write": 0.125, "cache_read": 0.01},
}
# Haiku 5.5 costs more on prompts over 100,000 tokens.
HAIKU_LONG_PROMPT_TOKENS = 100_000
HAIKU_LONG_PRICES = {"input": 0.50, "output": 2.50, "cache_write": 0.625, "cache_read": 0.05}

MODEL_LABELS = {
    FABLE: "Fable 5.1",
    OPUS: "Opus 5.5",
    SONNET: "Sonnet 5.5",
    HAIKU: "Haiku 5.5",
}
PLAYGROUND_MODELS = [OPUS, SONNET, HAIKU]
# Cheapest first. A model above the ideal one is overkill; a model below it is underpowered.
MODEL_RANK = {HAIKU: 0, SONNET: 1, OPUS: 2, FABLE: 3}

# https://docs.typesafe.ai/api/system-one.md (checked 2026-11-06)
JEV_MODEL = "jev-latest"
JEV_TIMEOUT_SECONDS = 1.5
JEV_MAX_STATE_CHARS = 8_000
JEV_YES = 0.7
JEV_NO = 0.3
JEV_MIN_CHOICE = 0.7
JEV_MIN_SCORE_CONFIDENCE = 0.5

SNIPPET_CHARS = 80
MIN_RATED_PROMPTS = 5
IDLE_GAP_SECONDS = 300
HISTORY_LIMIT = 100
ACTIVE_TIME_METRIC = "claude_code.active_time.total"

# The routing bar. Task kinds are set in rules.classify; each level maps them to a model.
# "routine" stays on Haiku everywhere, and "deep" never drops below Sonnet.
DEFAULT_LEVEL = 2
LEVELS = {
    1: {
        "name": "Fastest",
        "summary": "Unclear tasks run on Haiku. Investigation and design run on Sonnet.",
        "routes": {"routine": HAIKU, "simple": HAIKU, "grey": HAIKU, "heavy": SONNET, "deep": SONNET},
    },
    2: {
        "name": "Balanced",
        "summary": "Unclear tasks run on Sonnet. Investigation and design run on Opus.",
        "routes": {"routine": HAIKU, "simple": HAIKU, "grey": SONNET, "heavy": SONNET, "deep": OPUS},
    },
    3: {
        "name": "Thorough",
        "summary": "Unclear tasks and agent setups run on Opus. Mechanical tasks run on Sonnet.",
        "routes": {"routine": HAIKU, "simple": SONNET, "grey": OPUS, "heavy": OPUS, "deep": OPUS},
    },
    4: {
        "name": "Full power",
        "summary": "Everything runs on Opus except commits, pushes and single-fact lookups.",
        "routes": {"routine": HAIKU, "simple": OPUS, "grey": OPUS, "heavy": OPUS, "deep": OPUS},
    },
}

PASSWORD_MIN_CHARS = 8
DEMO_TEAM = "Demo"

OVERKILL_MAX_TOKENS = 4_000
ROUTINE_MAX_TOKENS = 60
LOOP_LIMIT = 3
PLAYGROUND_MAX_TOKENS = 2_048
PROMPT_MAX_CHARS = 8_000
ROAST_MAX_CHARS = 20_000
DEFAULT_BUDGET_USD = 1000.00  # the shared team budget; Reset demo returns it to this
# Each new user's own budget. Change it per user on User management; clearing it means no limit.
DEFAULT_USER_BUDGET_USD = 1000.00
DAYS_PER_MONTH = 30
PROJECTION_CALLS_PER_DAY = 100


@dataclass
class Settings:
    api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    gateway_token: str = field(default_factory=lambda: os.environ.get("CAVEDAWG_GATEWAY_TOKEN", ""))
    upstream: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_UPSTREAM", "https://api.anthropic.com")
    )
    typesafe_api_key: str = field(default_factory=lambda: os.environ.get("TYPESAFE_API_KEY", ""))
    jev_url: str = field(
        default_factory=lambda: os.environ.get(
            "CAVEDAWG_JEV_URL", "https://api.typesafe.ai/v1/systemone"
        )
    )
    public_url: str = field(
        default_factory=lambda: os.environ.get("CAVEDAWG_PUBLIC_URL", "http://127.0.0.1:8000")
    )
    db_path: str = field(default_factory=lambda: os.environ.get("CAVEDAWG_DB", "data/cavedawg.db"))
    # Lifetime ceiling for a public demo. Reset demo does not clear it.
    hard_cap_usd: float = field(
        default_factory=lambda: float(os.environ.get("CAVEDAWG_HARD_CAP_USD", "5"))
    )
    # Access given to logins made with the sign-in page's Demo button: self, team, all, or off.
    demo_access: str = field(
        default_factory=lambda: os.environ.get("CAVEDAWG_DEMO_ACCESS", "self").strip().lower()
    )


settings = Settings()
