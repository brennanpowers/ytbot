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

    def cog_unload(self) -> None:
        self.retry_failed.cancel()

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
                    await message.add_reaction("\U0001f501")  # 🔁
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
            )
            if is_not_found:
                await db.mark_permanent_failure(vid)

            try:
                if is_not_found:
                    await message.add_reaction("\u274c")  # ❌
                elif result:
                    await message.add_reaction("\u2705")  # ✅
                else:
                    await message.add_reaction("\u26a0\ufe0f")  # ⚠️
            except discord.HTTPException:
                pass

    @tasks.loop(minutes=30)
    async def retry_failed(self) -> None:
        failed = await db.get_failed_videos()
        if not failed:
            return

        log.info("Retrying %d failed videos", len(failed))
        import asyncio
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        for video in failed:
            if not self.yt.quota_available():
                log.warning("Quota exhausted during retry, stopping")
                break
            result = await self.yt.add_to_playlist(video["video_id"])
            if result == "quota_exceeded":
                log.warning("Quota exhausted during retry, stopping")
                break
            if result == "not_found":
                await db.mark_permanent_failure(video["video_id"])
                log.info("Marked %s as permanent failure (not found)", video["video_id"])
            elif result:
                await db.mark_video_added(video["video_id"], now, result)
                log.info("Retry succeeded for %s", video["video_id"])
            await asyncio.sleep(1)

    @retry_failed.before_loop
    async def before_retry(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    yt = bot._youtube_client  # type: ignore[attr-defined]
    await bot.add_cog(LinkListener(bot, yt))
