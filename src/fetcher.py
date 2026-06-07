"""
fetcher.py - Instagram Data Fetcher
=====================================
Fetches account info, followers, posts, and engagement data.
Uses Instagrapi as primary method with Selenium as fallback.
"""

import time
import random
from dataclasses import dataclass, field
from typing import Optional, Generator
from datetime import datetime

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from tqdm import tqdm

try:
    from instagrapi import Client
    from instagrapi.types import User, Media, UserShort
    from instagrapi.exceptions import UserNotFound, PrivateError, RateLimitError
except ImportError:
    logger.error("instagrapi not installed")

from src.auth import InstagramAuth, MultiAccountManager


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class AccountInfo:
    username: str
    full_name: str
    bio: str
    follower_count: int
    following_count: int
    post_count: int
    is_verified: bool
    is_private: bool
    profile_pic_url: str
    external_url: str
    account_type: str  # "personal", "business", "creator"
    category: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    # Computed fields
    follower_following_ratio: float = field(init=False)
    engagement_rate: Optional[float] = None
    estimated_account_age_years: Optional[float] = None
    total_likes: int = 0
    total_comments: int = 0
    total_views: int = 0
    avg_likes_per_post: float = 0.0
    avg_comments_per_post: float = 0.0

    def __post_init__(self):
        self.follower_following_ratio = (
            self.follower_count / max(self.following_count, 1)
        )


@dataclass
class PostInfo:
    pk: str
    shortcode: str
    media_type: int  # 1=Photo, 2=Video, 8=Album
    caption: str
    like_count: int
    comment_count: int
    view_count: int  # For videos/reels
    play_count: int  # For reels
    taken_at: datetime
    thumbnail_url: str
    permalink: str
    is_reel: bool
    location: Optional[str]

    @property
    def engagement(self) -> int:
        return self.like_count + self.comment_count

    @property
    def media_type_label(self) -> str:
        return {1: "Photo", 2: "Video", 8: "Album"}.get(self.media_type, "Unknown")


@dataclass
class FollowerInfo:
    username: str
    full_name: str
    pk: str
    is_verified: bool
    is_private: bool
    profile_pic_url: str
    bio: Optional[str] = None
    follower_count: Optional[int] = None
    following_count: Optional[int] = None
    post_count: Optional[int] = None
    # Bot detection fields (populated by analyzer)
    bot_score: Optional[float] = None
    bot_label: Optional[str] = None  # "real", "suspicious", "bot"


# ---------------------------------------------------------------------------
# Main Fetcher
# ---------------------------------------------------------------------------

class AccountFetcher:
    """
    Fetches Instagram account data using Instagrapi.
    Handles rate limiting, retries, and Selenium fallback.

    Example:
        auth = InstagramAuth()
        client = auth.login()
        fetcher = AccountFetcher(client)

        account = fetcher.get_account_info("nasa")
        posts = fetcher.get_recent_posts("nasa", limit=12)
        followers = fetcher.get_followers("nasa", limit=500)
    """

    def __init__(
        self,
        client: Optional["Client"] = None,
        account_manager: Optional[MultiAccountManager] = None,
        request_delay: tuple[float, float] = (1.5, 4.0),
    ):
        if client:
            self._client = client
            self._manager = None
        elif account_manager:
            self._manager = account_manager
            self._client = account_manager.get_client()
        else:
            # Auto-init from env
            auth = InstagramAuth()
            self._client = auth.login()
            self._manager = None

        self.request_delay = request_delay
        self._request_count = 0

    def _delay(self):
        """Apply randomized delay between requests."""
        self._request_count += 1
        # Every 50 requests, take a longer break
        if self._request_count % 50 == 0:
            pause = random.uniform(30, 60)
            logger.info(f"Rate-limit break: sleeping {pause:.0f}s (request #{self._request_count})")
            time.sleep(pause)
        else:
            time.sleep(random.uniform(*self.request_delay))

    def _rotate_client(self):
        """Switch to next account if using multi-account manager."""
        if self._manager:
            self._client = self._manager.get_client()
            logger.info("Rotated to next Instagram account")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def get_account_info(self, username: str) -> AccountInfo:
        """
        Fetch comprehensive account information.

        Args:
            username: Instagram username (with or without @)

        Returns:
            AccountInfo dataclass with all available account data
        """
        username = username.lstrip("@").lower().strip()
        logger.info(f"Fetching account info for @{username}")
        self._delay()

        try:
            user: User = self._client.user_info_by_username(username)
        except Exception as e:
            logger.error(f"Failed to fetch @{username}: {e}")
            raise

        account = AccountInfo(
            username=user.username,
            full_name=user.full_name or "",
            bio=user.biography or "",
            follower_count=user.follower_count,
            following_count=user.following_count,
            post_count=user.media_count,
            is_verified=user.is_verified,
            is_private=user.is_private,
            profile_pic_url=str(user.profile_pic_url) if user.profile_pic_url else "",
            external_url=str(user.external_url) if user.external_url else "",
            account_type=user.account_type or "personal",
            category=getattr(user, "category", None),
            email=getattr(user, "public_email", None),
            phone=getattr(user, "public_phone_number", None),
        )

        logger.info(
            f"✅ @{username}: {account.follower_count:,} followers, "
            f"{account.following_count:,} following, {account.post_count:,} posts"
        )
        return account

    def get_recent_posts(self, username: str, limit: int = 12) -> list[PostInfo]:
        """
        Fetch recent posts with engagement data.

        Args:
            username: Instagram username
            limit: Number of posts to fetch (max ~50 recommended)

        Returns:
            List of PostInfo objects sorted by date (newest first)
        """
        username = username.lstrip("@").lower()
        logger.info(f"Fetching {limit} recent posts for @{username}")
        self._delay()

        try:
            user_id = self._client.user_id_from_username(username)
            self._delay()
            raw_posts = self._client.user_medias(user_id, amount=limit)
        except Exception as e:
            logger.error(f"Failed to fetch posts for @{username}: {e}")
            return []

        posts = []
        for p in raw_posts:
            try:
                post = PostInfo(
                    pk=str(p.pk),
                    shortcode=p.code,
                    media_type=p.media_type,
                    caption=p.caption_text or "",
                    like_count=p.like_count or 0,
                    comment_count=p.comment_count or 0,
                    view_count=getattr(p, "view_count", 0) or 0,
                    play_count=getattr(p, "play_count", 0) or 0,
                    taken_at=p.taken_at,
                    thumbnail_url=str(p.thumbnail_url) if p.thumbnail_url else "",
                    permalink=f"https://www.instagram.com/p/{p.code}/",
                    is_reel=p.media_type == 2 and getattr(p, "product_type", "") == "clips",
                    location=str(p.location) if p.location else None,
                )
                posts.append(post)
            except Exception as e:
                logger.warning(f"Error parsing post {p.pk}: {e}")
                continue

        logger.info(f"✅ Fetched {len(posts)} posts for @{username}")
        return sorted(posts, key=lambda x: x.taken_at, reverse=True)

    def enrich_account_with_posts(
        self, account: AccountInfo, posts: list[PostInfo]
    ) -> AccountInfo:
        """
        Compute engagement metrics from posts and add to account.

        Args:
            account: AccountInfo to enrich
            posts: List of recent PostInfo objects

        Returns:
            Enriched AccountInfo
        """
        if not posts:
            return account

        account.total_likes = sum(p.like_count for p in posts)
        account.total_comments = sum(p.comment_count for p in posts)
        account.total_views = sum(p.view_count + p.play_count for p in posts)
        account.avg_likes_per_post = account.total_likes / len(posts)
        account.avg_comments_per_post = account.total_comments / len(posts)

        # Engagement rate = (avg likes + avg comments) / followers * 100
        if account.follower_count > 0:
            account.engagement_rate = (
                (account.avg_likes_per_post + account.avg_comments_per_post)
                / account.follower_count
                * 100
            )

        return account

    def get_followers(
        self,
        username: str,
        limit: int = 500,
        fetch_details: bool = False,
        progress: bool = True,
    ) -> list[FollowerInfo]:
        """
        Fetch follower list.

        Args:
            username: Target Instagram username
            limit: Max followers to fetch
            fetch_details: If True, fetch full profile for each (very slow!)
            progress: Show progress bar

        Returns:
            List of FollowerInfo objects

        Warning:
            Fetching details for many followers will trigger rate limits.
            Use fetch_details=True only for small accounts or small samples.
        """
        username = username.lstrip("@").lower()
        logger.info(f"Fetching up to {limit} followers for @{username}")
        self._delay()

        try:
            user_id = self._client.user_id_from_username(username)
            self._delay()
            raw_followers = self._client.user_followers(user_id, amount=limit)
        except Exception as e:
            logger.error(f"Failed to fetch followers for @{username}: {e}")
            return []

        followers = []
        items = list(raw_followers.values()) if isinstance(raw_followers, dict) else raw_followers
        items = items[:limit]

        iterator = tqdm(items, desc="Processing followers", unit="user") if progress else items

        for user_short in iterator:
            try:
                follower = FollowerInfo(
                    username=user_short.username,
                    full_name=user_short.full_name or "",
                    pk=str(user_short.pk),
                    is_verified=user_short.is_verified,
                    is_private=user_short.is_private,
                    profile_pic_url=str(user_short.profile_pic_url) if user_short.profile_pic_url else "",
                )

                if fetch_details:
                    self._delay()
                    try:
                        details = self._client.user_info(user_short.pk)
                        follower.bio = details.biography or ""
                        follower.follower_count = details.follower_count
                        follower.following_count = details.following_count
                        follower.post_count = details.media_count
                    except Exception as e:
                        logger.debug(f"Could not fetch details for @{user_short.username}: {e}")

                followers.append(follower)
            except Exception as e:
                logger.warning(f"Error processing follower {user_short}: {e}")
                continue

        logger.info(f"✅ Fetched {len(followers)} followers for @{username}")
        return followers

    def get_following(self, username: str, limit: int = 500) -> list[FollowerInfo]:
        """Fetch accounts that the target user follows."""
        username = username.lstrip("@").lower()
        logger.info(f"Fetching up to {limit} following for @{username}")
        self._delay()

        try:
            user_id = self._client.user_id_from_username(username)
            self._delay()
            raw = self._client.user_following(user_id, amount=limit)
        except Exception as e:
            logger.error(f"Failed to fetch following for @{username}: {e}")
            return []

        result = []
        items = list(raw.values()) if isinstance(raw, dict) else raw
        for user_short in items[:limit]:
            result.append(FollowerInfo(
                username=user_short.username,
                full_name=user_short.full_name or "",
                pk=str(user_short.pk),
                is_verified=user_short.is_verified,
                is_private=user_short.is_private,
                profile_pic_url=str(user_short.profile_pic_url) if user_short.profile_pic_url else "",
            ))

        return result

    def get_post_comments(self, post: PostInfo, limit: int = 100) -> list[dict]:
        """Fetch comments for a post (used in bot detection)."""
        self._delay()
        try:
            comments = self._client.media_comments(post.pk, amount=limit)
            return [
                {
                    "username": c.user.username,
                    "text": c.text,
                    "created_at": c.created_at_utc,
                    "like_count": getattr(c, "like_count", 0),
                }
                for c in comments
            ]
        except Exception as e:
            logger.warning(f"Could not fetch comments for post {post.pk}: {e}")
            return []


# ---------------------------------------------------------------------------
# Selenium Fallback (for public data without login)
# ---------------------------------------------------------------------------

class SeleniumFetcher:
    """
    Fallback fetcher using Selenium for public data.
    Used when Instagrapi is unavailable or fails.
    """

    def __init__(self, headless: bool = True):
        self._driver = None
        self.headless = headless

    def _init_driver(self):
        try:
            import undetected_chromedriver as uc
            options = uc.ChromeOptions()
            if self.headless:
                options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")
            self._driver = uc.Chrome(options=options)
            logger.info("Selenium driver initialized")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Chrome driver: {e}")

    def get_public_account_info(self, username: str) -> dict:
        """Scrape basic public account info via Selenium."""
        if not self._driver:
            self._init_driver()

        url = f"https://www.instagram.com/{username}/"
        logger.info(f"Selenium fetching: {url}")
        self._driver.get(url)
        time.sleep(random.uniform(3, 5))

        # Parse meta tags (Instagram embeds data in meta)
        data = {}
        try:
            from selenium.webdriver.common.by import By
            metas = self._driver.find_elements(By.TAG_NAME, "meta")
            for meta in metas:
                name = meta.get_attribute("name") or meta.get_attribute("property")
                content = meta.get_attribute("content")
                if name and content:
                    data[name] = content
        except Exception as e:
            logger.error(f"Selenium parsing error: {e}")

        return data

    def quit(self):
        if self._driver:
            self._driver.quit()
            self._driver = None

    def __del__(self):
        self.quit()
