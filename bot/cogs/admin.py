import datetime
import logging

from discord.ext import commands

from bot import config, db
from bot.youtube import YouTubeClient

log = logging.getLogger(__name__)


def is_admin():
    async def predicate(ctx: commands.Context) -> bool:
        if config.DISCORD_ADMIN_USER_ID is None:
            return False
        return ctx.author.id == config.DISCORD_ADMIN_USER_ID
    return commands.check(predicate)


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot, yt: YouTubeClient, start_time: datetime.datetime) -> None:
        self.bot = bot
        self.yt = yt
        self.start_time = start_time

    @commands.command()
    @is_admin()
    async def status(self, ctx: commands.Context) -> None:
        uptime = datetime.datetime.now(datetime.timezone.utc) - self.start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        s = await db.get_stats()
        scan_state = await db.get_scan_state()

        lines = [
            f"**Uptime:** {hours}h {minutes}m {seconds}s",
            f"**Videos tracked:** {s['total']}",
            f"**Added to playlist:** {s['added']}",
            f"**Failed/pending:** {s['failed']}",
            f"**Estimated quota used:** {self.yt.estimated_quota_used}/{config.QUOTA_DAILY_LIMIT}",
            f"**Remaining inserts:** {self.yt.remaining_inserts}",
        ]

        if scan_state:
            lines.append(f"\n**Scan status:** {scan_state['status']}")
            lines.append(f"**Messages scanned:** {scan_state['messages_scanned']}")
            lines.append(f"**Videos added (scan):** {scan_state['videos_added']}")

        await ctx.send("\n".join(lines))

    @commands.command()
    @is_admin()
    async def quota(self, ctx: commands.Context) -> None:
        available, message = await self.yt.check_quota()
        emoji = config.REACTION_QUOTA_OK if available else config.REACTION_QUOTA_FAIL
        await ctx.send(f"{emoji} {message}")

    @commands.command()
    @is_admin()
    async def retry(self, ctx: commands.Context) -> None:
        failed = await db.get_failed_videos()
        if not failed:
            await ctx.send("No failed videos to retry.")
            return

        await ctx.send(f"Retrying {len(failed)} failed videos...")
        import asyncio
        succeeded = 0
        skipped = 0
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        for video in failed:
            if not self.yt.quota_available():
                await ctx.send(f"Quota exhausted. Retried {succeeded}/{len(failed)} successfully, {skipped} failed.")
                return
            result = await self.yt.add_to_playlist(video["video_id"])
            if result == "not_found":
                await db.mark_permanent_failure(video["video_id"])
                skipped += 1
            elif result:
                await db.mark_video_added(video["video_id"], now, result)
                succeeded += 1
            else:
                skipped += 1
            await asyncio.sleep(config.RETRY_THROTTLE_SECONDS)

        await ctx.send(f"Retry complete. {succeeded} succeeded, {skipped} failed.")


async def setup(bot: commands.Bot) -> None:
    yt = bot._youtube_client  # type: ignore[attr-defined]
    start_time = bot._start_time  # type: ignore[attr-defined]
    await bot.add_cog(Admin(bot, yt, start_time))
