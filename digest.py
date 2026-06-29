"""
Boever Daily Opportunity Digest
Cost: <<$0.10/day

Sources (ALL FREE - no Anthropic API cost):
  - USAJobs API:        USGS, EPA, CDC/ATSDR, DOE, NIEHS jobs
  - Josh's Water Jobs:  Direct page fetch + parse
  - Geosyntec iCIMS:    Direct page fetch + parse (Atlanta + Kennesaw)
  - Life Cycle Geo:     Direct page fetch + parse
  - AGU Career Center:  Direct page fetch + parse

Sources (ONE Anthropic API call ~$0.02-0.05 total):
  - Conferences + calls for abstracts only

Email: Gmail SMTP (free)
"""

import os, ssl, smtplib, datetime, json, re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import anthropic
import requests
from bs4 import BeautifulSoup

# ── CONFIG ────────────────────────────────────────────────────────────────────

RECIPIENT_EMAIL  = "tonyboever@gmail.com"
SENDER_EMAIL     = "tonyboever@gmail.com"
USAJOBS_API_URL  = "https://data.usajobs.gov/api/Search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

SOUTHEAST = {
    "GA","FL","SC","NC","TN","AL","MS","LA","AR","VA","KY",
    "Georgia","Florida","South Carolina","North Carolina","Tennessee",
    "Alabama","Mississippi","Louisiana","Arkansas","Virginia","Kentucky",
    "Atlanta","Orlando","Charlotte","Nashville","Raleigh","Durham",
    "Chattanooga","Savannah","Jacksonville","Tampa","Alpharetta","Duluth",
    "Kennesaw",
}

# Standing reminders — auto-expire when end date passes
STANDING_REMINDERS = [
    {"label":"⭐ Georgia Environmental Conference — Jekyll Island, GA","start":datetime.date(2026,8,19),"end":datetime.date(2026,8,21),"note":"Southeast's largest env. conference. Register by Aug 18. georgiaenet.com","southeast":True},
    {"label":"⚠️ AGU26 Abstract Deadline","start":datetime.date(2026,8,5),"end":datetime.date(2026,8,5),"note":"Submit to Earth & Environmental Sciences sessions. agu.confex.com","southeast":False},
    {"label":"NRC RAP Deadline","start":datetime.date(2026,8,1),"end":datetime.date(2026,8,1),"note":"NRC Research Associateship — postdocs at federal labs. nas.edu/rap","southeast":False},
    {"label":"AEG Annual Meeting — Chattanooga, TN","start":datetime.date(2026,9,13),"end":datetime.date(2026,9,19),"note":"Easy drive from Atlanta. 120+ presentations. aegannualmeeting.org","southeast":True},
    {"label":"A&WMA Science of PFAS — Durham, NC","start":datetime.date(2026,9,22),"end":datetime.date(2026,9,24),"note":"Practitioners + regulators. Drivable from Atlanta. awma.org/pfas","southeast":True},
    {"label":"AVIP Vapor Intrusion — Orlando, FL","start":datetime.date(2026,10,11),"end":datetime.date(2026,10,14),"note":"Contaminant fate/transport. viconference.vaporintrusion.org","southeast":True},
    {"label":"NRC RAP Deadline","start":datetime.date(2026,11,1),"end":datetime.date(2026,11,1),"note":"NRC Research Associateship — postdocs at federal labs. nas.edu/rap","southeast":False},
    {"label":"SETAC North America — Montreal","start":datetime.date(2026,11,2),"end":datetime.date(2026,11,5),"note":"Exposure science + contaminant bioavailability. setac.org","southeast":False},
]

# ── FREE FETCHERS ─────────────────────────────────────────────────────────────

def fetch_lifecyclegeo():
    """Fetch Life Cycle Geo jobs page."""
    url = "https://www.lifecyclegeo.com/jobs/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(" ", strip=True).lower()
        if "no open positions" in text or "no current" in text:
            return [{"title":"No current openings","org":"Life Cycle Geo","location":"","date":"","url":url,"note":"Check back regularly — small firm, posts infrequently"}]
        # Try to find job listings
        jobs = []
        for tag in soup.find_all(["h2","h3","h4","li","a"], limit=50):
            t = tag.get_text(strip=True)
            if len(t) > 10 and any(kw in t.lower() for kw in ["geochemist","scientist","engineer","hydrogeolog","analyst","technician","postdoc","researcher"]):
                href = tag.get("href","") if tag.name == "a" else ""
                jobs.append({"title":t,"org":"Life Cycle Geo","location":"","date":"","url":href or url,"note":""})
        if not jobs:
            return [{"title":"Page live — review manually","org":"Life Cycle Geo","location":"","date":"","url":url,"note":"No structured job listings detected"}]
        return jobs[:5]
    except Exception as e:
        return [{"title":f"Could not reach page: {e}","org":"Life Cycle Geo","location":"","date":"","url":url,"note":""}]


def fetch_geosyntec():
    """Fetch all Geosyntec jobs in Atlanta + Kennesaw via Google search (iCIMS blocks direct fetch)."""
    results = []
    seen = set()
    for city in ["Atlanta", "Kennesaw"]:
        try:
            # Use site: search to get iCIMS listings for each city
            search_url = f"https://careers-geosyntec.icims.com/jobs/search?ss=1&searchLocation={city}%2C+Georgia&searchLocationState=GA&searchLocationCity={city}"
            r = requests.get(search_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")
            # iCIMS job listings are in anchor tags with /jobs/<id>/<title>/job pattern
            for a in soup.find_all("a", href=re.compile(r"/jobs/\d+/.+/job")):
                title = a.get_text(strip=True)
                href  = "https://careers-geosyntec.icims.com" + a["href"] if a["href"].startswith("/") else a["href"]
                if title and href not in seen:
                    seen.add(href)
                    results.append({"title":title,"org":"Geosyntec Consultants","location":f"{city}, GA","date":"","url":href,"note":"All roles — broadened per contact's advice"})
        except Exception as e:
            print(f"Geosyntec {city} fetch error: {e}")

    if not results:
        results.append({
            "title": "Visit portal to view all Atlanta + Kennesaw openings",
            "org":   "Geosyntec Consultants",
            "location": "Atlanta + Kennesaw, GA",
            "date":  "",
            "url":   "https://careers-geosyntec.icims.com/jobs/search?ss=1&searchLocation=Atlanta%2C+Georgia",
            "note":  "Direct fetch blocked — click to view live listings"
        })
    return results


def fetch_joshs_water_jobs():
    """Fetch and parse Josh's Water Jobs listings."""
    keywords = ["geochemist","biogeochemistry","remediation","pfas","contaminant",
                "hydrogeolog","groundwater","sediment","environmental scientist",
                "geologist","exposure","toxicolog"]
    url = "https://www.joshswaterjobs.com/jobs/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        seen = set()
        # JWJ uses a table with rows containing job info
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if not cells:
                continue
            link = row.find("a", href=re.compile(r"/jobs/\d+"))
            if not link:
                continue
            title    = link.get_text(strip=True)
            job_url  = "https://www.joshswaterjobs.com" + link["href"] if link["href"].startswith("/") else link["href"]
            full_text = row.get_text(" ", strip=True).lower()
            if job_url in seen:
                continue
            if any(kw in title.lower() or kw in full_text for kw in keywords):
                seen.add(job_url)
                # Extract org and location from the row text
                spans = row.find_all(["strong","span","td"])
                org  = spans[1].get_text(strip=True) if len(spans) > 1 else ""
                loc  = ""
                date_added = ""
                tds = row.find_all("td")
                if len(tds) >= 2:
                    loc = tds[0].get_text(" ", strip=True).replace(title,"").strip()
                    loc = re.sub(r'\s+',' ', loc).strip()
                if len(tds) >= 3:
                    date_added = tds[1].get_text(strip=True)
                is_se = any(s in loc for s in SOUTHEAST)
                results.append({
                    "title":     title,
                    "org":       org,
                    "location":  loc,
                    "date":      date_added,
                    "url":       job_url,
                    "southeast": is_se,
                })
        return results[:10]
    except Exception as e:
        print(f"JWJ fetch error: {e}")
        return []


def fetch_agu_jobs():
    """Fetch AGU Career Center listings for relevant keywords."""
    keywords = ["geochemist","biogeochemistry","remediation","contaminant",
                "hydrogeolog","groundwater","environmental scientist","geologist"]
    url = "https://findajob.agu.org/jobs/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        seen = set()
        for a in soup.find_all("a", href=True):
            title = a.get_text(strip=True)
            if len(title) < 5:
                continue
            href = a["href"]
            if href in seen:
                continue
            if any(kw in title.lower() for kw in keywords):
                seen.add(href)
                if not href.startswith("http"):
                    href = "https://findajob.agu.org" + href
                # Try to get org/location from surrounding context
                parent = a.find_parent(["li","div","tr","article"])
                context = parent.get_text(" ", strip=True) if parent else ""
                context = context.replace(title,"").strip()[:120]
                results.append({
                    "title":     title,
                    "org":       "",
                    "location":  context,
                    "date":      "",
                    "url":       href,
                    "southeast": any(s in context for s in SOUTHEAST),
                })
        return results[:8]
    except Exception as e:
        print(f"AGU fetch error: {e}")
        return []


# ── USAJOBS API (FREE) ────────────────────────────────────────────────────────

def fetch_usajobs(key):
    """Query USAJobs API for relevant federal jobs. Free, no token cost."""
    if not key:
        print("No USAJobs key — skipping government jobs")
        return []

    searches = [
        ("geochemist OR hydrogeologist", "IN"),   # USGS (Interior)
        ("environmental scientist OR toxicologist OR epidemiologist", "HE"),  # CDC/ATSDR/NIH
        ("environmental scientist OR geochemist", "EP"),   # EPA
        ("environmental scientist OR geochemist", "DJ"),   # DOE
    ]

    results = []
    seen = set()

    for keyword, org_code in searches:
        try:
            r = requests.get(
                USAJOBS_API_URL,
                headers={
                    "Host":              "data.usajobs.gov",
                    "User-Agent":        RECIPIENT_EMAIL,
                    "Authorization-Key": key,
                },
                params={
                    "Keyword":         keyword,
                    "OrganizationID":  org_code,
                    "ResultsPerPage":  5,
                    "SortField":       "OpenDate",
                    "SortDirection":   "Desc",
                },
                timeout=15,
            )
            r.raise_for_status()
            items = r.json().get("SearchResult", {}).get("SearchResultItems", [])
            for item in items:
                d    = item.get("MatchedObjectDescriptor", {})
                key_ = d.get("PositionTitle","") + d.get("OrganizationName","")
                if key_ in seen:
                    continue
                seen.add(key_)
                loc  = d.get("PositionLocationDisplay","")
                low  = d.get("PositionRemuneration",[{}])[0].get("MinimumRange","")
                high = d.get("PositionRemuneration",[{}])[0].get("MaximumRange","")
                salary = f"${int(float(low)):,}–${int(float(high)):,}" if low and high else "See posting"
                apply_urls = d.get("ApplyURI", [])
                apply_url  = apply_urls[0] if apply_urls else d.get("PositionURI","#")
                results.append({
                    "title":     d.get("PositionTitle",""),
                    "org":       d.get("OrganizationName","") or d.get("DepartmentName",""),
                    "location":  loc,
                    "salary":    salary,
                    "date":      d.get("PublicationStartDate","")[:10],
                    "url":       apply_url,
                    "southeast": any(s in loc for s in SOUTHEAST),
                })
        except Exception as e:
            print(f"USAJobs error ({org_code}): {e}")

    return results


# ── ONE ANTHROPIC CALL: CONFERENCES + CFAs ONLY ───────────────────────────────

def fetch_conferences_and_cfas(api_key):
    """
    Single Anthropic API call for conferences and CFAs only.
    This is the only call that costs money — kept minimal.
    """
    client = anthropic.Anthropic(api_key=api_key)
    years  = str(datetime.date.today().year)
    if datetime.date.today().month >= 10:
        years += f" OR {datetime.date.today().year + 1}"
    today  = datetime.date.today().strftime("%B %d, %Y")

    prompt = f"""Today is {today}. Search for:

1. Upcoming environmental conferences ({years}) relevant to: biogeochemistry, groundwater
   remediation, PFAS, contaminant science, exposure science. Include both industry events
   (NGWA, AEHS, Battelle, RemTEC, SETAC, A&WMA) and academic (AGU, ACS, Goldschmidt).
   Southeast US locations are preferred for in-person travel.
   Only include events that have NOT yet occurred as of today.

2. Active calls for abstracts with deadlines still in the future ({years}), relevant to
   environmental geochemistry, biogeochemistry, remediation, or PFAS.

Return a JSON array. Each item:
  type: "conference" | "cfa"
  title, org, location, date, desc (1 sentence), url
  southeast: true if in GA/FL/SC/NC/TN/AL/MS/LA/VA/KY

Return ONLY the JSON array. No markdown."""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1500,
            tools=[{"type":"web_search_20250305","name":"web_search"}],
            messages=[{"role":"user","content":prompt}],
        )
    except Exception as e:
        print(f"Anthropic API error: {e}")
        return []

    raw = ""
    for block in response.content:
        if hasattr(block, "text"):
            raw += block.text
    raw = raw.strip().replace("```json","").replace("```","").strip()
    s, e = raw.find("["), raw.rfind("]")
    if s == -1:
        return []
    try:
        return json.loads(raw[s:e+1])
    except:
        return []


# ── STANDING REMINDERS ────────────────────────────────────────────────────────

def get_reminders():
    today = datetime.date.today()
    soon  = today + datetime.timedelta(days=14)
    out, seen = [], set()
    for r in STANDING_REMINDERS:
        if r["end"] >= today and r["label"] not in seen:
            seen.add(r["label"])
            r = dict(r)
            r["imminent"] = r["start"] <= soon
            out.append(r)
    return out


# ── EMAIL BUILDER ─────────────────────────────────────────────────────────────

def badge(text, color):
    c = {"red":("fff0f0","c0392b"),"green":("f0fff4","27ae60"),"blue":("e8f0fe","1a56db")}
    bg,fg = c.get(color,("f0f0f0","333"))
    return f"<span style='background:#{bg};color:#{fg};font-size:11px;padding:2px 7px;border-radius:99px;font-weight:600;margin-right:4px;'>{text}</span>"

def card(title, org, location, salary_or_date, url, note="", badges=""):
    meta = " · ".join(filter(None,[org, location, salary_or_date]))
    return (f"<div style='margin-bottom:10px;padding:10px 14px;background:#fafafa;"
            f"border:1px solid #e8e8e8;border-radius:6px;'>"
            f"{'<div style=margin-bottom:4px>'+badges+'</div>' if badges else ''}"
            f"<p style='margin:0 0 2px;font-size:14px;font-weight:600;'>"
            f"<a href='{url}' style='color:#1a56db;text-decoration:none;'>{title}</a></p>"
            f"{'<p style=margin:0 0 2px;font-size:12px;color:#888>'+meta+'</p>' if meta else ''}"
            f"{'<p style=margin:0;font-size:12px;color:#666;font-style:italic>'+note+'</p>' if note else ''}"
            f"</div>")

def section(title):
    return (f"<h2 style='font-size:14px;font-weight:600;color:#1a1a1a;"
            f"border-bottom:1px solid #e0e0e0;padding-bottom:5px;margin:20px 0 10px;'>{title}</h2>")

def build_email(today_str, lcg, geosyntec, jwj, agu, govt, conf_cfa, reminders):
    confs = [r for r in conf_cfa if r.get("type") == "conference"]
    cfas  = [r for r in conf_cfa if r.get("type") == "cfa"]

    html = (f"<!DOCTYPE html><html><body style=\"font-family:-apple-system,BlinkMacSystemFont,"
            f"'Segoe UI',Arial,sans-serif;max-width:620px;margin:0 auto;padding:16px;color:#1a1a1a;\">"
            f"<div style='border-bottom:2px solid #1a56db;padding-bottom:10px;margin-bottom:16px;'>"
            f"<h1 style='font-size:17px;font-weight:600;margin:0;'>Daily Opportunity Digest</h1>"
            f"<p style='font-size:12px;color:#666;margin:3px 0 0;'>{today_str}</p></div>")

    # ── Life Cycle Geo
    html += section("⭐ Life Cycle Geo")
    for j in lcg:
        b = badge("Priority","red")
        html += card(j["title"], j["org"], j["location"], j["date"], j["url"], j.get("note",""), b)

    # ── Geosyntec
    html += section("⭐ Geosyntec — All Atlanta & Kennesaw Roles")
    priority_science = ["scientist","geochemist","hydrogeolog","geologist","engineer","technician","analyst","chemist","remediat"]
    science_jobs = [j for j in geosyntec if any(kw in j["title"].lower() for kw in priority_science)]
    other_jobs   = [j for j in geosyntec if j not in science_jobs]
    for j in science_jobs:
        b = badge("⭐ Science/Technical","red")
        html += card(j["title"], j["org"], j["location"], j["date"], j["url"], j.get("note",""), b)
    for j in other_jobs:
        html += card(j["title"], j["org"], j["location"], j["date"], j["url"], j.get("note",""))

    # ── Josh's Water Jobs
    html += section("💧 Josh's Water Jobs")
    if jwj:
        for j in jwj:
            b = badge("📍 Southeast","green") if j.get("southeast") else ""
            html += card(j["title"], j["org"], j["location"], j["date"], j["url"], "", b)
    else:
        html += "<p style='font-size:13px;color:#888;'>No keyword matches today — <a href='https://www.joshswaterjobs.com/jobs/'>browse all</a></p>"

    # ── AGU Career Center
    html += section("🔬 AGU Career Center")
    if agu:
        for j in agu:
            b = badge("📍 Southeast","green") if j.get("southeast") else ""
            html += card(j["title"], j["org"], j["location"], j["date"], j["url"], "", b)
    else:
        html += "<p style='font-size:13px;color:#888;'>No keyword matches today — <a href='https://findajob.agu.org/jobs/'>browse all</a></p>"

    # ── Government Jobs
    html += section("🏛 Government Jobs (USGS · EPA · CDC/ATSDR · DOE · NIEHS)")
    if govt:
        for j in govt:
            b = badge("📍 Southeast","green") if j.get("southeast") else ""
            html += card(j["title"], j["org"], j["location"], j.get("salary",""), j["url"], "", b)
    else:
        html += ("<p style='font-size:13px;color:#888;'>No results today. Browse directly: "
                 "<a href='https://www.usajobs.gov/Search/Results?d=IN'>USGS</a> · "
                 "<a href='https://www.usajobs.gov/Search/Results?d=HE'>CDC/ATSDR</a> · "
                 "<a href='https://www.usajobs.gov/Search/Results?d=EP'>EPA</a> · "
                 "<a href='https://www.usajobs.gov/Search/Results?d=DJ'>DOE</a></p>")

    # ── Conferences
    if confs:
        html += section("🏭 Conferences & Events")
        for c in confs:
            b = badge("📍 Southeast","green") if c.get("southeast") else ""
            html += card(c["title"], c.get("org",""), c.get("location",""), c.get("date",""), c.get("url","#"), c.get("desc",""), b)

    # ── CFAs
    if cfas:
        html += section("📋 Calls for Abstracts")
        for c in cfas:
            html += card(c["title"], c.get("org",""), c.get("location",""), c.get("date",""), c.get("url","#"), c.get("desc",""))

    # ── Reminders
    if reminders:
        html += section("📌 Upcoming Reminders")
        html += "<div style='background:#fffbea;border-left:3px solid #d4a017;padding:10px 14px;border-radius:4px;'>"
        for r in reminders:
            b = (badge("Soon","red") if r["imminent"] else "") + (badge("Southeast","green") if r["southeast"] else "")
            ds = r["start"].strftime("%b %-d")
            ds += f"–{r['end'].strftime('%-d, %Y')}" if r["start"] != r["end"] else f", {r['start'].year}"
            html += (f"<p style='margin:5px 0;font-size:13px;'>{b}<strong>{r['label']}</strong>"
                     f" &nbsp;·&nbsp; {ds}<br><span style='color:#666;font-size:12px;'>{r['note']}</span></p>")
        html += "</div>"

    html += ("<div style='margin-top:24px;padding-top:10px;border-top:1px solid #e0e0e0;"
             "font-size:11px;color:#999;'>Automated daily digest · Edit digest.py to update</div>"
             "</body></html>")
    return html


# ── EMAIL SENDER ──────────────────────────────────────────────────────────────

def send_email(html, subject, pw):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECIPIENT_EMAIL
    msg.attach(MIMEText(html, "html"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
        s.login(SENDER_EMAIL, pw)
        s.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
    print(f"✅ Sent to {RECIPIENT_EMAIL}")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    anthropic_key = os.environ["ANTHROPIC_API_KEY"]
    gmail_pw      = os.environ["GMAIL_APP_PASSWORD"]
    usajobs_key   = os.environ.get("USAJOBS_API_KEY","")

    today_str = datetime.date.today().strftime("%A, %B %-d, %Y")
    subject   = f"Opportunity Digest — {today_str}"

    print("Fetching Life Cycle Geo...")
    lcg = fetch_lifecyclegeo()

    print("Fetching Geosyntec (Atlanta + Kennesaw)...")
    geosyntec = fetch_geosyntec()

    print("Fetching Josh's Water Jobs...")
    jwj = fetch_joshs_water_jobs()

    print("Fetching AGU Career Center...")
    agu = fetch_agu_jobs()

    print("Fetching USAJobs (free API)...")
    govt = fetch_usajobs(usajobs_key)

    print("Fetching conferences + CFAs (1 Anthropic call)...")
    conf_cfa = fetch_conferences_and_cfas(anthropic_key)

    print("Getting reminders...")
    reminders = get_reminders()

    print("Building and sending email...")
    html = build_email(today_str, lcg, geosyntec, jwj, agu, govt, conf_cfa, reminders)
    send_email(html, subject, gmail_pw)

if __name__ == "__main__":
    main()
