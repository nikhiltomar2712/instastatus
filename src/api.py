"""
api.py - FastAPI REST Backend
==============================
REST API for Instagram analysis.

Launch with:
    uvicorn src.api:app --reload --port 8000
    
Docs at: http://localhost:8000/docs
"""

import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Security
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from loguru import logger

from src.auth import InstagramAuth
from src.fetcher import AccountFetcher, AccountInfo
from src.analyzer import BotDetector, AccountAnalysisResult
from src.exporter import ReportExporter


# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="InstaStatus-Analyzer API",
    description="Comprehensive Instagram Account Intelligence & Bot Detection",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("API_SECRET_KEY", "dev-secret-change-in-production")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(key: Optional[str] = Security(api_key_header)):
    if os.getenv("API_DEBUG", "false").lower() == "true":
        return True  # Skip auth in debug mode
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return key


# Shared client (lazy init)
_client = None

def get_client():
    global _client
    if _client is None:
        auth = InstagramAuth()
        _client = auth.login()
    return _client


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    username: str = Field(..., description="Instagram username (without @)")
    followers_limit: int = Field(200, ge=10, le=2000)
    posts_limit: int = Field(12, ge=1, le=50)
    bot_detection: bool = True
    fetch_follower_details: bool = False


class AccountResponse(BaseModel):
    username: str
    full_name: str
    bio: str
    followers: int
    following: int
    posts: int
    verified: bool
    private: bool
    engagement_rate: Optional[float]
    total_likes: int
    total_views: int
    follower_following_ratio: float


class BotAnalysisResponse(BaseModel):
    total_analyzed: int
    real_count: int
    suspicious_count: int
    bot_count: int
    real_pct: float
    suspicious_pct: float
    bot_pct: float
    engagement_quality: str
    overall_health_score: float
    top_flags: list[str]


class FullAnalysisResponse(BaseModel):
    account: AccountResponse
    bot_analysis: Optional[BotAnalysisResponse]
    top_posts: list[dict]
    generated_at: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
    }


@app.post("/analyze/{username}", response_model=FullAnalysisResponse)
async def analyze_account(
    username: str,
    request: Optional[AnalyzeRequest] = None,
    _: str = Depends(verify_api_key),
):
    """
    Run full account analysis.

    Returns account info, engagement metrics, bot detection summary, and top posts.
    """
    username = username.lstrip("@").lower()

    if request is None:
        request = AnalyzeRequest(username=username)

    try:
        client = get_client()
        fetcher = AccountFetcher(client)

        account = fetcher.get_account_info(username)
        posts = fetcher.get_recent_posts(username, limit=request.posts_limit)
        account = fetcher.enrich_account_with_posts(account, posts)

        bot_response = None
        if request.bot_detection:
            followers = fetcher.get_followers(
                username,
                limit=request.followers_limit,
                fetch_details=request.fetch_follower_details,
                progress=False,
            )
            detector = BotDetector()
            result = detector.analyze_followers(followers, account, show_progress=False)

            bot_response = BotAnalysisResponse(
                total_analyzed=result.total_analyzed,
                real_count=result.real_count,
                suspicious_count=result.suspicious_count,
                bot_count=result.bot_count,
                real_pct=round(result.real_percentage, 1),
                suspicious_pct=round(result.suspicious_percentage, 1),
                bot_pct=round(result.bot_percentage, 1),
                engagement_quality=result.engagement_quality,
                overall_health_score=round(result.overall_health_score, 1),
                top_flags=result.top_flags,
            )

        account_response = AccountResponse(
            username=account.username,
            full_name=account.full_name,
            bio=account.bio,
            followers=account.follower_count,
            following=account.following_count,
            posts=account.post_count,
            verified=account.is_verified,
            private=account.is_private,
            engagement_rate=account.engagement_rate,
            total_likes=account.total_likes,
            total_views=account.total_views,
            follower_following_ratio=account.follower_following_ratio,
        )

        top_posts = [
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

        return FullAnalysisResponse(
            account=account_response,
            bot_analysis=bot_response,
            top_posts=top_posts,
            generated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"Analysis failed for @{username}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/followers/{username}")
async def get_followers(
    username: str,
    limit: int = 100,
    page: int = 1,
    _: str = Depends(verify_api_key),
):
    """Get paginated follower list."""
    username = username.lstrip("@").lower()
    try:
        client = get_client()
        fetcher = AccountFetcher(client)
        followers = fetcher.get_followers(username, limit=limit, progress=False)

        # Simple pagination
        start = (page - 1) * 50
        end = start + 50
        page_data = followers[start:end]

        return {
            "username": username,
            "total_fetched": len(followers),
            "page": page,
            "per_page": 50,
            "followers": [
                {
                    "username": f.username,
                    "full_name": f.full_name,
                    "verified": f.is_verified,
                    "private": f.is_private,
                    "profile_url": f"https://instagram.com/{f.username}",
                }
                for f in page_data
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/bot-score/{username}")
async def bot_score_summary(
    username: str,
    sample_size: int = 100,
    _: str = Depends(verify_api_key),
):
    """Quick bot score estimation for an account."""
    username = username.lstrip("@").lower()
    try:
        client = get_client()
        fetcher = AccountFetcher(client)

        account = fetcher.get_account_info(username)
        posts = fetcher.get_recent_posts(username, limit=6)
        account = fetcher.enrich_account_with_posts(account, posts)

        followers = fetcher.get_followers(username, limit=sample_size, progress=False)
        detector = BotDetector()
        result = detector.analyze_followers(followers, account, show_progress=False)

        return {
            "username": username,
            "sample_size": result.total_analyzed,
            "estimated_bot_percentage": round(result.bot_percentage, 1),
            "estimated_suspicious_percentage": round(result.suspicious_percentage, 1),
            "engagement_rate": account.engagement_rate,
            "engagement_quality": result.engagement_quality,
            "health_score": round(result.overall_health_score, 1),
            "top_flags": result.top_flags,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/export/{username}")
async def export_report(
    username: str,
    format: str = "pdf",
    sample_size: int = 200,
    _: str = Depends(verify_api_key),
):
    """Generate and download a report file."""
    username = username.lstrip("@").lower()

    try:
        client = get_client()
        fetcher = AccountFetcher(client)
        exporter = ReportExporter()

        account = fetcher.get_account_info(username)
        posts = fetcher.get_recent_posts(username, limit=12)
        account = fetcher.enrich_account_with_posts(account, posts)

        followers = fetcher.get_followers(username, limit=sample_size, progress=False)
        detector = BotDetector()
        result = detector.analyze_followers(followers, account, show_progress=False)

        if format == "pdf":
            path = exporter.to_pdf(account, result, posts)
            media_type = "application/pdf"
        elif format == "json":
            path = exporter.analysis_to_json(account, result, posts)
            media_type = "application/json"
        elif format == "csv":
            path = exporter.followers_to_csv(followers)
            media_type = "text/csv"
        else:
            raise HTTPException(status_code=400, detail="format must be pdf, json, or csv")

        return FileResponse(
            path=str(path),
            media_type=media_type,
            filename=path.name,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
