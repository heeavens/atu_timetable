import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot.handlers.auth_handler import AuthHandler
from bot.handlers.error_handler import error_handler
from bot.handlers.schedule_handler import ScheduleHandler
from config.settings import LOG_LEVEL, SCHEDULE_CACHE_TTL_HOURS, TELEGRAM_BOT_TOKEN
from services.auth_service import AuthService
from services.schedule_service import ScheduleService
from services.scraper_service import ScraperService
from storage.database import Database
from storage.schedule_repository import ScheduleRepository
from storage.session_repository import SessionRepository

logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    database = Database()
    await database.connect()

    session_repo = SessionRepository(database)
    schedule_repo = ScheduleRepository(database)
    auth_service = AuthService()
    scraper_service = ScraperService()
    schedule_service = ScheduleService(
        scraper=scraper_service,
        schedule_repo=schedule_repo,
        session_repo=session_repo,
    )

    application.bot_data["database"] = database
    application.bot_data["session_repo"] = session_repo
    application.bot_data["schedule_repo"] = schedule_repo
    application.bot_data["auth_service"] = auth_service
    application.bot_data["schedule_service"] = schedule_service

    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(
            _refresh_cache_job,
            interval=SCHEDULE_CACHE_TTL_HOURS * 3600,
            first=SCHEDULE_CACHE_TTL_HOURS * 3600,
            name="cache_refresh",
        )
        logger.info(
            "APScheduler: cache refresh every %dh", SCHEDULE_CACHE_TTL_HOURS
        )

    logger.info("Application initialized: DB, services, scheduler ready")


async def _refresh_cache_job(context) -> None:
    schedule_service: ScheduleService = context.bot_data["schedule_service"]
    session_repo: SessionRepository = context.bot_data["session_repo"]

    user_ids = await session_repo.get_all_user_ids()
    for user_id in user_ids:
        await schedule_service.refresh_cache_for_user(user_id)


async def post_shutdown(application: Application) -> None:
    auth_service: AuthService = application.bot_data.get("auth_service")
    if auth_service:
        await auth_service.close()

    database: Database = application.bot_data.get("database")
    if database:
        await database.close()

    logger.info("Application shutdown complete")


def create_application() -> Application:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=getattr(logging, LOG_LEVEL),
    )

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    auth_conv_handler = AuthHandler.get_conversation_handler()
    schedule_handler = ScheduleHandler()

    application.add_handler(auth_conv_handler)
    application.add_handler(CommandHandler("logout", AuthHandler().logout))

    application.add_handler(
        MessageHandler(
            filters.Regex("^🕐 Now$"), schedule_handler.now
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex("^⏭ Next$"), schedule_handler.next_lesson
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex("^📅 Day$"), schedule_handler.day
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex("^🚪 Sign Out$"),
            AuthHandler().logout,
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            schedule_handler.day_selected, pattern="^day_"
        )
    )

    application.add_error_handler(error_handler)

    return application
