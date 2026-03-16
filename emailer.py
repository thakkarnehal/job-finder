import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()


def build_html(jobs):
    today = date.today().strftime("%B %d, %Y")

    cards = ""
    for job in jobs:
        score = job.get("score") or 0
        if score >= 7:
            badge_color = "#065f46"
            badge_bg = "#d1fae5"
        elif score >= 4:
            badge_color = "#92400e"
            badge_bg = "#fef3c7"
        else:
            badge_color = "#991b1b"
            badge_bg = "#fee2e2"

        cards += f"""
        <div style="background:#fff;border-radius:10px;padding:20px 24px;margin-bottom:16px;
                    box-shadow:0 1px 4px rgba(0,0,0,0.08);">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:6px;flex-wrap:wrap;">
            <span style="font-size:16px;font-weight:600;color:#111;">{job['title']}</span>
            <span style="font-size:13px;color:#555;">{job['company']}</span>
            <span style="font-size:12px;font-weight:700;padding:3px 10px;border-radius:20px;
                         background:{badge_bg};color:{badge_color};">{score}/10</span>
          </div>
          <div style="font-size:12px;color:#888;margin-bottom:8px;">{job.get('location','')}</div>
          <div style="font-size:14px;color:#444;line-height:1.5;margin-bottom:14px;">
            {job.get('summary') or '<em>No summary available.</em>'}
          </div>
          <a href="{job['url']}" style="display:inline-block;background:#2563eb;color:#fff;
             text-decoration:none;padding:8px 18px;border-radius:6px;font-size:13px;">
            Apply →
          </a>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                 background:#f4f6f9;padding:32px;color:#1a1a1a;">
      <div style="max-width:640px;margin:0 auto;">
        <h1 style="font-size:22px;margin-bottom:4px;">Your Daily Job Digest</h1>
        <p style="font-size:14px;color:#666;margin-bottom:24px;">{today} · Top {len(jobs)} matches</p>
        {cards}
        <p style="font-size:12px;color:#aaa;margin-top:24px;">
          Sent by your job finder pipeline.
        </p>
      </div>
    </body>
    </html>
    """


def send_digest(jobs):
    sender = os.getenv("GMAIL_ADDRESS")
    password = os.getenv("GMAIL_APP_PASSWORD")
    recipient = os.getenv("EMAIL_RECIPIENT")

    if not all([sender, password, recipient]):
        raise ValueError(
            "Missing email config. Set GMAIL_ADDRESS, GMAIL_APP_PASSWORD, "
            "and EMAIL_RECIPIENT in your .env file."
        )

    today = date.today().strftime("%B %d, %Y")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Job Digest — {today} ({len(jobs)} top picks)"
    msg["From"] = sender
    msg["To"] = recipient

    html = build_html(jobs)
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.starttls()
        smtp.login(sender, password)
        smtp.sendmail(sender, recipient, msg.as_string())

    print(f"  Email sent to {recipient} with {len(jobs)} jobs.")


if __name__ == "__main__":
    # Quick test: send with whatever is in the DB today
    from database import get_top_jobs_today
    jobs = get_top_jobs_today(5)
    if jobs:
        send_digest(jobs)
    else:
        print("No scored jobs found today to email.")
