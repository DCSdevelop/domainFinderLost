#!/usr/bin/env python3
"""
Domain Checker Tool
===================
Checks domain availability, parking status, and sale status for historical
domains. Performs HTTP probing, content analysis, and WHOIS lookups to
determine each domain's current state and provide acquisition recommendations.
"""

import argparse
import json
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from threading import Lock
from urllib.parse import urlparse

import requests
import whois
from bs4 import BeautifulSoup
from tqdm import tqdm

from domain_lists import DOMAINS_BY_YEAR

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

REQUEST_TIMEOUT = 15  # seconds
MAX_RETRIES = 2
RATE_LIMIT_DELAY = 0.5  # seconds between requests per worker

PARKED_KEYWORDS = [
    "buy this domain",
    "this domain is for sale",
    "domain is for sale",
    "domain may be for sale",
    "parked free",
    "parked by",
    "parked domain",
    "domain parking",
    "this webpage was generated",
    "is available for purchase",
    "make an offer",
    "purchase this domain",
    "acquire this domain",
    "domain for sale",
    "this domain name",
    "get this domain",
]

SALE_PLATFORMS = [
    "godaddy",
    "sedo",
    "afternic",
    "dan.com",
    "hugedomains",
    "namecheap",
    "flippa",
    "squadhelp",
    "brandpa",
    "atom.com",
    "undeveloped",
    "domainagents",
    "buy.it",
    "bodis",
]

# Known-active domains that may block HTTP probes (geo-restrictions, bot
# protection, etc.). These will always be classified as "active" even if
# our probe fails, to prevent false "parked" classifications.
KNOWN_ACTIVE_DOMAINS = {
    "ebay.com", "baidu.com", "washingtonpost.com", "snap.com",
    "about.com", "realplayer.com",
}

HIGH_VALUE_KEYWORDS = [
    "tech", "ai", "cloud", "data", "cyber", "net", "web", "app", "code",
    "dev", "digital", "smart", "auto", "pay", "fin", "bank", "cash", "money",
    "crypto", "trade", "invest", "fund", "loan", "credit", "insurance",
    "social", "chat", "meet", "link", "share", "connect", "hub", "live",
    "stream", "video", "media", "news", "health", "med", "care", "fit",
    "shop", "store", "buy", "deal", "market", "sale",
    "game", "play", "bet", "win", "sport",
    "travel", "trip", "fly", "hotel", "book",
    "food", "eat", "cook", "recipe",
    "learn", "edu", "study", "course", "tutor",
    "job", "hire", "work", "career", "talent",
    "home", "house", "real", "rent", "property",
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Global rate-limit lock (per-worker delays handled inside worker)
_rate_lock = Lock()


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _safe_str(value) -> str | None:
    """Convert a value to string safely, handling lists and None."""
    if value is None:
        return None
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value)


def _safe_date(value) -> str | None:
    """Convert a date-like value to ISO date string."""
    if value is None:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)


def _safe_list(value) -> list:
    """Ensure a value is a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v).lower() for v in value]
    return [str(value)]


# ---------------------------------------------------------------------------
# Build year-to-domain and domain-to-years mappings
# ---------------------------------------------------------------------------

def build_domain_index(
    domains_by_year: dict[int, list[str]],
    filter_year: int | None = None,
    quick: bool = False,
) -> tuple[list[str], dict[str, list[int]]]:
    """
    Build a deduplicated domain list and a mapping of domain -> years it appeared.

    Parameters
    ----------
    domains_by_year : dict mapping year (int) to list of domain strings
    filter_year : optional single year to restrict to
    quick : if True, only take first 5 domains per year

    Returns
    -------
    (unique_domains, domain_years) where domain_years maps each domain to its
    list of years.
    """
    domain_years: dict[str, list[int]] = {}

    years = [filter_year] if filter_year else sorted(domains_by_year.keys())

    for year in years:
        domains = domains_by_year.get(year, [])
        if quick:
            domains = domains[:5]
        for domain in domains:
            domain = domain.strip().lower()
            if not domain:
                continue
            domain_years.setdefault(domain, []).append(year)

    # Sort years for each domain
    for d in domain_years:
        domain_years[d] = sorted(set(domain_years[d]))

    unique_domains = sorted(domain_years.keys())
    return unique_domains, domain_years


# ---------------------------------------------------------------------------
# HTTP probing
# ---------------------------------------------------------------------------

def probe_http(domain: str) -> dict:
    """
    Perform an HTTP GET against the domain and analyse the response.

    Returns a dict with keys:
        http_status_code, page_title, body_text, redirect_url,
        is_parked, is_for_sale, sale_platform, final_url, error
    """
    result = {
        "http_status_code": None,
        "page_title": None,
        "body_text": "",
        "redirect_url": None,
        "is_parked": False,
        "is_for_sale": False,
        "sale_platform": None,
        "final_url": None,
        "error": None,
    }

    urls_to_try = [f"https://{domain}", f"http://{domain}"]

    for url in urls_to_try:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.get(
                    url,
                    timeout=REQUEST_TIMEOUT,
                    headers={"User-Agent": USER_AGENT},
                    allow_redirects=True,
                )
                result["http_status_code"] = resp.status_code
                result["final_url"] = resp.url

                # Check for cross-domain redirect
                original_domain = domain.lower()
                final_domain = urlparse(resp.url).netloc.lower()
                # Strip www. for comparison
                clean_original = original_domain.removeprefix("www.")
                clean_final = final_domain.removeprefix("www.")
                if clean_final != clean_original:
                    result["redirect_url"] = resp.url

                # Parse HTML
                if resp.status_code == 200 and resp.text:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    title_tag = soup.find("title")
                    if title_tag and title_tag.string:
                        result["page_title"] = title_tag.string.strip()[:200]

                    body_text = soup.get_text(separator=" ", strip=True).lower()
                    # Keep a limited portion for analysis
                    result["body_text"] = body_text[:5000]

                    # Detect parked / for-sale pages
                    _analyse_page_content(result, body_text, resp.text.lower())

                return result

            except requests.exceptions.SSLError:
                # If HTTPS fails with SSL error, try HTTP
                if url.startswith("https://"):
                    break  # break retry loop, move to http
                result["error"] = "SSL error"

            except requests.exceptions.ConnectionError:
                if attempt == MAX_RETRIES:
                    if url == urls_to_try[-1]:
                        result["error"] = "Connection refused"
                    else:
                        break  # try next URL scheme
                time.sleep(1)

            except requests.exceptions.Timeout:
                if attempt == MAX_RETRIES:
                    if url == urls_to_try[-1]:
                        result["error"] = "Timeout"
                    else:
                        break
                time.sleep(1)

            except requests.exceptions.RequestException as exc:
                result["error"] = str(exc)[:200]
                if attempt == MAX_RETRIES and url == urls_to_try[-1]:
                    return result
                if attempt == MAX_RETRIES:
                    break
                time.sleep(1)

    return result


def _analyse_page_content(result: dict, body_text: str, raw_html: str) -> None:
    """Detect parked and for-sale signals in page content.

    Uses a scoring approach to avoid false positives on legitimate sites
    that may contain platform names in ads or third-party scripts.
    """
    stripped_len = len(body_text.replace(" ", ""))
    is_thin_page = stripped_len < 2000

    # If the page has substantial content (>5000 chars stripped) AND a real
    # title that doesn't mention "domain" or "parked", treat it as a real site.
    # This prevents false positives from platform keywords in ads/scripts.
    title = (result.get("page_title") or "").lower()
    is_real_site = (
        stripped_len > 5000
        and title
        and not any(w in title for w in ["domain", "parked", "for sale", "coming soon"])
    )
    if is_real_site:
        return  # Skip parked/for-sale analysis entirely for real sites

    # --- Parked keyword detection ---
    parked_hits = sum(1 for kw in PARKED_KEYWORDS if kw in body_text)
    if parked_hits >= 2 or (parked_hits >= 1 and is_thin_page):
        result["is_parked"] = True

    # --- Sale platform detection ---
    # Only on thin pages to avoid false positives from ads/scripts.
    platform_found = None
    for platform in SALE_PLATFORMS:
        if platform in body_text:
            platform_found = platform
            break
    if platform_found and is_thin_page:
        result["is_for_sale"] = True
        result["sale_platform"] = platform_found

    # --- Explicit for-sale phrases (strong signal) ---
    sale_phrases = [
        "buy this domain", "purchase this domain",
        "make an offer on this domain", "acquire this domain",
        "this domain is for sale", "domain is available for purchase",
        "domain may be for sale",
    ]
    for phrase in sale_phrases:
        if phrase in body_text:
            result["is_for_sale"] = True
            break

    # If for-sale, also mark as parked
    if result["is_for_sale"]:
        result["is_parked"] = True

    # Detect minimal placeholder / parking pages
    if stripped_len < 150 and result["page_title"]:
        title_lower = result["page_title"].lower()
        if any(kw in title_lower for kw in ["parked", "for sale", "domain", "coming soon"]):
            result["is_parked"] = True


# ---------------------------------------------------------------------------
# WHOIS lookup
# ---------------------------------------------------------------------------

def lookup_whois(domain: str) -> dict:
    """
    Query WHOIS for a domain and return structured data.

    Returns a dict with keys: registrar, creation_date, expiration_date,
    name_servers, registrant, registrant_email, raw_error
    """
    info = {
        "registrar": None,
        "creation_date": None,
        "expiration_date": None,
        "name_servers": [],
        "registrant": None,
        "registrant_email": None,
    }

    try:
        w = whois.whois(domain)

        if w is None or (isinstance(w, dict) and not w):
            return info

        info["registrar"] = _safe_str(getattr(w, "registrar", None))
        info["creation_date"] = _safe_date(getattr(w, "creation_date", None))
        info["expiration_date"] = _safe_date(getattr(w, "expiration_date", None))
        info["name_servers"] = _safe_list(getattr(w, "name_servers", None))

        # Registrant info - try multiple fields
        registrant = (
            getattr(w, "org", None)
            or getattr(w, "name", None)
            or getattr(w, "registrant_name", None)
        )
        info["registrant"] = _safe_str(registrant)

        email = (
            getattr(w, "emails", None)
            or getattr(w, "registrant_email", None)
        )
        if isinstance(email, list):
            info["registrant_email"] = email[0] if email else None
        else:
            info["registrant_email"] = _safe_str(email)

    except whois.parser.PywhoisError:
        # Domain likely not registered
        pass
    except Exception as exc:
        logger.debug("WHOIS error for %s: %s", domain, exc)

    return info


# ---------------------------------------------------------------------------
# Domain status determination
# ---------------------------------------------------------------------------

def determine_status(http_result: dict, whois_info: dict, domain: str = "") -> str:
    """
    Determine the domain's status category.

    Returns one of: active, parked, for_sale, redirect, expired, available
    """
    # Known-active domains that block our HTTP probes
    if domain in KNOWN_ACTIVE_DOMAINS:
        return "active"

    has_http = http_result["http_status_code"] is not None

    # Check for redirect first
    if http_result.get("redirect_url"):
        return "redirect"

    # For-sale takes priority over generic parked
    if http_result.get("is_for_sale"):
        return "for_sale"

    if http_result.get("is_parked"):
        return "parked"

    # If HTTP responded with a real page
    if has_http and http_result["http_status_code"] in range(200, 400):
        return "active"

    # No HTTP response -- check WHOIS
    has_whois = any(
        whois_info.get(k)
        for k in ("registrar", "creation_date", "expiration_date", "name_servers")
    )

    expiration = whois_info.get("expiration_date")
    if expiration:
        try:
            exp_date = datetime.fromisoformat(str(expiration))
            if exp_date < datetime.now():
                return "expired"
            elif not has_http:
                # Domain is registered and not expired, but no website.
                # This means it's being held/parked (no active content).
                return "parked"
        except (ValueError, TypeError):
            pass

    # No WHOIS record at all
    if not has_whois and not has_http:
        return "available"

    # Has WHOIS but no expiration date and no HTTP — likely expired or holding
    if not has_http and has_whois:
        return "expired"

    return "active"


# ---------------------------------------------------------------------------
# Recommendation scoring
# ---------------------------------------------------------------------------

def score_domain(
    domain: str,
    years_popular: list[int],
    status: str,
    whois_info: dict,
) -> dict:
    """
    Score a domain 1-10 and provide a recommendation.

    Scoring factors:
      - Domain age (older = higher)
      - Domain length (shorter = higher)
      - .com TLD bonus
      - Historical popularity (more years = higher)
      - High-value keyword presence
      - Brandability (length, pronounceability heuristic)
    """
    score = 5.0  # base
    reasons = []

    # --- Domain age ---
    creation_date_str = whois_info.get("creation_date")
    domain_age_years = 0
    if creation_date_str:
        try:
            creation = datetime.fromisoformat(str(creation_date_str))
            domain_age_years = (datetime.now() - creation).days / 365.25
            if domain_age_years >= 20:
                score += 2.0
                reasons.append(f"Very old domain ({int(domain_age_years)} years)")
            elif domain_age_years >= 10:
                score += 1.5
                reasons.append(f"Established domain ({int(domain_age_years)} years)")
            elif domain_age_years >= 5:
                score += 0.5
                reasons.append(f"Moderate age ({int(domain_age_years)} years)")
        except (ValueError, TypeError):
            pass

    # --- Domain length ---
    name_part = domain.split(".")[0]
    name_len = len(name_part)
    if name_len <= 3:
        score += 2.0
        reasons.append(f"Ultra-short name ({name_len} chars)")
    elif name_len <= 5:
        score += 1.5
        reasons.append(f"Short name ({name_len} chars)")
    elif name_len <= 8:
        score += 0.5
        reasons.append("Concise name")
    elif name_len >= 15:
        score -= 1.0
        reasons.append("Long name reduces memorability")

    # --- TLD bonus ---
    if domain.endswith(".com"):
        score += 1.0
        reasons.append(".com TLD premium")
    elif domain.endswith((".io", ".ai", ".co")):
        score += 0.5
        reasons.append(f"Desirable TLD ({domain.split('.')[-1]})")

    # --- Historical popularity ---
    year_count = len(years_popular)
    if year_count >= 5:
        score += 1.5
        reasons.append(f"Appeared in {year_count} years of top lists")
    elif year_count >= 3:
        score += 1.0
        reasons.append(f"Appeared in {year_count} years of top lists")
    elif year_count >= 2:
        score += 0.5
        reasons.append(f"Appeared in {year_count} years of top lists")

    # --- High-value keywords ---
    name_lower = name_part.lower()
    matched_keywords = [kw for kw in HIGH_VALUE_KEYWORDS if kw in name_lower]
    if matched_keywords:
        keyword_bonus = min(len(matched_keywords) * 0.5, 1.5)
        score += keyword_bonus
        reasons.append(f"High-value keywords: {', '.join(matched_keywords[:3])}")

    # --- Brandability heuristic ---
    # Simple heuristic: reasonable length, contains vowels, no excessive hyphens
    vowel_ratio = sum(1 for c in name_lower if c in "aeiou") / max(len(name_lower), 1)
    hyphen_count = name_lower.count("-")
    digit_count = sum(1 for c in name_lower if c.isdigit())

    if 0.2 <= vowel_ratio <= 0.6 and hyphen_count == 0 and digit_count == 0:
        score += 0.5
        reasons.append("Good brandability (pronounceable, clean)")
    elif hyphen_count >= 2 or digit_count >= 3:
        score -= 0.5
        reasons.append("Low brandability (hyphens/digits)")

    # --- Status adjustment ---
    if status == "available":
        score += 0.5
        reasons.append("Potentially available for registration")
    elif status == "for_sale":
        reasons.append("Listed for sale -- acquisition possible")
    elif status == "active":
        score -= 0.5
        reasons.append("Currently active -- acquisition unlikely")

    # Clamp score
    final_score = max(1, min(10, round(score)))

    # Estimate value range
    estimated_value = _estimate_value(final_score, domain_age_years, name_len, status)

    if not reasons:
        reasons.append("Standard domain")

    return {
        "score": final_score,
        "reason": "; ".join(reasons),
        "estimated_value": estimated_value,
    }


def _estimate_value(score: int, age_years: float, name_len: int, status: str) -> str:
    """Rough value estimate based on scoring factors."""
    if status == "available":
        return "$10-$15 (registration cost)"

    ranges = {
        1: "$0-$100",
        2: "$100-$500",
        3: "$500-$1,000",
        4: "$1,000-$2,500",
        5: "$2,500-$5,000",
        6: "$5,000-$10,000",
        7: "$10,000-$25,000",
        8: "$25,000-$50,000",
        9: "$50,000-$100,000",
        10: "$100,000+",
    }
    return ranges.get(score, "$1,000-$5,000")


# ---------------------------------------------------------------------------
# Single-domain check (worker function)
# ---------------------------------------------------------------------------

def check_domain(domain: str, years_popular: list[int]) -> dict:
    """
    Perform all checks on a single domain and return a result dict.
    """
    result = {
        "domain": domain,
        "years_popular": years_popular,
        "status": "unknown",
        "http_status_code": None,
        "redirect_url": None,
        "page_title": None,
        "is_parked": False,
        "is_for_sale": False,
        "sale_platform": None,
        "whois": {},
        "recommendation": {},
        "checked_at": _now_iso(),
    }

    # Rate limiting
    with _rate_lock:
        time.sleep(RATE_LIMIT_DELAY)

    # Step 1: HTTP probe
    http_result = probe_http(domain)

    result["http_status_code"] = http_result["http_status_code"]
    result["redirect_url"] = http_result["redirect_url"]
    result["page_title"] = http_result["page_title"]
    result["is_parked"] = http_result["is_parked"]
    result["is_for_sale"] = http_result["is_for_sale"]
    result["sale_platform"] = http_result["sale_platform"]

    # Step 2: WHOIS lookup (if no HTTP response or if parked/for-sale)
    whois_info = {}
    needs_whois = (
        http_result["http_status_code"] is None
        or http_result["is_parked"]
        or http_result["is_for_sale"]
        or http_result.get("error")
    )
    if needs_whois:
        whois_info = lookup_whois(domain)
    else:
        # Still do a quick WHOIS for scoring purposes (age, registrar)
        try:
            whois_info = lookup_whois(domain)
        except Exception:
            whois_info = {}

    result["whois"] = whois_info

    # Step 3: Determine status
    result["status"] = determine_status(http_result, whois_info, domain)

    # Step 4: Score and recommend
    result["recommendation"] = score_domain(
        domain, years_popular, result["status"], whois_info
    )

    result["checked_at"] = _now_iso()

    return result


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def run_checker(
    filter_year: int | None = None,
    max_workers: int = 10,
    output_file: str = "domain_results.json",
    quick: bool = False,
) -> None:
    """
    Main entry point: build domain list, check all domains in parallel,
    write results to JSON.
    """
    logger.info("Building domain index...")
    unique_domains, domain_years = build_domain_index(
        DOMAINS_BY_YEAR,
        filter_year=filter_year,
        quick=quick,
    )

    total = len(unique_domains)
    if total == 0:
        logger.warning("No domains to check. Verify domain_lists.py and filters.")
        return

    logger.info(
        "Checking %d unique domains with %d workers%s...",
        total,
        max_workers,
        " (quick mode)" if quick else "",
    )

    results: list[dict] = []
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_domain = {
            executor.submit(check_domain, domain, domain_years[domain]): domain
            for domain in unique_domains
        }

        with tqdm(total=total, desc="Checking domains", unit="domain") as pbar:
            for future in as_completed(future_to_domain):
                domain = future_to_domain[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as exc:
                    logger.error("Unhandled error checking %s: %s", domain, exc)
                    errors.append(domain)
                    results.append({
                        "domain": domain,
                        "years_popular": domain_years[domain],
                        "status": "error",
                        "http_status_code": None,
                        "redirect_url": None,
                        "page_title": None,
                        "is_parked": False,
                        "is_for_sale": False,
                        "sale_platform": None,
                        "whois": {},
                        "recommendation": {"score": 1, "reason": f"Check failed: {exc}", "estimated_value": "Unknown"},
                        "checked_at": _now_iso(),
                    })
                finally:
                    pbar.update(1)

    # Sort results by recommendation score descending, then domain name
    results.sort(key=lambda r: (-r.get("recommendation", {}).get("score", 0), r["domain"]))

    # Build output
    output = {
        "generated_at": _now_iso(),
        "total_domains": len(results),
        "summary": _build_summary(results),
        "results": results,
    }

    # Write JSON
    output_path = output_file
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    logger.info("Results written to %s", output_path)

    # Print summary
    _print_summary(output["summary"], errors)


def _build_summary(results: list[dict]) -> dict:
    """Build a summary breakdown of results."""
    summary: dict[str, int] = {
        "active": 0,
        "parked": 0,
        "for_sale": 0,
        "expired": 0,
        "available": 0,
        "redirect": 0,
        "error": 0,
        "unknown": 0,
    }
    for r in results:
        status = r.get("status", "unknown")
        summary[status] = summary.get(status, 0) + 1
    return summary


def _print_summary(summary: dict, errors: list[str]) -> None:
    """Print a human-readable summary to stdout."""
    print("\n" + "=" * 60)
    print("DOMAIN CHECK SUMMARY")
    print("=" * 60)
    total = sum(summary.values())
    print(f"  Total checked:  {total}")
    print(f"  Active:         {summary.get('active', 0)}")
    print(f"  Parked:         {summary.get('parked', 0)}")
    print(f"  For Sale:       {summary.get('for_sale', 0)}")
    print(f"  Redirect:       {summary.get('redirect', 0)}")
    print(f"  Expired:        {summary.get('expired', 0)}")
    print(f"  Available:      {summary.get('available', 0)}")
    print(f"  Errors:         {summary.get('error', 0)}")
    print("=" * 60)

    interesting = summary.get("for_sale", 0) + summary.get("available", 0) + summary.get("expired", 0)
    if interesting > 0:
        print(f"\n  ** {interesting} domains may be acquirable! Check the JSON output for details. **")

    if errors:
        print(f"\n  Domains with errors: {', '.join(errors[:10])}")
        if len(errors) > 10:
            print(f"    ... and {len(errors) - 10} more")

    print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Check domain availability, parking status, and sale status.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python checker.py                      # Check all domains\n"
            "  python checker.py --year 2005           # Check only 2005 domains\n"
            "  python checker.py --quick               # Quick test (5 per year)\n"
            "  python checker.py --workers 20 -o out.json\n"
        ),
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Only check domains from this specific year",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Number of concurrent workers (default: 10)",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="domain_results.json",
        help="Output JSON file path (default: domain_results.json)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: only check first 5 domains per year",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Main entry point."""
    args = parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate year if provided
    if args.year is not None:
        if args.year not in DOMAINS_BY_YEAR:
            available_years = sorted(DOMAINS_BY_YEAR.keys())
            logger.error(
                "Year %d not found in domain lists. Available years: %s",
                args.year,
                available_years,
            )
            sys.exit(1)

    # Clamp workers
    workers = max(1, min(args.workers, 50))

    run_checker(
        filter_year=args.year,
        max_workers=workers,
        output_file=args.output,
        quick=args.quick,
    )


if __name__ == "__main__":
    main()
