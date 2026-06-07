"""
analyzer.py - Bot Detection Engine
=====================================
Multi-signal bot detection combining:
  - Rule-based heuristics (engagement, ratio, bio quality)
  - Scikit-learn ML classifier
  - Hugging Face comment sentiment analysis
  - Posting pattern analysis
"""

import re
import os
import math
import pickle
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

import numpy as np
from loguru import logger

from src.fetcher import AccountInfo, PostInfo, FollowerInfo


# ---------------------------------------------------------------------------
# Result Types
# ---------------------------------------------------------------------------

@dataclass
class BotSignals:
    """Individual signal scores (0-100) used in bot detection."""
    engagement_score: float = 0.0       # Low = suspicious
    follower_ratio_score: float = 0.0   # High following/low followers = suspicious
    bio_quality_score: float = 0.0      # Generic/empty bio = suspicious
    posting_pattern_score: float = 0.0  # No posts or spammy = suspicious
    comment_quality_score: float = 0.0  # Generic spam comments = suspicious
    account_age_score: float = 0.0      # Very new with many followers = suspicious
    profile_completeness_score: float = 0.0  # No pic, no name = suspicious


@dataclass
class FollowerAnalysisResult:
    """Result of analyzing a single follower account."""
    username: str
    bot_score: float          # 0-100, higher = more likely bot
    label: str                # "real", "suspicious", "bot"
    signals: BotSignals
    flags: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class AccountAnalysisResult:
    """Full analysis results for an account's follower base."""
    username: str
    total_analyzed: int
    real_count: int
    suspicious_count: int
    bot_count: int
    real_percentage: float
    suspicious_percentage: float
    bot_percentage: float
    engagement_rate: float
    engagement_quality: str  # "excellent", "good", "average", "poor"
    follower_results: list[FollowerAnalysisResult]
    top_flags: list[str]
    overall_health_score: float  # 0-100


# ---------------------------------------------------------------------------
# Signal Weights
# ---------------------------------------------------------------------------

SIGNAL_WEIGHTS = {
    "engagement_score": 0.30,
    "follower_ratio_score": 0.20,
    "bio_quality_score": 0.15,
    "posting_pattern_score": 0.15,
    "comment_quality_score": 0.10,
    "account_age_score": 0.10,
}

BOT_THRESHOLD = float(os.getenv("BOT_SCORE_THRESHOLD", "70"))
SUSPICIOUS_THRESHOLD = float(os.getenv("SUSPICIOUS_SCORE_THRESHOLD", "40"))

# Known spam bio patterns
SPAM_BIO_PATTERNS = [
    r"follow\s*(for\s*follow|4\s*follow|back)",
    r"(follow|gain)\s*\d+k?\s*(followers?|following)",
    r"dm\s*(for\s*)?(promo|collab|business|free)",
    r"(buy|get)\s*(followers?|likes?)",
    r"link\s*in\s*bio.*shop",
    r"^\s*$",  # Empty bio
    r"^[\W_]+$",  # Only symbols
    r"(onlyfans|of\.com)",
    r"(passive\s*income|work\s*from\s*home|\$\d+\/day)",
]

GENERIC_COMMENT_PATTERNS = [
    r"^(nice|great|beautiful|cool|awesome|love\s*this?|fire|lit|🔥+|❤+|😍+|👏+)\.?$",
    r"^(check\s*out\s*my|visit\s*my|follow\s*me|follow\s*back|f4f|l4l).*",
    r"^(wow|omg|amazing|fantastic|incredible)\.?$",
    r"(giveaway|win\s*\$|free\s*iphone|claim\s*your)",
    r"(click\s*link|visit\s*site|bit\.ly|tinyurl)",
]


# ---------------------------------------------------------------------------
# Rule-Based Signals
# ---------------------------------------------------------------------------

class RuleEngine:
    """Computes heuristic bot signals from follower profile data."""

    def compute_signals(self, follower: FollowerInfo) -> tuple[BotSignals, list[str]]:
        """
        Compute all signals for a follower.

        Returns:
            (BotSignals, flags) where flags are human-readable descriptions
        """
        signals = BotSignals()
        flags = []

        # --- Follower/Following Ratio ---
        if follower.follower_count is not None and follower.following_count is not None:
            ratio = follower.following_count / max(follower.follower_count, 1)
            if ratio > 10:
                signals.follower_ratio_score = 90
                flags.append(f"Following/follower ratio: {ratio:.1f}x (extremely suspicious)")
            elif ratio > 5:
                signals.follower_ratio_score = 70
                flags.append(f"High following/follower ratio: {ratio:.1f}x")
            elif ratio > 2:
                signals.follower_ratio_score = 40
            else:
                signals.follower_ratio_score = 10
        else:
            signals.follower_ratio_score = 30  # Unknown = slightly suspicious

        # --- Bio Quality ---
        bio = (follower.bio or "").strip()
        bio_score = 0
        if not bio:
            bio_score = 70
            flags.append("Empty bio")
        else:
            for pattern in SPAM_BIO_PATTERNS:
                if re.search(pattern, bio, re.IGNORECASE):
                    bio_score = max(bio_score, 80)
                    flags.append(f"Spam bio pattern detected")
                    break
            if len(bio) < 10:
                bio_score = max(bio_score, 50)
                flags.append("Very short bio")
        signals.bio_quality_score = bio_score

        # --- Posting Pattern ---
        post_count = follower.post_count
        if post_count is not None:
            if post_count == 0:
                signals.posting_pattern_score = 80
                flags.append("No posts (ghost account)")
            elif post_count < 3:
                signals.posting_pattern_score = 50
                flags.append(f"Very few posts ({post_count})")
            elif post_count > 5000:
                signals.posting_pattern_score = 60
                flags.append(f"Abnormally high post count ({post_count:,})")
            else:
                signals.posting_pattern_score = 10
        else:
            signals.posting_pattern_score = 25  # Unknown

        # --- Profile Completeness ---
        completeness_score = 0
        if not follower.profile_pic_url or "default" in follower.profile_pic_url:
            completeness_score += 40
            flags.append("Default/no profile picture")
        if not follower.full_name:
            completeness_score += 20
            flags.append("No display name")
        if not bio:
            completeness_score += 20  # Already counted above but contributes
        signals.profile_completeness_score = min(completeness_score, 100)

        # --- Username Pattern ---
        username = follower.username
        if re.search(r"\d{4,}", username):
            signals.bio_quality_score = max(signals.bio_quality_score, 50)
            flags.append("Username contains many digits (bot pattern)")
        if re.search(r"[._]{2,}", username):
            signals.bio_quality_score = max(signals.bio_quality_score, 40)

        # --- Verification Bonus (real accounts) ---
        if follower.is_verified:
            # Verified accounts are essentially never bots
            signals.follower_ratio_score = 0
            signals.bio_quality_score = 0
            signals.posting_pattern_score = 0
            flags = []

        return signals, flags

    def compute_composite_score(self, signals: BotSignals) -> float:
        """Compute weighted composite bot score (0-100)."""
        score = (
            signals.engagement_score * SIGNAL_WEIGHTS["engagement_score"]
            + signals.follower_ratio_score * SIGNAL_WEIGHTS["follower_ratio_score"]
            + signals.bio_quality_score * SIGNAL_WEIGHTS["bio_quality_score"]
            + signals.posting_pattern_score * SIGNAL_WEIGHTS["posting_pattern_score"]
            + signals.comment_quality_score * SIGNAL_WEIGHTS["comment_quality_score"]
            + signals.account_age_score * SIGNAL_WEIGHTS["account_age_score"]
        )
        return min(max(score, 0), 100)

    def label_from_score(self, score: float) -> str:
        if score >= BOT_THRESHOLD:
            return "bot"
        elif score >= SUSPICIOUS_THRESHOLD:
            return "suspicious"
        return "real"


# ---------------------------------------------------------------------------
# Comment Quality Analyzer
# ---------------------------------------------------------------------------

class CommentAnalyzer:
    """Analyzes comment quality to detect spam/bot comments."""

    def __init__(self, use_ml: bool = False):
        self.use_ml = use_ml
        self._sentiment_pipeline = None

        if use_ml:
            self._load_model()

    def _load_model(self):
        """Load HuggingFace sentiment model (lazy)."""
        try:
            from transformers import pipeline
            model_name = os.getenv(
                "SENTIMENT_MODEL",
                "cardiffnlp/twitter-roberta-base-sentiment-latest"
            )
            logger.info(f"Loading sentiment model: {model_name}")
            self._sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model=model_name,
                truncation=True,
                max_length=128,
            )
            logger.info("✅ Sentiment model loaded")
        except Exception as e:
            logger.warning(f"Could not load ML model: {e}. Using rule-based fallback.")
            self._sentiment_pipeline = None

    def is_spam_comment(self, text: str) -> tuple[bool, float]:
        """
        Classify whether a comment is generic spam.

        Returns:
            (is_spam, confidence_score)
        """
        text = text.strip()
        if not text:
            return True, 1.0

        # Rule-based check
        for pattern in GENERIC_COMMENT_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True, 0.9

        # ML check if available
        if self._sentiment_pipeline:
            try:
                result = self._sentiment_pipeline(text)[0]
                # In context: extremely positive one-word comments are often bots
                if result["label"] in ("POSITIVE", "POS") and result["score"] > 0.95:
                    if len(text.split()) <= 3:
                        return True, 0.7
            except Exception:
                pass

        return False, 0.1

    def analyze_comments(self, comments: list[dict]) -> float:
        """
        Compute spam ratio for a list of comments.

        Returns:
            spam_ratio (0.0–1.0)
        """
        if not comments:
            return 0.0

        spam_count = sum(1 for c in comments if self.is_spam_comment(c.get("text", ""))[0])
        return spam_count / len(comments)


# ---------------------------------------------------------------------------
# Main Bot Detector
# ---------------------------------------------------------------------------

class BotDetector:
    """
    Main orchestrator for bot detection across followers.

    Example:
        detector = BotDetector()
        results = detector.analyze_followers(followers, account_info)
    """

    def __init__(self, use_ml_comments: bool = False):
        self.rule_engine = RuleEngine()
        self.comment_analyzer = CommentAnalyzer(use_ml=use_ml_comments)

    def analyze_follower(
        self,
        follower: FollowerInfo,
        sample_comments: Optional[list[dict]] = None,
    ) -> FollowerAnalysisResult:
        """
        Full bot analysis for a single follower.

        Args:
            follower: FollowerInfo object
            sample_comments: Optional list of the user's recent comments

        Returns:
            FollowerAnalysisResult with score, label, and explanation
        """
        signals, flags = self.rule_engine.compute_signals(follower)

        # Comment quality signal
        if sample_comments:
            spam_ratio = self.comment_analyzer.analyze_comments(sample_comments)
            signals.comment_quality_score = spam_ratio * 100
            if spam_ratio > 0.8:
                flags.append(f"High spam comment ratio: {spam_ratio:.0%}")

        score = self.rule_engine.compute_composite_score(signals)
        label = self.rule_engine.label_from_score(score)
        confidence = abs(score - 50) / 50  # Higher = more confident

        # Update follower object
        follower.bot_score = score
        follower.bot_label = label

        return FollowerAnalysisResult(
            username=follower.username,
            bot_score=score,
            label=label,
            signals=signals,
            flags=flags,
            confidence=confidence,
        )

    def analyze_followers(
        self,
        followers: list[FollowerInfo],
        account: Optional[AccountInfo] = None,
        show_progress: bool = True,
    ) -> AccountAnalysisResult:
        """
        Analyze all followers and produce a summary report.

        Args:
            followers: List of FollowerInfo objects
            account: Optional AccountInfo for overall metrics
            show_progress: Show tqdm progress bar

        Returns:
            AccountAnalysisResult with full breakdown
        """
        if not followers:
            logger.warning("No followers to analyze")

        from tqdm import tqdm

        results = []
        iterator = tqdm(followers, desc="Analyzing followers", unit="account") if show_progress else followers

        for follower in iterator:
            result = self.analyze_follower(follower)
            results.append(result)

        # Aggregate counts
        real_results = [r for r in results if r.label == "real"]
        suspicious_results = [r for r in results if r.label == "suspicious"]
        bot_results = [r for r in results if r.label == "bot"]

        total = len(results)

        # Collect top flags
        all_flags: dict[str, int] = {}
        for r in results:
            for flag in r.flags:
                key = flag.split(":")[0]  # Normalize
                all_flags[key] = all_flags.get(key, 0) + 1
        top_flags = [
            f"{flag} ({count} accounts)"
            for flag, count in sorted(all_flags.items(), key=lambda x: -x[1])[:5]
        ]

        # Account health score
        engagement_rate = account.engagement_rate if account and account.engagement_rate else 0.0
        bot_ratio = len(bot_results) / max(total, 1)
        health_score = max(0, 100 - (bot_ratio * 60) - (max(0, 3 - engagement_rate) * 10))

        engagement_quality = (
            "excellent" if engagement_rate >= 6
            else "good" if engagement_rate >= 3
            else "average" if engagement_rate >= 1
            else "poor"
        )

        return AccountAnalysisResult(
            username=account.username if account else "unknown",
            total_analyzed=total,
            real_count=len(real_results),
            suspicious_count=len(suspicious_results),
            bot_count=len(bot_results),
            real_percentage=len(real_results) / max(total, 1) * 100,
            suspicious_percentage=len(suspicious_results) / max(total, 1) * 100,
            bot_percentage=len(bot_results) / max(total, 1) * 100,
            engagement_rate=engagement_rate,
            engagement_quality=engagement_quality,
            follower_results=results,
            top_flags=top_flags,
            overall_health_score=health_score,
        )


def compute_engagement_rate(
    likes: float, comments: float, followers: int
) -> float:
    """Helper: compute engagement rate percentage."""
    if followers <= 0:
        return 0.0
    return ((likes + comments) / followers) * 100


def classify_engagement_rate(rate: float) -> str:
    """Return qualitative label for engagement rate."""
    if rate >= 6:
        return "🌟 Excellent (influencer-level)"
    elif rate >= 3:
        return "✅ Good"
    elif rate >= 1:
        return "⚠️  Average"
    else:
        return "❌ Poor (bot-inflated likely)"
