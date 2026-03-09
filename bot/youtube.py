import asyncio
import datetime
import logging
import time

import aiohttp

from bot import config

log = logging.getLogger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"
PLAYLIST_INSERT_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
PLAYLIST_LIST_URL = "https://www.googleapis.com/youtube/v3/playlists"


class YouTubeClient:
    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None
        self._access_token: str | None = None
        self._token_expiry: float = 0
        self.api_calls_today: int = 0
        self._quota_reset_time: float = 0
        self.last_error: str | None = None

    @property
    def estimated_quota_used(self) -> int:
        return self.api_calls_today * config.QUOTA_COST_PER_INSERT

    @property
    def remaining_inserts(self) -> int:
        return max(0, (config.QUOTA_DAILY_LIMIT - self.estimated_quota_used) // config.QUOTA_COST_PER_INSERT)

    def quota_available(self) -> bool:
        if time.time() > self._quota_reset_time:
            self.api_calls_today = 0
            self._reset_quota_timer()
        return self.remaining_inserts > 0

    async def initialize(self) -> None:
        self._session = aiohttp.ClientSession()
        self._reset_quota_timer()

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    def _reset_quota_timer(self) -> None:
        now = datetime.datetime.now(datetime.timezone.utc)
        pacific = datetime.timezone(datetime.timedelta(hours=-8))
        now_pacific = now.astimezone(pacific)
        midnight = now_pacific.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
        self._quota_reset_time = midnight.timestamp()

    def _set_quota_cooldown(self) -> None:
        self._quota_reset_time = time.time() + datetime.timedelta(hours=config.QUOTA_COOLDOWN_HOURS).total_seconds()
        log.warning("Quota cooldown set for %d hours from now", config.QUOTA_COOLDOWN_HOURS)

    async def _refresh_access_token(self) -> None:
        assert self._session is not None
        async with self._session.post(TOKEN_URL, data={
            "client_id": config.YOUTUBE_CLIENT_ID,
            "client_secret": config.YOUTUBE_CLIENT_SECRET,
            "refresh_token": config.YOUTUBE_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        }) as resp:
            if resp.status != 200:
                body = await resp.text()
                log.error("Token refresh failed (%d): %s", resp.status, body)
                raise RuntimeError(f"OAuth token refresh failed: {resp.status}")
            data = await resp.json()
            self._access_token = data["access_token"]
            self._token_expiry = time.time() + data.get("expires_in", 3600) - 60

    async def _ensure_valid_token(self) -> None:
        if not self._access_token or time.time() >= self._token_expiry:
            await self._refresh_access_token()

    async def check_quota(self) -> tuple[bool, str]:
        assert self._session is not None
        await self._ensure_valid_token()
        async with self._session.get(
            PLAYLIST_LIST_URL,
            params={"part": "id", "id": config.YOUTUBE_PLAYLIST_ID, "maxResults": "1"},
            headers={"Authorization": f"Bearer {self._access_token}"},
        ) as resp:
            body = await resp.text()
            log.info("Quota check response (%d): %s", resp.status, body)
            if resp.status == 200:
                return True, "API responding, quota available"
            if resp.status == 403 and "quotaExceeded" in body:
                return False, "Quota still exhausted"
            return False, f"Unexpected response ({resp.status}): {body}"

    async def add_to_playlist(self, video_id: str) -> str | None:
        assert self._session is not None
        self.last_error = None

        if not self.quota_available():
            self.last_error = "YouTube daily quota exhausted. Waiting for reset."
            log.warning("YouTube quota exhausted, skipping add for %s", video_id)
            return None

        await self._ensure_valid_token()

        body = {
            "snippet": {
                "playlistId": config.YOUTUBE_PLAYLIST_ID,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id,
                },
            }
        }

        for attempt in range(config.RETRY_MAX_ATTEMPTS):
            async with self._session.post(
                PLAYLIST_INSERT_URL,
                params={"part": "snippet"},
                json=body,
                headers={"Authorization": f"Bearer {self._access_token}"},
            ) as resp:
                if resp.status == 200:
                    self.api_calls_today += 1
                    data = await resp.json()
                    log.info("Added %s to playlist (item %s)", video_id, data["id"])
                    return data["id"]

                if resp.status == 409:
                    log.info("Video %s already in playlist (409 conflict)", video_id)
                    self.api_calls_today += 1
                    return "already_in_playlist"

                if resp.status == 404:
                    self.api_calls_today += 1
                    self.last_error = f"HTTP 404 — YouTube says this video does not exist."
                    log.warning("Video %s not found (404), marking as permanent failure", video_id)
                    return "not_found"

                if resp.status == 403:
                    resp_body = await resp.text()
                    log.error("YouTube 403 response: %s", resp_body)
                    if "quotaExceeded" in resp_body:
                        self.last_error = "HTTP 403 — YouTube daily quota exceeded."
                        self.api_calls_today = config.QUOTA_DAILY_LIMIT // config.QUOTA_COST_PER_INSERT
                        self._set_quota_cooldown()
                        return "quota_exceeded"
                    self.last_error = f"HTTP 403 — Access forbidden. Response: {resp_body[:200]}"
                    log.error("Playlist insert forbidden (403): %s", resp_body)
                    return None

                if resp.status == 429:
                    wait = (config.RETRY_BACKOFF_BASE ** attempt) * config.RETRY_BACKOFF_MULTIPLIER
                    log.warning("Rate limited (429), backing off %ds", wait)
                    await asyncio.sleep(wait)
                    continue

                resp_body = await resp.text()
                self.last_error = f"HTTP {resp.status} — {resp_body[:200]}"
                log.error("Playlist insert failed (%d): %s", resp.status, resp_body)
                return None

        self.last_error = f"HTTP 429 — Rate limited. Exhausted {config.RETRY_MAX_ATTEMPTS} retries."
        log.error("Exhausted retries for playlist insert of %s", video_id)
        return None
