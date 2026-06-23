# Market Recap Bot

A standalone Python script that pulls **real** EU + US market data for the most
recent completed session and **auto-sends** an HTML recap to your inbox via Gmail.

Every email leads with a plain-English **"What Happened Overnight"** summary that
ties the moves to the likely drivers — so you wake up knowing the story, not just
a wall of numbers. Below that: major indices, FX, rates, commodities, and
market-relevant headlines (lifestyle/junk filtered out).

Source policy is hard-coded: **no China-based outlets, X/Twitter as a source, or
content farms; no Grok/xAI-generated content.** (News *about* Tesla, SpaceX, etc.
is allowed.)

### The overnight summary
By default the summary is built from the data with simple rules (zero setup). For
a sharper, human-sounding write-up, set `ANTHROPIC_API_KEY` in your `.env` and the
bot will have Claude write it from the fetched data (it won't invent numbers).

---

## 1. Install

```bash
cd market-recap-bot
pip install -r requirements.txt
```

## 2. Configure Gmail auto-send

Gmail blocks plain password login, so you need a **16-character App Password**
(this is the supported way to auto-send — no drafts involved):

1. Enable 2-Step Verification: https://myaccount.google.com/security
2. Create an App Password: https://myaccount.google.com/apppasswords
3. Copy `.env.example` to `.env`, paste in your address + app password, then:

```bash
cp .env.example .env      # edit .env with your values
source .env
```

Or set `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, and `RECIPIENTS` as real
environment variables / secrets.

## 3. Run

```bash
python market_recap.py --dry-run     # preview in terminal, nothing sent
python market_recap.py --save out.html   # also save the HTML body
python market_recap.py               # fetch + SEND the email
```

---

## 4. Schedule it (pick one)

The US market closes at **4:00pm ET**. In **GMT+8** that's roughly **4–5am**, so a
good slot is a **weekday morning, e.g. 7:30am GMT+8 (Tue–Sat)** — each run recaps
the US session that just closed.

### Option A — cron (Linux/macOS)
```cron
# 7:30am Tue–Sat, GMT+8 machine
30 7 * * 2-6 cd /path/to/market-recap-bot && source .env && /usr/bin/python3 market_recap.py >> recap.log 2>&1
```

### Option B — Windows Task Scheduler
Create a Basic Task → Daily 7:30am → Action: `python.exe` with argument
`C:\path\to\market_recap.py`. Set the env vars in the task or a wrapper `.bat`.

### Option C — GitHub Actions (free, runs in the cloud, no PC needed)
A ready workflow is included at `.github/workflows/recap.yml`. Push this folder
to a private GitHub repo, then add three **repository secrets**
(Settings → Secrets and variables → Actions): `GMAIL_ADDRESS`,
`GMAIL_APP_PASSWORD`, `RECIPIENTS`. It runs automatically on schedule.

---

## How the numbers are computed

Percent change for indices, FX, and commodities:

$$\Delta\% = \frac{P_{\text{close}} - P_{\text{prev}}}{P_{\text{prev}}} \times 100$$

Yield moves (rates) are shown in basis points:

$$\Delta_{\text{bps}} = \left(y_{\text{close}} - y_{\text{prev}}\right) \times 100$$

## Customizing

- Edit the `US_INDICES`, `EU_INDICES`, `FX`, `RATES`, `COMMODITIES` lists in
  `market_recap.py` to add/remove tickers (Yahoo Finance symbols).
- Add or remove news feeds in `NEWS_FEEDS`.
- Extend `BLOCKED_SOURCE_SUBSTRINGS` to block more sources.

## Notes

- Market data: Yahoo Finance (via `yfinance`). Headlines: reputable finance RSS.
- The script never sends if `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` are missing.
- Keep your `.env` private — never commit it. (Use GitHub secrets for Option C.)
