"""
Boever Daily Opportunity Digest
Runs via GitHub Actions every morning.
Fetches live job/conference data via Anthropic API + direct page fetches,
then sends a formatted HTML email via Gmail SMTP.
"""

import os
import ssl
import smtplib
import datetime
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic
import requests

# ── CONFIG ────────────────────────────────────────────────────────────────────
# All sensitive values come from GitHub Actions secrets (never hardcoded here)

RECIPIENT_EMAIL = "tonyboever@gmail.com"
SENDER_EMAIL    = "tonyboever@gmail.com"

# Direct pages to fetch live — no search API needed
PRIORITY_PAGES = [
    {
        "name":      "Life Cycle Geo",
        "url":       "https://www.lifecyclegeo.com/jobs/",
        "empty_signal": "there are no open positions",
    },
    {
        "name":      "Geosyntec Consultants",
        "url":       "https://geosyntec.com/careers",
        "empty_signal": None,  # just report page is live
    },
]

# Standing conference reminders — auto-expire when end date passes
STANDING_REMINDERS = [
    {
        "label":    "⭐ PFAS Forum VI — Orlando, FL",
        "start":    datetime.date(2026, 5, 13),
        "end":      datetime.date(2026, 5, 15),
        "note":     "Geosyntec speakers present. pfasforum.org",
        "southeast": True,
    },
    {
        "label":    "⭐ Georgia Environmental Conference — Jekyll Island, GA",
        "start":    datetime.date(2026, 8, 19),
        "end":      datetime.date(2026, 8, 21),
        "note":     "Southeast's largest env. conference. Register by Aug 18. georgiaenet.com",
        "southeast": True,
    },
    {
        "label":    "⚠️ AGU26 Abstract Deadline",
        "start":    datetime.date(2026, 8, 5),
        "end":      datetime.date(2026, 8, 5),
        "note":     "Submit to Earth & Environmental Sciences sessions. agu.confex.com",
        "southeast": False,
    },
    {
        "label":    "AEG Annual Meeting — Chattanooga, TN",
        "start":    datetime.date(2026, 9, 13),
        "end":      datetime.date(2026, 9, 19),
        "note":     "Easy drive from Atlanta. 120+ presentations, networking for early-career. aegannualmeeting.org",
        "southeast": True,
    },
    {
        "label":    "A&WMA Science of PFAS — Durham, NC",
        "start":    datetime.date(2026, 9, 22),
        "end":      datetime.date(2026, 9, 24),
        "note":     "Practitioners + regulators. Drivable from Atlanta. awma.org/pfas",
        "southeast": True,
    },
    {
        "label":    "AVIP Vapor Intrusion Conference — Orlando, FL",
        "start":    datetime.date(2026, 10, 11),
        "end":      datetime.date(2026, 10, 14),
        "note":     "Contaminant fate/transport. State regulators present. viconference.vaporintrusion.org",
        "southeast": True,
    },
    {
        "label":    "SETAC North America — Montreal",
        "start":    datetime.date(2026, 11, 2),
        "end":      datetime.date(2026, 11, 5),
        "note":     "Exposure science + contaminant bioavailability. setac.org",
        "southeast": False,
    },
]

# ── LIVE PAGE FETCHES ─────────────────────────────────────────────────────────

def fetch_priority_pages():
    """Fetch each priority employer page and report what's actually there."""
    results = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; digest-bot/1.0)"}

    for page in PRIORITY_PAGES:
        try:
            r = requests.get(page["url"], headers=headers, timeout=15)
            r.raise_for_status()
            text_lower = r.text.lower()

            if page["empty_signal"] and page["empty_signal"] in text_lower:
                status = "No current openings listed."
            else:
                # Look for positive signals of active postings
                signals = ["apply now", "open position", "we are hiring",
                           "job opening", "full-time", "full time", "submit your resume"]
                has_jobs = any(s in text_lower for s in signals)
                status = "✅ Active postings detected — visit to apply." if has_jobs else "Page live — review manually for postings."

            results.append({
                "name":   page["name"],
                "url":    page["url"],
                "status": status,
            })
        except Exception as e:
            results.append({
                "name":   page["name"],
                "url":    page["url"],
                "status": f"⚠️ Could not reach page: {e}",
            })

    return results

# ── ANTHROPIC SEARCH ──────────────────────────────────────────────────────────

def build_search_years():
    """Return current year, plus next year starting in October."""
    now = datetime.date.today()
    this_year = now.year
    if now.month >= 10:
        return f"{this_year} OR {this_year + 1}"
    return str(this_year)

def run_ai_search(api_key):
    """Call Anthropic API with web search to find live jobs, conferences, CFAs."""
    client = anthropic.Anthropic(api_key=api_key)
    years = build_search_years()
    today = datetime.date.today().strftime("%B %d, %Y")

    prompt = f"""You are a research assistant helping an environmental geochemist find opportunities.
Today is {today}. Search the web for LIVE, CURRENT results only — no training data, no assumptions.

Researcher profile:
- PhD Environmental Geochemistry, Georgia Tech (May 2026)
- Expertise: redox biogeochemistry, contaminant cycling, PFAS, uranium, groundwater remediation
- Prior industry: REGENESIS Bioremediation
- Location: Atlanta, GA — open to remote/hybrid or travel within Southeast US
- Priority employers: Geosyntec Consultants, Life Cycle Geo

Search for and return ONLY verified live results in these three categories:

1. JOBS (3-5): Environmental consulting, geochemistry, or remediation roles at firms like
   Arcadis, AECOM, Ramboll, Haley & Aldrich, Stantec — in Atlanta area or remote.
   Only include if you can verify the posting exists today. If you cannot verify, exclude it.

2. INDUSTRY CONFERENCES ({years}): Upcoming events where environmental consultants,
   hydrogeologists, and remediation professionals network — NGWA, AEHS, RemTEC, Battelle,
   SETAC, ITRC, regional environmental events. For Southeast US events, note that.
   Only include events that have not yet occurred as of today.

3. CALLS FOR ABSTRACTS ({years}): Active calls with future deadlines relevant to
   biogeochemistry, environmental geochemistry, contaminant science, or remediation.
   Only include if the deadline is in the future.

Return a JSON array. Each item must have:
  type: "job" | "conference" | "cfa"
  title: string
  org: string
  location: string (city/state or "Remote")
  date: string (event date, deadline, or posting date)
  desc: string (1-2 sentences on relevance — for conferences, who attends)
  url: string (direct link you verified exists)
  southeast: boolean (true if in GA, FL, SC, NC, TN, AL, MS, LA, VA, KY)

Return ONLY the JSON array. No markdown, no preamble. If you cannot find verified results
for a category, return an empty array for that type — do not fabricate."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )

    # Extract text from response
    raw = ""
    for block in response.content:
        if block.type == "text":
            raw += block.text

    # Parse JSON
    raw = raw.strip()
    start = raw.find("[")
    end   = raw.rfind("]")
    if start == -1 or end == -1:
        return []

    return json.loads(raw[start:end + 1])

# ── STANDING REMINDERS ────────────────────────────────────────────────────────

def get_upcoming_reminders():
    """Return only reminders whose end date has not yet passed."""
    today = datetime.date.today()
    soon  = today + datetime.timedelta(days=14)
    upcoming = []
    for r in STANDING_REMINDERS:
        if r["end"] >= today:
            r["imminent"] = r["start"] <= soon
            upcoming.append(r)
    return upcoming

# ── EMAIL BUILDER ─────────────────────────────────────────────────────────────

def badge(text, color):
    colors = {
        "red":    ("fff0f0", "c0392b"),
        "green":  ("f0fff4", "27ae60"),
        "yellow": ("fffbea", "7a5c00"),
        "orange": ("fff3cd", "856404"),
    }
    bg, fg = colors.get(color, ("f0f0f0", "333333"))
    return (f"<span style='background:#{bg};color:#{fg};font-size:11px;"
            f"padding:2px 8px;border-radius:99px;font-weight:600;"
            f"margin-right:4px;'>{text}</span>")

def result_card(item):
    badges = ""
    if item.get("southeast"):
        badges += badge("📍 Southeast", "green")
    html  = f"<div style='margin-bottom:12px;padding:12px 14px;background:#fafafa;border:1px solid #e8e8e8;border-radius:6px;'>"
    if badges:
        html += f"<div style='margin-bottom:5px;'>{badges}</div>"
    url   = item.get("url", "#")
    html += f"<p style='margin:0 0 3px;font-size:14px;font-weight:600;'><a href='{url}' style='color:#1a56db;text-decoration:none;'>{item['title']}</a></p>"
    meta  = " · ".join(filter(None, [item.get("org"), item.get("location"), item.get("date")]))
    html += f"<p style='margin:0 0 4px;font-size:12px;color:#888;'>{meta}</p>"
    html += f"<p style='margin:0;font-size:13px;color:#555;line-height:1.5;'>{item.get('desc', '')}</p>"
    html += "</div>"
    return html

def section_header(title):
    return (f"<h2 style='font-size:15px;font-weight:600;color:#1a1a1a;"
            f"border-bottom:1px solid #e0e0e0;padding-bottom:6px;margin:24px 0 12px;'>{title}</h2>")

def build_html(today_str, priority_pages, ai_results, reminders):
    jobs  = [r for r in ai_results if r["type"] == "job"]
    confs = [r for r in ai_results if r["type"] == "conference"]
    cfas  = [r for r in ai_results if r["type"] == "cfa"]

    html = f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;
max-width:640px;margin:0 auto;padding:20px;color:#1a1a1a;">

<div style="border-bottom:2px solid #1a56db;padding-bottom:12px;margin-bottom:20px;">
  <h1 style="font-size:18px;font-weight:600;margin:0;">Daily Opportunity Digest</h1>
  <p style="font-size:13px;color:#666;margin:4px 0 0;">{today_str} &nbsp;·&nbsp;
  Environmental Geochemistry | Remediation | Biogeochemistry</p>
</div>"""

    # Priority employer page status
    html += section_header("⭐ Priority Employers — Live Page Check")
    for p in priority_pages:
        html += (f"<div style='margin-bottom:10px;padding:10px 14px;background:#fafafa;"
                 f"border:1px solid #e8e8e8;border-radius:6px;'>"
                 f"<p style='margin:0 0 2px;font-size:14px;font-weight:600;'>"
                 f"<a href='{p['url']}' style='color:#1a56db;text-decoration:none;'>{p['name']}</a></p>"
                 f"<p style='margin:0;font-size:13px;color:#555;'>{p['status']}</p></div>")

    # Jobs
    if jobs:
        html += section_header("💼 Jobs")
        for item in jobs:
            html += result_card(item)
    else:
        html += section_header("💼 Jobs")
        html += "<p style='font-size:13px;color:#888;'>No new verified postings found today.</p>"

    # Industry conferences
    if confs:
        html += section_header("🏭 Conferences & Industry Events")
        for item in confs:
            html += result_card(item)

    # Calls for abstracts
    if cfas:
        html += section_header("📋 Calls for Abstracts")
        for item in cfas:
            html += result_card(item)

    # Standing reminders
    if reminders:
        html += section_header("📌 Upcoming Calendar Reminders")
        html += "<div style='background:#fffbea;border-left:3px solid #d4a017;padding:12px 16px;border-radius:4px;'>"
        for r in reminders:
            b = ""
            if r["imminent"]:
                b += badge("Soon", "red")
            if r["southeast"]:
                b += badge("Southeast", "green")
            date_str = r["start"].strftime("%b %-d")
            if r["start"] != r["end"]:
                date_str += f"–{r['end'].strftime('%-d, %Y')}"
            else:
                date_str += f", {r['start'].year}"
            html += (f"<p style='margin:6px 0;font-size:13px;'>{b}"
                     f"<strong>{r['label']}</strong> &nbsp;·&nbsp; {date_str}<br>"
                     f"<span style='color:#666;font-size:12px;'>{r['note']}</span></p>")
        html += "</div>"

    html += """
<div style="margin-top:32px;padding-top:12px;border-top:1px solid #e0e0e0;font-size:11px;color:#999;">
  Automated by GitHub Actions · Live results only · Edit digest.py to update
</div>
</body></html>"""

    return html

# ── EMAIL SENDER ──────────────────────────────────────────────────────────────

def send_email(html_body, subject, gmail_app_password):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(SENDER_EMAIL, gmail_app_password)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())

    print(f"✅ Digest sent to {RECIPIENT_EMAIL}")

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    anthropic_key     = os.environ["ANTHROPIC_API_KEY"]
    gmail_app_password = os.environ["GMAIL_APP_PASSWORD"]

    today_str = datetime.date.today().strftime("%A, %B %-d, %Y")
    subject   = f"Opportunity Digest — {today_str}"

    print("Fetching priority employer pages...")
    priority_pages = fetch_priority_pages()

    print("Running AI-powered web search...")
    ai_results = run_ai_search(anthropic_key)
    print(f"  Found {len(ai_results)} results")

    print("Filtering standing reminders...")
    reminders = get_upcoming_reminders()

    print("Building and sending email...")
    html = build_html(today_str, priority_pages, ai_results, reminders)
    send_email(html, subject, gmail_app_password)

if __name__ == "__main__":
    main()
