# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Python Discord bot that monitors a channel for YouTube links, adds them to a YouTube playlist via the YouTube Data API, and tracks everything in SQLite. Fully async (discord.py, aiosqlite, aiohttp), Python 3.13.

## Running

```bash
# Install dependencies
pip install -r requirements.txt

# Run directly
python -m bot.main

# Run with Docker (recommended for production)
docker compose up -d
```

Requires `.env` file (copy from `.env.example`) with Discord bot token, channel ID, YouTube OAuth credentials, and playlist ID. Non-secret tunables live in `config.toml` with optional `config.local.toml` overrides (gitignored).

## YouTube OAuth Token Refresh

If the bot's refresh token expires or is revoked (`invalid_grant` error), re-run the auth script locally to obtain a new one:

```bash
# Python version (opens browser, handles callback automatically)
python scripts/get_refresh_token.py

# Shell version (manual: copy/paste redirect URL)
bash scripts/get_refresh_token.sh
```

Both require `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET` in `.env`. The script outputs a new `YOUTUBE_REFRESH_TOKEN` to add to `.env`. After updating, restart the bot.

## No Tests / No Linting

There are no unit tests, linters, or formatters configured.

## Architecture

**Entry point:** `bot/main.py` — initializes Discord bot, attaches `YouTubeClient` instance, loads three cogs.

**Cogs pattern** (modular command groups in `bot/cogs/`):
- `listener.py` — `on_message` event handler (auto-add YouTube links), background retry loop (6h interval)
- `commands.py` — User commands (`!scan`, `!link`, `!stats`), auto-resume scan loop (6h interval)
- `admin.py` — Admin-gated commands (`!status`, `!quota`, `!errors`, `!retry`)

**Core modules in `bot/`:**
- `youtube.py` — OAuth token refresh, `add_to_playlist()` with status-code handling (200/409/404/403/429), quota tracking with Pacific-midnight reset, 48h cooldown on quota exhaustion
- `db.py` — Async SQLite via global `_db` singleton. Two tables: `videos` (tracked links + error state) and `scan_state` (backfill progress). Auto-migrates missing columns.
- `url_parser.py` — Regex extraction of YouTube video IDs from various URL formats
- `config.py` — Loads `.env` + deep-merges `config.toml` with `config.local.toml`, exposes module-level constants

**Configuration layering:** secrets in `.env`, defaults in `config.toml` (versioned), overrides in `config.local.toml` (gitignored).

## Key Patterns

- **All I/O is async** — database, HTTP, Discord operations
- **Quota awareness** — tracks YouTube API usage in-memory, pauses on exhaustion, verifies quota with a cheap API call before resuming
- **Error categories** — permanent (404, marked in DB), temporary (queued for retry with exponential backoff), quota (pauses scans, sets 48h cooldown)
- **Scan state persistence** — long backfill scans save progress to DB and auto-resume after quota recovery
- **Discord 2000-char limit** — multi-message output splits across messages when needed
- **All timestamps are ISO-8601**
