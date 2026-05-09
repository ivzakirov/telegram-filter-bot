from __future__ import annotations
import aiosqlite
from dataclasses import dataclass
from typing import Optional
import expr_parser
from config import DB_PATH


@dataclass
class Filter:
    id: int
    name: str
    expression: str
    chat_id: Optional[int]


@dataclass
class MonitoredChat:
    chat_id: int
    title: str
    username: Optional[str]


# In-memory set of monitored chat IDs to avoid a DB hit on every message.
_monitored_ids: Optional[set[int]] = None


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS monitored_chats (
                chat_id   INTEGER PRIMARY KEY,
                title     TEXT,
                username  TEXT,
                added_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS filters (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    NOT NULL,
                expression TEXT    NOT NULL,
                chat_id    INTEGER
            )
        """)
        await db.commit()


async def _get_monitored_ids() -> set[int]:
    global _monitored_ids
    if _monitored_ids is None:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT chat_id FROM monitored_chats") as cur:
                rows = await cur.fetchall()
        _monitored_ids = {row[0] for row in rows}
    return _monitored_ids


async def is_monitored(chat_id: int) -> bool:
    return chat_id in await _get_monitored_ids()


async def save_chat(chat_id: int, title: str, username: Optional[str]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO monitored_chats (chat_id, title, username) VALUES (?, ?, ?)",
            (chat_id, title, username),
        )
        await db.commit()
    ids = await _get_monitored_ids()
    ids.add(chat_id)


async def delete_chat(chat_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM monitored_chats WHERE chat_id = ?", (chat_id,)
        )
        await db.commit()
        deleted = cur.rowcount > 0
    if deleted:
        ids = await _get_monitored_ids()
        ids.discard(chat_id)
    return deleted


async def get_all_chats() -> list[MonitoredChat]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT chat_id, title, username FROM monitored_chats ORDER BY added_at"
        ) as cur:
            rows = await cur.fetchall()
    return [MonitoredChat(*row) for row in rows]


async def get_filters_for_chat(chat_id: int) -> list[Filter]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, name, expression, chat_id FROM filters "
            "WHERE chat_id = ? OR chat_id IS NULL ORDER BY id",
            (chat_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [Filter(*row) for row in rows]


async def save_filter(
    name: str, expression: str, chat_id: Optional[int] = None
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        # Check for existing filter with same name+chat_id (NULL-safe comparison).
        async with db.execute(
            "SELECT id FROM filters WHERE name = ? AND chat_id IS ?",
            (name, chat_id),
        ) as cur:
            existing = await cur.fetchone()

        if existing:
            fid = existing[0]
            await db.execute(
                "UPDATE filters SET expression = ? WHERE id = ?",
                (expression, fid),
            )
            expr_parser.invalidate(fid)
        else:
            await db.execute(
                "INSERT INTO filters (name, expression, chat_id) VALUES (?, ?, ?)",
                (name, expression, chat_id),
            )
        await db.commit()


async def delete_filter(name: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM filters WHERE name = ?", (name,)
        ) as cur:
            rows = await cur.fetchall()
        if not rows:
            return False
        for (fid,) in rows:
            expr_parser.invalidate(fid)
        await db.execute("DELETE FROM filters WHERE name = ?", (name,))
        await db.commit()
    return True


async def get_all_filters() -> list[Filter]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, name, expression, chat_id FROM filters ORDER BY name, chat_id"
        ) as cur:
            rows = await cur.fetchall()
    return [Filter(*row) for row in rows]


async def count_chats() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM monitored_chats") as cur:
            row = await cur.fetchone()
    return row[0]


async def count_filters() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM filters") as cur:
            row = await cur.fetchone()
    return row[0]
