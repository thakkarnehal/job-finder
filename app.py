import json
import os
from datetime import date

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
from openai import OpenAI

from database import get_all_jobs, set_applied, get_jobs_today, get_newsletter, save_newsletter

load_dotenv()

app = Flask(__name__)

_openai_client = None


def get_openai_client():
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if api_key:
            _openai_client = OpenAI(api_key=api_key, timeout=60.0)
    return _openai_client


NEWSLETTER_PROMPT = """You are analyzing job postings to help a candidate improve their resume.

Here are {n} job postings scraped today:

{jobs_text}

Based on these postings, produce a JSON object with exactly these keys:
- "must_have_skills": list of the top 8 technical skills/tools explicitly required across most postings
- "nice_to_have_skills": list of 5 skills mentioned as preferred or a plus
- "resume_tips": list of 4 concrete, specific tips for tailoring a resume to these roles
- "market_summary": 2-3 sentence summary of what today's market looks like for these roles

Return only valid JSON, no markdown fences."""


def generate_newsletter(jobs):
    client = get_openai_client()
    if not client:
        return None

    jobs_text = "\n\n".join(
        f"Title: {j['title']}\nCompany: {j['company']}\nDescription: {(j.get('description') or '')[:800]}"
        for j in jobs
    )

    prompt = NEWSLETTER_PROMPT.format(n=len(jobs), jobs_text=jobs_text)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    raw = response.choices[0].message.content.strip()
    return json.loads(raw)


@app.route("/")
def index():
    jobs = get_all_jobs()
    return render_template("index.html", jobs=jobs, active_tab="jobs")


@app.route("/apply", methods=["POST"])
def apply():
    data = request.get_json()
    set_applied(data["id"], data["applied"])
    return jsonify({"ok": True})


@app.route("/insights")
def insights():
    today = date.today().isoformat()
    cached = get_newsletter(today)

    newsletter = None
    error = None
    jobs_today = get_jobs_today()

    if cached:
        newsletter = json.loads(cached)
    elif jobs_today:
        try:
            newsletter = generate_newsletter(jobs_today)
            if newsletter:
                save_newsletter(today, json.dumps(newsletter))
        except Exception as e:
            error = str(e)

    return render_template(
        "insights.html",
        newsletter=newsletter,
        error=error,
        job_count=len(jobs_today),
        today=today,
        active_tab="insights",
    )


@app.route("/insights/refresh", methods=["POST"])
def refresh_insights():
    """Force-regenerate today's newsletter."""
    today = date.today().isoformat()
    jobs_today = get_jobs_today()
    if not jobs_today:
        return jsonify({"ok": False, "error": "No jobs scraped today"})
    try:
        newsletter = generate_newsletter(jobs_today)
        if newsletter:
            save_newsletter(today, json.dumps(newsletter))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


if __name__ == "__main__":
    app.run(debug=True)
