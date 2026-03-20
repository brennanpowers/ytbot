from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from bot.cogs.listener import LinkListener


@pytest_asyncio.fixture
async def listener():
    mock_bot = MagicMock()
    mock_bot.wait_until_ready = AsyncMock()

    mock_yt = MagicMock()
    mock_yt.add_to_playlist = AsyncMock(return_value="PLitem123")
    mock_yt.quota_available.return_value = True
    mock_yt.check_quota = AsyncMock(return_value=(True, "OK"))
    mock_yt.last_error = None

    cog = LinkListener(mock_bot, mock_yt)
    cog.retry_failed.cancel()
    yield cog


# ---------------------------------------------------------------------------
# on_message
# ---------------------------------------------------------------------------

class TestOnMessage:
    async def test_skips_bot_messages(self, listener, make_message):
        msg = make_message(content="https://youtu.be/dQw4w9WgXcQ", author_bot=True)
        with patch("bot.cogs.listener.db") as mock_db:
            await listener.on_message(msg)
            mock_db.video_exists.assert_not_called()

    async def test_skips_wrong_channel(self, listener, make_message):
        msg = make_message(content="https://youtu.be/dQw4w9WgXcQ", channel_id=999)
        with patch("bot.cogs.listener.db") as mock_db:
            await listener.on_message(msg)
            mock_db.video_exists.assert_not_called()

    async def test_no_urls_does_nothing(self, listener, make_message):
        msg = make_message(content="just chatting")
        with patch("bot.cogs.listener.db") as mock_db:
            await listener.on_message(msg)
            mock_db.video_exists.assert_not_called()

    async def test_new_video_added_reacts(self, listener, make_message):
        msg = make_message(content="https://youtu.be/dQw4w9WgXcQ")
        with patch("bot.cogs.listener.db") as mock_db:
            mock_db.video_exists = AsyncMock(return_value=False)
            mock_db.add_video = AsyncMock()
            mock_db.mark_permanent_failure = AsyncMock()

            await listener.on_message(msg)

            mock_db.add_video.assert_awaited_once()
            msg.add_reaction.assert_any_await("✅")

    async def test_duplicate_video_reacts(self, listener, make_message):
        msg = make_message(content="https://youtu.be/dQw4w9WgXcQ")
        with patch("bot.cogs.listener.db") as mock_db:
            mock_db.video_exists = AsyncMock(return_value=True)

            await listener.on_message(msg)

            msg.add_reaction.assert_any_await("🔁")
            listener.yt.add_to_playlist.assert_not_awaited()

    async def test_not_found_reacts_and_replies(self, listener, make_message):
        msg = make_message(content="https://youtu.be/dQw4w9WgXcQ")
        listener.yt.add_to_playlist.return_value = "not_found"
        listener.yt.last_error = "HTTP 404 — video not found"

        with patch("bot.cogs.listener.db") as mock_db:
            mock_db.video_exists = AsyncMock(return_value=False)
            mock_db.add_video = AsyncMock()
            mock_db.mark_permanent_failure = AsyncMock()

            await listener.on_message(msg)

            mock_db.mark_permanent_failure.assert_awaited_once_with("dQw4w9WgXcQ")
            msg.add_reaction.assert_any_await("❌")
            msg.reply.assert_awaited_once()

    async def test_temporary_failure_reacts_warning(self, listener, make_message):
        msg = make_message(content="https://youtu.be/dQw4w9WgXcQ")
        listener.yt.add_to_playlist.return_value = None
        listener.yt.last_error = "HTTP 500 — server error"

        with patch("bot.cogs.listener.db") as mock_db:
            mock_db.video_exists = AsyncMock(return_value=False)
            mock_db.add_video = AsyncMock()
            mock_db.mark_permanent_failure = AsyncMock()

            await listener.on_message(msg)

            msg.add_reaction.assert_any_await("⚠️")
            msg.reply.assert_awaited_once()


# ---------------------------------------------------------------------------
# retry_failed (background task body)
# ---------------------------------------------------------------------------

class TestRetryFailed:
    async def test_no_failed_returns_early(self, listener):
        with patch("bot.cogs.listener.db") as mock_db:
            mock_db.get_failed_videos = AsyncMock(return_value=[])

            await listener.retry_failed.coro(listener)

            listener.yt.check_quota.assert_not_awaited()

    @patch("bot.cogs.listener.asyncio.sleep", new_callable=AsyncMock)
    async def test_marks_not_found_as_permanent(self, mock_sleep, listener):
        listener.yt.add_to_playlist.return_value = "not_found"
        listener.yt.last_error = "HTTP 404"

        with patch("bot.cogs.listener.db") as mock_db:
            mock_db.get_failed_videos = AsyncMock(
                return_value=[{"video_id": "v1", "youtube_url": "url1"}],
            )
            mock_db.update_error_detail = AsyncMock()
            mock_db.mark_permanent_failure = AsyncMock()
            mock_db.mark_video_added = AsyncMock()

            await listener.retry_failed.coro(listener)

            mock_db.mark_permanent_failure.assert_awaited_once_with("v1")

    @patch("bot.cogs.listener.asyncio.sleep", new_callable=AsyncMock)
    async def test_marks_success_as_added(self, mock_sleep, listener):
        listener.yt.add_to_playlist.return_value = "PLitem_ok"
        listener.yt.last_error = None

        with patch("bot.cogs.listener.db") as mock_db:
            mock_db.get_failed_videos = AsyncMock(
                return_value=[{"video_id": "v1", "youtube_url": "url1"}],
            )
            mock_db.update_error_detail = AsyncMock()
            mock_db.mark_video_added = AsyncMock()

            await listener.retry_failed.coro(listener)

            mock_db.mark_video_added.assert_awaited_once()

    @patch("bot.cogs.listener.asyncio.sleep", new_callable=AsyncMock)
    async def test_stops_on_quota_exceeded(self, mock_sleep, listener):
        listener.yt.add_to_playlist.return_value = "quota_exceeded"
        listener.yt.last_error = "quota"

        with patch("bot.cogs.listener.db") as mock_db:
            mock_db.get_failed_videos = AsyncMock(
                return_value=[
                    {"video_id": "v1", "youtube_url": "url1"},
                    {"video_id": "v2", "youtube_url": "url2"},
                ],
            )
            mock_db.update_error_detail = AsyncMock()

            await listener.retry_failed.coro(listener)

            # Should stop after first video hits quota
            assert listener.yt.add_to_playlist.await_count == 1
