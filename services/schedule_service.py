import logging
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from config.settings import TIMEZONE
from models.lesson import Lesson
from models.schedule import DaySchedule
from services.scraper_service import ScraperService, SessionExpiredError
from storage.schedule_repository import ScheduleRepository
from storage.session_repository import SessionRepository

logger = logging.getLogger(__name__)


class ScheduleService:
    def __init__(
        self,
        scraper: ScraperService,
        schedule_repo: ScheduleRepository,
        session_repo: SessionRepository,
    ) -> None:
        self._scraper = scraper
        self._schedule_repo = schedule_repo
        self._session_repo = session_repo

    def get_current_lesson(
        self, schedule: DaySchedule, now: datetime
    ) -> Lesson | None:
        current_time = now.time()
        for lesson in schedule.lessons:
            if lesson.start_time <= current_time < lesson.end_time:
                return lesson
        return None

    def get_next_lesson(
        self, schedule: DaySchedule, now: datetime
    ) -> Lesson | None:
        current_time = now.time()
        next_hour = (now.hour + 1) % 24
        next_hour_time = time(next_hour, 0)
        next_hour_end = time(next_hour, 59)

        for lesson in schedule.lessons:
            if next_hour_time <= lesson.start_time <= next_hour_end:
                return lesson

        for lesson in schedule.lessons:
            if lesson.start_time > current_time:
                return lesson

        return None

    async def get_day_schedule(
        self, user_id: int, target_date: date
    ) -> DaySchedule:
        cached = await self._schedule_repo.get_cached_schedule(user_id, target_date)
        if cached:
            logger.info("Using cached schedule for %s", target_date.isoformat())
            return cached

        session = await self._session_repo.get_session(user_id)
        if session is None:
            raise AuthenticationRequiredError("No session found, please /start first")

        try:
            lessons = await self._scraper.scrape_schedule(
                session.session_state, target_date
            )
        except SessionExpiredError:
            await self._session_repo.delete_session(user_id)
            raise AuthenticationRequiredError(
                "Your session has expired. Please use /start to log in again."
            )

        schedule = DaySchedule(date=target_date, lessons=lessons)
        await self._schedule_repo.cache_schedule(user_id, schedule)
        return schedule

    @staticmethod
    def now_dublin() -> datetime:
        return datetime.now(tz=ZoneInfo(TIMEZONE))

    @staticmethod
    def today_dublin() -> date:
        return datetime.now(tz=ZoneInfo(TIMEZONE)).date()

    async def refresh_cache_for_user(self, user_id: int) -> None:
        try:
            today = self.today_dublin()
            await self.get_day_schedule(user_id, today)
            logger.info("Cache refreshed for user %d", user_id)
        except Exception as exc:
            logger.warning("Cache refresh failed for user %d: %s", user_id, exc)


class AuthenticationRequiredError(Exception):
    pass
