# YouTube Playlist Discord Bot

Monitors a Discord channel for YouTube links, automatically adds them to a public YouTube playlist, and tracks everything in SQLite.

## Setup

### 1. Create a Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application, add a bot
3. Enable **Message Content Intent** under Privileged Gateway Intents
4. Invite the bot to your server with permissions: Read Messages, Send Messages, Add Reactions, Read Message History

### 2. Set Up YouTube OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project, enable YouTube Data API v3
3. Create OAuth 2.0 credentials (Desktop app type)
4. Copy `.env.example` to `.env` and fill in `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET`
5. Run the token helper:
   ```bash
   python scripts/get_refresh_token.py
   ```
6. Copy the printed `YOUTUBE_REFRESH_TOKEN` into `.env`

### 3. Configure `.env`

```bash
cp .env.example .env
# Fill in all required values
```

### 4. Run

**Docker (recommended):**
```bash
docker compose up -d
```

**Local:**
```bash
pip install -r requirements.txt
DB_PATH=./ytbot.db python -m bot.main
```

## Configuration

Non-secret settings live in `config.toml` (committed with defaults). To override without modifying the defaults, create `config.local.toml` with only the values you want to change:

```toml
# config.local.toml — only include what you want to override
[quota]
cooldown_hours = 24

[scan]
throttle_seconds = 2.0

[reactions]
added = "\U0001f389"
```

The local file is gitignored and deep-merged over the defaults.

## Commands

| Command | Description |
|---------|-------------|
| `!scan YYYY-MM-DD` | Scan channel history from date, add all YouTube links |
| `!scan cancel` | Cancel a running or paused scan |
| `!link` | Post the playlist URL |
| `!stats` | Show video counts and recent additions |
| `!status` | (Admin) Bot uptime, quota usage, scan state |
| `!retry` | (Admin) Retry failed playlist additions |
| `!quota` | (Admin) Check YouTube API quota with a live API call |

## Reactions

- ✅ Successfully added to playlist
- 🔁 Already tracked (duplicate)
- ⚠️ Temporary failure (will retry)
- ❌ Video not found (permanent failure, won't retry)
