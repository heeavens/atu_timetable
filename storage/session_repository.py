import logging
from datetime import datetime

from cryptography.fernet import Fernet

from config.settings import SESSION_ENCRYPTION_KEY
from models.user_session import UserSession
from storage.database import Database

logger = logging.getLogger(__name__)


class SessionRepository:
    def __init__(self, database: Database) -> None:
        self._db = database
        self._fernet = Fernet(SESSION_ENCRYPTION_KEY.encode())

    async def get_session(self, user_id: int) -> UserSession | None:
        cursor = await self._db.connection.execute(
            "SELECT user_id, email, session_state, created_at, updated_at "
            "FROM user_sessions WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        decrypted_state = self._fernet.decrypt(row[2])
        return UserSession(
            user_id=row[0],
            email=row[1],
            session_state=decrypted_state,
            created_at=datetime.fromisoformat(row[3]),
            updated_at=datetime.fromisoformat(row[4]),
        )

    async def save_session(self, session: UserSession) -> None:
        encrypted_state = self._fernet.encrypt(session.session_state)
        await self._db.connection.execute(
            "INSERT OR REPLACE INTO user_sessions "
            "(user_id, email, session_state, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                session.user_id,
                session.email,
                encrypted_state,
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
            ),
        )
        await self._db.connection.commit()

    async def delete_session(self, user_id: int) -> None:
        await self._db.connection.execute(
            "DELETE FROM user_sessions WHERE user_id = ?", (user_id,)
        )
        await self._db.connection.commit()

    async def get_all_user_ids(self) -> list[int]:
        cursor = await self._db.connection.execute(
            "SELECT user_id FROM user_sessions"
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]
