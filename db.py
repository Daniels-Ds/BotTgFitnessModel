"""
SQLite-based persistence.
- FSM storage: сохраняет состояния пользователей между перезапусками
- User data: кэш сгенерированного контента
"""
import json
import logging
import aiosqlite
from pathlib import Path
from typing import Optional, Dict, Any

from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType
from aiogram.fsm.state import State

logger = logging.getLogger(__name__)

DB_PATH = Path("data/bot.db")


async def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS fsm_data (
                key TEXT PRIMARY KEY,
                state TEXT,
                data TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS generation_queue (
                user_id INTEGER PRIMARY KEY,
                status TEXT DEFAULT 'idle',
                position INTEGER DEFAULT 0,
                updated_at REAL DEFAULT (unixepoch())
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS workout_weeks (
                user_id INTEGER NOT NULL,
                week_no INTEGER NOT NULL CHECK(week_no BETWEEN 1 AND 4),
                body TEXT NOT NULL DEFAULT '',
                updated_at REAL DEFAULT (unixepoch()),
                PRIMARY KEY (user_id, week_no)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS workout_days (
                user_id INTEGER NOT NULL,
                day_date TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                updated_at REAL DEFAULT (unixepoch()),
                PRIMARY KEY (user_id, day_date)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS body_measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                waist_cm INTEGER NOT NULL,
                hips_cm INTEGER NOT NULL,
                chest_cm INTEGER NOT NULL,
                shoulders_cm INTEGER NOT NULL,
                thigh_cm INTEGER NOT NULL,
                calf_cm INTEGER NOT NULL,
                biceps_cm INTEGER NOT NULL,
                front_photo_file_id TEXT,
                runninghub_task_id TEXT,
                runninghub_result_url TEXT,
                runninghub_status TEXT DEFAULT 'pending',
                runninghub_reason TEXT,
                created_at REAL DEFAULT (unixepoch())
            )
        """)
        await db.commit()
    logger.info("DB initialized")


class SQLiteStorage(BaseStorage):
    """FSM storage backed by SQLite — survives bot restarts."""

    def _key(self, key: StorageKey) -> str:
        return f"{key.bot_id}:{key.chat_id}:{key.user_id}"

    async def set_state(self, key: StorageKey, state: StateType = None):
        k = self._key(key)
        state_str = state.state if isinstance(state, State) else (state or "")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO fsm_data(key, state) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET state=excluded.state",
                (k, state_str)
            )
            await db.commit()

    async def get_state(self, key: StorageKey) -> Optional[str]:
        k = self._key(key)
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT state FROM fsm_data WHERE key=?", (k,)) as cur:
                row = await cur.fetchone()
                return row[0] if row else None

    async def set_data(self, key: StorageKey, data: Dict[str, Any]):
        k = self._key(key)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO fsm_data(key, data) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET data=excluded.data",
                (k, json.dumps(data, default=_bytes_serializer))
            )
            await db.commit()

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        k = self._key(key)
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT data FROM fsm_data WHERE key=?", (k,)) as cur:
                row = await cur.fetchone()
                if row and row[0]:
                    return json.loads(row[0], object_hook=_bytes_deserializer)
                return {}

    async def close(self):
        pass


def _bytes_serializer(obj):
    if isinstance(obj, (bytes, bytearray)):
        return {"__bytes__": True, "data": list(obj)}
    raise TypeError(f"Not serializable: {type(obj)}")


def _bytes_deserializer(d):
    if d.get("__bytes__"):
        return bytes(d["data"])
    return d


# ── Generation queue ──────────────────────────────────────

_active_generations: set[int] = set()  # user_ids currently generating
MAX_CONCURRENT = 3  # max parallel VEO jobs


def is_generating(user_id: int) -> bool:
    return user_id in _active_generations


def generation_count() -> int:
    return len(_active_generations)


def start_generation(user_id: int):
    _active_generations.add(user_id)


def finish_generation(user_id: int):
    _active_generations.discard(user_id)


async def save_body_measurement(
    user_id: int,
    values: Dict[str, int],
    *,
    front_photo_file_id: str = "",
    runninghub_task_id: str = "",
    runninghub_result_url: str = "",
    runninghub_status: str = "pending",
    runninghub_reason: str = "",
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO body_measurements (
                user_id,
                waist_cm,
                hips_cm,
                chest_cm,
                shoulders_cm,
                thigh_cm,
                calf_cm,
                biceps_cm,
                front_photo_file_id,
                runninghub_task_id,
                runninghub_result_url,
                runninghub_status,
                runninghub_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                int(values["waist"]),
                int(values["hips"]),
                int(values["chest"]),
                int(values["shoulders"]),
                int(values["thigh"]),
                int(values["calf"]),
                int(values["biceps"]),
                front_photo_file_id or "",
                runninghub_task_id or "",
                runninghub_result_url or "",
                runninghub_status or "pending",
                runninghub_reason or "",
            ),
        )
        await db.commit()


async def get_latest_body_measurement(user_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT
                waist_cm,
                hips_cm,
                chest_cm,
                shoulders_cm,
                thigh_cm,
                calf_cm,
                biceps_cm,
                runninghub_status,
                runninghub_result_url,
                created_at
            FROM body_measurements
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "waist": int(row[0]),
                "hips": int(row[1]),
                "chest": int(row[2]),
                "shoulders": int(row[3]),
                "thigh": int(row[4]),
                "calf": int(row[5]),
                "biceps": int(row[6]),
                "runninghub_status": str(row[7] or ""),
                "runninghub_result_url": str(row[8] or ""),
                "created_at": float(row[9] or 0),
            }


# ── Workout plan (4 weeks, stored separately) ───────────────────────────


async def get_workout_ready_weeks(user_id: int) -> set[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT week_no FROM workout_weeks WHERE user_id = ? AND length(trim(body)) > 0",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
            return {int(r[0]) for r in rows}


async def get_workout_week_body(user_id: int, week_no: int) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT body FROM workout_weeks WHERE user_id = ? AND week_no = ?",
            (user_id, week_no),
        ) as cur:
            row = await cur.fetchone()
            if not row or not str(row[0] or "").strip():
                return None
            return str(row[0])


async def save_workout_week_body(user_id: int, week_no: int, body: str) -> None:
    text = (body or "").strip()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO workout_weeks(user_id, week_no, body, updated_at)
            VALUES (?, ?, ?, unixepoch())
            ON CONFLICT(user_id, week_no) DO UPDATE SET
                body = excluded.body,
                updated_at = excluded.updated_at
            """,
            (user_id, week_no, text),
        )
        await db.commit()


async def clear_workout_plan(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM workout_weeks WHERE user_id = ?", (user_id,))
        await db.commit()


# ── Тренировка на сегодня (по календарной дате) ─────────────────────────


async def get_workout_day_body(user_id: int, day_date: str) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT body FROM workout_days WHERE user_id = ? AND day_date = ?",
            (user_id, day_date),
        ) as cur:
            row = await cur.fetchone()
            if not row or not str(row[0] or "").strip():
                return None
            return str(row[0])


async def save_workout_day_body(user_id: int, day_date: str, body: str) -> None:
    text = (body or "").strip()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO workout_days(user_id, day_date, body, updated_at)
            VALUES (?, ?, ?, unixepoch())
            ON CONFLICT(user_id, day_date) DO UPDATE SET
                body = excluded.body,
                updated_at = excluded.updated_at
            """,
            (user_id, day_date, text),
        )
        await db.commit()


async def delete_workout_day(user_id: int, day_date: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM workout_days WHERE user_id = ? AND day_date = ?",
            (user_id, day_date),
        )
        await db.commit()