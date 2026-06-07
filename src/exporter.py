"""
exporter.py - Report & Data Export
=====================================
Exports analysis results to CSV, JSON, and PDF formats.
"""

import json
import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from src.fetcher import AccountInfo, PostInfo, FollowerInfo
from src.analyzer import AccountAnalysisResult


EXPORT_DIR = Path(os.getenv("EXPORT_DIR", "./exports"))
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


class ReportExporter:
    """
    Export analysis results to various formats.

    Example:
        exporter = ReportExporter()
        exporter.followers_to_csv(followers, "followers.csv")
        exporter.analysis_to_json(result, "analysis.json")
        exporter.to_pdf(account, result, posts, "report.pdf")
    """

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or EXPORT_DIR

    # -------------------------------------------------------------------------
    # CSV Exports
    # -------------------------------------------------------------------------

    def followers_to_csv(
        self,
        followers: list[FollowerInfo],
        filename: Optional[str] = None,
    ) -> Path:
        """
        Export follower list to CSV.

        Columns: username, full_name, verified, private, followers,
                 following, posts, bio, bot_score, bot_label
        """
        filename = filename or f"followers_{_timestamp()}.csv"
        path = self.output_dir / filename

        fieldnames = [
            "username", "full_name", "verified", "private",
            "follower_count", "following_count", "post_count",
            "bio", "profile_url", "bot_score", "bot_label",
        ]

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for follower in followers:
                writer.writerow({
                    "username": follower.username,
                    "full_name": follower.full_name,
                    "verified": follower.is_verified,
                    "private": follower.is_private,
                    "follower_count": follower.follower_count or "",
                    "following_count": follower.following_count or "",
                    "post_count": follower.post_count or "",
                    "bio": (follower.bio or "").replace("\n", " "),
                    "profile_url": f"https://instagram.com/{follower.username}",
                    "bot_score": follower.bot_score or "",
                    "bot_label": follower.bot_label or "",
                })

        logger.info(f"✅ Followers exported to {path}")
        return path

    def posts_to_csv(
        self,
        posts: list[PostInfo],
        username: str,
        filename: Optional[str] = None,
    ) -> Path:
        """Export post metrics to CSV."""
        filename = filename or f"posts_{username}_{_timestamp()}.csv"
        path = self.output_dir / filename

        fieldnames = [
            "shortcode", "type", "date", "likes", "comments",
            "views", "engagement", "caption_preview", "permalink"
        ]

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for post in posts:
                caption_preview = (post.caption or "")[:100].replace("\n", " ")
                writer.writerow({
                    "shortcode": post.shortcode,
                    "type": post.media_type_label,
                    "date": post.taken_at.strftime("%Y-%m-%d"),
                    "likes": post.like_count,
                    "comments": post.comment_count,
                    "views": post.view_count,
                    "engagement": post.engagement,
                    "caption_preview": caption_preview,
                    "permalink": post.permalink,
                })

        logger.info(f"✅ Posts exported to {path}")
        return path

    # -------------------------------------------------------------------------
    # JSON Export
    # -------------------------------------------------------------------------

    def analysis_to_json(
        self,
        account: AccountInfo,
        result: AccountAnalysisResult,
        posts: Optional[list[PostInfo]] = None,
        filename: Optional[str] = None,
    ) -> Path:
        """Export full analysis to JSON."""
        filename = filename or f"analysis_{account.username}_{_timestamp()}.json"
        path = self.output_dir / filename

        data = {
            "generated_at": datetime.now().isoformat(),
            "account": {
                "username": account.username,
                "full_name": account.full_name,
                "bio": account.bio,
                "followers": account.follower_count,
                "following": account.following_count,
                "posts": account.post_count,
                "verified": account.is_verified,
                "private": account.is_private,
                "engagement_rate": account.engagement_rate,
                "total_likes": account.total_likes,
                "total_comments": account.total_comments,
                "total_views": account.total_views,
                "avg_likes_per_post": account.avg_likes_per_post,
                "follower_following_ratio": account.follower_following_ratio,
            },
            "bot_analysis": {
                "total_analyzed": result.total_analyzed,
                "real_count": result.real_count,
                "suspicious_count": result.suspicious_count,
                "bot_count": result.bot_count,
                "real_pct": round(result.real_percentage, 1),
                "suspicious_pct": round(result.suspicious_percentage, 1),
                "bot_pct": round(result.bot_percentage, 1),
                "engagement_quality": result.engagement_quality,
                "overall_health_score": round(result.overall_health_score, 1),
                "top_flags": result.top_flags,
            },
            "follower_details": [
                {
                    "username": r.username,
                    "bot_score": round(r.bot_score, 1),
                    "label": r.label,
                    "flags": r.flags,
                }
                for r in result.follower_results
            ],
        }

        if posts:
            data["top_posts"] = [
                {
                    "shortcode": p.shortcode,
                    "type": p.media_type_label,
                    "likes": p.like_count,
                    "comments": p.comment_count,
                    "views": p.view_count,
                    "date": p.taken_at.isoformat(),
                    "url": p.permalink,
                }
                for p in sorted(posts, key=lambda x: x.engagement, reverse=True)[:10]
            ]

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"✅ Analysis exported to {path}")
        return path

    # -------------------------------------------------------------------------
    # PDF Report
    # -------------------------------------------------------------------------

    def to_pdf(
        self,
        account: AccountInfo,
        result: AccountAnalysisResult,
        posts: Optional[list[PostInfo]] = None,
        filename: Optional[str] = None,
    ) -> Path:
        """
        Generate a professional PDF report.
        Uses fpdf2 library.
        """
        filename = filename or f"report_{account.username}_{_timestamp()}.pdf"
        path = self.output_dir / filename

        try:
            from fpdf import FPDF, XPos, YPos

            class PDF(FPDF):
                def header(self):
                    self.set_font("Helvetica", "B", 14)
                    self.set_fill_color(30, 30, 46)
                    self.set_text_color(255, 255, 255)
                    self.cell(0, 12, "InstaStatus-Analyzer Report", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
                    self.set_text_color(0, 0, 0)
                    self.ln(2)

                def footer(self):
                    self.set_y(-15)
                    self.set_font("Helvetica", "I", 8)
                    self.set_text_color(128, 128, 128)
                    self.cell(0, 10, f"Page {self.page_no()} | Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | Educational use only", align="C")

            pdf = PDF()
            pdf.add_page()
            pdf.set_auto_page_break(auto=True, margin=15)

            # --- Account Overview ---
            pdf.set_font("Helvetica", "B", 16)
            pdf.set_text_color(30, 30, 46)
            pdf.cell(0, 10, f"Account: @{account.username}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(0, 6, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(5)

            # Key metrics table
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_fill_color(240, 240, 240)
            pdf.cell(0, 8, "Account Overview", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
            pdf.ln(2)

            metrics = [
                ("Followers", f"{account.follower_count:,}"),
                ("Following", f"{account.following_count:,}"),
                ("Posts", f"{account.post_count:,}"),
                ("Verified", "Yes" if account.is_verified else "No"),
                ("Engagement Rate", f"{account.engagement_rate:.2f}%" if account.engagement_rate else "N/A"),
                ("Total Likes (recent)", f"{account.total_likes:,}"),
                ("Total Views (recent)", f"{account.total_views:,}"),
                ("Bio", (account.bio or "")[:80]),
            ]

            pdf.set_font("Helvetica", "", 10)
            for label, value in metrics:
                pdf.set_fill_color(250, 250, 250)
                pdf.cell(60, 7, label, border=1, fill=True)
                pdf.cell(0, 7, str(value), border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            pdf.ln(8)

            # --- Bot Detection Summary ---
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_fill_color(240, 240, 240)
            pdf.cell(0, 8, "Bot Detection Analysis", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
            pdf.ln(2)

            bot_metrics = [
                ("Accounts Analyzed", str(result.total_analyzed)),
                ("✅ Real Followers", f"{result.real_count:,} ({result.real_percentage:.1f}%)"),
                ("⚠️  Suspicious", f"{result.suspicious_count:,} ({result.suspicious_percentage:.1f}%)"),
                ("🤖 Likely Bots", f"{result.bot_count:,} ({result.bot_percentage:.1f}%)"),
                ("Engagement Quality", result.engagement_quality.capitalize()),
                ("Account Health Score", f"{result.overall_health_score:.0f}/100"),
            ]

            pdf.set_font("Helvetica", "", 10)
            for label, value in bot_metrics:
                pdf.cell(70, 7, label, border=1)
                pdf.cell(0, 7, value, border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            if result.top_flags:
                pdf.ln(5)
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(0, 7, "Top Suspicious Patterns:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_font("Helvetica", "", 10)
                for flag in result.top_flags:
                    pdf.cell(0, 6, f"  • {flag}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            # --- Top Posts ---
            if posts:
                pdf.add_page()
                pdf.set_font("Helvetica", "B", 12)
                pdf.set_fill_color(240, 240, 240)
                pdf.cell(0, 8, "Top 10 Posts by Engagement", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
                pdf.ln(2)

                top_posts = sorted(posts, key=lambda x: x.engagement, reverse=True)[:10]

                pdf.set_font("Helvetica", "B", 9)
                pdf.cell(25, 7, "Date", border=1)
                pdf.cell(20, 7, "Type", border=1)
                pdf.cell(25, 7, "Likes", border=1)
                pdf.cell(25, 7, "Comments", border=1)
                pdf.cell(25, 7, "Views", border=1)
                pdf.cell(0, 7, "URL", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

                pdf.set_font("Helvetica", "", 8)
                for post in top_posts:
                    pdf.cell(25, 6, post.taken_at.strftime("%Y-%m-%d"), border=1)
                    pdf.cell(20, 6, post.media_type_label, border=1)
                    pdf.cell(25, 6, f"{post.like_count:,}", border=1)
                    pdf.cell(25, 6, f"{post.comment_count:,}", border=1)
                    pdf.cell(25, 6, f"{post.view_count:,}", border=1)
                    pdf.cell(0, 6, post.permalink[:40], border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            # Disclaimer
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 8, "⚠️ Disclaimer", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(100, 100, 100)
            disclaimer = (
                "This report was generated using InstaStatus-Analyzer for educational and research "
                "purposes only. The tool uses unofficial Instagram APIs which may violate Instagram's "
                "Terms of Service. Bot detection results are probabilistic estimates and not guaranteed "
                "to be accurate. Do not use this data to harass, stalk, or harm individuals. The authors "
                "are not responsible for any consequences arising from use of this tool."
            )
            pdf.multi_cell(0, 5, disclaimer)

            pdf.output(str(path))
            logger.info(f"✅ PDF report exported to {path}")
            return path

        except ImportError:
            logger.error("fpdf2 not installed. Install with: pip install fpdf2")
            # Fall back to JSON
            logger.info("Falling back to JSON export")
            return self.analysis_to_json(account, result, posts)
        except Exception as e:
            logger.error(f"PDF generation failed: {e}")
            raise

    # -------------------------------------------------------------------------
    # Convenience: Export All
    # -------------------------------------------------------------------------

    def export_all(
        self,
        account: AccountInfo,
        result: AccountAnalysisResult,
        followers: list[FollowerInfo],
        posts: Optional[list[PostInfo]] = None,
        username_prefix: Optional[str] = None,
    ) -> dict[str, Path]:
        """
        Export everything: CSV followers, JSON analysis, PDF report.

        Returns:
            Dict with keys "csv", "json", "pdf" mapped to file paths
        """
        prefix = username_prefix or account.username
        ts = _timestamp()

        paths = {}

        paths["csv"] = self.followers_to_csv(followers, f"{prefix}_followers_{ts}.csv")
        paths["json"] = self.analysis_to_json(account, result, posts, f"{prefix}_analysis_{ts}.json")
        paths["pdf"] = self.to_pdf(account, result, posts, f"{prefix}_report_{ts}.pdf")

        if posts:
            paths["posts_csv"] = self.posts_to_csv(posts, prefix, f"{prefix}_posts_{ts}.csv")

        logger.info(f"✅ All exports complete for @{prefix}")
        return paths
