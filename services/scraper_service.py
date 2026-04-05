import json
import logging
import re
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from playwright.async_api import async_playwright

from config.settings import TIMETABLE_URL
from models.lesson import Lesson
from services.maps_service import MapsService

logger = logging.getLogger(__name__)

SCHEDULE_API_PATH = "/Grid/ReadStudentSetSchedule"
ONLINE_TYPES = {
    "online lecture",
    "online learning",
    "online recorded",
    "online practical",
    "online tutorial",
}


class SessionExpiredError(Exception):
    pass


class ScraperService:
    def __init__(self) -> None:
        self._maps_service = MapsService()

    async def scrape_schedule(
        self, session_state: bytes, target_date: date
    ) -> list[Lesson]:
        storage_state = json.loads(
            session_state.decode("utf-8")
        )

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=True
        )
        context = await browser.new_context(
            storage_state=storage_state
        )
        page = await context.new_page()

        try:
            await page.goto(
                TIMETABLE_URL,
                wait_until="networkidle",
                timeout=30_000,
            )

            is_login = await page.query_selector(
                'input[type="email"], input[name="loginfmt"]'
            )
            if is_login:
                logger.warning("Session expired during scrape")
                raise SessionExpiredError(
                    "Session expired, re-authentication required"
                )

            student_set_id = self._extract_student_set_id(
                page.url
            )
            if not student_set_id:
                student_set_id = await self._find_student_set_id(
                    page
                )
            if not student_set_id:
                logger.error(
                    "Could not find studentSetID from URL: %s",
                    page.url,
                )
                return []

            logger.info(
                "Using studentSetID: %s", student_set_id
            )

            week_start = target_date - timedelta(
                days=target_date.weekday()
            )
            week_end = week_start + timedelta(days=5)

            api_url = (
                f"{TIMETABLE_URL.rstrip('/')}"
                f"{SCHEDULE_API_PATH}"
                f"?studentSetID={student_set_id}"
                f"&start={week_start.isoformat()}"
                f"&end={week_end.isoformat()}"
            )

            logger.info("Fetching schedule API: %s", api_url)

            response = await page.evaluate(
                """async (url) => {
                    const resp = await fetch(url, {
                        credentials: 'same-origin'
                    });
                    if (!resp.ok) {
                        return {error: resp.status + ' ' + resp.statusText};
                    }
                    return await resp.json();
                }""",
                api_url,
            )

            if isinstance(response, dict) and "error" in response:
                logger.error(
                    "API error: %s", response["error"]
                )
                return []

            lessons = await self._parse_api_response(
                response, target_date
            )
            logger.info(
                "Scraped %d lessons for %s",
                len(lessons),
                target_date.isoformat(),
            )
            return lessons

        finally:
            try:
                await page.close()
            except Exception:
                pass
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass
            try:
                await playwright.stop()
            except Exception:
                pass

    def _extract_student_set_id(self, url: str) -> str | None:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        ids = params.get("studentSetID", [])
        return ids[0] if ids else None

    async def _find_student_set_id(self, page) -> str | None:
        html = await page.content()
        match = re.search(
            r'studentSetID["\s:=]+([a-f0-9-]{36})',
            html,
            re.IGNORECASE,
        )
        if match:
            return match.group(1)
        return None

    async def _parse_api_response(
        self, events: list, target_date: date
    ) -> list[Lesson]:
        lessons: list[Lesson] = []

        for event in events:
            try:
                lesson = await self._parse_event(event, target_date)
                if lesson:
                    lessons.append(lesson)
            except Exception as exc:
                logger.debug(
                    "Failed to parse event: %s — %s",
                    event,
                    exc,
                )

        lessons.sort(key=lambda lesson: lesson.start_time)
        return lessons

    async def _parse_event(
        self, event: dict, target_date: date
    ) -> Lesson | None:
        start_str = event.get("start", "")
        end_str = event.get("end", "")

        if not start_str:
            return None

        start_dt = self._parse_datetime(start_str)
        end_dt = self._parse_datetime(end_str) if end_str else None

        if start_dt is None:
            return None

        if start_dt.date() != target_date:
            return None

        title = event.get("title", "")

        extended = event.get("extendedProps", {})
        activity_type = extended.get(
            "activityType", ""
        ).lower()
        rooms_raw = extended.get("rooms", "")
        lecturers_raw = extended.get("lecturers", "")

        if not title and not extended:
            title = event.get("description", "")

        room = rooms_raw.strip() if rooms_raw else "TBA"
        lecturer = (
            lecturers_raw.strip() if lecturers_raw else None
        )

        lesson_type = self._classify_type(activity_type, title)

        building = self._extract_building(room)
        maps_url = (
            await self._maps_service.get_maps_url(room)
            if room and room != "TBA"
            else ""
        )

        return Lesson(
            subject=title.strip() or "Unknown",
            start_time=start_dt.time(),
            end_time=end_dt.time() if end_dt else start_dt.time(),
            room=room,
            building=building,
            lecturer=lecturer,
            lesson_type=lesson_type,
            maps_url=maps_url,
        )

    def _parse_datetime(self, dt_str: str) -> datetime | None:
        formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(dt_str[:len(fmt) + 5], fmt)
            except (ValueError, IndexError):
                continue
        try:
            return datetime.fromisoformat(dt_str)
        except (ValueError, TypeError):
            return None

    def _classify_type(
        self, activity_type: str, title: str
    ) -> str:
        combined = f"{activity_type} {title}".lower()

        if any(t in combined for t in ONLINE_TYPES):
            return "online"
        if "practical" in combined or "lab" in combined:
            return "practical"
        if "tutorial" in combined or "tut" in combined:
            return "tutorial"
        if "lecture" in combined:
            return "lecture"
        if activity_type:
            return activity_type
        return "lecture"

    def _extract_building(self, room: str | None) -> str | None:
        if not room or room == "TBA":
            return None
        building_map = {
            "B1": "Building 1",
            "B2": "Building 2",
            "B3": "Building 3",
        }
        for prefix, name in building_map.items():
            if room.upper().startswith(prefix):
                return name
        return None
