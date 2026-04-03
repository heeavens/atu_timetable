import logging

import aiosqlite

from config.settings import DATABASE_URL

logger = logging.getLogger(__name__)


class Database:
    def __init__(self) -> None:
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        db_path = DATABASE_URL.replace("sqlite+aiosqlite:///", "")
        self._connection = await aiosqlite.connect(db_path)
        await self._create_tables()
        logger.info("Database connected: %s", db_path)

    async def _create_tables(self) -> None:
        if self._connection is None:
            raise RuntimeError("Database not connected")
        await self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_sessions (
                user_id INTEGER PRIMARY KEY,
                email TEXT NOT NULL,
                session_state BLOB NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        await self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schedule_cache (
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                lessons_json TEXT NOT NULL,
                cached_at TEXT NOT NULL,
                PRIMARY KEY (user_id, date)
            )
            """
        )
        await self._connection.commit()

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Database not connected")
        return self._connection

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()
            logger.info("Database connection closed")
