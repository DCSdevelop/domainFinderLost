# Domain Finder — Lost Treasures of the Web

Find historically popular domains (2000-2025) that may be available for acquisition.

## Prerequisites

- Python 3.10+
- pip

## Quick Start

```bash
# 1. Install dependencies (first time only)
./setup.sh

# 2. Run the domain scanner
./scan.sh

# 3. Start the web viewer
./start.sh

# 4. Stop the web viewer
./stop.sh
```

## Manual Usage

### Install Dependencies

```bash
pip3 install -r requirements.txt
```

### Run the Domain Scanner

Full scan (155 domains, ~2.5 minutes):

```bash
python3 checker.py --workers 10
```

Scan a specific year only:

```bash
python3 checker.py --year 2005 --workers 10
```

Quick test mode (5 domains per year):

```bash
python3 checker.py --quick --workers 5
```

Custom output file:

```bash
python3 checker.py --workers 10 -o my_results.json
```

Verbose logging:

```bash
python3 checker.py --workers 10 -v
```

### Scanner CLI Options

| Flag | Description | Default |
|---|---|---|
| `--workers N` | Parallel HTTP/WHOIS workers | 10 |
| `--year YEAR` | Check only domains from this year | all years |
| `--quick` | Test mode, first 5 domains per year | off |
| `-o FILE` | Output JSON file path | domain_results.json |
| `-v` | Verbose debug logging | off |

### Start the Web Viewer

```bash
python3 -m http.server 8090 --directory "$(pwd)"
```

Then open http://localhost:8090 in your browser.

### Stop the Web Viewer

```bash
kill $(lsof -ti:8090)
```

## Project Files

| File | Description |
|---|---|
| `domain_lists.py` | 50 popular domains per year, 2000-2025 (155 unique) |
| `checker.py` | HTTP prober + WHOIS lookup + recommendation scoring |
| `index.html` | Single-file HTML viewer (dark theme, filters, charts) |
| `domain_results.json` | Generated scan results (re-created by scanner) |
| `requirements.txt` | Python dependencies |
| `setup.sh` | One-time dependency install |
| `scan.sh` | Run the domain scanner |
| `start.sh` | Start the web viewer |
| `stop.sh` | Stop the web viewer |

## How It Works

1. **Domain Lists** — Curated lists of the 50 most popular websites for each year from 2000 to 2025, sourced from Alexa, Cloudflare Radar, Similarweb, comScore, and historical archives.

2. **HTTP Probing** — Each domain gets an HTTPS request (falling back to HTTP). The response is analyzed for parked-page signals, for-sale keywords, and content quality.

3. **WHOIS Lookup** — Domains that don't respond or appear inactive get a WHOIS query to find registrar, expiration date, and contact info.

4. **Status Classification**:
   - **Active** — Live website with real content
   - **Parked** — Registered but no website (potential acquisition target)
   - **For Sale** — Explicitly listed for sale
   - **Redirect** — Points to another domain
   - **Expired** — WHOIS shows past expiration
   - **Available** — No WHOIS record found

5. **Recommendation Scoring** (1-10) based on domain age, length, TLD, historical popularity, keyword value, and brandability.

6. **HTML Viewer** — Displays results with filtering, sorting, pie/bar charts, detail modals, CSV export, and clipboard copy.

## Tips

- Run the scanner periodically — domain statuses change over time
- Parked domains with GoDaddy or personal registrars are easier to negotiate than MarkMonitor (corporate brand protection)
- Domains expiring within 6 months may become available if not renewed
- Use the "Score" filter in the web viewer to focus on high-value targets
