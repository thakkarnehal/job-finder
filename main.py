"""
main.py — runs the full pipeline:
  1. Scrape new jobs from all sources
  2. Score unscored jobs with GPT-4o-mini
  3. Email only jobs not seen in previous runs
"""

import sys

from scraper import main as run_scraper
from scorer import main as run_scorer
from emailer import send_digest
from database import get_jobs_to_email, mark_emailed

MIN_SCORE = 60   # only email jobs scoring at least this (0-100)


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

    top_new = get_jobs_to_email(MIN_SCORE, limit=5)

    if not top_new:
        print("No new jobs above the score floor — skipping email.")
        return

    print(f"  Emailing {len(top_new)} jobs:")
    for job in top_new:
        print(f"    {job['score']}/100 — {job['title']} at {job['company']}")

    try:
        send_digest(top_new)
    except Exception as e:
        print(f"ERROR: Email failed: {e}")
        sys.exit(1)

    # Mark them emailed so a later run today doesn't send them again.
    mark_emailed([j["id"] for j in top_new])
    print("\nPipeline complete.")


if __name__ == "__main__":
    main()
