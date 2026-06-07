"""
tests/test_analyzer.py - Unit tests for bot detection engine
"""

import pytest
from src.fetcher import FollowerInfo, AccountInfo
from src.analyzer import (
    RuleEngine,
    BotDetector,
    CommentAnalyzer,
    BotSignals,
    compute_engagement_rate,
    classify_engagement_rate,
    BOT_THRESHOLD,
    SUSPICIOUS_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_follower(**kwargs) -> FollowerInfo:
    defaults = dict(
        username="testuser",
        full_name="Test User",
        pk="123456",
        is_verified=False,
        is_private=False,
        profile_pic_url="https://example.com/pic.jpg",
        bio="I love photography",
        follower_count=500,
        following_count=300,
        post_count=50,
    )
    defaults.update(kwargs)
    return FollowerInfo(**defaults)


def make_account(**kwargs) -> AccountInfo:
    defaults = dict(
        username="testaccount",
        full_name="Test Account",
        bio="Test bio",
        follower_count=10000,
        following_count=500,
        post_count=200,
        is_verified=False,
        is_private=False,
        profile_pic_url="https://example.com/pic.jpg",
        external_url="",
        account_type="personal",
        category=None,
        email=None,
        phone=None,
        engagement_rate=3.5,
    )
    defaults.update(kwargs)
    return AccountInfo(**defaults)


# ---------------------------------------------------------------------------
# RuleEngine Tests
# ---------------------------------------------------------------------------

class TestRuleEngine:
    def setup_method(self):
        self.engine = RuleEngine()

    def test_normal_follower_low_score(self):
        follower = make_follower(
            follower_count=500,
            following_count=300,
            post_count=50,
            bio="Travel lover and photographer",
        )
        signals, flags = self.engine.compute_signals(follower)
        score = self.engine.compute_composite_score(signals)
        assert score < SUSPICIOUS_THRESHOLD, f"Normal follower scored too high: {score}"

    def test_empty_bio_raises_score(self):
        follower = make_follower(bio="")
        signals, flags = self.engine.compute_signals(follower)
        assert signals.bio_quality_score >= 60
        assert any("bio" in f.lower() for f in flags)

    def test_high_following_ratio_is_suspicious(self):
        follower = make_follower(follower_count=10, following_count=5000)
        signals, flags = self.engine.compute_signals(follower)
        assert signals.follower_ratio_score >= 70
        assert any("ratio" in f.lower() for f in flags)

    def test_no_posts_is_suspicious(self):
        follower = make_follower(post_count=0)
        signals, flags = self.engine.compute_signals(follower)
        assert signals.posting_pattern_score >= 70
        assert any("post" in f.lower() or "ghost" in f.lower() for f in flags)

    def test_verified_account_not_bot(self):
        follower = make_follower(
            is_verified=True,
            bio="",
            follower_count=1,
            following_count=10000,
            post_count=0,
        )
        signals, flags = self.engine.compute_signals(follower)
        score = self.engine.compute_composite_score(signals)
        # Verified accounts should not be flagged
        assert score < SUSPICIOUS_THRESHOLD
        assert len(flags) == 0

    def test_spam_bio_pattern(self):
        follower = make_follower(bio="Follow for follow! DM for promo deals!")
        signals, flags = self.engine.compute_signals(follower)
        assert signals.bio_quality_score >= 70

    def test_digits_in_username(self):
        follower = make_follower(username="user123456789")
        signals, flags = self.engine.compute_signals(follower)
        # Should flag username with many digits
        assert any("digit" in f.lower() or "username" in f.lower() for f in flags)

    def test_label_from_score(self):
        assert self.engine.label_from_score(BOT_THRESHOLD + 1) == "bot"
        assert self.engine.label_from_score(SUSPICIOUS_THRESHOLD + 1) == "suspicious"
        assert self.engine.label_from_score(SUSPICIOUS_THRESHOLD - 1) == "real"

    def test_composite_score_bounds(self):
        signals = BotSignals(
            engagement_score=100,
            follower_ratio_score=100,
            bio_quality_score=100,
            posting_pattern_score=100,
            comment_quality_score=100,
            account_age_score=100,
        )
        score = self.engine.compute_composite_score(signals)
        assert 0 <= score <= 100

        zero_signals = BotSignals()
        score = self.engine.compute_composite_score(zero_signals)
        assert score == 0.0


# ---------------------------------------------------------------------------
# CommentAnalyzer Tests
# ---------------------------------------------------------------------------

class TestCommentAnalyzer:
    def setup_method(self):
        self.analyzer = CommentAnalyzer(use_ml=False)  # Rule-based only for tests

    def test_spam_comments_detected(self):
        spam = [
            {"text": "nice"},
            {"text": "great post!!!"},
            {"text": "follow me back"},
            {"text": "check out my page"},
            {"text": "🔥🔥🔥"},
        ]
        ratio = self.analyzer.analyze_comments(spam)
        assert ratio > 0.5, f"Expected high spam ratio, got {ratio}"

    def test_genuine_comments_low_spam(self):
        genuine = [
            {"text": "This really resonated with me, especially the part about morning routines!"},
            {"text": "I tried this last week and it actually works, thanks for sharing"},
            {"text": "Great breakdown of the topic, I learned something new today"},
        ]
        ratio = self.analyzer.analyze_comments(genuine)
        assert ratio < 0.5, f"Expected low spam ratio for genuine comments, got {ratio}"

    def test_empty_comment_is_spam(self):
        is_spam, confidence = self.analyzer.is_spam_comment("")
        assert is_spam is True

    def test_empty_list_returns_zero(self):
        ratio = self.analyzer.analyze_comments([])
        assert ratio == 0.0


# ---------------------------------------------------------------------------
# BotDetector Integration Tests
# ---------------------------------------------------------------------------

class TestBotDetector:
    def setup_method(self):
        self.detector = BotDetector()

    def test_analyze_single_follower(self):
        follower = make_follower()
        result = self.detector.analyze_follower(follower)
        assert 0 <= result.bot_score <= 100
        assert result.label in ("real", "suspicious", "bot")
        assert result.username == follower.username

    def test_obvious_bot_gets_high_score(self):
        bot = make_follower(
            username="user99887766",
            bio="",
            follower_count=1,
            following_count=8000,
            post_count=0,
            full_name="",
            profile_pic_url="",
        )
        result = self.detector.analyze_follower(bot)
        assert result.bot_score >= SUSPICIOUS_THRESHOLD, f"Obvious bot scored too low: {result.bot_score}"

    def test_analyze_followers_aggregation(self):
        followers = [
            make_follower(username=f"real_user_{i}", follower_count=400, following_count=200, post_count=30)
            for i in range(5)
        ] + [
            make_follower(
                username=f"bot_user_{i}",
                bio="",
                follower_count=1,
                following_count=9000,
                post_count=0,
            )
            for i in range(5)
        ]

        account = make_account()
        result = self.detector.analyze_followers(followers, account, show_progress=False)

        assert result.total_analyzed == 10
        assert result.real_count + result.suspicious_count + result.bot_count == 10
        assert 0 <= result.real_percentage <= 100
        assert abs(result.real_percentage + result.suspicious_percentage + result.bot_percentage - 100) < 0.1

    def test_analyze_empty_followers(self):
        account = make_account()
        result = self.detector.analyze_followers([], account, show_progress=False)
        assert result.total_analyzed == 0


# ---------------------------------------------------------------------------
# Utility Function Tests
# ---------------------------------------------------------------------------

class TestUtilityFunctions:
    def test_engagement_rate_calculation(self):
        rate = compute_engagement_rate(likes=1000, comments=50, followers=10000)
        assert abs(rate - 10.5) < 0.01

    def test_engagement_rate_zero_followers(self):
        rate = compute_engagement_rate(100, 10, 0)
        assert rate == 0.0

    def test_classify_engagement_rate(self):
        assert "Excellent" in classify_engagement_rate(8.0)
        assert "Good" in classify_engagement_rate(4.0)
        assert "Average" in classify_engagement_rate(2.0)
        assert "Poor" in classify_engagement_rate(0.5)
