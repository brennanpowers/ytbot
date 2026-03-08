import datetime
import logging
import os
import sys

import discord
from discord.ext import commands

from bot import config, db
from bot.youtube import YouTubeClient


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    log = logging.getLogger(__name__)

    os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)

    intents = discord.Intents.default()
    intents.message_content = True

    bot = commands.Bot(command_prefix=config.COMMAND_PREFIX, intents=intents)
    yt = YouTubeClient()
    bot._youtube_client = yt  # type: ignore[attr-defined]
    bot._start_time = datetime.datetime.now(datetime.timezone.utc)  # type: ignore[attr-defined]

    @bot.event
    async def on_ready() -> None:
        log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
        log.info("Watching channel %s", config.DISCORD_CHANNEL_ID)

    @bot.event
    async def setup_hook() -> None:
        await db.init_db(config.DB_PATH)
        await yt.initialize()
        await bot.load_extension("bot.cogs.listener")
        await bot.load_extension("bot.cogs.commands")
        await bot.load_extension("bot.cogs.admin")
        log.info("Bot setup complete")

    try:
        bot.run(config.DISCORD_BOT_TOKEN, log_handler=None)
    except KeyboardInterrupt:
        pass
    finally:
        log.info("Shutting down")


if __name__ == "__main__":
    main()
