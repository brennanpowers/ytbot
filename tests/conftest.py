import os

# Required env vars must be set BEFORE any bot module is imported.
# pytest loads conftest.py before collecting test modules, so these
# os.environ.setdefault() calls run before `from bot import config`
# in any test file — preventing the config module's _require() from
# calling sys.exit(1) on missing vars.
os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("DISCORD_CHANNEL_ID", "123456789")
os.environ.setdefault("YOUTUBE_PLAYLIST_ID", "PLtest123")
os.environ.setdefault("YOUTUBE_CLIENT_ID", "test-client-id")
os.environ.setdefault("YOUTUBE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("YOUTUBE_REFRESH_TOKEN", "test-refresh-token")

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from bot import db


@pytest_asyncio.fixture
async def tmp_db():
    """Provide a fresh in-memory database for each test, torn down after."""
    await db.init_db(":memory:")
    yield db
    await db.close_db()


@pytest.fixture
def make_message():
    """Factory fixture for mock Discord messages."""
    def _factory(
        content="",
        channel_id=123456789,
        author_bot=False,
        msg_id=1,
        user_id=100,
    ):
        msg = AsyncMock()
        msg.content = content
        msg.channel = MagicMock()
        msg.channel.id = channel_id
        msg.author = MagicMock()
        msg.author.bot = author_bot
        msg.author.id = user_id
        msg.id = msg_id
        msg.created_at = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
        return msg
    return _factory


@pytest.fixture
def make_ctx():
    """Factory fixture for mock Discord command contexts."""
    def _factory(channel_id=123456789, author_id=100):
        ctx = AsyncMock()
        ctx.channel = MagicMock()
        ctx.channel.id = channel_id
        ctx.send = AsyncMock()
        ctx.author = MagicMock()
        ctx.author.id = author_id
        return ctx
    return _factory
