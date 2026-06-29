"""
Boever Daily Opportunity Digest — v5
Sources:
  Industry jobs:   Indeed + ZipRecruiter (MCP)
  Government jobs: USAJobs API (USGS, CDC/ATSDR, EPA, DOE, NIEHS)
  Niche boards:    Josh's Water Jobs, AGU Career Center (web search)
  Fellowships:     Zintellect/ORISE, NRC RAP, NIEHS T32 (web search)
  Local postdocs:  Emory, GSU, KSU (web search)
  Conferences/CFAs: Web search
  Email:           Gmail SMTP
"""

import os, ssl, smtplib, datetime, json, urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import anthropic
import requests

# ── CONFIG ────────────────────────────────────────────────────────────────────

RECIPIENT_EMAIL      = "tonyboever@gmail.com"
SENDER_EMAIL         = "tonyboever@gmail.com"
INDEED_MCP_URL       = "https://mcp.indeed.com/claude/mcp"
ZIPRECRUITER_MCP_URL = "https://api.ziprecruiter.com/mcp"
USAJOBS_API_URL      = "https://data.usajobs.gov/api/Search"

SOUTHEAST_STATES = {
    "GA","FL","SC","NC","TN","AL","MS","LA","AR","VA","KY",
    "Georgia","Florida","South Carolina","North Carolina","Tennessee",
    "Alabama","Mississippi","Louisiana","Arkansas","Virginia","Kentucky",
    "Atlanta","Orlando","Charlotte","Nashville","Raleigh","Durham",
    "Chattanooga","Savannah","Jacksonville","Tampa","Alpharetta","Duluth",
}

# Priority employer direct links
PRIORITY_EMPLOYERS = [
    {"name":"Life Cycle Geo","url":"https://www.lifecyclegeo.com/jobs/","note":"Small firm — check manually"},
    {"name":"Geosyntec Consultants — All Atlanta & Kennesaw Jobs","url":"https://careers-geosyntec.icims.com/jobs/search?ss=1&searchLocation=Atlanta%2C+Georgia&searchLocationState=GA&searchLocationCity=Atlanta","note":"All open roles at Atlanta + Kennesaw offices — broadened per contact's advice"},
    {"name":"Josh's Water Jobs — Geochemist & Remediation","url":"https://www.joshswaterjobs.com/jobs/?q=geochemist+remediation","note":"Niche board, curated weekly — international included"},
    {"name":"AGU Career Center — Geochemistry","url":"https://findajob.agu.org/jobs/geochemistry/","note":"Academic & research jobs, postdocs — highly relevant"},
    {"name":"Zintellect / ORISE Opportunities","url":"https://www.zintellect.com/Catalog","note":"DOE, EPA, CDC, ATSDR, NIH fellowships & postdocs"},
    {"name":"NRC Research Associateship Programs","url":"https://nrc58.nas.edu/RAPLab10/Opportunity/Programs.aspx","note":"Postdocs at federal labs — deadlines Feb/May/Aug/Nov 1"},
]

# Academic postdoc portals — always shown as direct links
ACADEMIC_POSTDOC_LINKS = [
    {"name":"Emory University Jobs","url":"https://emory.jobs/jobs/?search=postdoc+environmental","note":"Filter for environmental/science postdocs"},
    {"name":"Georgia State University — Faculty & Research","url":"https://facultycareers.gsu.edu/postings/search","note":"Search 'postdoctoral' or 'research associate'"},
    {"name":"Kennesaw State University — Careers","url":"https://www.kennesaw.edu/human-resources/careers/index.php","note":"KSU posts postdocs as staff through OneUSG"},
]

# Government agency portals — always shown as direct links
GOVT_PORTAL_LINKS = [
    {"name":"USGS Jobs on USAJobs","url":"https://www.usajobs.gov/Search/Results?d=IN&j=1340%2C0499%2C1301&p=1","note":"Hydrologist, Physical Scientist, Life Scientist series"},
    {"name":"CDC / ATSDR Jobs on USAJobs","url":"https://www.usajobs.gov/Search/Results?d=HE&j=1340%2C0499%2C1301&p=1","note":"HHS/CDC/ATSDR — environmental health scientist roles"},
    {"name":"EPA Jobs on USAJobs","url":"https://www.usajobs.gov/Search/Results?d=EP&j=1340%2C0499%2C1301&p=1","note":"Environmental scientist / physical scientist / chemist"},
    {"name":"NIEHS (NIH) Jobs on USAJobs","url":"https://www.usajobs.gov/Search/Results?d=HE&l=Research+Triangle+Park%2C+NC&j=1340%2C0499&p=1","note":"National Institute of Environmental Health Sciences"},
]

# Standing reminders — auto-expire when end date passes
STANDING_REMINDERS = [
    {"label":"⭐ Georgia Environmental Conference — Jekyll Island, GA","start":datetime.date(2026,8,19),"end":datetime.date(2026,8,21),"note":"Southeast's largest env. conference. Register by Aug 18. georgiaenet.com","southeast":True},
    {"label":"⚠️ AGU26 Abstract Deadline","start":datetime.date(2026,8,5),"end":datetime.date(2026,8,5),"note":"Submit to Earth & Environmental Sciences sessions. agu.confex.com","southeast":False},
    {"label":"NRC RAP Next Deadline","start":datetime.date(2026,8,1),"end":datetime.date(2026,8,1),"note":"NRC Research Associateship — federal lab postdocs. nas.edu/rap","southeast":False},
    {"label":"AEG Annual Meeting — Chattanooga, TN","start":datetime.date(2026,9,13),"end":datetime.date(2026,9,19),"note":"Easy drive from Atlanta. 120+ presentations, networking. aegannualmeeting.org","southeast":True},
    {"label":"A&WMA Science of PFAS — Durham, NC","start":datetime.date(2026,9,22),"end":datetime.date(2026,9,24),"note":"Practitioners + regulators. Drivable from Atlanta. awma.org/pfas","southeast":True},
    {"label":"AVIP Vapor Intrusion Conference — Orlando, FL","start":datetime.date(2026,10,11),"end":datetime.date(2026,10,14),"note":"Contaminant fate/transport. State regulators present. viconference.vaporintrusion.org","southeast":True},
    {"label":"SETAC North America — Montreal","start":datetime.date(2026,11,2),"end":datetime.date(2026,11,5),"note":"Exposure science + contaminant bioavailability. setac.org","southeast":False},
    {"label":"NRC RAP Next Deadline","start":datetime.date(2026,11,1),"end":datetime.date(2026,11,1),"note":"NRC Research Associateship — federal lab postdocs. nas.edu/rap","southeast":False},
]

# ── USAJOBS API ───────────────────────────────────────────────────────────────

def search_usajobs(usajobs_key, keyword, organization_codes, max_results=5):
    """Query the USAJobs API for a keyword + agency combination."""
    headers = {
        "Host": "data.usajobs.gov",
        "User-Agent": RECIPIENT_EMAIL,
        "Authorization-Key": usajobs_key,
    }
    params = {
        "Keyword": keyword,
        "OrganizationID": organization_codes,
        "ResultsPerPage": max_results,
        "SortField": "OpenDate",
        "SortDirection": "Desc",
    }
    try:
        r = requests.get(USAJOBS_API_URL, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        items = data.get("SearchResult", {}).get("SearchResultItems", [])
        results = []
        for item in items:
            d = item.get("MatchedObjectDescriptor", {})
            locations = d.get("PositionLocationDisplay", "")
            low  = d.get("PositionRemuneration", [{}])[0].get("MinimumRange", "")
            high = d.get("PositionRemuneration", [{}])[0].get("MaximumRange", "")
            salary = f"${int(float(low)):,}–${int(float(high)):,}" if low and high else "See posting"
            is_se = any(s in locations for s in SOUTHEAST_STATES)
            results.append({
                "title":     d.get("PositionTitle", ""),
                "org":       d.get("OrganizationName", "") or d.get("DepartmentName", ""),
                "location":  locations,
                "salary":    salary,
                "date":      d.get("PublicationStartDate", "")[:10],
                "url":       d.get("PositionURI", d.get("ApplyURI", ["#"])[0] if d.get("ApplyURI") else "#"),
                "southeast": is_se,
            })
        return results
    except Exception as e:
        print(f"USAJobs error ({keyword}): {e}")
        return []

def search_all_govt_jobs(usajobs_key):
    """Run targeted USAJobs searches across relevant agencies."""
    results = []
    seen = set()

    searches = [
        # (keyword, org_code_string)  — org codes: IN=Interior(USGS), HE=HHS(CDC/ATSDR/NIH), EP=EPA, DJ=DOE
        ("geochemist OR hydrogeologist OR environmental scientist",   "IN"),   # USGS
        ("environmental scientist OR toxicologist OR epidemiologist", "HE"),   # CDC/ATSDR/NIEHS
        ("environmental scientist OR geochemist OR chemist",          "EP"),   # EPA
        ("environmental scientist OR geochemist OR hydrogeologist",   "DJ"),   # DOE
    ]

    for keyword, org in searches:
        items = search_usajobs(usajobs_key, keyword, org, max_results=5)
        for item in items:
            key = (item["title"], item["org"])
            if key not in seen:
                seen.add(key)
                results.append(item)

    return results

# ── INDUSTRY JOBS VIA INDEED + ZIPRECRUITER MCP ──────────────────────────────

def search_industry_jobs(api_key):
    """Search Indeed + ZipRecruiter via Anthropic MCP."""
    client = anthropic.Anthropic(api_key=api_key)
    prompt = """Search for full-time jobs for this candidate:
- PhD Environmental Geochemistry, Georgia Tech (May 2026)
- Skills: redox biogeochemistry, PFAS, groundwater remediation, contaminant cycling,
  in situ remediation (ISCO/ISCR, bioaugmentation), ICP-MS, PHREEQC, field science
- Location: Atlanta, GA — open to remote, hybrid, or Southeast US
- Contact at Geosyntec advised broadening beyond just science titles to get in the door

Run these searches:
1. Indeed: search "Geosyntec" in "Atlanta, GA" — return ALL open roles, any title
2. Indeed: search "Geosyntec" in "Kennesaw, GA" — return ALL open roles, any title
3. Indeed: search "environmental scientist remediation" in "Atlanta, GA" fulltime
4. ZipRecruiter: search "environmental scientist" in "Atlanta, GA" full-time physical/remote/hybrid
5. ZipRecruiter: search "geochemist remediation" in "Atlanta, GA" full-time

For searches 1 and 2 (Geosyntec): include every result regardless of job title — the goal
is to see all openings at those two offices. Flag each with company="Geosyntec Consultants".

For searches 3-5: return the most relevant results. Prioritize: Arcadis, AECOM, Ramboll,
Haley & Aldrich, Stantec, Tetra Tech, REGENESIS. Exclude results older than 60 days.

Return up to 12 total results (no duplicates across all searches).

Each item: title, company, location, salary (string or "Not listed"), days_ago (int),
url (exact from tool), southeast (bool: GA/FL/SC/NC/TN/AL/MS/LA/VA/KY).
Return ONLY a JSON array."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        mcp_servers=[
            {"type":"url","url":INDEED_MCP_URL,"name":"indeed"},
            {"type":"url","url":ZIPRECRUITER_MCP_URL,"name":"ziprecruiter"},
        ],
        messages=[{"role":"user","content":prompt}],
    )
    return _parse_json(response, "industry jobs")

# ── WEB SEARCH: NICHE BOARDS, FELLOWSHIPS, LOCAL POSTDOCS, CONFERENCES ───────

def build_search_years():
    now = datetime.date.today()
    y = now.year
    return f"{y} OR {y+1}" if now.month >= 10 else str(y)

def search_web_opportunities(api_key):
    """Single comprehensive web search covering all niche/fellowship/academic/conference sources."""
    client = anthropic.Anthropic(api_key=api_key)
    years  = build_search_years()
    today  = datetime.date.today().strftime("%B %d, %Y")

    prompt = f"""Today is {today}. You are searching for opportunities for an environmental
geochemist. PhD Environmental Geochemistry, Georgia Tech (May 2026). Skills: redox
biogeochemistry, contaminant cycling, PFAS, uranium/trace metals, groundwater remediation,
in situ remediation (ISCO/ISCR, bioaugmentation), ICP-MS, PHREEQC, field science leadership,
data analysis (MATLAB, wavelet analysis). Location: Atlanta, GA. Open to international
opportunities for once-in-a-lifetime roles.

Run ALL of these searches — do not skip any:

CONFERENCES & CFAs:
1. "environmental remediation conference {years} southeast"
2. "NGWA AEHS Battelle PFAS conference {years}"
3. "call for abstracts environmental geochemistry biogeochemistry remediation {years}"

NICHE JOB BOARDS (international OK for these):
4. site:joshswaterjobs.com geochemist OR biogeochemistry OR remediation OR PFAS {years}
5. site:findajob.agu.org geochemistry OR biogeochemistry OR remediation OR "environmental science" {years}

FELLOWSHIP & POSTDOC PROGRAMS:
6. site:zintellect.com geochemistry OR biogeochemistry OR remediation OR PFAS OR "environmental science" postdoc {years}
7. "NRC Research Associateship" geochemistry OR biogeochemistry OR "environmental science" OR remediation {years}
8. NIEHS postdoc fellowship "environmental health" OR "exposure science" OR geochemistry {years}
9. ORISE fellowship postdoc EPA OR "ATSDR" OR CDC geochemistry OR "environmental science" {years}
10. "Emory T32" OR "T32 environmental" OR "T32 exposure" postdoc fellowship {years}

LOCAL ACADEMIC POSTDOCS (Atlanta-area universities):
11. "postdoc" OR "postdoctoral" "environmental geochemistry" OR "biogeochemistry" OR "contaminant" OR "PFAS" OR "remediation" "Emory University" OR "Georgia State University" OR "Kennesaw State" {years}

Return a JSON array. Use these types:
  "conference"     — upcoming event not yet occurred as of {today}
  "cfa"            — call for abstracts with future deadline
  "job_jwj"        — job from joshswaterjobs.com (any country)
  "job_agu"        — job from AGU Career Center
  "fellowship"     — Zintellect/ORISE, NRC RAP, NIEHS, T32, or similar fellowship/postdoc program
  "postdoc_local"  — postdoc at Emory, GSU, or KSU matching researcher background

Filter postdoc_local strictly: only include if the role is clearly in environmental
geochemistry, biogeochemistry, contaminant science, exposure science, or water quality.
Exclude medical, clinical, social science, and ecology postdocs.

Each item:
  type, title, org, location, date, desc (1-2 sentences on relevance), url, southeast (bool)

Return ONLY the JSON array. No markdown, no explanation."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        tools=[{"type":"web_search_20250305","name":"web_search"}],
        messages=[{"role":"user","content":prompt}],
    )
    return _parse_json(response, "web opportunities")

# ── HELPERS ───────────────────────────────────────────────────────────────────

def _parse_json(response, label):
    raw = ""
    for block in response.content:
        if hasattr(block, "text"):
            raw += block.text
    raw = raw.strip().replace("```json","").replace("```","").strip()
    s, e = raw.find("["), raw.rfind("]")
    if s == -1 or e == -1:
        print(f"Warning: no JSON in {label} response. Raw: {raw[:300]}")
        return []
    try:
        return json.loads(raw[s:e+1])
    except json.JSONDecodeError as err:
        print(f"JSON error in {label}: {err}\nRaw: {raw[s:s+300]}")
        return []

def get_upcoming_reminders():
    today = datetime.date.today()
    soon  = today + datetime.timedelta(days=14)
    result = []
    seen = set()
    for r in STANDING_REMINDERS:
        key = r["label"]
        if r["end"] >= today and key not in seen:
            seen.add(key)
            r = dict(r)
            r["imminent"] = r["start"] <= soon
            result.append(r)
    return result

# ── EMAIL BUILDER ─────────────────────────────────────────────────────────────

def badge(text, color):
    colors = {"red":("fff0f0","c0392b"),"green":("f0fff4","27ae60"),"blue":("e8f0fe","1a56db"),"purple":("f3e8ff","6d28d9")}
    bg, fg = colors.get(color, ("f0f0f0","333"))
    return f"<span style='background:#{bg};color:#{fg};font-size:11px;padding:2px 8px;border-radius:99px;font-weight:600;margin-right:4px;'>{text}</span>"

def job_card(job):
    is_se = job.get("southeast") or any(s in job.get("location","") for s in SOUTHEAST_STATES)
    priority_cos = ["geosyntec","arcadis","aecom","ramboll","haley","stantec","tetra tech","regenesis"]
    is_p = any(p in job.get("company","").lower() for p in priority_cos)
    b = (badge("⭐ Priority","red") if is_p else "") + (badge("📍 Southeast","green") if is_se else "")
    days_str = f"{job.get('days_ago')}d ago" if job.get("days_ago") is not None else ""
    meta = " · ".join(filter(None,[job.get("company"),job.get("location"),job.get("salary",""),days_str]))
    return (f"<div style='margin-bottom:12px;padding:12px 14px;background:#fafafa;border:1px solid #e8e8e8;border-radius:6px;'>"
            f"{'<div style=margin-bottom:5px>'+b+'</div>' if b else ''}"
            f"<p style='margin:0 0 3px;font-size:14px;font-weight:600;'><a href='{job.get('url','#')}' style='color:#1a56db;text-decoration:none;'>{job.get('title','')}</a></p>"
            f"<p style='margin:0;font-size:12px;color:#888;'>{meta}</p></div>")

def govt_card(job):
    is_se = job.get("southeast")
    b = (badge("📍 Southeast","green") if is_se else "")
    meta = " · ".join(filter(None,[job.get("org"),job.get("location"),job.get("salary",""),job.get("date","")]))
    return (f"<div style='margin-bottom:12px;padding:12px 14px;background:#fafafa;border:1px solid #e8e8e8;border-radius:6px;'>"
            f"{'<div style=margin-bottom:5px>'+b+'</div>' if b else ''}"
            f"<p style='margin:0 0 3px;font-size:14px;font-weight:600;'><a href='{job.get('url','#')}' style='color:#1a56db;text-decoration:none;'>{job.get('title','')}</a></p>"
            f"<p style='margin:0;font-size:12px;color:#888;'>{meta}</p></div>")

def result_card(item):
    is_se = item.get("southeast")
    b = badge("📍 Southeast","green") if is_se else ""
    meta = " · ".join(filter(None,[item.get("org"),item.get("location"),item.get("date")]))
    return (f"<div style='margin-bottom:12px;padding:12px 14px;background:#fafafa;border:1px solid #e8e8e8;border-radius:6px;'>"
            f"{'<div style=margin-bottom:5px>'+b+'</div>' if b else ''}"
            f"<p style='margin:0 0 3px;font-size:14px;font-weight:600;'><a href='{item.get('url','#')}' style='color:#1a56db;text-decoration:none;'>{item.get('title','')}</a></p>"
            f"<p style='margin:0 0 4px;font-size:12px;color:#888;'>{meta}</p>"
            f"<p style='margin:0;font-size:13px;color:#555;line-height:1.5;'>{item.get('desc','')}</p></div>")

def portal_link(e):
    return (f"<div style='margin-bottom:8px;padding:8px 14px;background:#fafafa;border:1px solid #e8e8e8;border-radius:6px;'>"
            f"<p style='margin:0 0 2px;font-size:13px;font-weight:600;'><a href='{e['url']}' style='color:#1a56db;text-decoration:none;'>{e['name']} →</a></p>"
            f"<p style='margin:0;font-size:12px;color:#555;'>{e['note']}</p></div>")

def section_header(title):
    return f"<h2 style='font-size:15px;font-weight:600;color:#1a1a1a;border-bottom:1px solid #e0e0e0;padding-bottom:6px;margin:24px 0 12px;'>{title}</h2>"

def build_html(today_str, industry_jobs, govt_jobs, web_results, reminders):
    confs         = [r for r in web_results if r.get("type") == "conference"]
    cfas          = [r for r in web_results if r.get("type") == "cfa"]
    jwj_jobs      = [r for r in web_results if r.get("type") == "job_jwj"]
    agu_jobs      = [r for r in web_results if r.get("type") == "job_agu"]
    fellowships   = [r for r in web_results if r.get("type") == "fellowship"]
    postdoc_local = [r for r in web_results if r.get("type") == "postdoc_local"]

    html = (f"<!DOCTYPE html><html><body style=\"font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;max-width:640px;margin:0 auto;padding:20px;color:#1a1a1a;\">"
            f"<div style='border-bottom:2px solid #1a56db;padding-bottom:12px;margin-bottom:20px;'>"
            f"<h1 style='font-size:18px;font-weight:600;margin:0;'>Daily Opportunity Digest</h1>"
            f"<p style='font-size:13px;color:#666;margin:4px 0 0;'>{today_str} &nbsp;·&nbsp; Environmental Geochemistry | Remediation | Biogeochemistry</p></div>")

    # Priority employer links
    html += section_header("⭐ Priority Employers & Programs — Check Today")
    for e in PRIORITY_EMPLOYERS:
        html += portal_link(e)

    # Industry jobs
    html += section_header("💼 Industry Jobs — Indeed & ZipRecruiter")
    if industry_jobs:
        def sort_key(j):
            co = j.get("company","").lower()
            if "geosyntec" in co: tier = 0
            elif any(p in co for p in ["arcadis","aecom","ramboll","haley","stantec","tetra tech","regenesis"]): tier = 1
            else: tier = 2
            return (tier, j.get("days_ago") or 99)
        for job in sorted(industry_jobs, key=sort_key):
            html += job_card(job)
    else:
        html += "<p style='font-size:13px;color:#888;'>No new postings found today.</p>"

    # Government jobs
    html += section_header("🏛 Government Jobs — USAJobs (USGS · CDC/ATSDR · EPA · DOE · NIEHS)")
    html += "<p style='font-size:12px;color:#888;margin:0 0 10px;'>Check portals directly:</p>"
    for e in GOVT_PORTAL_LINKS:
        html += portal_link(e)
    if govt_jobs:
        html += "<p style='font-size:12px;color:#888;margin:10px 0 8px;'>Found via API today:</p>"
        for job in govt_jobs:
            html += govt_card(job)

    # Niche boards
    if jwj_jobs:
        html += section_header("💧 Josh's Water Jobs (International)")
        for item in jwj_jobs:
            html += result_card(item)
    if agu_jobs:
        html += section_header("🔬 AGU Career Center")
        for item in agu_jobs:
            html += result_card(item)

    # Fellowships
    html += section_header("🏅 Fellowships & Postdoc Programs")
    if fellowships:
        for item in fellowships:
            html += result_card(item)
    else:
        html += "<p style='font-size:13px;color:#888;'>No new fellowship postings found today — check Zintellect and NRC RAP links above.</p>"

    # Local academic postdocs
    html += section_header("🎓 Local Academic Postdocs (Emory · GSU · KSU)")
    html += "<p style='font-size:12px;color:#888;margin:0 0 10px;'>Check portals directly:</p>"
    for e in ACADEMIC_POSTDOC_LINKS:
        html += portal_link(e)
    if postdoc_local:
        html += "<p style='font-size:12px;color:#888;margin:10px 0 8px;'>Found today:</p>"
        for item in postdoc_local:
            html += result_card(item)

    # Conferences
    if confs:
        html += section_header("🏭 Conferences & Industry Events")
        for item in confs:
            html += result_card(item)

    # CFAs
    if cfas:
        html += section_header("📋 Calls for Abstracts")
        for item in cfas:
            html += result_card(item)

    # Standing reminders
    if reminders:
        html += section_header("📌 Upcoming Calendar Reminders")
        html += "<div style='background:#fffbea;border-left:3px solid #d4a017;padding:12px 16px;border-radius:4px;'>"
        for r in reminders:
            b = (badge("Soon","red") if r["imminent"] else "") + (badge("Southeast","green") if r["southeast"] else "")
            date_str = r["start"].strftime("%b %-d")
            date_str += f"–{r['end'].strftime('%-d, %Y')}" if r["start"] != r["end"] else f", {r['start'].year}"
            html += (f"<p style='margin:6px 0;font-size:13px;'>{b}<strong>{r['label']}</strong> &nbsp;·&nbsp; {date_str}<br>"
                     f"<span style='color:#666;font-size:12px;'>{r['note']}</span></p>")
        html += "</div>"

    html += ("<div style='margin-top:32px;padding-top:12px;border-top:1px solid #e0e0e0;font-size:11px;color:#999;'>"
             "Automated · Indeed+ZipRecruiter+USAJobs+Web Search · Edit digest.py to update</div></body></html>")
    return html

# ── EMAIL SENDER ──────────────────────────────────────────────────────────────

def send_email(html_body, subject, gmail_app_password):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_body, "html"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
        s.login(SENDER_EMAIL, gmail_app_password)
        s.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
    print(f"✅ Digest sent to {RECIPIENT_EMAIL}")

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    anthropic_key      = os.environ["ANTHROPIC_API_KEY"]
    gmail_app_password = os.environ["GMAIL_APP_PASSWORD"]
    usajobs_key        = os.environ.get("USAJOBS_API_KEY", "")

    today_str = datetime.date.today().strftime("%A, %B %-d, %Y")
    subject   = f"Opportunity Digest — {today_str}"

    print("Searching industry jobs (Indeed + ZipRecruiter)...")
    industry_jobs = search_industry_jobs(anthropic_key)
    print(f"  {len(industry_jobs)} results")

    print("Searching government jobs (USAJobs API)...")
    govt_jobs = search_all_govt_jobs(usajobs_key) if usajobs_key else []
    print(f"  {len(govt_jobs)} results" + (" (no USAJobs key set)" if not usajobs_key else ""))

    print("Running web search (niche boards, fellowships, local postdocs, conferences)...")
    web_results = search_web_opportunities(anthropic_key)
    print(f"  {len(web_results)} results")

    print("Filtering reminders...")
    reminders = get_upcoming_reminders()

    print("Building and sending email...")
    html = build_html(today_str, industry_jobs, govt_jobs, web_results, reminders)
    send_email(html, subject, gmail_app_password)

if __name__ == "__main__":
    main()
