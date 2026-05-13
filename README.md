# Job Finder

A daily automated pipeline that scrapes ML/AI/Data Science job postings, scores them against your resume using GPT-4o-mini, and emails you the top matches every morning.

## How it works

1. **Scrape** — pulls jobs from LinkedIn, Indeed, and Greenhouse boards (Stripe, Datadog), filtering for title keywords, US locations, and companies on an allowlist
2. **Filter** — automatically drops roles requiring 4+ years of experience, a Master's/PhD, or senior/staff/director titles
3. **Score** — sends each new job + your resume to GPT-4o-mini for a 1–10 fit score with a short summary
4. **Email** — sends a daily digest with the top 5 new jobs as a formatted HTML email

Seen jobs are tracked in `seen_jobs.json` so you never get the same listing twice.

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/thakkarnehal/job-finder.git
cd job-finder
pip install -r requirements.txt
playwright install --with-deps chromium
```

### 2. Add your resume

Paste your resume text into `resume.txt`.

### 3. Configure environment variables

Create a `.env` file:

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

The workflow runs daily at ~9 AM EDT via `.github/workflows/daily_scrape.yml`. It requires the following repository secrets:

| Secret | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key |
| `GMAIL_ADDRESS` | Gmail address to send from |
| `GMAIL_APP_PASSWORD` | Gmail app password |
| `EMAIL_RECIPIENT` | Email address to send the digest to |

Add them at **Settings → Secrets and variables → Actions**.

## Customization

- **Add Greenhouse boards** — add entries to `GREENHOUSE_BOARDS` in [scraper.py](scraper.py)
- **Add/remove companies** — edit `COMPANY_ALLOWLIST` in [scraper.py](scraper.py)
- **Change search queries** — edit `SEARCH_QUERIES` in [scraper.py](scraper.py)
- **Adjust experience/education filters** — edit `EXPERIENCE_RE` and `EDUCATION_RE` in [scraper.py](scraper.py)

## Limitations

- **LinkedIn/Indeed scraping is fragile** — both sites actively block bots and change their HTML structure. Scraping can silently return 0 results if they update their layout or serve a CAPTCHA page.
- **No job description for LinkedIn/Indeed at scrape time** — descriptions are fetched later during scoring via a separate HTTP request, which can fail or return incomplete content.
- **SQLite doesn't persist across GitHub Actions runs** — `jobs.db` is rebuilt from scratch each run since the Actions runner is ephemeral. Only `seen_jobs.json` persists (committed back to the repo).
- **Company allowlist is manually curated** — jobs from companies not on the list are silently dropped, so you can miss good roles at smaller or newer companies.
- **GitHub Actions scheduler lag** — scheduled runs can be delayed 15–30 minutes during peak hours.
- **Experience/education filters use regex** — they can produce false positives (e.g. a job mentioning "4 years of stability" in a non-requirements context gets filtered out).

## Next steps

- **Add more job sources** — Lever, Workday, and direct company career pages (e.g. Google Careers, Meta Careers) would significantly increase coverage
- **Replace LinkedIn/Indeed scraping with APIs** — LinkedIn has an official Jobs API (requires partnership); Indeed has a Publisher API for more reliable access
- **Persist the database** — store `jobs.db` in a persistent store (e.g. Supabase, PlanetScale, or even a committed SQLite file) so scores and history accumulate across runs
- **Build a simple review UI** — a lightweight web app to browse all scored jobs, mark applied/rejected, and give feedback to improve scoring over time
- **Fine-tune scoring with feedback** — use thumbs up/down on emailed jobs to build a dataset and improve fit scoring beyond a generic GPT prompt
- **Slack/SMS notifications** — send the digest to Slack or via SMS (Twilio) as an alternative to email

## Project structure

```
main.py          # orchestrates the pipeline
scraper.py       # scrapes LinkedIn, Indeed, Greenhouse
scorer.py        # scores jobs with GPT-4o-mini
emailer.py       # builds and sends the HTML email digest
database.py      # SQLite helpers (jobs.db)
resume.txt       # your resume (used for scoring)
seen_jobs.json   # tracks already-emailed job URLs
```
