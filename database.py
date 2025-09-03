# database.py
import aiosqlite
from datetime import datetime
from config import DB_PATH

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS warnings (
    user_id INTEGER PRIMARY KEY,
    count   INTEGER DEFAULT 0
);
"""

CREATE_IMMUNE_SQL = """
CREATE TABLE IF NOT EXISTS immune_users (
    user_id   INTEGER PRIMARY KEY,
    username  TEXT,
    added_at  TEXT
);
"""

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_TABLE_SQL)
        await db.execute(CREATE_IMMUNE_SQL)   # <--- NEW
        await db.commit()

# ----- warnings (как у тебя было) -----
async def get_warnings(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT count FROM warnings WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0

async def add_warning(user_id: int) -> int:
    current = await get_warnings(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        if current == 0:
            await db.execute("INSERT INTO warnings (user_id, count) VALUES (?, 1)", (user_id,))
        else:
            await db.execute("UPDATE warnings SET count = count + 1 WHERE user_id = ?", (user_id,))
        await db.commit()
    return current + 1

async def reset_warnings(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM warnings WHERE user_id = ?", (user_id,))
        await db.commit()

# ----- IMMUNE USERS (NEW) -----
async def add_immune_user(user_id: int, username: str | None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO immune_users (user_id, username, added_at) VALUES (?, ?, ?)",
            (user_id, username, datetime.utcnow().isoformat(timespec="seconds"))
        )
        await db.commit()

async def remove_immune_user(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM immune_users WHERE user_id = ?", (user_id,))
        await db.commit()

async def is_immune_user(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM immune_users WHERE user_id = ?", (user_id,))
        return (await cur.fetchone()) is not None

async def list_immune_users() -> list[tuple[int, str | None, str]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id, username, added_at FROM immune_users ORDER BY added_at DESC")
        return await cur.fetchall()
