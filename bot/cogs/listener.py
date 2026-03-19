import asyncio
import datetime
import logging

import discord
from discord.ext import commands, tasks

from bot import config, db
from bot.url_parser import extract_video_ids
from bot.youtube import YouTubeClient

log = logging.getLogger(__name__)


class LinkListener(commands.Cog):
    def __init__(self, bot: commands.Bot, yt: YouTubeClient) -> None:
        self.bot = bot
        self.yt = yt
        self.retry_failed.start()
        self._startup_scan_done = False

    def cog_unload(self) -> None:
        self.retry_failed.cancel()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._startup_scan_done:
            return
        self._startup_scan_done = True
        await self._startup_scan()

    async def _startup_scan(self) -> None:
        last_msg_id = await db.get_latest_discord_message_id()
        if not last_msg_id:
            log.info("Startup scan: no videos in DB, skipping")
            return

        channel = self.bot.get_channel(config.DISCORD_CHANNEL_ID)
        if not channel:
            log.warning("Startup scan: channel %s not found", config.DISCORD_CHANNEL_ID)
            return

        log.info("Startup scan: checking for new messages after %s", last_msg_id)
        added = 0
        scanned = 0

        async for message in channel.history(
            limit=None, after=discord.Object(id=last_msg_id), oldest_first=True,
        ):
            if message.author.bot:
                continue
            scanned += 1

            video_ids = extract_video_ids(message.content)
            if not video_ids:
                continue

            now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            posted_at = message.created_at.strftime("%Y-%m-%dT%H:%M:%S")

            for vid in video_ids:
                if await db.video_exists(vid):
                    continue

                if not self.yt.quota_available():
                    log.warning("Startup scan: quota exhausted after %d messages, %d added", scanned, added)
                    return

                url = f"https://youtube.com/watch?v={vid}"
                result = await self.yt.add_to_playlist(vid)

                if result == "quota_exceeded":
                    log.warning("Startup scan: quota exhausted after %d messages, %d added", scanned, added)
                    return

                if result is None and self.yt.last_error and "OAuth" in self.yt.last_error:
                    log.error("Startup scan: auth failure, aborting — %s", self.yt.last_error)
                    return

                is_not_found = result == "not_found"
                sentinel = ("not_found", "quota_exceeded")
                added_at = now if (result and result not in sentinel) else None
                playlist_item_id = result if (result and result not in sentinel) else None

                await db.add_video(
                    video_id=vid,
                    youtube_url=url,
                    discord_message_id=message.id,
                    discord_user_id=message.author.id,
                    posted_in_discord_at=posted_at,
                    added_to_playlist_at=added_at,
                    playlist_item_id=playlist_item_id,
                    error_detail=self.yt.last_error,
                )
                if is_not_found:
                    await db.mark_permanent_failure(vid)
                elif result:
                    added += 1
                    try:
                        await message.add_reaction(config.REACTION_ADDED)
                    except discord.HTTPException:
                        pass

                await asyncio.sleep(config.SCAN_THROTTLE_SECONDS)

        log.info("Startup scan complete: scanned %d messages, added %d videos", scanned, added)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.channel.id != config.DISCORD_CHANNEL_ID:
            return

        video_ids = extract_video_ids(message.content)
        if not video_ids:
            return

        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        posted_at = message.created_at.strftime("%Y-%m-%dT%H:%M:%S")

        for vid in video_ids:
            if await db.video_exists(vid):
                try:
                    await message.add_reaction(config.REACTION_DUPLICATE)
                except discord.HTTPException:
                    pass
                continue

            url = f"https://youtube.com/watch?v={vid}"
            result = await self.yt.add_to_playlist(vid)

            sentinel = ("not_found", "quota_exceeded")
            is_not_found = result == "not_found"
            added_at = now if (result and result not in sentinel) else None
            playlist_item_id = result if (result and result not in sentinel) else None

            await db.add_video(
                video_id=vid,
                youtube_url=url,
                discord_message_id=message.id,
                discord_user_id=message.author.id,
                posted_in_discord_at=posted_at,
                added_to_playlist_at=added_at,
                playlist_item_id=playlist_item_id,
                error_detail=self.yt.last_error,
            )
            if is_not_found:
                await db.mark_permanent_failure(vid)

            try:
                if is_not_found:
                    await message.add_reaction(config.REACTION_NOT_FOUND)
                    error_detail = self.yt.last_error or "Unknown error"
                    await message.reply(
                        f"Couldn't add `{vid}` to the playlist — video not found on YouTube. "
                        f"It may have been deleted or made private.\n"
                        f"**Video ID:** `{vid}`\n"
                        f"**URL:** {url}\n"
                        f"**Error:** {error_detail}",
                        mention_author=False,
                    )
                elif result:
                    await message.add_reaction(config.REACTION_ADDED)
                else:
                    await message.add_reaction(config.REACTION_WARNING)
                    error_detail = self.yt.last_error or "Unknown error"
                    await message.reply(
                        f"Couldn't add `{vid}` to the playlist right now. I'll keep trying automatically.\n"
                        f"**Video ID:** `{vid}`\n"
                        f"**URL:** {url}\n"
                        f"**Error:** {error_detail}",
                        mention_author=False,
                    )
            except discord.HTTPException:
                pass

    @tasks.loop(hours=config.RETRY_INTERVAL_HOURS)
    async def retry_failed(self) -> None:
        failed = await db.get_failed_videos()
        if not failed:
            return

        if not self.yt.quota_available():
            return

        available, msg = await self.yt.check_quota()
        if not available:
            log.info("Retry check: %s", msg)
            return

        log.info("Retrying %d failed videos", len(failed))
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        for video in failed:
            if not self.yt.quota_available():
                log.warning("Quota exhausted during retry, stopping")
                break
            result = await self.yt.add_to_playlist(video["video_id"])
            if result == "quota_exceeded":
                await db.update_error_detail(video["video_id"], self.yt.last_error)
                log.warning("Quota exhausted during retry, stopping")
                break
            if result == "not_found":
                await db.update_error_detail(video["video_id"], self.yt.last_error)
                await db.mark_permanent_failure(video["video_id"])
                log.info("Marked %s as permanent failure (not found)", video["video_id"])
            elif result:
                await db.update_error_detail(video["video_id"], None)
                await db.mark_video_added(video["video_id"], now, result)
                log.info("Retry succeeded for %s", video["video_id"])
            else:
                await db.update_error_detail(video["video_id"], self.yt.last_error)
            await asyncio.sleep(config.RETRY_THROTTLE_SECONDS)

    @retry_failed.before_loop
    async def before_retry(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    yt = bot._youtube_client  # type: ignore[attr-defined]
    await bot.add_cog(LinkListener(bot, yt))
