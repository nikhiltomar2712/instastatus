"""
auth.py - Instagram Authentication & Session Management
========================================================
Handles login, session persistence, 2FA, and multi-account rotation.
Uses Instagrapi with Selenium fallback for challenged logins.
"""

import json
import os
import time
import random
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from instagrapi import Client
    from instagrapi.exceptions import (
        LoginRequired,
        ChallengeRequired,
        TwoFactorRequired,
        BadPassword,
        UserNotFound,
    )
    INSTAGRAPI_AVAILABLE = True
except ImportError:
    INSTAGRAPI_AVAILABLE = False
    logger.warning("instagrapi not installed. Install with: pip install instagrapi")

load_dotenv()


class AuthError(Exception):
    """Raised when authentication fails."""
    pass


class SessionExpiredError(AuthError):
    """Raised when the Instagram session has expired."""
    pass


class InstagramAuth:
    """
    Manages Instagram authentication with session persistence,
    multi-account support, and automatic retry logic.

    Example:
        auth = InstagramAuth()
        client = auth.login()
        # client is now ready to use
    """

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        session_file: Optional[str] = None,
        proxy: Optional[str] = None,
    ):
        self.username = username or os.getenv("INSTAGRAM_USERNAME")
        self.password = password or os.getenv("INSTAGRAM_PASSWORD")
        self.session_file = session_file or os.getenv(
            "INSTAGRAM_SESSION_FILE", ".instagram_session.json"
        )
        self.proxy = proxy or (
            os.getenv("PROXY_URL") if os.getenv("PROXY_ENABLED", "false").lower() == "true" else None
        )
        self.totp_secret = os.getenv("INSTAGRAM_TOTP_SECRET")
        self._client: Optional["Client"] = None

        if not self.username or not self.password:
            raise AuthError(
                "Instagram credentials not found. "
                "Set INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD in .env"
            )

    @property
    def client(self) -> "Client":
        """Returns the authenticated client, initializing if needed."""
        if self._client is None:
            self._client = self.login()
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        reraise=True,
    )
    def login(self) -> "Client":
        """
        Authenticate with Instagram. Tries to reuse saved session first,
        falls back to fresh login.

        Returns:
            Authenticated instagrapi Client

        Raises:
            AuthError: If login fails after all retries
        """
        if not INSTAGRAPI_AVAILABLE:
            raise AuthError("instagrapi is not installed. Run: pip install instagrapi")

        cl = Client()
        cl.delay_range = [
            float(os.getenv("RATE_LIMIT_MIN_DELAY", "1.5")),
            float(os.getenv("RATE_LIMIT_MAX_DELAY", "4.0")),
        ]

        # Configure proxy if set
        if self.proxy:
            logger.info(f"Using proxy: {self.proxy}")
            cl.set_proxy(self.proxy)

        # Try loading existing session
        session_path = Path(self.session_file)
        if session_path.exists():
            try:
                logger.info(f"Loading session from {session_path}")
                cl.load_settings(session_path)
                cl.login(self.username, self.password)
                cl.get_timeline_feed()  # Test the session is valid
                logger.info(f"✅ Session restored for @{self.username}")
                self._client = cl
                return cl
            except (LoginRequired, SessionExpiredError, Exception) as e:
                logger.warning(f"Saved session invalid ({e}), performing fresh login...")
                session_path.unlink(missing_ok=True)

        # Fresh login
        try:
            logger.info(f"Logging in as @{self.username}...")
            cl.login(
                self.username,
                self.password,
                verification_code=self._get_totp_code() if self.totp_secret else "",
            )
            # Save session for future use
            cl.dump_settings(session_path)
            logger.info(f"✅ Logged in successfully as @{self.username}")
            self._client = cl
            return cl

        except TwoFactorRequired:
            logger.info("2FA required. Provide TOTP code...")
            code = input("Enter 2FA code: ").strip()
            cl.login(self.username, self.password, verification_code=code)
            cl.dump_settings(session_path)
            self._client = cl
            return cl

        except ChallengeRequired as e:
            logger.error(f"Instagram challenge required: {e}")
            logger.info("Try logging in manually via browser first, then retry.")
            raise AuthError(f"Challenge required: {e}") from e

        except BadPassword:
            raise AuthError("Invalid Instagram password. Check your .env credentials.")

        except Exception as e:
            raise AuthError(f"Login failed: {e}") from e

    def _get_totp_code(self) -> str:
        """Generate TOTP code from secret."""
        try:
            import pyotp
            return pyotp.TOTP(self.totp_secret).now()
        except ImportError:
            logger.warning("pyotp not installed. Install with: pip install pyotp")
            return input("Enter 2FA code manually: ").strip()

    def logout(self) -> None:
        """Log out and clear session."""
        if self._client:
            try:
                self._client.logout()
                Path(self.session_file).unlink(missing_ok=True)
                logger.info("Logged out successfully")
            except Exception as e:
                logger.error(f"Logout error: {e}")
            finally:
                self._client = None

    def refresh_session(self) -> "Client":
        """Force a fresh login, clearing old session."""
        Path(self.session_file).unlink(missing_ok=True)
        self._client = None
        return self.login()

    def __enter__(self):
        return self.login()

    def __exit__(self, *args):
        self.logout()


class MultiAccountManager:
    """
    Manages a pool of Instagram accounts for rotation to avoid rate limiting.

    Example:
        manager = MultiAccountManager()
        with manager.get_client() as client:
            # use client...
    """

    def __init__(self, accounts_str: Optional[str] = None):
        """
        Args:
            accounts_str: Comma-separated "username:password" pairs,
                          or reads from INSTAGRAM_ACCOUNTS env var.
        """
        raw = accounts_str or os.getenv("INSTAGRAM_ACCOUNTS", "")
        self._accounts = []
        self._current_idx = 0

        if raw:
            for pair in raw.split(","):
                pair = pair.strip()
                if ":" in pair:
                    username, password = pair.split(":", 1)
                    self._accounts.append({"username": username, "password": password})

        # Fall back to single account from env
        if not self._accounts:
            username = os.getenv("INSTAGRAM_USERNAME")
            password = os.getenv("INSTAGRAM_PASSWORD")
            if username and password:
                self._accounts.append({"username": username, "password": password})

        if not self._accounts:
            raise AuthError("No Instagram accounts configured.")

        logger.info(f"Loaded {len(self._accounts)} Instagram account(s)")
        self._auth_instances = [
            InstagramAuth(a["username"], a["password"]) for a in self._accounts
        ]

    def get_client(self) -> "Client":
        """Get next client in rotation."""
        auth = self._auth_instances[self._current_idx]
        self._current_idx = (self._current_idx + 1) % len(self._auth_instances)
        # Add jitter between account switches
        time.sleep(random.uniform(0.5, 2.0))
        return auth.client

    @property
    def account_count(self) -> int:
        return len(self._accounts)
