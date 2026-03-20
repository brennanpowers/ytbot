import pytest

from bot import db


class TestVideoOperations:
    async def test_add_and_exists(self, tmp_db):
        await db.add_video(
            video_id="vid1",
            youtube_url="https://youtube.com/watch?v=vid1",
            discord_message_id=100,
            discord_user_id=200,
            posted_in_discord_at="2024-01-01T00:00:00",
        )
        assert await db.video_exists("vid1") is True

    async def test_not_exists(self, tmp_db):
        assert await db.video_exists("nonexistent") is False

    async def test_duplicate_ignored(self, tmp_db):
        kwargs = dict(
            video_id="vid1",
            youtube_url="https://youtube.com/watch?v=vid1",
            discord_message_id=100,
            discord_user_id=200,
            posted_in_discord_at="2024-01-01T00:00:00",
        )
        await db.add_video(**kwargs)
        await db.add_video(**kwargs)
        stats = await db.get_stats()
        assert stats["total"] == 1

    async def test_mark_video_added(self, tmp_db):
        await db.add_video("vid1", "url1", 100, 200, "2024-01-01T00:00:00")
        await db.mark_video_added("vid1", "2024-01-01T01:00:00", "PLitem1")
        stats = await db.get_stats()
        assert stats["added"] == 1
        assert stats["failed"] == 0

    async def test_mark_permanent_failure(self, tmp_db):
        await db.add_video("vid1", "url1", 100, 200, "2024-01-01T00:00:00")
        await db.mark_permanent_failure("vid1")
        failed = await db.get_failed_videos()
        assert len(failed) == 0

    async def test_update_error_detail(self, tmp_db):
        await db.add_video("vid1", "url1", 100, 200, "2024-01-01T00:00:00")
        await db.update_error_detail("vid1", "HTTP 500 — Server error")
        errors, total = await db.get_retryable_errors()
        assert total == 1
        assert errors[0]["error_detail"] == "HTTP 500 — Server error"

    async def test_clear_error_detail(self, tmp_db):
        await db.add_video(
            "vid1", "url1", 100, 200, "2024-01-01T00:00:00",
            error_detail="some error",
        )
        await db.update_error_detail("vid1", None)
        errors, _ = await db.get_retryable_errors()
        assert errors[0]["error_detail"] is None


class TestRetryableErrors:
    async def test_returns_only_pending(self, tmp_db):
        await db.add_video("v1", "url1", 1, 1, "2024-01-01T00:00:00")
        await db.add_video(
            "v2", "url2", 2, 1, "2024-01-01T00:00:00",
            added_to_playlist_at="2024-01-01T01:00:00", playlist_item_id="p1",
        )
        await db.add_video("v3", "url3", 3, 1, "2024-01-01T00:00:00")
        await db.mark_permanent_failure("v3")

        errors, total = await db.get_retryable_errors()
        assert total == 1
        assert errors[0]["video_id"] == "v1"

    async def test_pagination(self, tmp_db):
        for i in range(15):
            await db.add_video(f"v{i:02}", f"url{i}", i, 1, "2024-01-01T00:00:00")

        page1, total = await db.get_retryable_errors(limit=10, offset=0)
        assert total == 15
        assert len(page1) == 10

        page2, total = await db.get_retryable_errors(limit=10, offset=10)
        assert total == 15
        assert len(page2) == 5

    async def test_clear_all_pending(self, tmp_db):
        await db.add_video("v1", "url1", 1, 1, "2024-01-01T00:00:00")
        await db.add_video("v2", "url2", 2, 1, "2024-01-01T00:00:00")
        count = await db.clear_all_pending_errors()
        assert count == 2
        failed = await db.get_failed_videos()
        assert len(failed) == 0


class TestGetFailedVideos:
    async def test_returns_unadded_non_permanent(self, tmp_db):
        await db.add_video("v1", "url1", 1, 1, "2024-01-01T00:00:00")
        await db.add_video("v2", "url2", 2, 1, "2024-01-01T00:00:00")
        failed = await db.get_failed_videos()
        assert len(failed) == 2
        video_ids = {v["video_id"] for v in failed}
        assert video_ids == {"v1", "v2"}

    async def test_excludes_added_and_permanent(self, tmp_db):
        await db.add_video(
            "v1", "url1", 1, 1, "2024-01-01T00:00:00",
            added_to_playlist_at="2024-01-01T01:00:00", playlist_item_id="p1",
        )
        await db.add_video("v2", "url2", 2, 1, "2024-01-01T00:00:00")
        await db.mark_permanent_failure("v2")
        await db.add_video("v3", "url3", 3, 1, "2024-01-01T00:00:00")

        failed = await db.get_failed_videos()
        assert len(failed) == 1
        assert failed[0]["video_id"] == "v3"


class TestStats:
    async def test_empty_db(self, tmp_db):
        stats = await db.get_stats()
        assert stats["total"] == 0
        assert stats["added"] == 0
        assert stats["failed"] == 0
        assert stats["unique_posters"] == 0
        assert stats["recent"] == []

    async def test_counts(self, tmp_db):
        await db.add_video(
            "v1", "url1", 1, 100, "2024-01-01T00:00:00",
            added_to_playlist_at="2024-01-01T01:00:00", playlist_item_id="p1",
        )
        await db.add_video("v2", "url2", 2, 200, "2024-01-01T00:00:00")
        stats = await db.get_stats()
        assert stats["total"] == 2
        assert stats["added"] == 1
        assert stats["failed"] == 1
        assert stats["unique_posters"] == 2

    async def test_recent_limit(self, tmp_db):
        for i in range(10):
            await db.add_video(f"v{i}", f"url{i}", i, 1, "2024-01-01T00:00:00")
        stats = await db.get_stats(recent_limit=3)
        assert len(stats["recent"]) == 3


class TestLatestDiscordMessageId:
    async def test_empty_db(self, tmp_db):
        assert await db.get_latest_discord_message_id() is None

    async def test_returns_max(self, tmp_db):
        await db.add_video("v1", "url1", 100, 1, "2024-01-01T00:00:00")
        await db.add_video("v2", "url2", 300, 1, "2024-01-01T00:00:00")
        await db.add_video("v3", "url3", 200, 1, "2024-01-01T00:00:00")
        assert await db.get_latest_discord_message_id() == 300


class TestScanState:
    async def test_no_scan_state(self, tmp_db):
        assert await db.get_scan_state() is None

    async def test_save_and_get(self, tmp_db):
        await db.save_scan_state(
            channel_id=123, scan_from="2024-01-01", started_at="2024-01-01T00:00:00",
        )
        state = await db.get_scan_state()
        assert state is not None
        assert state["channel_id"] == 123
        assert state["scan_from"] == "2024-01-01"
        assert state["status"] == "running"
        assert state["messages_scanned"] == 0

    async def test_update_progress(self, tmp_db):
        await db.save_scan_state(123, "2024-01-01", "2024-01-01T00:00:00")
        await db.update_scan_progress(
            last_message_id=456, messages_scanned=50,
            videos_added=5, status="paused",
        )
        state = await db.get_scan_state()
        assert state["last_message_id"] == 456
        assert state["messages_scanned"] == 50
        assert state["videos_added"] == 5
        assert state["status"] == "paused"

    async def test_clear(self, tmp_db):
        await db.save_scan_state(123, "2024-01-01", "2024-01-01T00:00:00")
        await db.clear_scan_state()
        assert await db.get_scan_state() is None

    async def test_replace_existing(self, tmp_db):
        await db.save_scan_state(123, "2024-01-01", "2024-01-01T00:00:00")
        await db.save_scan_state(456, "2024-06-01", "2024-06-01T00:00:00")
        state = await db.get_scan_state()
        assert state["channel_id"] == 456
        assert state["scan_from"] == "2024-06-01"


class TestMigration:
    async def test_migration_is_idempotent(self, tmp_db):
        """Running _migrate twice doesn't fail (column already exists)."""
        conn = db.get_db()
        await db._migrate(conn)
        await db.add_video("v1", "url1", 1, 1, "2024-01-01T00:00:00", error_detail="test")
        errors, _ = await db.get_retryable_errors()
        assert errors[0]["error_detail"] == "test"
