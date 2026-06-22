"""
main.py — runs the full pipeline:
  1. Scrape new jobs from all sources
  2. Score unscored jobs with GPT-4o-mini
  3. Email only jobs not seen in previous runs
"""

import sys

from scraper import main as run_scraper, load_seen_urls, save_seen_urls
from scorer import main as run_scorer
from emailer import send_digest
from database import get_top_jobs_today


def main():
    # ── Step 1: Scrape ───────────────────────────
    print("=" * 60)
    print("STEP 1: Scraping jobs")
    print("=" * 60)
    try:
        run_scraper()
    except Exception as e:
        print(f"ERROR: Scraper crashed: {e}")
        sys.exit(1)

    # ── Step 2: Score ────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 2: Scoring jobs")
    print("=" * 60)
    try:
        run_scorer()
    except Exception as e:
        print(f"ERROR: Scorer crashed: {e}")
        sys.exit(1)

    # ── Step 3: Email only new jobs ───────────────
    print("\n" + "=" * 60)
    print("STEP 3: Sending email digest")
    print("=" * 60)

    seen_urls = load_seen_urls()
    all_jobs_today = get_top_jobs_today(n=50)
    new_jobs = [j for j in all_jobs_today if j["url"] not in seen_urls and j['score'] >= 60]

    if not new_jobs:
        print("No new jobs since last run — skipping email.")
        return

    top_new = new_jobs[:5]
    print(f"  {len(new_jobs)} new jobs found, emailing top {len(top_new)}:")
    for job in top_new:
        print(f"    {job['score']}/100 — {job['title']} at {job['company']}")

    try:
        send_digest(top_new)
    except Exception as e:
        print(f"ERROR: Email failed: {e}")
        sys.exit(1)

    # Mark all today's jobs as seen so they don't get re-emailed
    save_seen_urls({j["url"] for j in all_jobs_today})
    print("\nPipeline complete.")


if __name__ == "__main__":
    main()
