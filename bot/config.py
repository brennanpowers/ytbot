import os
import sys
import tomllib
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- TOML config loading (defaults + local override) ---

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_toml() -> dict:
    default_path = _PROJECT_ROOT / "config.toml"
    local_path = _PROJECT_ROOT / "config.local.toml"

    with open(default_path, "rb") as f:
        cfg = tomllib.load(f)

    if local_path.exists():
        with open(local_path, "rb") as f:
            overrides = tomllib.load(f)
        _deep_merge(cfg, overrides)

    return cfg


def _deep_merge(base: dict, override: dict) -> None:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


_cfg = _load_toml()

# --- Env var helpers ---


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    return value.split("#")[0].strip() or None


def _require(name: str) -> str:
    value = _clean(os.getenv(name))
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value


# --- Secrets (env vars only) ---

DISCORD_BOT_TOKEN: str = _require("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID: int = int(_require("DISCORD_CHANNEL_ID"))
YOUTUBE_PLAYLIST_ID: str = _require("YOUTUBE_PLAYLIST_ID")
YOUTUBE_CLIENT_ID: str = _require("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET: str = _require("YOUTUBE_CLIENT_SECRET")
YOUTUBE_REFRESH_TOKEN: str = _require("YOUTUBE_REFRESH_TOKEN")

DISCORD_ADMIN_USER_ID: int | None = (
    int(v) if (v := _clean(os.getenv("DISCORD_ADMIN_USER_ID"))) else None
)
DB_PATH: str = _clean(os.getenv("DB_PATH")) or "/data/ytbot.db"
LOG_LEVEL: str = _clean(os.getenv("LOG_LEVEL")) or "INFO"
COMMAND_PREFIX: str = _clean(os.getenv("COMMAND_PREFIX")) or "!"

# --- TOML config (non-secret, tunable) ---

QUOTA_DAILY_LIMIT: int = _cfg["quota"]["daily_limit"]
QUOTA_COST_PER_INSERT: int = _cfg["quota"]["cost_per_insert"]
QUOTA_COOLDOWN_HOURS: int = _cfg["quota"]["cooldown_hours"]

SCAN_THROTTLE_SECONDS: float = _cfg["scan"]["throttle_seconds"]
SCAN_PROGRESS_INTERVAL: int = _cfg["scan"]["progress_interval"]
SCAN_PAGE_COOLDOWN_INTERVAL: int = _cfg["scan"]["page_cooldown_interval"]
SCAN_PAGE_COOLDOWN_SECONDS: float = _cfg["scan"]["page_cooldown_seconds"]
SCAN_RESUME_INTERVAL_HOURS: int = _cfg["scan"]["resume_interval_hours"]

RETRY_INTERVAL_HOURS: int = _cfg["retry"]["interval_hours"]
RETRY_THROTTLE_SECONDS: float = _cfg["retry"]["throttle_seconds"]
RETRY_MAX_ATTEMPTS: int = _cfg["retry"]["max_attempts"]
RETRY_BACKOFF_BASE: int = _cfg["retry"]["backoff_base"]
RETRY_BACKOFF_MULTIPLIER: int = _cfg["retry"]["backoff_multiplier"]

STATS_RECENT_VIDEOS_LIMIT: int = _cfg["stats"]["recent_videos_limit"]

REACTION_ADDED: str = _cfg["reactions"]["added"]
REACTION_DUPLICATE: str = _cfg["reactions"]["duplicate"]
REACTION_WARNING: str = _cfg["reactions"]["warning"]
REACTION_NOT_FOUND: str = _cfg["reactions"]["not_found"]
REACTION_QUOTA_OK: str = _cfg["reactions"]["quota_check_ok"]
REACTION_QUOTA_FAIL: str = _cfg["reactions"]["quota_check_fail"]
