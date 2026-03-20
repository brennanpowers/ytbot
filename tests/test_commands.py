from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from bot.cogs.commands import Commands


@pytest_asyncio.fixture
async def cog():
    mock_bot = MagicMock()
    mock_bot.wait_until_ready = AsyncMock()

    mock_yt = MagicMock()
    mock_yt.add_to_playlist = AsyncMock(return_value="PLitem123")
    mock_yt.quota_available.return_value = True
    mock_yt.check_quota = AsyncMock(return_value=(True, "OK"))

    c = Commands(mock_bot, mock_yt)
    c.auto_resume_scan.cancel()
    yield c


# ---------------------------------------------------------------------------
# !scan
# ---------------------------------------------------------------------------

class TestScan:
    async def test_wrong_channel_ignored(self, cog, make_ctx):
        ctx = make_ctx(channel_id=999)
        await cog.scan.callback(cog, ctx, None)
        ctx.send.assert_not_awaited()

    async def test_no_arg_shows_usage(self, cog, make_ctx):
        ctx = make_ctx()
        await cog.scan.callback(cog, ctx, None)
        ctx.send.assert_awaited_once()
        assert "Usage" in ctx.send.call_args[0][0]

    async def test_invalid_date_shows_error(self, cog, make_ctx):
        ctx = make_ctx()
        await cog.scan.callback(cog, ctx, "not-a-date")
        ctx.send.assert_awaited_once()
        assert "Invalid date" in ctx.send.call_args[0][0]

    async def test_cancel_while_scanning(self, cog, make_ctx):
        cog._scanning = True
        ctx = make_ctx()
        await cog.scan.callback(cog, ctx, "cancel")
        assert cog._scan_cancelled is True
        ctx.send.assert_awaited_once_with("Cancelling scan...")

    async def test_cancel_while_not_scanning(self, cog, make_ctx):
        ctx = make_ctx()
        with patch("bot.cogs.commands.db") as mock_db:
            mock_db.clear_scan_state = AsyncMock()
            await cog.scan.callback(cog, ctx, "cancel")
            mock_db.clear_scan_state.assert_awaited_once()
            ctx.send.assert_awaited_once_with("Scan state cleared.")

    async def test_already_scanning(self, cog, make_ctx):
        cog._scanning = True
        ctx = make_ctx()
        await cog.scan.callback(cog, ctx, "2024-01-01")
        ctx.send.assert_awaited_once_with("A scan is already running.")


# ---------------------------------------------------------------------------
# !link
# ---------------------------------------------------------------------------

class TestLink:
    async def test_sends_playlist_url(self, cog, make_ctx):
        ctx = make_ctx()
        await cog.link.callback(cog, ctx)
        ctx.send.assert_awaited_once()
        assert "PLtest123" in ctx.send.call_args[0][0]


# ---------------------------------------------------------------------------
# !stats
# ---------------------------------------------------------------------------

class TestStats:
    async def test_formats_stats(self, cog, make_ctx):
        ctx = make_ctx()
        with patch("bot.cogs.commands.db") as mock_db:
            mock_db.get_stats = AsyncMock(return_value={
                "total": 42,
                "added": 40,
                "failed": 2,
                "unique_posters": 5,
                "recent": [
                    {"video_id": "abc", "youtube_url": "url", "posted_in_discord_at": "2024-01-01T00:00:00"},
                ],
            })
            await cog.stats.callback(cog, ctx)

        output = ctx.send.call_args[0][0]
        assert "42" in output
        assert "40" in output
        assert "2" in output
        assert "5" in output
        assert "abc" in output
