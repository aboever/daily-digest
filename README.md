# Daily Opportunity Digest

Sends a daily email with live job postings, conferences, and calls for abstracts
in environmental geochemistry and remediation.

## How it works
- GitHub Actions runs the script every morning at 8 AM ET
- `digest.py` fetches live employer pages + searches via Anthropic API
- Results are emailed to tonyboever@gmail.com via Gmail SMTP

## One-time setup

### 1. Get an Anthropic API key
- Go to https://console.anthropic.com
- Create an API key (you'll need a small amount of credit — ~$5 lasts months at this usage rate)

### 2. Get a Gmail App Password
- Go to https://myaccount.google.com/security
- Under "How you sign in to Google", enable 2-Step Verification if not already on
- Then go to https://myaccount.google.com/apppasswords
- Create a new app password — name it "digest-bot"
- Copy the 16-character password shown

### 3. Add secrets to this GitHub repository
- Go to your repo → Settings → Secrets and variables → Actions → New repository secret
- Add: `ANTHROPIC_API_KEY` = your Anthropic key
- Add: `GMAIL_APP_PASSWORD` = your 16-character Gmail app password

### 4. Push this repo to GitHub
```bash
git init
git add .
git commit -m "Initial digest setup"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```

### 5. Test it manually
- Go to your repo on GitHub → Actions tab
- Click "Daily Opportunity Digest" → "Run workflow"
- Check your inbox within ~60 seconds

## Customization
Edit `digest.py` to:
- Add/remove employers in `PRIORITY_PAGES`
- Add/remove conferences in `STANDING_REMINDERS`
- Change recipient email at the top of the file

Edit `.github/workflows/daily-digest.yml` to change the send time (currently 8 AM ET).
