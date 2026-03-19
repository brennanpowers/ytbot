import aiosqlite

_db: aiosqlite.Connection | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id             TEXT NOT NULL UNIQUE,
    youtube_url          TEXT NOT NULL,
    discord_message_id   INTEGER NOT NULL,
    discord_user_id      INTEGER NOT NULL,
    added_to_playlist_at TEXT,
    posted_in_discord_at TEXT NOT NULL,
    playlist_item_id     TEXT,
    permanent_failure    INTEGER NOT NULL DEFAULT 0,
    error_detail         TEXT,
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_videos_video_id ON videos(video_id);

CREATE TABLE IF NOT EXISTS scan_state (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    channel_id          INTEGER NOT NULL,
    last_message_id     INTEGER,
    scan_from           TEXT NOT NULL,
    started_at          TEXT NOT NULL,
    messages_scanned    INTEGER NOT NULL DEFAULT 0,
    videos_added        INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'running'
);
"""


async def init_db(db_path: str) -> None:
    global _db
    _db = await aiosqlite.connect(db_path)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(_SCHEMA)
    await _migrate(_db)
    await _db.commit()


async def _migrate(db: aiosqlite.Connection) -> None:
    columns = await db.execute_fetchall("PRAGMA table_info(videos)")
    col_names = {row["name"] for row in columns}
    if "error_detail" not in col_names:
        await db.execute("ALTER TABLE videos ADD COLUMN error_detail TEXT")


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None


def get_db() -> aiosqlite.Connection:
    assert _db is not None, "Database not initialized"
    return _db


async def video_exists(video_id: str) -> bool:
    row = await get_db().execute_fetchall(
        "SELECT 1 FROM videos WHERE video_id = ?", (video_id,)
    )
    return len(row) > 0


async def add_video(
    video_id: str,
    youtube_url: str,
    discord_message_id: int,
    discord_user_id: int,
    posted_in_discord_at: str,
    added_to_playlist_at: str | None = None,
    playlist_item_id: str | None = None,
    error_detail: str | None = None,
) -> None:
    await get_db().execute(
        """INSERT OR IGNORE INTO videos
           (video_id, youtube_url, discord_message_id, discord_user_id,
            posted_in_discord_at, added_to_playlist_at, playlist_item_id, error_detail)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (video_id, youtube_url, discord_message_id, discord_user_id,
         posted_in_discord_at, added_to_playlist_at, playlist_item_id, error_detail),
    )
    await get_db().commit()


async def update_error_detail(video_id: str, error_detail: str | None) -> None:
    await get_db().execute(
        "UPDATE videos SET error_detail = ? WHERE video_id = ?",
        (error_detail, video_id),
    )
    await get_db().commit()


async def mark_video_added(video_id: str, added_at: str, playlist_item_id: str) -> None:
    await get_db().execute(
        """UPDATE videos SET added_to_playlist_at = ?, playlist_item_id = ?
           WHERE video_id = ?""",
        (added_at, playlist_item_id, video_id),
    )
    await get_db().commit()


async def mark_permanent_failure(video_id: str) -> None:
    await get_db().execute(
        "UPDATE videos SET permanent_failure = 1 WHERE video_id = ?", (video_id,)
    )
    await get_db().commit()


async def get_retryable_errors(limit: int = 10, offset: int = 0) -> tuple[list[dict], int]:
    db = get_db()
    count_row = await db.execute_fetchall(
        "SELECT COUNT(*) as c FROM videos "
        "WHERE added_to_playlist_at IS NULL AND permanent_failure = 0"
    )
    total = count_row[0]["c"]
    rows = await db.execute_fetchall(
        "SELECT video_id, youtube_url, error_detail, created_at FROM videos "
        "WHERE added_to_playlist_at IS NULL AND permanent_failure = 0 "
        "ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return [dict(r) for r in rows], total


async def clear_all_pending_errors() -> int:
    db = get_db()
    cursor = await db.execute(
        "UPDATE videos SET permanent_failure = 1 "
        "WHERE added_to_playlist_at IS NULL AND permanent_failure = 0"
    )
    await db.commit()
    return cursor.rowcount


async def get_failed_videos() -> list[dict]:
    rows = await get_db().execute_fetchall(
        "SELECT video_id, youtube_url FROM videos "
        "WHERE added_to_playlist_at IS NULL AND permanent_failure = 0"
    )
    return [dict(r) for r in rows]


async def get_stats(recent_limit: int = 5) -> dict:
    db = get_db()
    total = (await db.execute_fetchall("SELECT COUNT(*) as c FROM videos"))[0]["c"]
    added = (await db.execute_fetchall(
        "SELECT COUNT(*) as c FROM videos WHERE added_to_playlist_at IS NOT NULL"
    ))[0]["c"]
    failed = total - added
    posters = (await db.execute_fetchall(
        "SELECT COUNT(DISTINCT discord_user_id) as c FROM videos"
    ))[0]["c"]
    recent = await db.execute_fetchall(
        "SELECT video_id, youtube_url, posted_in_discord_at FROM videos "
        "ORDER BY created_at DESC LIMIT ?",
        (recent_limit,),
    )
    return {
        "total": total,
        "added": added,
        "failed": failed,
        "unique_posters": posters,
        "recent": [dict(r) for r in recent],
    }


async def get_latest_discord_message_id() -> int | None:
    rows = await get_db().execute_fetchall(
        "SELECT MAX(discord_message_id) as mid FROM videos"
    )
    return rows[0]["mid"] if rows and rows[0]["mid"] else None


async def get_scan_state() -> dict | None:
    rows = await get_db().execute_fetchall("SELECT * FROM scan_state WHERE id = 1")
    return dict(rows[0]) if rows else None


async def save_scan_state(
    channel_id: int,
    scan_from: str,
    started_at: str,
    last_message_id: int | None = None,
    messages_scanned: int = 0,
    videos_added: int = 0,
    status: str = "running",
) -> None:
    await get_db().execute(
        """INSERT OR REPLACE INTO scan_state
           (id, channel_id, last_message_id, scan_from, started_at,
            messages_scanned, videos_added, status)
           VALUES (1, ?, ?, ?, ?, ?, ?, ?)""",
        (channel_id, last_message_id, scan_from, started_at,
         messages_scanned, videos_added, status),
    )
    await get_db().commit()


async def update_scan_progress(
    last_message_id: int,
    messages_scanned: int,
    videos_added: int,
    status: str = "running",
) -> None:
    await get_db().execute(
        """UPDATE scan_state SET last_message_id = ?, messages_scanned = ?,
           videos_added = ?, status = ? WHERE id = 1""",
        (last_message_id, messages_scanned, videos_added, status),
    )
    await get_db().commit()


async def clear_scan_state() -> None:
    await get_db().execute("DELETE FROM scan_state WHERE id = 1")
    await get_db().commit()
