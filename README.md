# 📊 InstaStatus-Analyzer

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)
![Stars](https://img.shields.io/github/stars/nikhiltomar2712/InstaStatus-Analyzer?style=for-the-badge)
![Forks](https://img.shields.io/github/forks/nikhiltomar2712/InstaStatus-Analyzer?style=for-the-badge)
![Issues](https://img.shields.io/github/issues/nikhiltomar2712/InstaStatus-Analyzer?style=for-the-badge)
![CI](https://img.shields.io/github/actions/workflow/status/nikhiltomar2712/InstaStatus-Analyzer/ci.yml?style=for-the-badge&label=CI)

**Comprehensive Instagram Account Intelligence & Bot Detection Platform**

*Real followers vs fake detection · Engagement analytics · Follower export · Beautiful reports*

[Features](#-features) · [Installation](#-installation) · [Usage](#-usage) · [Dashboard](#-web-dashboard) · [API](#-api) · [Docker](#-docker) · [Disclaimer](#%EF%B8%8F-disclaimer)

</div>

---

## 🌟 Features

### 🤖 Bot / Fake Follower Detection
- **ML-based detection** using scikit-learn classifier trained on engagement patterns
- **Rule-based flags**: low engagement rate, generic bios, high following/low follower ratio
- **Comment quality analysis** via Hugging Face sentiment models
- **Posting pattern analysis**: frequency, timing, content diversity
- **Suspicion scoring** (0–100) with detailed breakdown per account

### 📈 Account Analytics
- Total likes across recent posts
- Reel & video view counts
- Engagement rate (likes + comments / followers)
- Growth trend estimation
- Top performing posts
- Follower/following ratio

### 👥 Follower Intelligence
- Full follower list export (username, bio, verified status, follower count)
- Bulk account classification (real / bot / suspicious)
- CSV, JSON, and PDF report export

### 🖥️ Interfaces
- **Rich CLI** with beautiful tables and progress bars (Typer + Rich)
- **Streamlit Web Dashboard** for visual exploration
- **FastAPI REST backend** for integration
- **Docker** for one-command deployment

### 🔐 Technical Features
- Instagrapi (unofficial API) + Selenium fallback
- Multi-account session management
- Proxy rotation support
- Rate limiting & retry logic
- Encrypted credential storage

---

## 📸 Screenshots

```
┌─────────────────────────────────────────────────────────────┐
│          InstaStatus-Analyzer - Account Overview            │
├─────────────────────────────────────────────────────────────┤
│  Username : @example_user     Verified : ✅                 │
│  Followers: 125,430           Following: 892                │
│  Posts    : 487               Account Age: ~3.2 years       │
│  Eng. Rate: 2.34%             Bio Score : 78/100            │
├─────────────────────────────────────────────────────────────┤
│  BOT ANALYSIS SUMMARY                                       │
│  Real Followers    : 98,241  (78.3%)   ████████████░░░░    │
│  Suspicious        : 18,914  (15.1%)   ████░░░░░░░░░░░░    │
│  Likely Bots       :  8,275  ( 6.6%)   ██░░░░░░░░░░░░░░    │
└─────────────────────────────────────────────────────────────┘
```

*Web dashboard: interactive charts with follower breakdown, engagement trends, top post grid*

---

## ⚙️ Installation

### Prerequisites
- Python 3.10+
- Chrome/Chromium (for Selenium fallback)
- Instagram account credentials

### Quick Install

```bash
# Clone the repository
git clone https://github.com/nikhiltomar2712/InstaStatus-Analyzer.git
cd InstaStatus-Analyzer

# Install dependencies
pip install -r requirements.txt

# Or with Poetry
poetry install

# Copy and configure environment
cp .env.example .env
# Edit .env with your credentials
```

### With Poetry (recommended)

```bash
poetry install
poetry shell
```

---

## 🚀 Usage

### CLI

```bash
# Analyze an account
python -m src.cli analyze @username

# Full analysis with bot detection
python -m src.cli analyze @username --bot-detection --export csv

# Export followers list
python -m src.cli followers @username --output followers.csv

# Batch analyze multiple accounts
python scripts/batch_analyze.py --input accounts.txt --output results/

# Run with proxy
python -m src.cli analyze @username --proxy socks5://127.0.0.1:9050
```

### Python API

```python
from src.auth import InstagramAuth
from src.fetcher import AccountFetcher
from src.analyzer import BotDetector
from src.exporter import ReportExporter

# Authenticate
auth = InstagramAuth()
client = auth.login()

# Fetch account data
fetcher = AccountFetcher(client)
account = fetcher.get_account_info("username")
followers = fetcher.get_followers("username", limit=500)

# Detect bots
detector = BotDetector()
results = detector.analyze_followers(followers)

print(f"Real: {results.real_count} | Bots: {results.bot_count}")

# Export report
exporter = ReportExporter()
exporter.to_pdf(account, results, "report.pdf")
```

---

## 🌐 Web Dashboard

```bash
# Launch Streamlit dashboard
streamlit run src/dashboard.py

# Open http://localhost:8501
```

The dashboard provides:
- Account overview cards
- Interactive pie chart: Real vs Bot vs Suspicious followers
- Engagement rate timeline
- Top posts grid with metrics
- Follower export with filtering

---

## 🔌 API

```bash
# Start FastAPI server
uvicorn src.api:app --reload --port 8000

# Docs at http://localhost:8000/docs
```

**Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/analyze/{username}` | Full account analysis |
| GET | `/followers/{username}` | Paginated follower list |
| GET | `/bot-score/{username}` | Bot detection summary |
| POST | `/export/{username}` | Generate downloadable report |
| GET | `/health` | Health check |

---

## 🐳 Docker

```bash
# Quick start
docker-compose up -d

# Access dashboard at http://localhost:8501
# Access API at http://localhost:8000
```

---

## 📁 Project Structure

```
InstaStatus-Analyzer/
├── src/
│   ├── __init__.py
│   ├── auth.py          # Instagram authentication & session management
│   ├── fetcher.py       # Data fetching (Instagrapi + Selenium fallback)
│   ├── analyzer.py      # Bot detection ML + rule engine
│   ├── exporter.py      # CSV / JSON / PDF export
│   ├── dashboard.py     # Streamlit web UI
│   ├── api.py           # FastAPI REST backend
│   └── cli.py           # Typer CLI
├── tests/
│   ├── test_auth.py
│   ├── test_fetcher.py
│   ├── test_analyzer.py
│   └── test_exporter.py
├── scripts/
│   └── batch_analyze.py
├── .github/
│   └── workflows/
│       └── ci.yml
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
├── .env.example
├── .gitignore
├── LICENSE
├── CONTRIBUTING.md
└── README.md
```

---

## 🤖 Bot Detection Logic

The analyzer uses a multi-signal approach:

| Signal | Weight | Description |
|--------|--------|-------------|
| Engagement Rate | 30% | Likes+Comments / Followers (< 1% flagged) |
| Follower Ratio | 20% | Following >> Followers = suspicious |
| Bio Quality | 15% | Generic/empty bio patterns |
| Post Frequency | 15% | No posts or extreme posting |
| Comment Sentiment | 10% | Generic spam comments detected |
| Account Age | 10% | Very new accounts with many followers |

Accounts scoring > 70 are classified as **Likely Bot**.
Accounts scoring 40–70 are **Suspicious**.
Below 40 are **Likely Real**.

---

## ⚠️ Disclaimer

> **IMPORTANT**: This tool uses Instagram's **unofficial/private APIs** which violates Instagram's Terms of Service. Use at your own risk.
>
> - Your account **may be temporarily or permanently banned**
> - Use a **dedicated/throwaway account** for authentication
> - Respect **rate limits** — the tool enforces delays automatically
> - Do **not** use this to harass, stalk, or harm individuals
> - The authors are **not responsible** for any account bans or legal issues
> - This tool is for **educational and research purposes only**
>
> Instagram actively detects automation. Use proxies and realistic delays.

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

```bash
# Run tests
pytest tests/ -v

# Lint
ruff check src/
black src/ --check
```

---

## 📄 License

MIT License — see [LICENSE](LICENSE)

---

<div align="center">
Made with ❤️ for ethical research use only
</div>
