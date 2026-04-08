# ATU Timetable Bot

<div align="center">

**A Telegram bot for Atlantic Technological University students to instantly check their class schedule.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Telegram Bot API](https://img.shields.io/badge/Telegram_Bot_API-21.x-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://python-telegram-bot.org)
[![Playwright](https://img.shields.io/badge/Playwright-Headless-2EAD33?style=for-the-badge&logo=playwright&logoColor=white)](https://playwright.dev)
[![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)

</div>

---

## Features

| Feature | Description |
|---------|-------------|
| **Secure SSO Login** | Authenticate via Microsoft SSO with 2FA support (Authenticator number matching & OTP) |
| **Current Class** | Instantly see what class is happening right now |
| **Next Class** | Check your upcoming class at a glance |
| **Day Schedule** | View full schedule for any day of the week |
| **Maps Integration** | Direct links to room locations via MazeMap |
| **Auto-Caching** | Schedule is cached and refreshed automatically for speed |
| **Encrypted Sessions** | User sessions stored with Fernet symmetric encryption |

---

## Architecture

```
atu_bot/
├── main.py                     # Entry point
├── bot/
│   ├── application.py          # App factory, lifecycle, scheduler
│   ├── handlers/
│   │   ├── auth_handler.py     # Login conversation (email → password → 2FA)
│   │   ├── schedule_handler.py # Now / Next / Day commands
│   │   └── error_handler.py    # Global error handler
│   └── keyboards/
│       └── main_keyboard.py    # Reply & inline keyboards
├── config/
│   ├── settings.py             # Environment config via python-decouple
│   └── mappings.py             # Room coordinates, emoji maps, URLs
├── models/
│   ├── lesson.py               # Lesson dataclass
│   ├── schedule.py             # DaySchedule dataclass
│   └── user_session.py         # UserSession dataclass
├── services/
│   ├── auth_service.py         # Playwright-based Microsoft SSO automation
│   ├── scraper_service.py      # Schedule scraping from timetables.atu.ie
│   ├── schedule_service.py     # Business logic for schedule queries
│   └── maps_service.py         # Room → map URL resolver
└── storage/
    ├── database.py             # SQLite connection & table setup
    ├── session_repository.py   # Encrypted session CRUD
    └── schedule_repository.py  # Schedule cache CRUD
```

---

##  Getting Started

### Requirements

- **Python 3.11+**
- A **Telegram Bot Token** from [@BotFather](https://t.me/BotFather)
- A **Fernet encryption key** (generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/atu-bot.git
cd atu-bot

# 2. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # macOS / Linux
# venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browsers
playwright install chromium

# 5. Configure environment
cp .env.example .env
# Edit .env with your actual values
```

### Configuration

Copy `.env.example` to `.env` and fill in your values:

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | *required* |
| `SESSION_ENCRYPTION_KEY` | Fernet key for encrypting sessions | *required* |
| `DATABASE_URL` | SQLite database path | `sqlite+aiosqlite:///./atu_bot.db` |
| `TIMETABLE_URL` | ATU timetable base URL | `https://timetables.atu.ie` |
| `SCHEDULE_CACHE_TTL_HOURS` | Cache lifetime in hours | `6` |
| `TIMEZONE` | Timezone for schedule display | `Europe/Dublin` |
| `LOG_LEVEL` | Logging level | `INFO` |

### Running

```bash
python main.py
```

---

## Bot Commands

| Command / Button | Description |
|-----------------|-------------|
| `/start` | Begin login or resume session |
|  **Now** | Show current class |
|  **Next** | Show next upcoming class |
|  **Day** | Pick a day to view schedule |
| **Sign Out** | Log out via button |

---

## Security

- **Passwords are never stored** — only browser session cookies are saved
- Session state is **encrypted with Fernet** (AES-128-CBC) before database storage
- Password messages are **auto-deleted** from chat for privacy
- `.env` secrets are excluded from version control via `.gitignore`

---

## Tech Stack

- **[python-telegram-bot](https://python-telegram-bot.org/)** — Async Telegram Bot framework
- **[Playwright](https://playwright.dev/python/)** — Headless browser for SSO authentication & scraping
- **[aiosqlite](https://github.com/omnilib/aiosqlite)** — Async SQLite driver
- **[cryptography](https://cryptography.io/)** — Fernet encryption for session storage
- **[APScheduler](https://apscheduler.readthedocs.io/)** — Periodic cache refresh jobs
- **[BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/)** — HTML parsing
- **[python-decouple](https://github.com/HBNetwork/python-decouple)** — Environment variable management

---

## License

This project is for educational purposes at Atlantic Technological University.
