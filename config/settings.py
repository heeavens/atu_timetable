from decouple import config

TELEGRAM_BOT_TOKEN: str = config("TELEGRAM_BOT_TOKEN")

SESSION_ENCRYPTION_KEY: str = config("SESSION_ENCRYPTION_KEY")

DATABASE_URL: str = config("DATABASE_URL", default="sqlite+aiosqlite:///./atu_bot.db")

TIMETABLE_URL: str = config("TIMETABLE_URL", default="https://timetables.atu.ie")

SCHEDULE_CACHE_TTL_HOURS: int = config(
    "SCHEDULE_CACHE_TTL_HOURS", default=6, cast=int
)

TIMEZONE: str = config("TIMEZONE", default="Europe/Dublin")

LOG_LEVEL: str = config("LOG_LEVEL", default="INFO")
