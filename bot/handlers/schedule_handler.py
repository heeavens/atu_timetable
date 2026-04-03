import logging
from datetime import date

from telegram import Update
from telegram.ext import ContextTypes

from bot.keyboards.main_keyboard import MainKeyboard
from config.mappings import LESSON_TYPE_EMOJI
from models.lesson import Lesson
from services.schedule_service import (
    AuthenticationRequiredError,
    ScheduleService,
)
from storage.session_repository import SessionRepository

logger = logging.getLogger(__name__)


class ScheduleHandler:
    async def _check_session(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        user_id = update.effective_user.id
        session_repo: SessionRepository = context.bot_data[
            "session_repo"
        ]
        session = await session_repo.get_session(user_id)
        if session is None:
            await update.message.reply_text(
                "🔒 You are not logged in.\n"
                "Please send /start to log in first.",
                reply_markup=MainKeyboard.MAIN_MENU,
            )
            return False
        return True

    async def now(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await self._check_session(update, context):
            return
        user_id = update.effective_user.id
        schedule_service: ScheduleService = (
            context.bot_data["schedule_service"]
        )

        try:
            now = schedule_service.now_dublin()
            today = now.date()
            schedule = await schedule_service.get_day_schedule(user_id, today)

            current = schedule_service.get_current_lesson(schedule, now)
            if current:
                card = self._format_lesson_card(current)
                await update.message.reply_text(card, parse_mode="Markdown")
                return

            next_lesson = schedule_service.get_next_lesson(schedule, now)
            if next_lesson:
                await update.message.reply_text(
                    f"*No class right now.*\n\n"
                    f"Next class: *{next_lesson.subject}* "
                    f"at {next_lesson.start_time.strftime('%H:%M')}",
                    parse_mode="Markdown",
                )
                return

            await update.message.reply_text(
                "*No more classes today. See you tomorrow!* 👋",
                parse_mode="Markdown",
            )
        except AuthenticationRequiredError as exc:
            await update.message.reply_text(f"🔒 {exc}\nPlease use /start to log in.")
        except Exception as exc:
            logger.error("Error in 'now' handler: %s", exc)
            await update.message.reply_text(
                "⚠️ Could not retrieve your schedule. Please try again later."
            )

    async def next_lesson(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await self._check_session(update, context):
            return
        user_id = update.effective_user.id
        schedule_service: ScheduleService = (
            context.bot_data["schedule_service"]
        )

        try:
            now = schedule_service.now_dublin()
            today = now.date()
            next_hour = (now.hour + 1) % 24
            schedule = await schedule_service.get_day_schedule(
                user_id, today
            )

            upcoming = schedule_service.get_next_lesson(
                schedule, now
            )
            if upcoming:
                card = self._format_lesson_card(upcoming)
                await update.message.reply_text(
                    f"⏭ *Next class (at "
                    f"{upcoming.start_time.strftime('%H:%M')}"
                    f"):*\n\n{card}",
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
                return

            await update.message.reply_text(
                f"*No more classes today "
                f"(after {next_hour:02d}:00).* 📭\n"
                f"Have a nice evening! 👋",
                parse_mode="Markdown",
            )
        except AuthenticationRequiredError as exc:
            await update.message.reply_text(
                f"🔒 {exc}\nPlease use /start to log in."
            )
        except Exception as exc:
            logger.error("Error in 'next' handler: %s", exc)
            await update.message.reply_text(
                "⚠️ Could not retrieve your schedule. "
                "Please try again later."
            )

    async def day(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await self._check_session(update, context):
            return
        await update.message.reply_text(
            "📅 Choose a day:",
            reply_markup=MainKeyboard.day_selection_keyboard(),
        )

    async def day_selected(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        selected_date_str = query.data.replace("day_", "")
        selected_date = date.fromisoformat(selected_date_str)
        schedule_service: ScheduleService = context.bot_data["schedule_service"]

        try:
            schedule = await schedule_service.get_day_schedule(
                user_id, selected_date
            )
            day_label = selected_date.strftime("%A, %d %B")

            if not schedule.lessons:
                await query.edit_message_text(
                    f"*No classes on {day_label}.* 📭",
                    parse_mode="Markdown",
                )
                return

            text = f"📅 *Schedule for {day_label}:*\n\n"
            for idx, lesson in enumerate(schedule.lessons, start=1):
                emoji = LESSON_TYPE_EMOJI.get(lesson.lesson_type, "📖")
                text += (
                    f"*{idx}.* {emoji} *{lesson.subject}*\n"
                    f"    🕐 {lesson.start_time.strftime('%H:%M')} – "
                    f"{lesson.end_time.strftime('%H:%M')}\n"
                    f"    🏛 Room: {lesson.room}\n"
                )
                if lesson.maps_url:
                    text += f"    🔗 [Open on Map]({lesson.maps_url})\n"
                text += "\n"

            await query.edit_message_text(
                text,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
        except AuthenticationRequiredError as exc:
            await query.edit_message_text(f"🔒 {exc}\nPlease use /start to log in.")
        except Exception as exc:
            logger.error("Error in 'day_selected' handler: %s", exc)
            await query.edit_message_text(
                "⚠️ Could not retrieve schedule. Please try again later."
            )

    def _format_lesson_card(
        self, lesson: Lesson, show_date: date | None = None
    ) -> str:
        emoji = LESSON_TYPE_EMOJI.get(lesson.lesson_type, "📖")
        card = (
            f"{emoji} *{lesson.subject}*\n"
            f"🕐 {lesson.start_time.strftime('%H:%M')} – "
            f"{lesson.end_time.strftime('%H:%M')}\n"
            f"🏛 Room: {lesson.room}\n"
        )
        if lesson.building:
            card += f"🏢 Building: {lesson.building}\n"
        if lesson.lecturer:
            card += f"👤 Lecturer: {lesson.lecturer}\n"
        if show_date:
            card += f"📆 Date: {show_date.strftime('%A, %d %B')}\n"
        if lesson.maps_url:
            card += f"🔗 [Open on Maze Map]({lesson.maps_url})"
        return card
