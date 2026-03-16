"""
main.py — runs the full pipeline:
  1. Scrape new jobs from all sources
  2. Score unscored jobs with GPT-4o-mini
  3. Email the top 5 of today's jobs
"""

import sys

from scraper import main as run_scraper
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

    # ── Step 3: Email ────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 3: Sending email digest")
    print("=" * 60)
    jobs = get_top_jobs_today(n=5)
    if not jobs:
        print("No scored jobs found from today — skipping email.")
        return

    print(f"  Top {len(jobs)} jobs today:")
    for job in jobs:
        print(f"    {job['score']}/10 — {job['title']} at {job['company']}")

    try:
        send_digest(jobs)
    except Exception as e:
        print(f"ERROR: Email failed: {e}")
        sys.exit(1)

    print("\nPipeline complete.")


if __name__ == "__main__":
    main()
