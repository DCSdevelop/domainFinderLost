# Domain Finder — Lost Treasures of the Web

> Discover historically popular domains from the internet's golden years (2000-2025) that may now be available for acquisition.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Domains](https://img.shields.io/badge/Domains_Tracked-155-orange)

## What is this?

Every year, websites that were once household names quietly disappear. Their domains — short, brandable, and loaded with SEO history — sit idle, parked by registrars, or waiting for a new owner.

This tool:

1. **Tracks 1,300 entries** across 26 years (50 top domains per year, 2000-2025)
2. **Probes each domain** with HTTP requests to detect if it's still alive, parked, redirected, or for sale
3. **Queries WHOIS** for inactive domains to find registrar, expiration dates, and contact info
4. **Scores and recommends** domains based on age, length, brandability, keyword value, and historical popularity
5. **Displays everything** in a polished dark-theme web interface with filters, charts, and export

### Sample Findings

| Domain | Status | Why it's interesting |
|---|---|---|
| `kazaa.com` | Parked | Legendary P2P app, 5-char .com, GoDaddy registered |
| `metacafe.com` | Parked | Former YouTube competitor, strong video brand |
| `del.icio.us` | Parked | Pioneering bookmarking service, personal registrant |
| `technorati.com` | Parked | Original blog search engine, tech brand equity |
| `musical.ly` | Parked | Pre-TikTok viral video app |
| `geocities.com` | Redirect | Web 1.0 icon, redirects to Yahoo |
| `altavista.com` | Redirect | Early search giant, redirects to Yahoo |

## Quick Start

```bash
git clone https://github.com/DCSdevelop/domainFinderLost.git
cd domainFinderLost

# Install dependencies
./setup.sh

# Scan all domains (~2.5 minutes)
./scan.sh

# Open the web viewer (auto-opens browser)
./start.sh

# When done
./stop.sh
```

## Screenshots

The web viewer includes:

- **Stats dashboard** with status distribution pie chart and domains-by-year bar chart
- **Top Picks** section highlighting the best acquisition targets
- **Filterable results** with card and table views
- **Detail modals** with full WHOIS data and buy/lookup links
- **CSV export** and clipboard copy

## Requirements

- Python 3.10+
- pip
- Internet connection (for HTTP probes and WHOIS lookups)

## Usage

### Shell Scripts

| Script | Description |
|---|---|
| `./setup.sh` | Install Python dependencies (run once) |
| `./scan.sh` | Run the full domain scanner |
| `./scan.sh 20` | Run with 20 parallel workers |
| `./start.sh` | Start web viewer on port 8090 |
| `./start.sh 9000` | Start on custom port |
| `./stop.sh` | Stop the web viewer |

### Python CLI

```bash
# Full scan with 10 workers (default)
python3 checker.py --workers 10

# Scan a single year
python3 checker.py --year 2005

# Quick test (5 domains per year)
python3 checker.py --quick

# Custom output path
python3 checker.py -o results/scan_2026.json

# Verbose logging
python3 checker.py -v
```

### CLI Options

| Flag | Description | Default |
|---|---|---|
| `--workers N` | Number of parallel workers | 10 |
| `--year YEAR` | Scan only one year | All (2000-2025) |
| `--quick` | Test mode, 5 domains per year | Off |
| `-o`, `--output` | Output JSON file path | `domain_results.json` |
| `-v`, `--verbose` | Debug logging | Off |

## How It Works

### 1. Domain Lists (`domain_lists.py`)

Curated lists of the 50 most popular websites per year, compiled from:

- Alexa Top Sites (historical via Wayback Machine)
- Cloudflare Radar Year in Review (2020-2023)
- Similarweb / Semrush top 100 (2024-2025)
- comScore Media Metrix top 50 US web properties
- TIME Magazine "50 Best Websites" annual lists
- Visual Capitalist historical web traffic data

**155 unique domains** tracked, with 71 that were popular pre-2010 but vanished from rankings post-2020.

### 2. HTTP Probing (`checker.py`)

Each domain gets an HTTPS request (falling back to HTTP on SSL errors):

- Follows redirects, detects cross-domain redirects
- Parses HTML with BeautifulSoup to extract title and body text
- Analyzes page content for parked/for-sale signals using keyword detection
- Uses a thin-page heuristic to avoid false positives from ads/scripts on real sites
- Concurrent checking with ThreadPoolExecutor (configurable workers)

### 3. WHOIS Lookup

Domains that fail HTTP probes get a WHOIS query to extract:

- Registrar name
- Creation and expiration dates
- Name servers
- Registrant contact info (when available)

### 4. Status Classification

| Status | Meaning |
|---|---|
| **Active** | Live website serving real content |
| **Parked** | Registered but no website — potential acquisition target |
| **For Sale** | Explicitly listed for sale (detected via page content) |
| **Redirect** | Domain redirects to another site |
| **Expired** | WHOIS shows past expiration date |
| **Available** | No WHOIS record found |

### 5. Recommendation Scoring (1-10)

Domains are scored on:

- **Domain age** — Older domains rank higher (up to +2 for 20+ years)
- **Domain length** — Shorter names rank higher (up to +2 for 3 chars)
- **TLD** — `.com` gets a bonus (+1)
- **Historical popularity** — More years in top lists = higher score
- **Keyword value** — Tech, finance, social, health keywords boost score
- **Brandability** — Pronounceable, no hyphens/digits, good vowel ratio

### 6. Web Viewer (`index.html`)

Single-file HTML application (~75KB) with:

- Dark navy theme with gradient accents
- Stats bar with live counts
- Pie chart (status distribution) and bar chart (domains by year)
- Sticky filter bar: search, status, year, score slider, sort options
- Card view and table view (toggleable)
- Detail modals with full WHOIS and recommendation data
- CSV export and clipboard copy
- Demo mode (works without scan data)

## Project Structure

```
.
├── README.md              # This file
├── INSTRUCTIONS.md        # Detailed usage guide
├── requirements.txt       # Python dependencies
├── domain_lists.py        # 50 domains/year, 2000-2025
├── checker.py             # HTTP + WHOIS checker + scoring
├── index.html             # Web viewer (single file)
├── domain_results.json    # Generated scan results
├── setup.sh               # Install dependencies
├── scan.sh                # Run domain scanner
├── start.sh               # Start web viewer
└── stop.sh                # Stop web viewer
```

## Acquisition Tips

- **GoDaddy / personal registrars** — Domains held here are often individually owned and more negotiable
- **MarkMonitor** — Corporate brand protection registrar (Google, Yahoo, Microsoft). These domains are held by large companies and are unlikely to be sold cheaply
- **Expiring soon** — Domains expiring within 6 months may become available if not renewed. Set calendar reminders
- **Redirect chains** — Domains like `geocities.com` (redirects to Yahoo) or `altavista.com` (redirects to Yahoo Search) indicate corporate ownership but the parent may let them lapse eventually
- **Contact directly** — For parked domains with personal registrant emails, a direct inquiry is often more effective than going through a marketplace

## Disclaimer

This tool is for **research and informational purposes only**. Domain availability and pricing change constantly. Always verify current status through official registrars before making purchase decisions. The recommendation scores are algorithmic estimates, not financial advice.

## License

MIT
