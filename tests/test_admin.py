import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from bot.cogs.admin import Admin


@pytest_asyncio.fixture
async def cog():
    mock_bot = MagicMock()
    mock_yt = MagicMock()
    mock_yt.estimated_quota_used = 500
    mock_yt.remaining_inserts = 190
    mock_yt.check_quota = AsyncMock(return_value=(True, "API responding, quota available"))
    mock_yt.add_to_playlist = AsyncMock(return_value="PLitem")
    mock_yt.quota_available.return_value = True
    mock_yt.last_error = None

    start_time = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    return Admin(mock_bot, mock_yt, start_time)


# ---------------------------------------------------------------------------
# !status
# ---------------------------------------------------------------------------

class TestStatus:
    async def test_displays_uptime_and_stats(self, cog, make_ctx):
        ctx = make_ctx()
        with patch("bot.cogs.admin.db") as mock_db:
            mock_db.get_stats = AsyncMock(return_value={
                "total": 10, "added": 8, "failed": 2,
                "unique_posters": 3, "recent": [],
            })
            mock_db.get_scan_state = AsyncMock(return_value=None)

            await cog.status.callback(cog, ctx)

        output = ctx.send.call_args[0][0]
        assert "Uptime:" in output
        assert "Videos tracked:" in output
        assert "10" in output

    async def test_includes_scan_state(self, cog, make_ctx):
        ctx = make_ctx()
        with patch("bot.cogs.admin.db") as mock_db:
            mock_db.get_stats = AsyncMock(return_value={
                "total": 10, "added": 8, "failed": 2,
                "unique_posters": 3, "recent": [],
            })
            mock_db.get_scan_state = AsyncMock(return_value={
                "status": "paused",
                "messages_scanned": 500,
                "videos_added": 30,
            })

            await cog.status.callback(cog, ctx)

        output = ctx.send.call_args[0][0]
        assert "paused" in output
        assert "500" in output


# ---------------------------------------------------------------------------
# !quota
# ---------------------------------------------------------------------------

class TestQuota:
    async def test_shows_available(self, cog, make_ctx):
        ctx = make_ctx()
        await cog.quota.callback(cog, ctx)
        output = ctx.send.call_args[0][0]
        assert "✅" in output
        assert "available" in output.lower()

    async def test_shows_unavailable(self, cog, make_ctx):
        cog.yt.check_quota.return_value = (False, "Quota still exhausted")
        ctx = make_ctx()
        await cog.quota.callback(cog, ctx)
        output = ctx.send.call_args[0][0]
        assert "❌" in output
        assert "exhausted" in output.lower()


# ---------------------------------------------------------------------------
# !errors
# ---------------------------------------------------------------------------

class TestErrors:
    async def test_no_errors(self, cog, make_ctx):
        ctx = make_ctx()
        with patch("bot.cogs.admin.db") as mock_db:
            mock_db.get_retryable_errors = AsyncMock(return_value=([], 0))
            await cog.errors.callback(cog, ctx, "1")
        ctx.send.assert_awaited_once_with("No pending errors.")

    async def test_clear_errors(self, cog, make_ctx):
        ctx = make_ctx()
        with patch("bot.cogs.admin.db") as mock_db:
            mock_db.clear_all_pending_errors = AsyncMock(return_value=5)
            await cog.errors.callback(cog, ctx, "clear")
        output = ctx.send.call_args[0][0]
        assert "5" in output

    async def test_paginated_errors(self, cog, make_ctx):
        ctx = make_ctx()
        videos = [
            {"video_id": f"v{i}", "youtube_url": f"url{i}",
             "error_detail": "err", "created_at": "2024-01-01"}
            for i in range(3)
        ]
        with patch("bot.cogs.admin.db") as mock_db:
            mock_db.get_retryable_errors = AsyncMock(return_value=(videos, 13))
            await cog.errors.callback(cog, ctx, "1")
        output = ctx.send.call_args[0][0]
        assert "page 1/" in output
        assert "13 total" in output
        assert "v0" in output


# ---------------------------------------------------------------------------
# !retry
# ---------------------------------------------------------------------------

class TestRetry:
    async def test_no_failed(self, cog, make_ctx):
        ctx = make_ctx()
        with patch("bot.cogs.admin.db") as mock_db:
            mock_db.get_failed_videos = AsyncMock(return_value=[])
            await cog.retry.callback(cog, ctx)
        ctx.send.assert_awaited_once_with("No failed videos to retry.")

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_retries_and_reports(self, mock_sleep, cog, make_ctx):
        ctx = make_ctx()
        with patch("bot.cogs.admin.db") as mock_db:
            mock_db.get_failed_videos = AsyncMock(return_value=[
                {"video_id": "v1", "youtube_url": "url1"},
                {"video_id": "v2", "youtube_url": "url2"},
            ])
            mock_db.mark_video_added = AsyncMock()
            mock_db.mark_permanent_failure = AsyncMock()

            await cog.retry.callback(cog, ctx)

        # Last send call should be the summary
        final_msg = ctx.send.call_args_list[-1][0][0]
        assert "Retry complete" in final_msg
