import json
import os
import time
from datetime import date
from dotenv import load_dotenv
from openai import OpenAI
from database import get_unscored_jobs, update_score, delete_job

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY", "").strip()
if not api_key:
    raise RuntimeError("OPENAI_API_KEY is not set. Add it to .env or GitHub Actions secrets.")

client = OpenAI(api_key=api_key, timeout=60.0, max_retries=3)

RESUME_PATH = "resume.txt"

PROMPT_TEMPLATE = """You are an ATS-style evaluator. Score the candidate's resume against the job below
using ONLY evidence explicitly present in the resume. Never infer skills, tools, or seniority that are
not stated. You MAY compute years of experience from the employment dates (internship excluded) in the resume relative to
today's date ({today}).

JOB TITLE: {title}
COMPANY: {company}
JOB LOCATION: {location}

MANDATORY LOCATION GATE — do this FIRST, before anything else. Read JOB LOCATION above. If it names any
place outside the United States — this INCLUDES any "Remote <country>" that is not the US,then you MUST add the exact
string "Location outside US" to the dealbreakers array and set overall_score to 0. Only US locations,
plain "Remote", "Remote US", and remote with no country named are acceptable. Never omit this dealbreaker
when the location is non-US, no matter how strong the rest of the match is.

<job_description>
{description}
</job_description>

<resume>
{resume}
</resume>

Step 1 — Extract the job's requirements:
- must_have: non-negotiable requirements (hard skills, minimum years of experience, required degree,
  certifications). A requirement the role is clearly built around counts as must_have even when softened
  with "preferred", "ideally", or "you may be a good fit if".
- nice_to_have: genuinely optional / bonus items.
- screening_constraints: hard pass/fail filters — a required current-student status or internship, outside the US location, education degrees

Step 2 — For each must_have and nice_to_have, assign "met", "partial", or "not_found" with the exact
resume quote as evidence (or null). Clearly synonymous skills are matches with "semantic_match": true.

Step 3 — Category scores (0-100): hard_skills_match; experience_level_match (years AND seniority, not
keyword presence); domain_relevance (industry / problem-space overlap); education_certification_match.

Step 4 — overall_score (0-100): weighted average. Default weights: hard_skills_match 40%,
experience_level_match 30%, domain_relevance 20%, education_certification_match 10%. Adjust only if the
JD clearly signals a different priority (e.g. heavily emphasizes "PhD required").

Step 5 — dealbreakers: list any violated screening_constraint, or any must_have marked "not_found"
(e.g. a required Master's/PhD the resume lacks, 5+ years when the resume shows far less, a location
outside the US, a required clearance). A dealbreaker must appear even if overall_score is high.

Be conservative: do not overstate the candidate's experience and do not credit skills the resume does
not show. Output ONLY valid JSON (no markdown fences) matching this schema:
"""

# Kept separate from PROMPT_TEMPLATE so its many braces don't collide with str.format().
SCHEMA = """{
  "must_have": [{"requirement": "string", "status": "met|partial|not_found", "evidence": "string or null", "semantic_match": false}],
  "nice_to_have": [{"requirement": "string", "status": "met|partial|not_found", "evidence": "string or null", "semantic_match": false}],
  "screening_constraints": [{"constraint": "string", "violated": false, "note": "string"}],
  "category_scores": {"hard_skills_match": 0, "experience_level_match": 0, "domain_relevance": 0, "education_certification_match": 0},
  "overall_score": 0,
  "dealbreakers": ["string"],
  "top_gaps": ["string"],
  "recommendation": "string, one sentence"
}"""

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
        today=date.today().isoformat(),
        resume=resume,
        title=job["title"],
        company=job["company"],
        location=job.get("location") or "Not specified",
        description=(job["description"] or "")[:3000],
    ) + SCHEMA

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)

    # Translate the ATS output into the pipeline's (eligible, score, reason, summary).
    dealbreakers = result.get("dealbreakers") or []
    eligible = len(dealbreakers) == 0
    score = result.get("overall_score", 0)        # 0-100 scale
    reason = "; ".join(dealbreakers) if dealbreakers else "no dealbreakers"
    summary = result.get("recommendation") or ""
    gaps = result.get("top_gaps") or []
    if gaps:
        summary += " | Gaps: " + "; ".join(gaps)
    return eligible, score, reason, summary


def main():
    resume = load_resume()
    jobs = get_unscored_jobs()

    if not jobs:
        print("No unscored jobs found.")
        return

    print(f"Scoring {len(jobs)} jobs...\n")

    for job in jobs:
        try:
            eligible, score, reason, summary = score_job(job, resume)
            if(not eligible):
                print(f"FILTERED OUT {reason}: {job['title']} at {job['company']}")
                delete_job(job['id'])
                continue
            update_score(job["id"], score, summary)
            print(f"  Scored: {job['title']} at {job['company']} — {score}/100")
        except Exception as e:
            print(f"  ERROR scoring {job['title']} at {job['company']}: {e}")
        time.sleep(0.3)

    print("\nDone.")


if __name__ == "__main__":
    main()
