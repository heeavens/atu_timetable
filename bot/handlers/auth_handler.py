import logging
import re
from datetime import datetime

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.keyboards.main_keyboard import MainKeyboard
from models.user_session import UserSession
from services.auth_service import AuthService, LoginError
from storage.schedule_repository import ScheduleRepository
from storage.session_repository import SessionRepository

logger = logging.getLogger(__name__)

EMAIL, PASSWORD, OTP_CODE = range(3)
EMAIL_PATTERN = re.compile(r"^[\w.+-]+@atu\.ie$", re.IGNORECASE)


class AuthHandler:
    async def start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        user_id = update.effective_user.id
        session_repo: SessionRepository = context.bot_data[
            "session_repo"
        ]
        auth_service: AuthService = context.bot_data["auth_service"]

        existing_session = await session_repo.get_session(user_id)

        if existing_session:
            is_valid = await auth_service.restore_session(
                existing_session.session_state
            )
            if is_valid:
                await update.message.reply_text(
                    "👋 Welcome back! Your session is active.\n\n"
                    "Use the buttons below to check your schedule.",
                    reply_markup=MainKeyboard.MAIN_MENU,
                )
                return ConversationHandler.END

            await session_repo.delete_session(user_id)
            await update.message.reply_text(
                "⚠️ Your previous session has expired. "
                "Let's log in again."
            )

        await update.message.reply_text(
            "👋 Welcome to ATU Timetable Bot!\n\n"
            "To get started, please enter your university email "
            "(e.g. student@atu.ie):"
        )
        return EMAIL

    async def receive_email(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        email = update.message.text.strip()

        if not EMAIL_PATTERN.match(email):
            await update.message.reply_text(
                "❌ Invalid email. "
                "Please enter a valid @atu.ie address:"
            )
            return EMAIL

        context.user_data["email"] = email
        await update.message.reply_text(
            f"📧 Email: {email}\n\n"
            "🔒 Now enter your password.\n"
            "_(Your message will be deleted immediately "
            "for security)_",
            parse_mode="Markdown",
        )
        return PASSWORD

    async def receive_password(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        password = update.message.text.strip()

        try:
            await update.message.delete()
        except Exception:
            logger.warning("Could not delete password message")

        email = context.user_data["email"]
        auth_service: AuthService = context.bot_data["auth_service"]

        status_message = await update.effective_chat.send_message(
            "🔄 Logging in... This may take a moment."
        )

        try:
            session_state = await auth_service.login(
                email, password
            )
        except LoginError as exc:
            logger.warning("Login rejected: %s", exc)
            await status_message.edit_text(
                f"❌ Login failed: {exc}\n\n"
                "Send your email to retry, or /cancel to abort."
            )
            return EMAIL
        except Exception as exc:
            logger.error("Login error: %s", exc)
            await status_message.edit_text(
                "❌ Something went wrong during login. "
                "Please try again.\n\n"
                "Send your email to retry, or /cancel to abort."
            )
            return EMAIL

        if auth_service.needs_2fa:
            if auth_service.two_fa_type == "number_matching":
                return await self._handle_number_matching(
                    update, context, auth_service, status_message
                )
            return await self._handle_otp_prompt(
                status_message
            )

        await self._finalize_login(
            update, context, session_state, status_message
        )
        return ConversationHandler.END

    async def _handle_number_matching(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        auth_service: AuthService,
        status_message,
    ) -> int:
        display_number = auth_service.display_number or "??"

        await status_message.edit_text(
            "🔐 *Two-Factor Authentication*\n\n"
            "Open *Microsoft Authenticator* on your phone.\n"
            f"Enter this number: *{display_number}*\n"
            "Then tap *Approve*.\n\n"
            "⏳ Waiting for your approval (2 min)...",
            parse_mode="Markdown",
        )

        try:
            session_state = await auth_service.wait_for_approval()
        except LoginError as exc:
            logger.warning("2FA approval failed: %s", exc)
            await status_message.edit_text(
                f"❌ 2FA failed: {exc}\n\n"
                "Send /start to try again."
            )
            return ConversationHandler.END
        except Exception as exc:
            logger.error("2FA approval error: %s", exc)
            await status_message.edit_text(
                "❌ Something went wrong during 2FA. "
                "Send /start to try again."
            )
            return ConversationHandler.END

        await self._finalize_login(
            update, context, session_state, status_message
        )
        return ConversationHandler.END

    async def _handle_otp_prompt(self, status_message) -> int:
        await status_message.edit_text(
            "🔐 *Two-Factor Authentication*\n\n"
            "Please enter your 6-digit verification code:\n"
            "⏳ You have 2 minutes.",
            parse_mode="Markdown",
        )
        return OTP_CODE

    async def receive_otp(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        code = update.message.text.strip()

        if not re.match(r"^\d{6}$", code):
            await update.message.reply_text(
                "❌ Please enter a valid 6-digit code:"
            )
            return OTP_CODE

        auth_service: AuthService = context.bot_data["auth_service"]

        status_message = await update.effective_chat.send_message(
            "🔄 Verifying code..."
        )

        try:
            session_state = await auth_service.verify_otp(code)
        except LoginError as exc:
            logger.warning("OTP verification failed: %s", exc)
            await status_message.edit_text(
                f"❌ Verification failed: {exc}\n\n"
                "Please try the code again, or /cancel to abort."
            )
            return OTP_CODE
        except Exception as exc:
            logger.error("OTP error: %s", exc)
            await status_message.edit_text(
                "❌ Something went wrong. "
                "Please try again, or /cancel to abort."
            )
            return OTP_CODE

        await self._finalize_login(
            update, context, session_state, status_message
        )
        return ConversationHandler.END

    async def _finalize_login(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        session_state: bytes,
        status_message,
    ) -> None:
        user_id = update.effective_user.id
        email = context.user_data["email"]
        session_repo: SessionRepository = context.bot_data[
            "session_repo"
        ]

        now = datetime.now()
        user_session = UserSession(
            user_id=user_id,
            email=email,
            session_state=session_state,
            created_at=now,
            updated_at=now,
        )
        await session_repo.save_session(user_session)

        await status_message.edit_text(
            "✅ Successfully logged in!\n\n"
            "Use the buttons below to check your schedule."
        )
        await update.effective_chat.send_message(
            "Choose an option:",
            reply_markup=MainKeyboard.MAIN_MENU,
        )
        context.user_data.clear()

    async def cancel(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        context.user_data.clear()
        await update.message.reply_text(
            "❌ Login cancelled. Send /start to try again."
        )
        return ConversationHandler.END

    async def logout(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user_id = update.effective_user.id
        session_repo: SessionRepository = context.bot_data[
            "session_repo"
        ]
        schedule_repo: ScheduleRepository = context.bot_data[
            "schedule_repo"
        ]

        existing = await session_repo.get_session(user_id)
        if existing:
            await session_repo.delete_session(user_id)
            await schedule_repo.delete_user_cache(user_id)
            context.user_data.clear()

            await update.message.reply_text(
                "🔓 You have been signed out.\n"
                "All your session and schedule data "
                "has been deleted.\n\n"
                "Send /start or press any button to log in again.",
                reply_markup=MainKeyboard.MAIN_MENU,
            )
        else:
            await update.message.reply_text(
                "ℹ️ You are not currently logged in.\n"
                "Send /start to log in.",
                reply_markup=MainKeyboard.MAIN_MENU,
            )

    @staticmethod
    def get_conversation_handler() -> ConversationHandler:
        handler = AuthHandler()
        return ConversationHandler(
            entry_points=[
                CommandHandler("start", handler.start)
            ],
            states={
                EMAIL: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        handler.receive_email,
                    )
                ],
                PASSWORD: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        handler.receive_password,
                    )
                ],
                OTP_CODE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        handler.receive_otp,
                    )
                ],
            },
            fallbacks=[
                CommandHandler("cancel", handler.cancel)
            ],
            conversation_timeout=300,
        )
