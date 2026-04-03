from dataclasses import dataclass
from datetime import datetime


@dataclass
class UserSession:
    user_id: int
    email: str
    session_state: bytes
    created_at: datetime
    updated_at: datetime
