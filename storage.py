from __future__ import annotations
import aiosqlite
from dataclasses import dataclass
from typing import Optional
import expr_parser
from config import DB_PATH


@dataclass
class Pipeline:
    id: int
    name: str
    source_id: int
    source_title: str
    source_username: Optional[str]
    output_id: int


@dataclass
class Filter:
    id: int
    pipeline_id: int
    name: str
    expression: str
    type: str = "allow"  # "allow" | "block"


# source_id → list[Pipeline]; None means not loaded yet
_pipeline_cache: Optional[dict[int, list[Pipeline]]] = None


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        # Migrate old tables out of the way (only if not already done)
        if await _table_exists(db, "monitored_chats") and not await _table_exists(db, "_legacy_monitored_chats"):
            await db.execute("ALTER TABLE monitored_chats RENAME TO _legacy_monitored_chats")
        if await _table_exists(db, "filters") and not await _table_exists(db, "_legacy_filters"):
            await db.execute("ALTER TABLE filters RENAME TO _legacy_filters")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS pipelines (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT    NOT NULL UNIQUE,
                source_id        INTEGER NOT NULL,
                source_title     TEXT    NOT NULL,
                source_username  TEXT,
                output_id        INTEGER NOT NULL,
                added_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS filters (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                pipeline_id   INTEGER NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
                name          TEXT    NOT NULL,
                expression    TEXT    NOT NULL,
                type          TEXT    NOT NULL DEFAULT 'allow',
                UNIQUE(pipeline_id, name)
            )
        """)
        await db.execute("PRAGMA foreign_keys = ON")
        await db.commit()


async def _table_exists(db: aiosqlite.Connection, table: str) -> bool:
    async with db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ) as cur:
        return await cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Pipeline cache helpers
# ---------------------------------------------------------------------------

async def _load_pipeline_cache() -> dict[int, list[Pipeline]]:
    global _pipeline_cache
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, name, source_id, source_title, source_username, output_id FROM pipelines"
        ) as cur:
            rows = await cur.fetchall()
    cache: dict[int, list[Pipeline]] = {}
    for row in rows:
        p = Pipeline(*row)
        cache.setdefault(p.source_id, []).append(p)
    _pipeline_cache = cache
    return cache


def _invalidate_cache() -> None:
    global _pipeline_cache
    _pipeline_cache = None


# ---------------------------------------------------------------------------
# Pipeline CRUD
# ---------------------------------------------------------------------------

async def get_pipelines_for_source(source_id: int) -> list[Pipeline]:
    cache = _pipeline_cache if _pipeline_cache is not None else await _load_pipeline_cache()
    return cache.get(source_id, [])


async def get_all_pipelines() -> list[Pipeline]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, name, source_id, source_title, source_username, output_id "
            "FROM pipelines ORDER BY added_at"
        ) as cur:
            rows = await cur.fetchall()
    return [Pipeline(*row) for row in rows]


async def get_pipeline_by_name(name: str) -> Optional[Pipeline]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, name, source_id, source_title, source_username, output_id "
            "FROM pipelines WHERE name = ?",
            (name,),
        ) as cur:
            row = await cur.fetchone()
    return Pipeline(*row) if row else None


async def save_pipeline(
    name: str,
    source_id: int,
    source_title: str,
    source_username: Optional[str],
    output_id: int,
) -> Pipeline:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            "INSERT INTO pipelines (name, source_id, source_title, source_username, output_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, source_id, source_title, source_username, output_id),
        )
        pipeline_id = cur.lastrowid
        await db.commit()
    _invalidate_cache()
    return Pipeline(pipeline_id, name, source_id, source_title, source_username, output_id)


async def delete_pipeline(name: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        # Invalidate AST cache for all filters of this pipeline before deleting
        async with db.execute(
            "SELECT f.id FROM filters f "
            "JOIN pipelines p ON f.pipeline_id = p.id WHERE p.name = ?",
            (name,),
        ) as cur:
            fids = await cur.fetchall()
        for (fid,) in fids:
            expr_parser.invalidate(fid)
        cur = await db.execute("DELETE FROM pipelines WHERE name = ?", (name,))
        await db.commit()
        deleted = cur.rowcount > 0
    if deleted:
        _invalidate_cache()
    return deleted


# ---------------------------------------------------------------------------
# Filter CRUD
# ---------------------------------------------------------------------------

async def get_filters_for_pipeline(pipeline_id: int) -> list[Filter]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, pipeline_id, name, expression, type FROM filters "
            "WHERE pipeline_id = ? ORDER BY id",
            (pipeline_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [Filter(*row) for row in rows]


async def save_filter(
    pipeline_id: int,
    name: str,
    expression: str,
    filter_type: str = "allow",
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        async with db.execute(
            "SELECT id FROM filters WHERE pipeline_id = ? AND name = ?",
            (pipeline_id, name),
        ) as cur:
            existing = await cur.fetchone()

        if existing:
            fid = existing[0]
            await db.execute(
                "UPDATE filters SET expression = ?, type = ? WHERE id = ?",
                (expression, filter_type, fid),
            )
            expr_parser.invalidate(fid)
        else:
            await db.execute(
                "INSERT INTO filters (pipeline_id, name, expression, type) VALUES (?, ?, ?, ?)",
                (pipeline_id, name, expression, filter_type),
            )
        await db.commit()


async def delete_filter(pipeline_id: int, name: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM filters WHERE pipeline_id = ? AND name = ?",
            (pipeline_id, name),
        ) as cur:
            rows = await cur.fetchall()
        if not rows:
            return False
        for (fid,) in rows:
            expr_parser.invalidate(fid)
        await db.execute(
            "DELETE FROM filters WHERE pipeline_id = ? AND name = ?",
            (pipeline_id, name),
        )
        await db.commit()
    return True


async def count_filters_for_pipeline(pipeline_id: int) -> tuple[int, int]:
    """Returns (allow_count, block_count)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT type, COUNT(*) FROM filters WHERE pipeline_id = ? GROUP BY type",
            (pipeline_id,),
        ) as cur:
            rows = await cur.fetchall()
    counts = {row[0]: row[1] for row in rows}
    return counts.get("allow", 0), counts.get("block", 0)
