import json
import logging

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
)

from config.settings import TIMETABLE_URL

logger = logging.getLogger(__name__)

SSO_LOGIN_URL = "https://login.microsoftonline.com"
APPROVAL_POLL_INTERVAL_MS = 2000
APPROVAL_TIMEOUT_MS = 120_000


class LoginError(Exception):
    pass


class AuthService:
    def __init__(self) -> None:
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._needs_2fa: bool = False
        self._2fa_type: str = "none"
        self._display_number: str | None = None

    @property
    def needs_2fa(self) -> bool:
        return self._needs_2fa

    @property
    def two_fa_type(self) -> str:
        return self._2fa_type

    @property
    def display_number(self) -> str | None:
        return self._display_number

    async def _ensure_browser(self) -> None:
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True
            )
            logger.info("Playwright browser launched (headless)")

    async def login(self, email: str, password: str) -> bytes | None:
        await self._ensure_browser()
        self._needs_2fa = False
        self._2fa_type = "none"
        self._display_number = None

        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()

        await self._page.goto(
            TIMETABLE_URL, wait_until="networkidle"
        )
        logger.info(
            "Navigated to timetable URL: %s", self._page.url
        )

        await self._page.wait_for_selector(
            'input[type="email"], input[name="loginfmt"]',
            timeout=15_000,
        )
        await self._page.fill(
            'input[type="email"], input[name="loginfmt"]', email
        )
        await self._page.click(
            'input[type="submit"], button[type="submit"]'
        )
        logger.info("Email submitted, waiting for password field")

        await self._page.wait_for_selector(
            'input[type="password"], input[name="passwd"]',
            timeout=15_000,
        )
        await self._page.fill(
            'input[type="password"], input[name="passwd"]', password
        )
        await self._page.click(
            'input[type="submit"], button[type="submit"]'
        )
        logger.info("Password submitted, waiting for response")

        await self._page.wait_for_timeout(5000)

        error_detected = await self._check_login_error()
        if error_detected:
            await self._cleanup_login_context()
            raise LoginError(error_detected)

        display_number = await self._get_number_matching_code()
        if display_number:
            self._needs_2fa = True
            self._2fa_type = "number_matching"
            self._display_number = display_number
            logger.info(
                "Number Matching 2FA detected, code: %s",
                display_number,
            )
            return None

        if await self._is_otp_page():
            self._needs_2fa = True
            self._2fa_type = "otp"
            logger.info("OTP 2FA page detected, awaiting code")
            return None

        await self._handle_stay_signed_in()

        is_authenticated = await self._verify_authentication()
        if not is_authenticated:
            await self._cleanup_login_context()
            raise LoginError(
                "Authentication failed — could not reach timetable."
            )

        return await self._save_session_state()

    async def _check_login_error(self) -> str | None:
        error_selectors = [
            "#usernameError",
            "#passwordError",
            "#errorText",
            "#errorMessage",
            '[id*="error"]',
        ]
        for selector in error_selectors:
            try:
                element = await self._page.query_selector(selector)
                if element and await element.is_visible():
                    text = await element.inner_text()
                    if text.strip():
                        logger.warning(
                            "Login error detected: %s", text.strip()
                        )
                        return text.strip()
            except Exception:
                continue

        error_texts = [
            "Your account or password is incorrect",
            "That Microsoft account doesn't exist",
            "This username may be incorrect",
            "Enter a valid email address",
            "Please enter your password",
            "Wrong password",
            "Sign-in was blocked",
            "Too many failed attempts",
        ]
        for error_text in error_texts:
            try:
                locator = self._page.get_by_text(
                    error_text, exact=False
                )
                if await locator.count() > 0:
                    visible = await locator.first.is_visible()
                    if visible:
                        full = await locator.first.inner_text()
                        logger.warning(
                            "Login error text found: %s", full
                        )
                        return full.strip()
            except Exception:
                continue

        still_on_password = await self._page.query_selector(
            'input[type="password"]:visible, '
            'input[name="passwd"]:visible'
        )
        if still_on_password:
            logger.warning(
                "Still on password page — likely wrong credentials"
            )
            return (
                "Your account or password is incorrect. "
                "Please try again."
            )

        return None

    async def _get_number_matching_code(self) -> str | None:
        number_selectors = [
            "#idRichContext_DisplaySign",
            ".display-sign",
            '[id*="DisplaySign"]',
            '[id*="displaySign"]',
        ]

        for selector in number_selectors:
            try:
                element = await self._page.query_selector(selector)
                if element and await element.is_visible():
                    number = await element.inner_text()
                    number = number.strip()
                    if number and number.isdigit():
                        return number
            except Exception:
                continue

        approval_texts = [
            "Approve sign in request",
            "Enter the number shown",
            "approve the sign in",
            "Open your Authenticator app",
            "We've sent a notification",
        ]
        for text in approval_texts:
            try:
                locator = self._page.get_by_text(text, exact=False)
                if await locator.count() > 0:
                    for selector in number_selectors:
                        try:
                            el = await self._page.query_selector(
                                selector
                            )
                            if el:
                                num = await el.inner_text()
                                num = num.strip()
                                if num and num.isdigit():
                                    return num
                        except Exception:
                            continue

                    all_text = await self._page.inner_text("body")
                    import re

                    match = re.search(
                        r'(?:enter|type|match)\s*(?:the\s*)?'
                        r'(?:number\s*)?[:\s]*(\d{1,2})\b',
                        all_text,
                        re.IGNORECASE,
                    )
                    if match:
                        return match.group(1)

                    return "??"
            except Exception:
                continue

        return None

    async def _is_otp_page(self) -> bool:
        selectors = [
            'input[name="otc"]',
            "#idTxtBx_SAOTCC_OTC",
            'input[id*="Code"]',
        ]
        for selector in selectors:
            try:
                element = await self._page.query_selector(selector)
                if element and await element.is_visible():
                    return True
            except Exception:
                continue
        return False

    async def wait_for_approval(self) -> bytes:
        if self._page is None:
            raise RuntimeError("No active login session")

        logger.info("Waiting for 2FA approval in Authenticator app")

        elapsed = 0
        approved = False
        while elapsed < APPROVAL_TIMEOUT_MS:
            await self._page.wait_for_timeout(
                APPROVAL_POLL_INTERVAL_MS
            )
            elapsed += APPROVAL_POLL_INTERVAL_MS

            is_stay_signed_in = await self._is_stay_signed_in_page()
            if is_stay_signed_in:
                logger.info(
                    "2FA approved — 'Stay signed in?' page appeared"
                )
                approved = True
                break

            current_url = self._page.url or ""
            if (
                SSO_LOGIN_URL not in current_url
                and TIMETABLE_URL.rstrip("/") in current_url
            ):
                logger.info(
                    "2FA approved, redirected to: %s", current_url
                )
                approved = True
                break

            error = await self._check_2fa_denial()
            if error:
                raise LoginError(f"2FA denied: {error}")

            if elapsed % 10_000 == 0:
                logger.info(
                    "Still waiting for 2FA approval (%ds)",
                    elapsed // 1000,
                )

        if not approved:
            raise LoginError(
                "2FA approval timed out (2 minutes). "
                "Please try /start again."
            )

        await self._handle_stay_signed_in()

        await self._page.wait_for_timeout(3000)

        is_authenticated = await self._verify_authentication()
        if not is_authenticated:
            await self._cleanup_login_context()
            raise LoginError(
                "Authentication failed after 2FA approval."
            )

        return await self._save_session_state()

    async def _check_2fa_denial(self) -> str | None:
        denial_texts = [
            "denied",
            "rejected",
            "was not approved",
            "try again",
            "timed out",
        ]
        for text in denial_texts:
            try:
                locator = self._page.get_by_text(text, exact=False)
                if await locator.count() > 0:
                    visible = await locator.first.is_visible()
                    if visible:
                        full = await locator.first.inner_text()
                        return full.strip()
            except Exception:
                continue
        return None

    async def verify_otp(self, code: str) -> bytes:
        if self._page is None:
            raise RuntimeError("No active login session for OTP")

        otp_selectors = [
            'input[name="otc"]',
            "#idTxtBx_SAOTCC_OTC",
            'input[id*="Code"]',
        ]

        for selector in otp_selectors:
            try:
                element = await self._page.query_selector(selector)
                if element:
                    await element.fill(code)
                    break
            except Exception:
                continue

        submit_selectors = [
            "#idSubmit_SAOTCC_Continue",
            'input[type="submit"]',
            'button[type="submit"]',
        ]
        for selector in submit_selectors:
            try:
                element = await self._page.query_selector(selector)
                if element:
                    await element.click()
                    break
            except Exception:
                continue

        logger.info("OTP code submitted")

        await self._page.wait_for_timeout(5000)

        error_detected = await self._check_login_error()
        if error_detected:
            raise LoginError(f"OTP verification failed: {error_detected}")

        await self._handle_stay_signed_in()

        is_authenticated = await self._verify_authentication()
        if not is_authenticated:
            raise LoginError(
                "Authentication failed after OTP."
            )

        return await self._save_session_state()

    async def _is_stay_signed_in_page(self) -> bool:
        try:
            kmsi = await self._page.query_selector(
                "#KmsiBanner, #idDiv_SAOTCS_Title, "
                "#idSIButton9, #idBtn_Back"
            )
            if kmsi:
                return True
        except Exception:
            pass

        stay_texts = [
            "Stay signed in?",
            "stay signed in",
            "Remain signed in",
            "Don't show this again",
        ]
        for text in stay_texts:
            try:
                locator = self._page.get_by_text(
                    text, exact=False
                )
                if await locator.count() > 0:
                    return True
            except Exception:
                continue

        return False

    async def _handle_stay_signed_in(self) -> None:
        try:
            is_kmsi = await self._is_stay_signed_in_page()
            if not is_kmsi:
                await self._page.wait_for_timeout(2000)
                is_kmsi = await self._is_stay_signed_in_page()

            if not is_kmsi:
                logger.info(
                    "No 'Stay signed in?' page detected, skipping"
                )
                return

            logger.info("'Stay signed in?' page detected")

            yes_selectors = [
                "#idSIButton9",
                'input[type="submit"][value="Yes"]',
                'button[type="submit"]',
                'input[type="submit"]',
            ]

            for selector in yes_selectors:
                try:
                    button = await self._page.query_selector(
                        selector
                    )
                    if button and await button.is_visible():
                        await button.click()
                        logger.info(
                            "Clicked 'Yes' on Stay signed in "
                            "(selector: %s)",
                            selector,
                        )
                        await self._page.wait_for_timeout(3000)
                        return
                except Exception:
                    continue

            try:
                yes_locator = self._page.get_by_role(
                    "button", name="Yes"
                )
                if await yes_locator.count() > 0:
                    await yes_locator.first.click()
                    logger.info(
                        "Clicked 'Yes' via role selector"
                    )
                    await self._page.wait_for_timeout(3000)
                    return
            except Exception:
                pass

            logger.warning(
                "Could not find 'Yes' button, trying any submit"
            )
            try:
                submit = self._page.locator(
                    'input[type="submit"], button[type="submit"]'
                ).first
                await submit.click()
                await self._page.wait_for_timeout(3000)
                logger.info("Clicked submit button as fallback")
            except Exception as exc:
                logger.warning(
                    "Failed to click Stay signed in: %s", exc
                )
        except Exception as exc:
            logger.warning(
                "Error handling Stay signed in: %s", exc
            )

    async def _verify_authentication(self) -> bool:
        current_url = self._page.url or ""
        logger.info(
            "Verifying auth, current URL: %s", current_url
        )

        if TIMETABLE_URL.rstrip("/") in current_url:
            login_form = await self._page.query_selector(
                'input[type="email"], input[name="loginfmt"]'
            )
            if not login_form:
                logger.info(
                    "Authentication verified — on timetable"
                )
                return True

        try:
            await self._page.wait_for_url(
                f"**{TIMETABLE_URL.rstrip('/')}**",
                timeout=15_000,
            )
            logger.info(
                "Reached timetable URL: %s", self._page.url
            )
            return True
        except Exception:
            logger.warning(
                "Did not reach timetable, URL: %s",
                self._page.url,
            )

        if SSO_LOGIN_URL in (self._page.url or ""):
            return False

        return False

    async def _save_session_state(self) -> bytes:
        storage_state = await self._context.storage_state()
        state_bytes = json.dumps(storage_state).encode("utf-8")
        logger.info(
            "Session state saved (%d bytes)", len(state_bytes)
        )
        return state_bytes

    async def _cleanup_login_context(self) -> None:
        try:
            if self._page and not self._page.is_closed():
                await self._page.close()
        except Exception:
            pass
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        self._page = None
        self._context = None

    async def restore_session(self, session_state: bytes) -> bool:
        await self._ensure_browser()

        storage_state = json.loads(session_state.decode("utf-8"))
        context = await self._browser.new_context(
            storage_state=storage_state
        )
        page = await context.new_page()

        try:
            await page.goto(
                TIMETABLE_URL,
                wait_until="networkidle",
                timeout=20_000,
            )

            is_login_page = await page.query_selector(
                'input[type="email"], input[name="loginfmt"]'
            )
            if is_login_page:
                logger.info("Session expired, login page detected")
                return False

            logger.info("Session restored successfully")
            return True
        except Exception as exc:
            logger.error("Session restore failed: %s", exc)
            return False
        finally:
            try:
                await page.close()
            except Exception:
                pass
            try:
                await context.close()
            except Exception:
                pass

    async def close(self) -> None:
        try:
            if self._page and not self._page.is_closed():
                await self._page.close()
        except Exception:
            pass
        self._page = None

        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        self._context = None

        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        self._browser = None

        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._playwright = None

        logger.info("AuthService closed")
