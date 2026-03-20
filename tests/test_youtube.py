import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.youtube import YouTubeClient


def make_response(status, json_data=None, text=""):
    """Create a mock aiohttp response usable as an async context manager.

    When YouTubeClient does `async with self._session.post(...) as resp:`,
    the post() call returns a context manager. __aenter__ yields the response
    object, and __aexit__ is a no-op.
    """
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    resp.text = AsyncMock(return_value=text)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.fixture
def yt():
    """YouTubeClient with a mock session and a pre-set valid access token."""
    client = YouTubeClient()
    client._session = MagicMock()
    client._access_token = "test-token"
    client._token_expiry = time.time() + 3600
    client._quota_reset_time = time.time() + 86400
    return client


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class TestProperties:
    def test_estimated_quota_used(self, yt):
        yt.api_calls_today = 5
        # config.toml: cost_per_insert = 50 → 5 * 50 = 250
        assert yt.estimated_quota_used == 250

    def test_remaining_inserts(self, yt):
        yt.api_calls_today = 5
        # (10_000 - 250) // 50 = 195
        assert yt.remaining_inserts == 195

    def test_remaining_inserts_never_negative(self, yt):
        yt.api_calls_today = 999
        assert yt.remaining_inserts == 0


# ---------------------------------------------------------------------------
# Quota
# ---------------------------------------------------------------------------

class TestQuotaAvailable:
    def test_available_under_limit(self, yt):
        yt.api_calls_today = 0
        assert yt.quota_available() is True

    def test_unavailable_at_limit(self, yt):
        yt.api_calls_today = 200  # 200 * 50 = 10_000
        assert yt.quota_available() is False

    def test_resets_when_past_reset_time(self, yt):
        yt.api_calls_today = 200
        yt._quota_reset_time = time.time() - 1
        assert yt.quota_available() is True
        assert yt.api_calls_today == 0


class TestQuotaTimer:
    def test_reset_sets_future_time(self, yt):
        yt._reset_quota_timer()
        assert yt._quota_reset_time > time.time()

    def test_reset_within_24h(self, yt):
        yt._reset_quota_timer()
        assert yt._quota_reset_time < time.time() + 86400

    def test_cooldown_sets_correct_offset(self, yt):
        before = time.time()
        yt._set_quota_cooldown()
        # config.toml: cooldown_hours = 48
        expected = 48 * 3600
        assert yt._quota_reset_time >= before + expected - 1
        assert yt._quota_reset_time <= before + expected + 1


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:
    async def test_initialize_creates_session(self):
        client = YouTubeClient()
        await client.initialize()
        assert client._session is not None
        await client.close()

    async def test_close_clears_session(self):
        client = YouTubeClient()
        await client.initialize()
        await client.close()
        assert client._session is None

    async def test_close_noop_when_no_session(self):
        client = YouTubeClient()
        await client.close()  # should not raise


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

class TestTokenRefresh:
    async def test_refresh_success(self, yt):
        yt._access_token = None
        yt._token_expiry = 0
        yt._session.post.return_value = make_response(
            200, json_data={"access_token": "new-token", "expires_in": 3600},
        )

        await yt._refresh_access_token()

        assert yt._access_token == "new-token"
        assert yt._token_expiry > time.time()

    async def test_refresh_failure_raises(self, yt):
        yt._access_token = None
        yt._session.post.return_value = make_response(401, text="invalid_grant")

        with pytest.raises(RuntimeError, match="OAuth token refresh failed"):
            await yt._refresh_access_token()

    async def test_ensure_valid_skips_when_valid(self, yt):
        await yt._ensure_valid_token()
        yt._session.post.assert_not_called()


# ---------------------------------------------------------------------------
# check_quota
# ---------------------------------------------------------------------------

class TestCheckQuota:
    async def test_quota_available(self, yt):
        yt._session.get.return_value = make_response(200, text='{"items":[]}')

        available, msg = await yt.check_quota()
        assert available is True
        assert "available" in msg.lower()

    async def test_quota_exhausted(self, yt):
        yt._session.get.return_value = make_response(403, text="quotaExceeded")

        available, msg = await yt.check_quota()
        assert available is False
        assert "exhausted" in msg.lower()

    async def test_unexpected_response(self, yt):
        yt._session.get.return_value = make_response(500, text="server error")

        available, msg = await yt.check_quota()
        assert available is False
        assert "500" in msg

    async def test_token_refresh_failure(self, yt):
        yt._access_token = None
        yt._token_expiry = 0
        yt._session.post.return_value = make_response(400, text="invalid_grant")

        available, msg = await yt.check_quota()
        assert available is False
        assert "OAuth" in msg


# ---------------------------------------------------------------------------
# add_to_playlist — one test per status-code branch
# ---------------------------------------------------------------------------

class TestAddToPlaylist:
    async def test_success_200(self, yt):
        yt._session.post.return_value = make_response(
            200, json_data={"id": "PLitem123"},
        )
        result = await yt.add_to_playlist("vid123")
        assert result == "PLitem123"
        assert yt.api_calls_today == 1

    async def test_already_in_playlist_409(self, yt):
        yt._session.post.return_value = make_response(409)

        result = await yt.add_to_playlist("vid123")
        assert result == "already_in_playlist"
        assert yt.api_calls_today == 1

    async def test_not_found_404(self, yt):
        yt._session.post.return_value = make_response(404)

        result = await yt.add_to_playlist("vid123")
        assert result == "not_found"
        assert yt.api_calls_today == 1
        assert "404" in yt.last_error

    async def test_precondition_failure_400(self, yt):
        yt._session.post.return_value = make_response(
            400, text="Precondition check failed",
        )
        result = await yt.add_to_playlist("vid123")
        assert result == "not_found"
        assert yt.api_calls_today == 1
        assert "Precondition" in yt.last_error

    async def test_bad_request_other_400(self, yt):
        yt._session.post.return_value = make_response(400, text="Some other error")

        result = await yt.add_to_playlist("vid123")
        assert result is None
        assert yt.api_calls_today == 1

    async def test_quota_exceeded_403(self, yt):
        yt._session.post.return_value = make_response(403, text="quotaExceeded")

        result = await yt.add_to_playlist("vid123")
        assert result == "quota_exceeded"
        assert "quota" in yt.last_error.lower()

    async def test_forbidden_other_403(self, yt):
        yt._session.post.return_value = make_response(403, text="Access forbidden")

        result = await yt.add_to_playlist("vid123")
        assert result is None
        assert "403" in yt.last_error

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_rate_limited_429_retries_then_succeeds(self, mock_sleep, yt):
        yt._session.post.side_effect = [
            make_response(429),
            make_response(200, json_data={"id": "PLitem123"}),
        ]
        result = await yt.add_to_playlist("vid123")

        assert result == "PLitem123"
        # config.toml: backoff_base=2, multiplier=2 → 2^0 * 2 = 2
        mock_sleep.assert_awaited_once_with(2)

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_rate_limited_429_exhausts_retries(self, mock_sleep, yt):
        # config.toml: max_attempts = 4
        yt._session.post.side_effect = [make_response(429)] * 4

        result = await yt.add_to_playlist("vid123")
        assert result is None
        assert "429" in yt.last_error
        assert mock_sleep.await_count == 4

    async def test_unexpected_status(self, yt):
        yt._session.post.return_value = make_response(500, text="Internal error")

        result = await yt.add_to_playlist("vid123")
        assert result is None
        assert "500" in yt.last_error

    async def test_quota_unavailable_skips_api_call(self, yt):
        yt.api_calls_today = 999  # way over limit

        result = await yt.add_to_playlist("vid123")
        assert result is None
        assert "quota" in yt.last_error.lower()
        yt._session.post.assert_not_called()

    async def test_token_refresh_failure_returns_none(self, yt):
        yt._access_token = None
        yt._token_expiry = 0
        yt._session.post.return_value = make_response(400, text="invalid_grant")

        result = await yt.add_to_playlist("vid123")
        assert result is None
        assert yt.last_error is not None
