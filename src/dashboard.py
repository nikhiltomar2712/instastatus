"""
dashboard.py - Streamlit Web Dashboard
=======================================
Visual web interface for Instagram account analysis.

Launch with:
    streamlit run src/dashboard.py
"""

import os
import json
from pathlib import Path
from datetime import datetime

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

st.set_page_config(
    page_title="InstaStatus-Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom CSS ---
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #833ab4, #fd1d1d, #fcb045);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.5rem;
        font-weight: 800;
    }
    .metric-card {
        background: #1e1e2e;
        border-radius: 12px;
        padding: 1rem;
        color: white;
        text-align: center;
    }
    .bot-badge-real { background: #22c55e; color: white; padding: 2px 8px; border-radius: 4px; }
    .bot-badge-suspicious { background: #f59e0b; color: white; padding: 2px 8px; border-radius: 4px; }
    .bot-badge-bot { background: #ef4444; color: white; padding: 2px 8px; border-radius: 4px; }
    .disclaimer-box {
        background: #fff3cd;
        border-left: 4px solid #ff9800;
        padding: 0.75rem 1rem;
        border-radius: 0 8px 8px 0;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session State
# ---------------------------------------------------------------------------

if "account" not in st.session_state:
    st.session_state.account = None
if "posts" not in st.session_state:
    st.session_state.posts = []
if "followers" not in st.session_state:
    st.session_state.followers = []
if "bot_result" not in st.session_state:
    st.session_state.bot_result = None
if "client" not in st.session_state:
    st.session_state.client = None


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 📊 InstaStatus-Analyzer")
    st.markdown("---")

    st.markdown("### 🔐 Authentication")
    ig_username = st.text_input(
        "Instagram Username",
        value=os.getenv("INSTAGRAM_USERNAME", ""),
        type="default",
        placeholder="your_username",
    )
    ig_password = st.text_input(
        "Instagram Password",
        value=os.getenv("INSTAGRAM_PASSWORD", ""),
        type="password",
        placeholder="••••••••",
    )
    proxy_url = st.text_input("Proxy (optional)", placeholder="socks5://127.0.0.1:9050")

    if st.button("🔑 Login", use_container_width=True):
        with st.spinner("Logging in..."):
            try:
                from src.auth import InstagramAuth
                auth = InstagramAuth(
                    username=ig_username,
                    password=ig_password,
                    proxy=proxy_url or None,
                )
                st.session_state.client = auth.login()
                st.success("✅ Logged in!")
            except Exception as e:
                st.error(f"❌ Login failed: {e}")

    st.markdown("---")
    st.markdown("### 🔍 Analysis Settings")
    target_username = st.text_input("Target Username", placeholder="@username")
    posts_limit = st.slider("Posts to analyze", 6, 50, 12)
    followers_limit = st.slider("Followers for bot detection", 50, 1000, 200, step=50)
    fetch_details = st.checkbox("Fetch follower details (slower)", value=False)
    run_bot_detection = st.checkbox("Run bot detection", value=True)

    analyze_btn = st.button("🚀 Analyze Account", use_container_width=True, type="primary")

    st.markdown("---")
    st.markdown("### 📁 Load from JSON")
    uploaded = st.file_uploader("Load saved analysis", type=["json"])
    if uploaded:
        _load_from_json(uploaded)

    st.markdown("---")
    st.markdown(
        "<div class='disclaimer-box'>"
        "⚠️ <b>Disclaimer:</b> This tool uses unofficial APIs. "
        "Use responsibly. Educational purposes only."
        "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Analysis Runner
# ---------------------------------------------------------------------------

def run_analysis(username: str):
    """Run full analysis and store in session state."""
    if not st.session_state.client:
        st.error("Please log in first.")
        return

    username = username.lstrip("@").lower()

    from src.fetcher import AccountFetcher
    from src.analyzer import BotDetector

    fetcher = AccountFetcher(st.session_state.client)

    progress_bar = st.progress(0, text="Fetching account info...")

    # Account info
    account = fetcher.get_account_info(username)
    progress_bar.progress(20, text="Fetching posts...")

    # Posts
    posts = fetcher.get_recent_posts(username, limit=posts_limit)
    account = fetcher.enrich_account_with_posts(account, posts)
    progress_bar.progress(50, text="Fetching followers...")

    st.session_state.account = account
    st.session_state.posts = posts

    # Bot detection
    bot_result = None
    if run_bot_detection:
        followers = fetcher.get_followers(
            username,
            limit=followers_limit,
            fetch_details=fetch_details,
            progress=False,
        )
        st.session_state.followers = followers
        progress_bar.progress(80, text="Running bot detection...")

        detector = BotDetector()
        bot_result = detector.analyze_followers(followers, account, show_progress=False)
        st.session_state.bot_result = bot_result

    progress_bar.progress(100, text="Done!")
    progress_bar.empty()
    st.success(f"✅ Analysis complete for @{username}")


if analyze_btn and target_username:
    try:
        run_analysis(target_username)
    except Exception as e:
        st.error(f"Analysis failed: {e}")


# ---------------------------------------------------------------------------
# Main Dashboard
# ---------------------------------------------------------------------------

st.markdown('<h1 class="main-header">📊 InstaStatus-Analyzer</h1>', unsafe_allow_html=True)
st.markdown("*Instagram Account Intelligence & Bot Detection Platform*")
st.markdown("---")

if not st.session_state.account:
    st.markdown("""
    ## Welcome! 👋

    **Get started:**
    1. Enter your Instagram credentials in the sidebar
    2. Click **Login**
    3. Enter the target username to analyze
    4. Click **Analyze Account**

    **What you'll get:**
    - 📈 Full engagement analytics
    - 🤖 Real vs Bot follower breakdown
    - 👥 Exportable follower list
    - 🖼️ Top posts by engagement
    - 📄 PDF / CSV / JSON export
    """)
    st.info("💡 Tip: Use a dedicated throwaway account to avoid risking your main account.")
    st.stop()

account = st.session_state.account
posts = st.session_state.posts
bot_result = st.session_state.bot_result

# ---------------------------------------------------------------------------
# Account Overview Row
# ---------------------------------------------------------------------------

st.subheader(f"@{account.username} {'✅' if account.is_verified else ''}")
st.caption(account.bio or "*No bio*")

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("👥 Followers", f"{account.follower_count:,}")
with col2:
    st.metric("➡️ Following", f"{account.following_count:,}")
with col3:
    st.metric("🖼️ Posts", f"{account.post_count:,}")
with col4:
    st.metric("💯 Engagement", f"{account.engagement_rate:.2f}%" if account.engagement_rate else "N/A")
with col5:
    st.metric("👀 Total Views", f"{account.total_views:,}")

col_a, col_b = st.columns(2)
with col_a:
    st.metric("❤️ Total Likes (recent)", f"{account.total_likes:,}")
with col_b:
    st.metric("F/F Ratio", f"{account.follower_following_ratio:.1f}x")

# ---------------------------------------------------------------------------
# Bot Detection
# ---------------------------------------------------------------------------

if bot_result:
    st.markdown("---")
    st.subheader("🤖 Bot Detection Analysis")

    # Donut chart
    col_chart, col_stats = st.columns([1, 1])

    with col_chart:
        fig = go.Figure(data=[go.Pie(
            labels=["Real Followers", "Suspicious", "Likely Bots"],
            values=[bot_result.real_count, bot_result.suspicious_count, bot_result.bot_count],
            hole=0.5,
            marker_colors=["#22c55e", "#f59e0b", "#ef4444"],
        )])
        fig.update_layout(
            title="Follower Composition",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#ffffff" if st.get_option("theme.base") == "dark" else "#000000",
            legend=dict(orientation="h"),
            height=350,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_stats:
        st.markdown("#### Summary")
        st.markdown(f"""
        | Category | Count | Percentage |
        |----------|-------|------------|
        | ✅ Real Followers | {bot_result.real_count:,} | {bot_result.real_percentage:.1f}% |
        | ⚠️ Suspicious | {bot_result.suspicious_count:,} | {bot_result.suspicious_percentage:.1f}% |
        | 🤖 Likely Bots | {bot_result.bot_count:,} | {bot_result.bot_percentage:.1f}% |
        | **Total Analyzed** | **{bot_result.total_analyzed:,}** | **100%** |
        """)
        st.progress(bot_result.overall_health_score / 100)
        st.caption(f"Account Health Score: {bot_result.overall_health_score:.0f}/100")

        st.markdown(f"**Engagement Quality:** `{bot_result.engagement_quality.upper()}`")

        if bot_result.top_flags:
            st.markdown("**🚩 Top Suspicious Patterns:**")
            for flag in bot_result.top_flags:
                st.markdown(f"• {flag}")

    # Follower table with bot scores
    if bot_result.follower_results:
        st.markdown("#### 👥 Follower Bot Scores")

        df = pd.DataFrame([
            {
                "Username": f"@{r.username}",
                "Bot Score": round(r.bot_score, 1),
                "Label": r.label.capitalize(),
                "Top Flag": r.flags[0] if r.flags else "",
            }
            for r in sorted(bot_result.follower_results, key=lambda x: -x.bot_score)
        ])

        label_filter = st.multiselect(
            "Filter by label", ["Real", "Suspicious", "Bot"],
            default=["Suspicious", "Bot"]
        )
        filtered_df = df[df["Label"].isin(label_filter)]

        st.dataframe(
            filtered_df,
            use_container_width=True,
            hide_index=True,
        )

        # Export
        if st.button("⬇️ Download Follower CSV"):
            from src.exporter import ReportExporter
            exporter = ReportExporter()
            path = exporter.followers_to_csv(st.session_state.followers)
            st.success(f"Exported to {path}")

# ---------------------------------------------------------------------------
# Posts Section
# ---------------------------------------------------------------------------

if posts:
    st.markdown("---")
    st.subheader("🖼️ Recent Posts")

    posts_df = pd.DataFrame([
        {
            "Date": p.taken_at.strftime("%Y-%m-%d"),
            "Type": p.media_type_label,
            "Likes": p.like_count,
            "Comments": p.comment_count,
            "Views": p.view_count,
            "Engagement": p.engagement,
            "URL": p.permalink,
        }
        for p in posts
    ])

    # Engagement bar chart
    fig_posts = px.bar(
        posts_df.sort_values("Date"),
        x="Date",
        y=["Likes", "Comments"],
        title="Engagement per Post",
        barmode="stack",
        color_discrete_map={"Likes": "#833ab4", "Comments": "#fd1d1d"},
    )
    fig_posts.update_layout(paper_bgcolor="rgba(0,0,0,0)", height=300)
    st.plotly_chart(fig_posts, use_container_width=True)

    st.dataframe(posts_df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Export Section
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("📤 Export Reports")

col_e1, col_e2, col_e3 = st.columns(3)

if account:
    with col_e1:
        if st.button("📊 Export JSON", use_container_width=True):
            if bot_result:
                from src.exporter import ReportExporter
                exporter = ReportExporter()
                path = exporter.analysis_to_json(account, bot_result, posts)
                st.success(f"Saved: {path}")
            else:
                st.warning("Run bot detection first")

    with col_e2:
        if st.button("📋 Export CSV", use_container_width=True):
            if st.session_state.followers:
                from src.exporter import ReportExporter
                exporter = ReportExporter()
                path = exporter.followers_to_csv(st.session_state.followers)
                st.success(f"Saved: {path}")
            else:
                st.warning("Fetch followers first")

    with col_e3:
        if st.button("📄 Export PDF Report", use_container_width=True):
            if bot_result:
                from src.exporter import ReportExporter
                exporter = ReportExporter()
                path = exporter.to_pdf(account, bot_result, posts)
                st.success(f"Saved: {path}")
            else:
                st.warning("Run bot detection first")


def _load_from_json(uploaded_file):
    """Load a previously saved JSON analysis."""
    try:
        data = json.load(uploaded_file)
        st.session_state.account = None  # TODO: reconstruct from JSON
        st.sidebar.success("Loaded analysis file")
    except Exception as e:
        st.sidebar.error(f"Failed to load: {e}")
