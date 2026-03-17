import sqlite3
from datetime import date

DB_PATH = "jobs.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    """Create the jobs table if it doesn't exist."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                company     TEXT NOT NULL,
                url         TEXT NOT NULL UNIQUE,
                location    TEXT,
                date_found  TEXT NOT NULL,
                description TEXT,
                score       REAL,
                summary     TEXT,
                applied     INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS newsletters (
                date     TEXT PRIMARY KEY,
                content  TEXT NOT NULL
            )
        """)
        conn.commit()


def job_exists(url, title=None, company=None):
    """Return True if a job with this URL or the same title+company already exists."""
    with get_connection() as conn:
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
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO jobs (title, company, url, location, date_found, description)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            job["title"],
            job["company"],
            job["url"],
            job.get("location"),
            date.today().isoformat(),
            job.get("description"),
        ))
        conn.commit()
    return True


def get_unscored_jobs():
    """Return all jobs that haven't been scored yet."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM jobs WHERE score IS NULL"
        ).fetchall()
    return [dict(row) for row in rows]


def update_score(job_id, score, summary):
    """Save the score and summary for a job."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET score = ?, summary = ? WHERE id = ?",
            (score, summary, job_id)
        )
        conn.commit()


def get_all_jobs():
    """Return all jobs sorted by score descending, then date descending."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM jobs
            ORDER BY score DESC NULLS LAST, date_found DESC
        """).fetchall()
    return [dict(row) for row in rows]


def set_applied(job_id, applied):
    """Set the applied status for a job."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET applied = ? WHERE id = ?",
            (1 if applied else 0, job_id)
        )
        conn.commit()


def get_jobs_today():
    """Return all jobs found today."""
    today = date.today().isoformat()
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM jobs WHERE date_found = ?", (today,)
        ).fetchall()
    return [dict(row) for row in rows]


def get_newsletter(date_str):
    """Return cached newsletter content for a given date, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT content FROM newsletters WHERE date = ?", (date_str,)
        ).fetchone()
    return row[0] if row else None


def save_newsletter(date_str, content):
    """Cache newsletter content for a given date."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO newsletters (date, content) VALUES (?, ?)",
            (date_str, content),
        )
        conn.commit()


def get_top_jobs_today(n=5):
    """Return the top N scored jobs found today, sorted by score descending."""
    today = date.today().isoformat()
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM jobs
            WHERE date_found = ? AND score IS NOT NULL
            ORDER BY score DESC
            LIMIT ?
        """, (today, n)).fetchall()
    return [dict(row) for row in rows]
