import json
import os
import re
from datetime import datetime
from urllib.parse import urlparse, urlunparse
import requests
from database import init_db, save_job

SEEN_JOBS_FILE = "seen_jobs.json"


def load_seen_urls():
    if os.path.exists(SEEN_JOBS_FILE):
        with open(SEEN_JOBS_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen_urls(new_urls):
    existing = load_seen_urls()
    updated = sorted(existing | new_urls)
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(updated, f, indent=2)


# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────

GREENHOUSE_BOARDS = {
    # Fintech
    "Stripe":     "stripe",
    "Affirm":     "affirm",
    "Brex":       "brex",
    "Chime":      "chime",
    "Ramp":       "rampnetwork",
    "Robinhood":  "robinhood",
    "Coinbase":   "coinbase",
    "Block":      "block",
    "Navan":      "tripactions",
    # Consumer / Marketplace
    "Airbnb":     "airbnb",
    "DoorDash":   "doordashusa",
    "Instacart":  "instacart",
    "Duolingo":   "duolingo",
    "Lyft":       "lyft",
    "SpaceX":     "spacex",
    # AI / ML
    "Anthropic":  "anthropic",
    "Scale AI":   "scaleai",
    "Glean":      "gleanwork",
    "Databricks": "databricks",
    # Data / Dev Tools
    "Datadog":    "datadog",
    "Cloudflare": "cloudflare",
    "MongoDB":    "mongodb",
    "Fivetran":   "fivetran",
    "Okta":       "okta",
    # Productivity / Design
    "Asana":      "asana",
    "Figma":      "figma",
    # Quant / HFT
    "Optiver":    "optiver",
}

LEVER_BOARDS = {
    "Plaid":     "plaid",
    "Palantir":  "palantir",
    "Spotify":   "spotify",
}

ASHBY_BOARDS = {
    "OpenAI":     "openai",
    "Perplexity": "perplexity",
    "Notion":     "notion",
    "Confluent":  "confluent",
    "Hopper":     "hopper",
}

# Title must contain at least one of these — prevents off-topic jobs sneaking in
# via a stray keyword mention in the description.
TITLE_KEYWORDS = [
    "machine learning",
    "data scientist",
    "data science",
    "ai engineer",
    "ml engineer",
    "artificial intelligence",
    "deep learning",
    "nlp",
    "large language model",
    "llm",
    "applied scientist",
    "applied ml",
    "computer vision",
    "analytics engineer",
]

EXCLUDE_KEYWORDS = [
    "senior",
    "staff",
    "principal",
    "director",
    "manager",
    "leader",
]


# A job is US-eligible only if its location matches one of these. We match on
# word boundaries (see US_RE) instead of plain substring, so "us" no longer
# matches "aUStralia". "remote" stays on the list on purpose — anything foreign
# that still slips through (e.g. "Remote - Canada") is caught by the LLM
# eligibility check downstream.
US_INDICATORS = [
    "united states", "usa", "us", "remote",
    "new york", "nyc", "san francisco", "bay area", "san jose", "palo alto",
    "mountain view", "sunnyvale", "seattle", "bellevue", "redmond",
    "los angeles", "san diego", "chicago", "boston", "cambridge",
    "austin", "dallas", "houston", "denver", "atlanta", "miami",
    "washington", "philadelphia", "phoenix", "portland", "pittsburgh",
    "detroit", "minneapolis", "nashville", "raleigh", "salt lake",
]

# Word-boundary match so "us" matches "Remote, US" but not "aUStralia".
US_RE = re.compile(
    r"\b(" + "|".join(re.escape(x) for x in US_INDICATORS) + r")\b",
    re.IGNORECASE,
)

HEADERS = {
    # Makes HTTP requests look like a real Chrome browser so servers don't reject them.
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ──────────────────────────────────────────────
# FILTERING (shared by all scrapers)
# ──────────────────────────────────────────────

def normalize_url(url):
    """Strip query params so tracking variants dedup correctly."""
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))


def passes_filters(title, location):
    if not US_RE.search(location):
        return False
    title_lower = title.lower()
    if not any(kw in title_lower for kw in TITLE_KEYWORDS):
        return False
    if any(kw in title_lower for kw in EXCLUDE_KEYWORDS):
        return False
    return True


# ──────────────────────────────────────────────
# GREENHOUSE
# ──────────────────────────────────────────────

def scrape_greenhouse(company_name, board_slug):
    """Scrape a Greenhouse job board via their public JSON API."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_slug}/jobs?content=true"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    raw_jobs = resp.json().get("jobs", [])
    print(f"  Fetched {len(raw_jobs)} total from {company_name} (Greenhouse)")

    jobs = []
    for j in raw_jobs:
        title = j.get("title", "")
        location = j.get("location", {}).get("name", "")
        description = (j.get("content") or "")
        if not passes_filters(title, location):
            continue
        jobs.append({
            "title": title,
            "company": company_name,
            "url": j.get("absolute_url", ""),
            "location": location,
            "date_posted": (j.get("updated_at") or "")[:10],
            "description": description[:3000],
        })
    return jobs


# ──────────────────────────────────────────────
# LEVER
# ──────────────────────────────────────────────

def scrape_lever(company_name, board_slug):
    """Scrape a Lever job board via their public JSON API."""
    url = f"https://api.lever.co/v0/postings/{board_slug}?mode=json"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    raw_jobs = resp.json()
    print(f"  Fetched {len(raw_jobs)} total from {company_name} (Lever)")

    jobs = []
    for j in raw_jobs:
        title = j.get("text", "")
        categories = j.get("categories", {})
        location = categories.get("location", "")
        description = j.get("descriptionPlain", "")
        job_url = j.get("hostedUrl", "")
        created_ms = j.get("createdAt")
        date_posted = datetime.fromtimestamp(created_ms / 1000).strftime("%Y-%m-%d") if created_ms else ""
        if not passes_filters(title, location):
            continue
        jobs.append({
            "title": title,
            "company": company_name,
            "url": normalize_url(job_url),
            "location": location,
            "date_posted": date_posted,
            "description": description[:3000],
        })
    return jobs


# ──────────────────────────────────────────────
# ASHBY
# ──────────────────────────────────────────────

def scrape_ashby(company_name, board_slug):
    """Scrape an Ashby job board via their public JSON API."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board_slug}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    raw_jobs = resp.json().get("jobs", [])
    print(f"  Fetched {len(raw_jobs)} total from {company_name} (Ashby)")

    jobs = []
    for j in raw_jobs:
        title = j.get("title", "")
        location = j.get("location", "")
        # Fall back to country-level address if location string is empty
        if not location:
            addr = j.get("address", {}).get("postalAddress", {})
            location = addr.get("addressLocality") or addr.get("addressRegion") or addr.get("addressCountry") or ""
        description = j.get("descriptionPlain", "")
        job_url = j.get("jobUrl", "")
        date_posted = (j.get("publishedAt") or "")[:10]
        if not passes_filters(title, location):
            continue
        jobs.append({
            "title": title,
            "company": company_name,
            "url": normalize_url(job_url),
            "location": location,
            "date_posted": date_posted,
            "description": description[:3000],
        })
    return jobs


# ──────────────────────────────────────────────
# PRINT HELPER
# ──────────────────────────────────────────────

def print_job(job):
    print(f"\n  Title:       {job['title']}")
    print(f"  Company:     {job['company']}")
    print(f"  Location:    {job['location']}")
    print(f"  URL:         {job['url']}")
    print(f"  {'-' * 60}")


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    init_db()
    all_jobs = []

    for company, slug in GREENHOUSE_BOARDS.items():
        print(f"\nScraping {company} (Greenhouse)...")
        try:
            jobs = scrape_greenhouse(company, slug)
            print(f"  {len(jobs)} matched after filtering")
            all_jobs.extend(jobs)
        except Exception as e:
            print(f"  WARNING: {company} Greenhouse failed: {e}")

    for company, slug in LEVER_BOARDS.items():
        print(f"\nScraping {company} (Lever)...")
        try:
            jobs = scrape_lever(company, slug)
            print(f"  {len(jobs)} matched after filtering")
            all_jobs.extend(jobs)
        except Exception as e:
            print(f"  WARNING: {company} Lever failed: {e}")

    for company, slug in ASHBY_BOARDS.items():
        print(f"\nScraping {company} (Ashby)...")
        try:
            jobs = scrape_ashby(company, slug)
            print(f"  {len(jobs)} matched after filtering")
            all_jobs.extend(jobs)
        except Exception as e:
            print(f"  WARNING: {company} Ashby failed: {e}")

    seen_urls = load_seen_urls()
    new_jobs = [j for j in all_jobs if j["url"] not in seen_urls]
    already_seen = len(all_jobs) - len(new_jobs)

    print(f"\n{'=' * 60}")
    print(f"TOTAL MATCHES: {len(all_jobs)} jobs across all sources")
    print(f"  Already seen in previous runs: {already_seen}")
    print(f"  New this run: {len(new_jobs)}")
    print(f"{'=' * 60}")

    saved = 0
    skipped = 0
    for job in new_jobs:
        print_job(job)
        if save_job(job):
            saved += 1
        else:
            skipped += 1

    print(f"\nSaved {saved} new jobs, skipped {skipped} duplicates")


if __name__ == "__main__":
    main()
