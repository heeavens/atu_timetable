from datetime import timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup


class MainKeyboard:
    MAIN_MENU = ReplyKeyboardMarkup(
        [
            ["🕐 Now", "⏭ Next", "📅 Day"],
            ["🚪 Sign Out"],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )

    @staticmethod
    def day_selection_keyboard() -> InlineKeyboardMarkup:
        buttons = []
        from datetime import date as date_cls

        start = date_cls(2026, 4, 13)
        for i in range(7):
            day = start + timedelta(days=i)
            label = day.strftime("%A, %d %b")
            if day.weekday() >= 5:
                label += " 🔸"
            buttons.append(
                [InlineKeyboardButton(
                    label,
                    callback_data=f"day_{day.isoformat()}",
                )]
            )
        return InlineKeyboardMarkup(buttons)
