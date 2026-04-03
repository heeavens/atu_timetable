import json
import logging
from datetime import date, datetime, time, timedelta

from config.settings import SCHEDULE_CACHE_TTL_HOURS
from models.lesson import Lesson
from models.schedule import DaySchedule
from storage.database import Database

logger = logging.getLogger(__name__)


class ScheduleRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def get_cached_schedule(
        self, user_id: int, target_date: date
    ) -> DaySchedule | None:
        cursor = await self._db.connection.execute(
            "SELECT lessons_json, cached_at FROM schedule_cache "
            "WHERE user_id = ? AND date = ?",
            (user_id, target_date.isoformat()),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        cached_at = datetime.fromisoformat(row[1])
        if datetime.now() - cached_at > timedelta(hours=SCHEDULE_CACHE_TTL_HOURS):
            return None

        lessons_data = json.loads(row[0])
        lessons = [
            Lesson(
                subject=entry["subject"],
                start_time=time.fromisoformat(entry["start_time"]),
                end_time=time.fromisoformat(entry["end_time"]),
                room=entry["room"],
                building=entry.get("building"),
                lecturer=entry.get("lecturer"),
                lesson_type=entry["lesson_type"],
                maps_url=entry["maps_url"],
            )
            for entry in lessons_data
        ]
        return DaySchedule(date=target_date, lessons=lessons)

    async def cache_schedule(
        self, user_id: int, schedule: DaySchedule
    ) -> None:
        lessons_json = json.dumps(
            [
                {
                    "subject": lesson.subject,
                    "start_time": lesson.start_time.isoformat(),
                    "end_time": lesson.end_time.isoformat(),
                    "room": lesson.room,
                    "building": lesson.building,
                    "lecturer": lesson.lecturer,
                    "lesson_type": lesson.lesson_type,
                    "maps_url": lesson.maps_url,
                }
                for lesson in schedule.lessons
            ]
        )
        await self._db.connection.execute(
            "INSERT OR REPLACE INTO schedule_cache "
            "(user_id, date, lessons_json, cached_at) VALUES (?, ?, ?, ?)",
            (
                user_id,
                schedule.date.isoformat(),
                lessons_json,
                datetime.now().isoformat(),
            ),
        )
        await self._db.connection.commit()

    async def delete_user_cache(self, user_id: int) -> None:
        await self._db.connection.execute(
            "DELETE FROM schedule_cache WHERE user_id = ?",
            (user_id,),
        )
        await self._db.connection.commit()
        logger.info(
            "Deleted schedule cache for user %d", user_id
        )
