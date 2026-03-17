import json
import os
import time

from dotenv import load_dotenv
from openai import OpenAI

from database import get_unscored_jobs, update_score

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY", "").strip()
if not api_key:
    raise RuntimeError("OPENAI_API_KEY is not set. Add it to .env or GitHub Actions secrets.")

client = OpenAI(api_key=api_key, timeout=60.0, max_retries=3)

RESUME_PATH = "resume.txt"

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
        description=(job["description"] or "")[:3000],  # stay within token limits
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,  # deterministic scoring
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
        try:
            score, summary = score_job(job, resume)
            update_score(job["id"], score, summary)
            print(f"  Scored: {job['title']} at {job['company']} — {score}/10")
        except Exception as e:
            print(f"  ERROR scoring {job['title']} at {job['company']}: {e}")
        time.sleep(0.3)  # avoid hitting rate limits

    print("\nDone.")


if __name__ == "__main__":
    main()
