"""
cli.py - Command Line Interface
=====================================
Beautiful CLI powered by Typer + Rich.

Usage:
    python -m src.cli analyze @username
    python -m src.cli followers @username --output followers.csv
    python -m src.cli posts @username --limit 20
"""

import sys
from typing import Optional
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.text import Text
from rich import box
from loguru import logger

app = typer.Typer(
    name="instaanalyzer",
    help="📊 InstaStatus-Analyzer - Comprehensive Instagram Account Intelligence",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()

# Suppress loguru output to not interfere with Rich
logger.remove()
logger.add(sys.stderr, level="WARNING")


def _get_client():
    """Initialize and return Instagram client."""
    from src.auth import InstagramAuth
    auth = InstagramAuth()
    return auth.login()


def _make_progress():
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    )


def _print_banner():
    console.print(Panel.fit(
        "[bold magenta]📊 InstaStatus-Analyzer[/bold magenta]\n"
        "[dim]Instagram Account Intelligence & Bot Detection[/dim]",
        border_style="magenta",
    ))
    console.print()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command()
def analyze(
    username: str = typer.Argument(..., help="Instagram username (with or without @)"),
    bot_detection: bool = typer.Option(True, "--bot-detection/--no-bot-detection", help="Run bot detection on followers"),
    followers_limit: int = typer.Option(200, "--followers-limit", "-f", help="Max followers to analyze for bot detection"),
    posts_limit: int = typer.Option(12, "--posts-limit", "-p", help="Number of recent posts to analyze"),
    export: Optional[str] = typer.Option(None, "--export", "-e", help="Export format: csv, json, pdf, all"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Output directory for exports"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy URL (e.g. socks5://127.0.0.1:9050)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
):
    """
    [bold]Full account analysis[/bold] including bot detection, engagement metrics, and top posts.

    Examples:
        instaanalyzer analyze @username
        instaanalyzer analyze username --export pdf --followers-limit 500
    """
    _print_banner()
    username = username.lstrip("@").lower()

    try:
        from src.auth import InstagramAuth
        from src.fetcher import AccountFetcher
        from src.analyzer import BotDetector
        from src.exporter import ReportExporter

        # Login
        console.print(f"[dim]Authenticating...[/dim]")
        auth = InstagramAuth(proxy=proxy)
        client = auth.login()

        fetcher = AccountFetcher(client)

        # Fetch account
        with console.status(f"[bold]Fetching @{username} account info...[/bold]"):
            account = fetcher.get_account_info(username)

        # Fetch posts
        with console.status(f"[bold]Fetching {posts_limit} recent posts...[/bold]"):
            posts = fetcher.get_recent_posts(username, limit=posts_limit)
            account = fetcher.enrich_account_with_posts(account, posts)

        # --- Print Account Overview ---
        _print_account_overview(account)

        # --- Print Post Stats ---
        if posts:
            _print_posts_table(posts, top_n=5)

        # --- Bot Detection ---
        bot_result = None
        if bot_detection:
            console.print(f"\n[bold yellow]🤖 Running bot detection on up to {followers_limit} followers...[/bold yellow]")
            console.print("[dim]This may take a few minutes due to rate limiting.[/dim]\n")

            followers = fetcher.get_followers(
                username,
                limit=followers_limit,
                fetch_details=True,
                progress=True,
            )

            detector = BotDetector()
            bot_result = detector.analyze_followers(followers, account)

            _print_bot_analysis(bot_result)

        # --- Export ---
        if export:
            if output_dir:
                from src.exporter import ReportExporter as RE
                exporter = RE(output_dir=output_dir)
            else:
                exporter = ReportExporter()

            console.print(f"\n[bold]📤 Exporting results...[/bold]")

            if export == "all" and bot_result:
                paths = exporter.export_all(account, bot_result, followers if bot_detection else [], posts)
                for fmt, path in paths.items():
                    console.print(f"  ✅ [green]{fmt.upper()}[/green]: {path}")
            elif export == "csv" and bot_result:
                path = exporter.followers_to_csv(followers if bot_detection else [])
                console.print(f"  ✅ CSV: {path}")
            elif export == "json" and bot_result:
                path = exporter.analysis_to_json(account, bot_result, posts)
                console.print(f"  ✅ JSON: {path}")
            elif export == "pdf" and bot_result:
                path = exporter.to_pdf(account, bot_result, posts)
                console.print(f"  ✅ PDF: {path}")
            else:
                console.print("[yellow]Note: Enable --bot-detection for full export[/yellow]")

        console.print("\n[bold green]✅ Analysis complete![/bold green]")

    except Exception as e:
        console.print(f"\n[bold red]❌ Error: {e}[/bold red]")
        if verbose:
            import traceback
            console.print_exception()
        raise typer.Exit(1)


@app.command()
def followers(
    username: str = typer.Argument(..., help="Instagram username"),
    limit: int = typer.Option(500, "--limit", "-l", help="Max followers to fetch"),
    details: bool = typer.Option(False, "--details", help="Fetch full profile details (slower)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output CSV file path"),
    analyze_bots: bool = typer.Option(False, "--analyze-bots", help="Run bot detection"),
):
    """
    [bold]Export follower list[/bold] to CSV with optional bot scoring.

    Examples:
        instaanalyzer followers @username --output followers.csv
        instaanalyzer followers @username --limit 1000 --analyze-bots
    """
    _print_banner()
    username = username.lstrip("@").lower()

    try:
        from src.auth import InstagramAuth
        from src.fetcher import AccountFetcher
        from src.exporter import ReportExporter

        auth = InstagramAuth()
        client = auth.login()
        fetcher = AccountFetcher(client)

        console.print(f"[bold]Fetching followers for @{username}...[/bold]")
        follower_list = fetcher.get_followers(
            username, limit=limit, fetch_details=details, progress=True
        )

        if analyze_bots:
            from src.analyzer import BotDetector
            console.print("[bold]Analyzing for bots...[/bold]")
            detector = BotDetector()
            for f in follower_list:
                result = detector.analyze_follower(f)
                f.bot_score = result.bot_score
                f.bot_label = result.label

        exporter = ReportExporter()
        csv_path = exporter.followers_to_csv(follower_list, output)

        console.print(f"\n✅ Exported [bold]{len(follower_list):,}[/bold] followers to [green]{csv_path}[/green]")

    except Exception as e:
        console.print(f"[bold red]❌ Error: {e}[/bold red]")
        raise typer.Exit(1)


@app.command()
def posts(
    username: str = typer.Argument(..., help="Instagram username"),
    limit: int = typer.Option(20, "--limit", "-l", help="Number of posts to fetch"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output CSV file"),
):
    """[bold]Fetch and display recent posts[/bold] with engagement metrics."""
    _print_banner()
    username = username.lstrip("@").lower()

    try:
        from src.auth import InstagramAuth
        from src.fetcher import AccountFetcher
        from src.exporter import ReportExporter

        auth = InstagramAuth()
        client = auth.login()
        fetcher = AccountFetcher(client)

        with console.status(f"Fetching posts for @{username}..."):
            post_list = fetcher.get_recent_posts(username, limit=limit)

        _print_posts_table(post_list, top_n=limit)

        if output:
            exporter = ReportExporter()
            path = exporter.posts_to_csv(post_list, username, output)
            console.print(f"\n✅ Exported to [green]{path}[/green]")

    except Exception as e:
        console.print(f"[bold red]❌ Error: {e}[/bold red]")
        raise typer.Exit(1)


@app.command()
def dashboard():
    """[bold]Launch the Streamlit web dashboard.[/bold]"""
    import subprocess
    console.print("[bold]🌐 Launching dashboard at http://localhost:8501[/bold]")
    subprocess.run(["streamlit", "run", "src/dashboard.py"])


@app.command()
def version():
    """Show version information."""
    from src import __version__
    console.print(f"InstaStatus-Analyzer v[bold]{__version__}[/bold]")


# ---------------------------------------------------------------------------
# Print Helpers
# ---------------------------------------------------------------------------

def _print_account_overview(account):
    from src.analyzer import classify_engagement_rate

    verified_badge = "✅ Verified" if account.is_verified else ""
    private_badge = "🔒 Private" if account.is_private else "🌐 Public"
    eng_label = classify_engagement_rate(account.engagement_rate or 0)

    table = Table(
        title=f"@{account.username} {verified_badge}",
        box=box.ROUNDED,
        border_style="blue",
        show_header=False,
        min_width=60,
    )
    table.add_column("Field", style="bold cyan", width=25)
    table.add_column("Value", style="white")

    table.add_row("Full Name", account.full_name or "[dim]N/A[/dim]")
    table.add_row("Bio", (account.bio or "")[:80] or "[dim]No bio[/dim]")
    table.add_row("Status", f"{private_badge}")
    table.add_row("Followers", f"[bold green]{account.follower_count:,}[/bold green]")
    table.add_row("Following", f"{account.following_count:,}")
    table.add_row("Posts", f"{account.post_count:,}")
    table.add_row("F/F Ratio", f"{account.follower_following_ratio:.1f}x")
    table.add_row("Engagement Rate", f"{account.engagement_rate:.2f}%" if account.engagement_rate else "N/A")
    table.add_row("Engagement Quality", eng_label)
    table.add_row("Total Likes (recent)", f"{account.total_likes:,}")
    table.add_row("Total Views (recent)", f"{account.total_views:,}")
    table.add_row("Avg Likes / Post", f"{account.avg_likes_per_post:,.0f}")

    console.print(table)


def _print_posts_table(posts, top_n: int = 10):
    table = Table(
        title=f"🖼️  Recent Posts (Top {min(top_n, len(posts))} by Engagement)",
        box=box.SIMPLE_HEAVY,
        border_style="magenta",
    )
    table.add_column("Date", style="dim", width=12)
    table.add_column("Type", width=8)
    table.add_column("Likes", justify="right", style="green")
    table.add_column("Comments", justify="right", style="cyan")
    table.add_column("Views", justify="right", style="blue")
    table.add_column("Engagement", justify="right", style="bold yellow")
    table.add_column("Link", style="dim")

    sorted_posts = sorted(posts, key=lambda x: x.engagement, reverse=True)[:top_n]
    for post in sorted_posts:
        table.add_row(
            post.taken_at.strftime("%Y-%m-%d"),
            post.media_type_label,
            f"{post.like_count:,}",
            f"{post.comment_count:,}",
            f"{post.view_count:,}",
            f"{post.engagement:,}",
            post.permalink[:35] + "...",
        )

    console.print()
    console.print(table)


def _print_bot_analysis(result):
    # Summary panel
    real_bar = "█" * int(result.real_percentage / 5)
    sus_bar = "█" * int(result.suspicious_percentage / 5)
    bot_bar = "█" * int(result.bot_percentage / 5)

    summary = (
        f"[bold]Analyzed: {result.total_analyzed:,} followers[/bold]\n\n"
        f"[green]✅ Real       {result.real_count:>7,}  ({result.real_percentage:5.1f}%) [green]{real_bar}[/green]\n"
        f"[yellow]⚠️  Suspicious {result.suspicious_count:>7,}  ({result.suspicious_percentage:5.1f}%) [yellow]{sus_bar}[/yellow]\n"
        f"[red]🤖 Bot        {result.bot_count:>7,}  ({result.bot_percentage:5.1f}%) [red]{bot_bar}[/red]\n\n"
        f"[bold]Health Score: {result.overall_health_score:.0f}/100[/bold]  |  "
        f"Engagement: [bold]{result.engagement_quality}[/bold]"
    )

    console.print()
    console.print(Panel(summary, title="🤖 Bot Detection Results", border_style="yellow"))

    # Top flags
    if result.top_flags:
        console.print("\n[bold]🚩 Top Suspicious Patterns:[/bold]")
        for flag in result.top_flags:
            console.print(f"  • {flag}")

    # Sample bot accounts
    bots = [r for r in result.follower_results if r.label == "bot"][:5]
    if bots:
        console.print("\n[bold red]Sample Detected Bots:[/bold red]")
        bot_table = Table(box=box.SIMPLE, show_header=True)
        bot_table.add_column("Username", style="red")
        bot_table.add_column("Score", justify="right")
        bot_table.add_column("Top Flag")
        for b in bots:
            bot_table.add_row(
                f"@{b.username}",
                f"{b.bot_score:.0f}/100",
                b.flags[0] if b.flags else "",
            )
        console.print(bot_table)


if __name__ == "__main__":
    app()
