# Job Finder

A daily automated pipeline that scrapes ML/AI/Data Science job postings, screens and scores them against your resume with an ATS-style GPT-4o evaluator, and emails you the top matches every morning.

## How it works

1. **Scrape** — pulls jobs from the public JSON APIs of a curated set of company boards on **Greenhouse, Lever, and Ashby**. A free pre-filter keeps only jobs that (a) are in a US location, (b) have an ML/AI/Data Science keyword in the title, and (c) aren't senior/staff/lead/manager/director by title.
2. **Screen & score** — each new job (with its location) plus your resume is sent to **GPT-4o** as an ATS-style evaluator. It extracts the job's must-have / nice-to-have requirements, checks them against evidence in your resume, and flags **dealbreakers** (a required Master's/PhD you don't have, far more experience than you have, a non-US location, a current-student/internship requirement, etc.). Jobs with any dealbreaker are dropped; the rest get a weighted **0–100** fit score plus a short summary.
3. **Email** — sends a daily HTML digest of the new jobs scoring **≥ 60**, top first.

Seen jobs are tracked in `seen_jobs.json` so you never get the same listing twice.

## Two-layer filtering

Filtering is deliberately split so the expensive model isn't wasted on obvious misses:

- **Cheap, deterministic (scraper)** — US location, title keyword, and seniority checks. No tokens spent.
- **Smart, evidence-based (GPT-4o)** — experience level, degree requirements, enrollment status, and a mandatory location backstop, judged against the actual resume.

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/thakkarnehal/job-finder.git
cd job-finder
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Add your resume

Paste your resume text into `resume.txt`. The scorer reads this directly, so keep it current.

### 3. Configure environment variables

Copy the template and fill in your values:

```bash
cp .env.example .env
```

```env
OPENAI_API_KEY=sk-...
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
EMAIL_RECIPIENT=you@gmail.com
```

For `GMAIL_APP_PASSWORD`, generate one at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) (requires 2FA enabled).

### 4. Run locally

```bash
python main.py
```

## GitHub Actions (automated daily run)

The workflow runs daily at ~9 AM EDT via `.github/workflows/daily_scrape.yml`. Locally the secrets come from `.env`; in Actions they come from repository secrets (no `.env` is committed):

| Secret | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key |
| `GMAIL_ADDRESS` | Gmail address to send from |
| `GMAIL_APP_PASSWORD` | Gmail app password |
| `EMAIL_RECIPIENT` | Email address to send the digest to |

Add them at **Settings → Secrets and variables → Actions**.

## Customization

- **Add company boards** — add entries to `GREENHOUSE_BOARDS`, `LEVER_BOARDS`, or `ASHBY_BOARDS` in [scraper.py](scraper.py)
- **Change which titles match** — edit `TITLE_KEYWORDS` (must-match) or `EXCLUDE_KEYWORDS` (seniority) in [scraper.py](scraper.py)
- **Adjust US location matching** — edit `US_INDICATORS` in [scraper.py](scraper.py)
- **Tune screening / scoring** — edit `PROMPT_TEMPLATE` in [scorer.py](scorer.py) (e.g. the experience threshold, weighting, or dealbreaker rules)
- **Change the email cutoff** — adjust the `score >= 60` floor in [main.py](main.py)

## Limitations

- **Board coverage is manually curated** — only companies listed in the board dicts are scraped, so you'll miss roles at companies you haven't added.
- **LLM judgments aren't perfectly deterministic** — even at `temperature=0` the model can occasionally vary. The mandatory location gate and dealbreaker rules reduce this, but a borderline call may flip run-to-run.
- **SQLite doesn't persist across GitHub Actions runs** — `jobs.db` is rebuilt each run since the Actions runner is ephemeral. Only `seen_jobs.json` persists (committed back to the repo).
- **Descriptions are truncated** — only the first ~3000 characters of each posting are sent to the model, so requirements buried deep in a long description may be missed.
- **GitHub Actions scheduler lag** — scheduled runs can be delayed 15–30 minutes during peak hours.

## Next steps

- **Add more job sources** — Workday and direct company career pages would increase coverage beyond Greenhouse/Lever/Ashby
- **Persist the database** — store `jobs.db` in a persistent store (e.g. Supabase) so scores and history accumulate across runs
- **Surface the rich ATS output** — the model already returns per-requirement evidence and category scores; storing and displaying them would make the digest far more informative
- **Build a review UI** — a lightweight web app to browse scored jobs, mark applied/rejected, and feed that back into scoring
- **Slack/SMS notifications** — send the digest to Slack or via SMS (Twilio) as an alternative to email

## Project structure

```
main.py          # orchestrates the pipeline (scrape → score → email)
scraper.py       # scrapes Greenhouse / Lever / Ashby boards + cheap pre-filter
scorer.py        # ATS-style screening & 0–100 scoring with GPT-4o
emailer.py       # builds and sends the HTML email digest
database.py      # SQLite helpers (jobs.db)
resume.txt       # your resume (used for scoring)
seen_jobs.json   # tracks already-emailed job URLs
.env.example     # template for required environment variables
```
