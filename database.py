import os
from datetime import date

import libsql
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "jobs.db"
_conn = None


def get_connection():
    """Return a shared libSQL connection.

    Uses Turso when TURSO_DATABASE_URL is set (e.g. in GitHub Actions), otherwise
    falls back to a local libSQL file for development.
    """
    global _conn
    if _conn is None:
        url = os.getenv("TURSO_DATABASE_URL")
        if url:
            _conn = libsql.connect(database=url, auth_token=os.getenv("TURSO_AUTH_TOKEN"))
        else:
            _conn = libsql.connect(DB_PATH)
    return _conn


def _rows(cur):
    """libSQL has no row_factory, so build dicts from the cursor description."""
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def init_db():
    """Create the tables if they don't exist."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            company     TEXT NOT NULL,
            url         TEXT NOT NULL UNIQUE,
            location    TEXT,
            date_posted TEXT,
            date_found  TEXT NOT NULL,
            description TEXT,
            score       REAL,
            summary     TEXT,
            applied     INTEGER NOT NULL DEFAULT 0,
            emailed     INTEGER NOT NULL DEFAULT 0,
            eligible    INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS newsletters (
            date     TEXT PRIMARY KEY,
            content  TEXT NOT NULL
        )
    """)
    # Migrations for DBs created before these columns existed (ALTER no-ops on new DBs).
    for column in (
        "emailed INTEGER NOT NULL DEFAULT 0",
        "eligible INTEGER NOT NULL DEFAULT 1",
        "date_posted TEXT",
    ):
        try:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {column}")
        except Exception:
            pass
    conn.commit()


def job_exists(url, title=None, company=None):
    """Return True if a job with this URL or the same title+company already exists."""
    conn = get_connection()
    if conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,)).fetchone():
        return True
    if title and company:
        if conn.execute(
            "SELECT 1 FROM jobs WHERE lower(title) = lower(?) AND lower(company) = lower(?)",
            (title, company),
        ).fetchone():
            return True
    return False


def save_job(job):
    """Insert a job into the database. Returns True if saved, False if duplicate."""
    if job_exists(job["url"], job.get("title"), job.get("company")):
        return False
    conn = get_connection()
    conn.execute("""
        INSERT INTO jobs (title, company, url, location, date_posted, date_found, description)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        job["title"],
        job["company"],
        job["url"],
        job.get("location"),
        job.get("date_posted"),
        date.today().isoformat(),
        job.get("description"),
    ))
    conn.commit()
    return True


def get_unscored_jobs():
    """Return all jobs that haven't been scored yet."""
    return _rows(get_connection().execute("SELECT * FROM jobs WHERE score IS NULL"))


def update_score(job_id, score, summary):
    """Save the score and summary for an eligible job."""
    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET score = ?, summary = ? WHERE id = ?",
        (score, summary, job_id),
    )
    conn.commit()


def mark_ineligible(job_id, score, summary):
    """Record a job as screened-out (a dealbreaker) instead of deleting it, so it
    is remembered and not re-scraped/re-scored on later runs."""
    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET score = ?, summary = ?, eligible = 0 WHERE id = ?",
        (score, summary, job_id),
    )
    conn.commit()


def get_all_jobs():
    """Return all jobs sorted by score descending, then date descending."""
    return _rows(get_connection().execute("""
        SELECT * FROM jobs
        ORDER BY score DESC NULLS LAST, date_found DESC
    """))


def delete_job(job_id):
    """Remove a job that failed post-scrape filtering."""
    conn = get_connection()
    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()


def update_description(job_id, description):
    """Store a fetched description so future runs don't need to re-fetch."""
    conn = get_connection()
    conn.execute("UPDATE jobs SET description = ? WHERE id = ?", (description, job_id))
    conn.commit()


def set_applied(job_id, applied):
    """Set the applied status for a job."""
    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET applied = ? WHERE id = ?",
        (1 if applied else 0, job_id),
    )
    conn.commit()


def get_jobs_today():
    """Return all jobs found today."""
    return _rows(get_connection().execute(
        "SELECT * FROM jobs WHERE date_found = ?", (date.today().isoformat(),)
    ))


def get_jobs_to_email(min_score, limit=5):
    """Return jobs that cleared the score floor and haven't been emailed yet."""
    return _rows(get_connection().execute(
        "SELECT * FROM jobs WHERE score >= ? AND emailed = 0 AND eligible = 1 "
        "ORDER BY score DESC LIMIT ?",
        (min_score, limit),
    ))


def mark_emailed(job_ids):
    """Mark jobs as emailed so they aren't sent again on a later run."""
    if not job_ids:
        return
    conn = get_connection()
    conn.executemany("UPDATE jobs SET emailed = 1 WHERE id = ?", [(i,) for i in job_ids])
    conn.commit()


def get_newsletter(date_str):
    """Return cached newsletter content for a given date, or None."""
    row = get_connection().execute(
        "SELECT content FROM newsletters WHERE date = ?", (date_str,)
    ).fetchone()
    return row[0] if row else None


def save_newsletter(date_str, content):
    """Cache newsletter content for a given date."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO newsletters (date, content) VALUES (?, ?)",
        (date_str, content),
    )
    conn.commit()


def get_top_jobs_today(n=5):
    """Return the top N scored jobs found today, sorted by score descending."""
    return _rows(get_connection().execute("""
        SELECT * FROM jobs
        WHERE date_found = ? AND score IS NOT NULL AND eligible = 1
        ORDER BY score DESC
        LIMIT ?
    """, (date.today().isoformat(), n)))
