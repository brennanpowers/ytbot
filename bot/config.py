import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value


DISCORD_BOT_TOKEN: str = _require("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID: int = int(_require("DISCORD_CHANNEL_ID"))
YOUTUBE_PLAYLIST_ID: str = _require("YOUTUBE_PLAYLIST_ID")
YOUTUBE_CLIENT_ID: str = _require("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET: str = _require("YOUTUBE_CLIENT_SECRET")
YOUTUBE_REFRESH_TOKEN: str = _require("YOUTUBE_REFRESH_TOKEN")

DISCORD_ADMIN_USER_ID: int | None = (
    int(v) if (v := os.getenv("DISCORD_ADMIN_USER_ID")) else None
)
DB_PATH: str = os.getenv("DB_PATH", "/data/ytbot.db")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
COMMAND_PREFIX: str = os.getenv("COMMAND_PREFIX", "!")
