import asyncio
import datetime
import logging

import discord
from discord.ext import commands, tasks

from bot import config, db
from bot.url_parser import extract_video_ids
from bot.youtube import YouTubeClient

log = logging.getLogger(__name__)


class Commands(commands.Cog):
    def __init__(self, bot: commands.Bot, yt: YouTubeClient) -> None:
        self.bot = bot
        self.yt = yt
        self._scanning = False
        self._scan_cancelled = False
        self.auto_resume_scan.start()

    def cog_unload(self) -> None:
        self.auto_resume_scan.cancel()

    @commands.command()
    async def scan(self, ctx: commands.Context, arg: str | None = None) -> None:
        if ctx.channel.id != config.DISCORD_CHANNEL_ID:
            return

        if arg == "cancel":
            if self._scanning:
                self._scan_cancelled = True
                await ctx.send("Cancelling scan...")
            else:
                await db.clear_scan_state()
                await ctx.send("Scan state cleared.")
            return

        if self._scanning:
            await ctx.send("A scan is already running.")
            return

        if arg is None:
            await ctx.send(f"Usage: `{config.COMMAND_PREFIX}scan YYYY-MM-DD` or `{config.COMMAND_PREFIX}scan cancel`")
            return

        try:
            scan_date = datetime.date.fromisoformat(arg)
        except ValueError:
            await ctx.send("Invalid date format. Use YYYY-MM-DD.")
            return

        # Discord snowflake epoch is 2015-01-01; clamp to that minimum
        discord_epoch = datetime.date(2015, 1, 1)
        effective_date = max(scan_date, discord_epoch)
        after = datetime.datetime.combine(effective_date, datetime.time.min, tzinfo=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        await db.save_scan_state(
            channel_id=ctx.channel.id,
            scan_from=arg,
            started_at=now,
        )

        await self._run_scan(ctx.channel, after)

    async def _run_scan(
        self,
        channel: discord.TextChannel,
        after: datetime.datetime,
        resume_from: int | None = None,
        initial_scanned: int = 0,
        initial_added: int = 0,
    ) -> None:
        self._scanning = True
        self._scan_cancelled = False

        progress_msg = await channel.send("Starting scan...")
        scanned = initial_scanned
        added = initial_added
        last_msg_id = resume_from

        try:
            after_point = discord.Object(id=resume_from) if resume_from else after

            async for message in channel.history(
                limit=None, after=after_point, oldest_first=True,
            ):
                if self._scan_cancelled:
                    await db.clear_scan_state()
                    await progress_msg.edit(content=f"Scan cancelled. Scanned {scanned} messages, added {added} videos.")
                    return

                scanned += 1
                last_msg_id = message.id

                video_ids = extract_video_ids(message.content)
                now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                posted_at = message.created_at.strftime("%Y-%m-%dT%H:%M:%S")

                for vid in video_ids:
                    if await db.video_exists(vid):
                        continue

                    if not self.yt.quota_available():
                        await db.update_scan_progress(last_msg_id, scanned, added, status="paused")
                        await progress_msg.edit(
                            content=f"Scan paused — YouTube quota exhausted. "
                                    f"Scanned {scanned} messages, added {added} videos. "
                                    f"Will auto-resume when quota resets."
                        )
                        return

                    url = f"https://youtube.com/watch?v={vid}"
                    result = await self.yt.add_to_playlist(vid)

                    if result == "quota_exceeded":
                        await db.update_scan_progress(last_msg_id, scanned, added, status="paused")
                        await progress_msg.edit(
                            content=f"Scan paused — YouTube quota exhausted. "
                                    f"Scanned {scanned} messages, added {added} videos. "
                                    f"Will auto-resume when quota resets."
                        )
                        return

                    is_not_found = result == "not_found"
                    added_at = now if (result and result not in ("not_found",)) else None
                    playlist_item_id = result if (result and result not in ("not_found",)) else None

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
                    elif result:
                        added += 1
                    await asyncio.sleep(1.5)

                if scanned % 100 == 0:
                    await db.update_scan_progress(last_msg_id, scanned, added)
                    await progress_msg.edit(
                        content=f"Scanned {scanned} messages, added {added} videos so far..."
                    )

                if scanned % 500 == 0:
                    await asyncio.sleep(0.5)

            await db.update_scan_progress(last_msg_id or 0, scanned, added, status="completed")
            await db.clear_scan_state()
            await progress_msg.edit(
                content=f"Scan complete! Scanned {scanned} messages, added {added} videos."
            )
        finally:
            self._scanning = False

    @tasks.loop(hours=6)
    async def auto_resume_scan(self) -> None:
        if self._scanning:
            return

        state = await db.get_scan_state()
        if not state or state["status"] != "paused":
            return

        if not self.yt.quota_available():
            return

        available, msg = await self.yt.check_quota()
        if not available:
            log.info("Auto-resume check: %s", msg)
            return

        channel = self.bot.get_channel(state["channel_id"])
        if not channel:
            return

        log.info("Auto-resuming paused scan (quota verified with API)")
        await channel.send("Resuming scan (quota verified available)...")

        after = datetime.datetime.combine(
            datetime.date.fromisoformat(state["scan_from"]),
            datetime.time.min,
            tzinfo=datetime.timezone.utc,
        )

        await self._run_scan(
            channel,
            after,
            resume_from=state["last_message_id"],
            initial_scanned=state["messages_scanned"],
            initial_added=state["videos_added"],
        )

    @auto_resume_scan.before_loop
    async def before_auto_resume(self) -> None:
        await self.bot.wait_until_ready()

    @commands.command()
    async def link(self, ctx: commands.Context) -> None:
        await ctx.send(f"https://www.youtube.com/playlist?list={config.YOUTUBE_PLAYLIST_ID}")

    @commands.command()
    async def stats(self, ctx: commands.Context) -> None:
        s = await db.get_stats()
        lines = [
            f"**Videos tracked:** {s['total']}",
            f"**Added to playlist:** {s['added']}",
            f"**Failed/pending:** {s['failed']}",
            f"**Unique posters:** {s['unique_posters']}",
        ]
        if s["recent"]:
            lines.append("\n**Recent additions:**")
            for v in s["recent"]:
                lines.append(f"- `{v['video_id']}` — {v['posted_in_discord_at']}")
        await ctx.send("\n".join(lines))


async def setup(bot: commands.Bot) -> None:
    yt = bot._youtube_client  # type: ignore[attr-defined]
    await bot.add_cog(Commands(bot, yt))
