import re
import time
from urllib.parse import urlparse, urlunparse
import requests
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from database import init_db, save_job

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────

GREENHOUSE_BOARDS = {
    "Stripe": "stripe",
    "Datadog": "datadog",
}

SEARCH_QUERIES = [
    "machine learning engineer",
    "data scientist",
    "AI engineer",
]

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
    "research scientist",
    "research engineer",
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
]

# Catches "4+ years" (explicit plus — unambiguous) OR "4 years of/in experience/work/industry"
EXPERIENCE_RE = re.compile(
    r'\b([4-9]|\d{2,})\s*\+\s*years?\b'
    r'|\b([4-9]|\d{2,})\s*years?\s*(of\s+)?(experience|exp|work\b|industry\b|professional)',
    re.IGNORECASE,
)

# Catches masters / MS / MBA degree requirements
EDUCATION_RE = re.compile(
    r"\bmaster['\u2019]?s?\s*(degree|of science|of engineering|in\b)"
    r'|\bm\.s\.\b|\bmsc\b|\bms\s+degree\b|\bm\.eng\b'
    r'|\bmba\b'
    r'|\bph\.?d\.?\b|\bdoctorate\b|\bdoctoral\b',
    re.IGNORECASE,
)

# Companies considered a clear step up from JPMorgan Chase for AI/DS roles.
# Matching is case-insensitive substring — "Google LLC" matches "google".
COMPANY_ALLOWLIST = {
    # Big Tech
    "google", "deepmind", "waymo",
    "meta", "facebook",
    "apple",
    "amazon", "aws",
    "microsoft",
    "netflix",
    "uber",
    "airbnb",
    "lyft",
    "linkedin",
    "salesforce",
    "adobe",
    "nvidia",
    "amd",
    "intel",
    "qualcomm",
    "spotify",
    "snap", "snapchat",
    "pinterest",
    "doordash",
    "instacart",
    "shopify",
    "bytedance", "tiktok",
    "tesla",
    "spacex",
    # AI / ML labs
    "openai",
    "anthropic",
    "cohere",
    "mistral",
    "scale ai",
    "hugging face",
    "stability ai",
    "inflection",
    "perplexity",
    "together ai",
    "xai",
    # Data / Cloud / Dev tools
    "snowflake",
    "databricks",
    "palantir",
    "datadog",
    "stripe",
    "twilio",
    "cloudflare",
    "confluent",
    "dbt labs",
    "fivetran",
    "mongodb",
    "elastic",
    "splunk",
    "okta",
    "crowdstrike",
    "palo alto networks",
    "zscaler",
    "block", "square",
    "robinhood",
    "coinbase",
    "asana",
    "notion",
    "figma",
    "canva",
    "servicenow",
    "workday",
    # Quant / HFT (strong ML culture, comp > JPM)
    "two sigma",
    "citadel",
    "jane street",
    "d.e. shaw", "de shaw",
    "renaissance",
    "optiver",
    "tower research",
    "hudson river trading",
    "jump trading",
    "virtu",
}

US_INDICATORS = [
    "us", "usa", "united states", "remote", "new york", "san francisco",
    "seattle", "chicago", "boston", "austin", "denver", "los angeles",
    "new york city", "nyc", "bay area",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ──────────────────────────────────────────────
# FILTERING (shared by all scrapers)
# ──────────────────────────────────────────────

def is_reputable(company):
    """Return True if the company is on the allowlist."""
    c = company.lower()
    return any(term in c for term in COMPANY_ALLOWLIST)


def normalize_url(url):
    """Strip query params so LinkedIn/Indeed tracking variants dedup correctly."""
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))


def passes_filters(title, description, location, company=""):
    if not is_reputable(company):
        return False
    loc = location.lower()
    if not any(ind in loc for ind in US_INDICATORS):
        return False
    title_lower = title.lower()
    # Title must match — prevents off-topic roles sneaking in via description keywords
    if not any(kw in title_lower for kw in TITLE_KEYWORDS):
        return False
    combined = (title + " " + description).lower()
    if any(kw in combined for kw in EXCLUDE_KEYWORDS):
        return False
    if EXPERIENCE_RE.search(combined):
        return False
    if EDUCATION_RE.search(combined):
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
        if not passes_filters(title, description, location, company_name):
            continue
        jobs.append({
            "title": title,
            "company": company_name,
            "url": j.get("absolute_url", ""),
            "location": location,
            "date_posted": (j.get("updated_at") or "")[:10],
            "description": description[:500],
        })
    return jobs


# ──────────────────────────────────────────────
# LINKEDIN (Playwright + stealth)
# ──────────────────────────────────────────────

def scrape_linkedin(page):
    """Scrape LinkedIn public job search using Playwright with stealth."""
    jobs = []
    seen_urls = set()

    for query in SEARCH_QUERIES:
        try:
            url = (
                f"https://www.linkedin.com/jobs/search/"
                f"?keywords={query.replace(' ', '%20')}"
                f"&location=United%20States&f_TPR=r86400"  # last 24h
            )
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector("ul.jobs-search__results-list li", timeout=15000)

            # scroll to load more
            for _ in range(3):
                page.keyboard.press("End")
                time.sleep(1)

            cards = page.query_selector_all("ul.jobs-search__results-list li")
            for card in cards:
                title_el = card.query_selector("h3.base-search-card__title")
                company_el = card.query_selector("h4.base-search-card__subtitle")
                location_el = card.query_selector("span.job-search-card__location")
                link_el = card.query_selector("a.base-card__full-link")

                title = title_el.inner_text().strip() if title_el else ""
                location = location_el.inner_text().strip() if location_el else ""
                job_url = link_el.get_attribute("href") if link_el else ""

                company = company_el.inner_text().strip() if company_el else "Unknown"
                clean_url = normalize_url(job_url) if job_url else ""
                if not title or not clean_url or clean_url in seen_urls:
                    continue
                if not passes_filters(title, "", location, company):
                    continue
                seen_urls.add(clean_url)
                jobs.append({
                    "title": title,
                    "company": company,
                    "url": clean_url,
                    "location": location,
                    "date_posted": "",
                    "description": "",
                })
            time.sleep(2)  # be polite between queries
        except Exception as e:
            print(f"  WARNING: LinkedIn query '{query}' failed: {e}")

    return jobs


# ──────────────────────────────────────────────
# INDEED (Playwright + stealth)
# ──────────────────────────────────────────────

def scrape_indeed(page):
    """Scrape Indeed job search using Playwright with stealth."""
    jobs = []
    seen_urls = set()

    for query in SEARCH_QUERIES:
        try:
            url = (
                f"https://www.indeed.com/jobs"
                f"?q={query.replace(' ', '+')}&l=United+States&fromage=7"  # last 7 days
            )
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector("div.job_seen_beacon", timeout=15000)

            cards = page.query_selector_all("div.job_seen_beacon")
            for card in cards:
                title_el = card.query_selector("h2.jobTitle span")
                company_el = card.query_selector("span[data-testid='company-name']")
                location_el = card.query_selector("div[data-testid='text-location']")
                link_el = card.query_selector("a[id^='job_']")

                title = title_el.inner_text().strip() if title_el else ""
                location = location_el.inner_text().strip() if location_el else ""
                href = link_el.get_attribute("href") if link_el else ""
                job_url = "https://www.indeed.com" + href if href.startswith("/") else href

                company = company_el.inner_text().strip() if company_el else "Unknown"
                clean_url = normalize_url(job_url) if job_url else ""
                if not title or not clean_url or clean_url in seen_urls:
                    continue
                if not passes_filters(title, "", location, company):
                    continue
                seen_urls.add(clean_url)
                jobs.append({
                    "title": title,
                    "company": company,
                    "url": clean_url,
                    "location": location,
                    "date_posted": "",
                    "description": "",
                })
            time.sleep(2)
        except Exception as e:
            print(f"  WARNING: Indeed query '{query}' failed: {e}")

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

    # ── Greenhouse (no browser needed) ──────────
    for company, slug in GREENHOUSE_BOARDS.items():
        print(f"\nScraping {company} (Greenhouse)...")
        try:
            jobs = scrape_greenhouse(company, slug)
            print(f"  {len(jobs)} matched after filtering")
            all_jobs.extend(jobs)
        except Exception as e:
            print(f"  WARNING: {company} Greenhouse failed: {e}")

    # ── Playwright scrapers ──────────────────────
    print("\nStarting browser for LinkedIn and Indeed...")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        print("\nScraping LinkedIn...")
        try:
            jobs = scrape_linkedin(page)
            print(f"  {len(jobs)} matched after filtering")
            all_jobs.extend(jobs)
        except Exception as e:
            print(f"  WARNING: LinkedIn failed: {e}")

        print("\nScraping Indeed...")
        try:
            jobs = scrape_indeed(page)
            print(f"  {len(jobs)} matched after filtering")
            all_jobs.extend(jobs)
        except Exception as e:
            print(f"  WARNING: Indeed failed: {e}")

        browser.close()

    # ── Save results ─────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"TOTAL MATCHES: {len(all_jobs)} jobs across all sources")
    print(f"{'=' * 60}")

    saved = 0
    skipped = 0
    for job in all_jobs:
        print_job(job)
        if save_job(job):
            saved += 1
        else:
            skipped += 1

    print(f"\nSaved {saved} new jobs, skipped {skipped} duplicates")


if __name__ == "__main__":
    main()
