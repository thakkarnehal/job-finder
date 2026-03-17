import json
import os
import time

import requests
from dotenv import load_dotenv
from openai import OpenAI

from database import get_unscored_jobs, update_score, delete_job
from scraper import EXPERIENCE_RE, EDUCATION_RE

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY", "").strip()
if not api_key:
    raise RuntimeError("OPENAI_API_KEY is not set. Add it to .env or GitHub Actions secrets.")

client = OpenAI(api_key=api_key, timeout=60.0, max_retries=3)

RESUME_PATH = "resume.txt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

PROMPT_TEMPLATE = """You are evaluating job fit for a candidate based on their resume.

RESUME:
{resume}

JOB TITLE: {title}
COMPANY: {company}
JOB DESCRIPTION:
{description}

Score how well this job fits the candidate on a scale of 1-10, where:
- 1-3: Poor fit (missing key skills or wrong level)
- 4-6: Partial fit (some overlap but significant gaps)
- 7-8: Good fit (strong overlap in skills and experience)
- 9-10: Excellent fit (near-perfect match)

Respond with only valid JSON in this exact format:
{{ "score": <number>, "summary": "<2-3 sentences explaining the fit>" }}"""


def fetch_description(url):
    """Try to scrape plain text from a job URL. Returns empty string on failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        # Strip HTML tags with a simple regex
        text = resp.text
        text = __import__('re').sub(r'<[^>]+>', ' ', text)
        text = __import__('re').sub(r'\s+', ' ', text)
        return text[:5000]
    except Exception:
        return ""


def load_resume():
    if not os.path.exists(RESUME_PATH):
        raise FileNotFoundError(f"{RESUME_PATH} not found. Please create it and paste your resume.")
    with open(RESUME_PATH) as f:
        content = f.read().strip()
    if not content:
        raise ValueError(f"{RESUME_PATH} is empty. Please paste your resume into it.")
    return content


def score_job(job, resume):
    prompt = PROMPT_TEMPLATE.format(
        resume=resume,
        title=job["title"],
        company=job["company"],
        description=(job["description"] or "")[:3000],
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    raw = response.choices[0].message.content.strip()
    result = json.loads(raw)
    return result["score"], result["summary"]


def main():
    resume = load_resume()
    jobs = get_unscored_jobs()

    if not jobs:
        print("No unscored jobs found.")
        return

    print(f"Scoring {len(jobs)} jobs...\n")

    for job in jobs:
        # If description is empty (LinkedIn/Indeed), fetch it from the job page
        description = job.get("description") or ""
        if not description.strip():
            print(f"  Fetching description for: {job['title']} at {job['company']}...")
            description = fetch_description(job["url"])

        # Re-run education/experience filters on the full description
        combined = (job["title"] + " " + description).lower()
        if EXPERIENCE_RE.search(combined):
            print(f"  FILTERED (experience): {job['title']} at {job['company']}")
            delete_job(job["id"])
            continue
        if EDUCATION_RE.search(combined):
            print(f"  FILTERED (education): {job['title']} at {job['company']}")
            delete_job(job["id"])
            continue

        # Update stored description so future runs have it
        if description.strip() and not (job.get("description") or "").strip():
            from database import update_description
            update_description(job["id"], description[:2000])
            job["description"] = description[:2000]

        try:
            score, summary = score_job(job, resume)
            update_score(job["id"], score, summary)
            print(f"  Scored: {job['title']} at {job['company']} — {score}/10")
        except Exception as e:
            print(f"  ERROR scoring {job['title']} at {job['company']}: {e}")
        time.sleep(0.3)

    print("\nDone.")


if __name__ == "__main__":
    main()
