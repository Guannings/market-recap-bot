# Market Recap Bot

![Python](https://img.shields.io/badge/python-3.12-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-active-brightgreen)

A standalone Python script that pulls **real** market data, then **auto-sends** an
HTML recap to your inbox via Gmail — no manual steps, runs free on GitHub Actions.

Each email **leads with the market news that moved things**, grouped by region
(Global, United States, United Kingdom, Europe, Japan & Korea, etc.), followed by
the numbers: major indices, FX, rates, and commodities. Promotional listicles,
crime/accident stories, and other non-market noise are filtered out.

Two scheduled runs:

- **US session** — full recap after the US close (default).
- **Europe / UK session** — a UK & Europe-led recap after the European close
  (`--session europe`).

Source policy is hard-coded: **no China-based outlets, no X/Twitter as a source,
no Grok/xAI-generated content, no content farms.** (News *about* companies such as
Tesla or SpaceX is allowed.)

> [!IMPORTANT]
> **Not financial advice.** Informational/educational use only — see the full
> **Disclaimer and Terms of Use** at the bottom of this README.

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
python market_recap.py --dry-run                  # preview the US recap, nothing sent
python market_recap.py --session europe --dry-run # preview the UK/Europe recap
python market_recap.py --save out.html            # also save the HTML body
python market_recap.py                            # fetch + SEND the US recap
python market_recap.py --session europe           # fetch + SEND the UK/Europe recap
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

### Option C — GitHub Actions (free, runs in the cloud, no PC needed) — recommended
A ready workflow is included at `.github/workflows/recap.yml`. Push this folder to
a GitHub repo, then add three **repository secrets** (Settings → Secrets and
variables → Actions): `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `RECIPIENTS`.

It runs two scheduled jobs automatically:

- `23:30 UTC` Mon–Fri → the **US** recap (7:30am GMT+8, Tue–Sat).
- `17:00 UTC` Mon–Fri → the **UK/Europe** recap (1:00am GMT+8 next day).

A keepalive step makes a tiny commit if the repo goes ~45 days without activity,
which stops GitHub from auto-disabling scheduled workflows after 60 days idle.

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
- Keep your `.env` private — never commit it. (`.gitignore` already excludes it;
  use GitHub secrets for Option C.)

====================================================================================

# **⚠️ Disclaimer and Terms of Use**

**1. Educational Purpose Only**

This software is for educational and research purposes only and was built as a personal project by a student, PARVAUX, studying at National Chengchi University (NCCU). It is not intended to be a source of financial advice, and the author is not a registered financial advisor. The data aggregation, regional classification, and headline-filtering techniques implemented herein are demonstrations of practical concepts and should not be construed as a recommendation to buy, sell, or hold any specific security or asset class.

**2. No Financial Advice**

Nothing in this repository or in the emails it generates constitutes professional financial, legal, or tax advice. Investment decisions should be made based on your own research and consultation with a qualified financial professional.

**3. Data Accuracy and Limitations**

a. Third-Party Sources: Market data is fetched from public APIs (e.g., Yahoo Finance) and headlines from third-party RSS feeds. This data may be delayed, inaccurate, or incomplete.

b. Automated Selection: Headlines are filtered and grouped by region algorithmically using keyword matching. This process is imperfect and may misclassify, omit, or surface irrelevant stories. The recap is not an exhaustive account of market events.

c. Timing: "Close" figures reflect the most recent completed session available from the data source at runtime and may differ from official end-of-day values.

**4. Risk of Loss**

All investments involve risk, including the possible loss of principal. Past performance and historical data referenced in any headline are not indicative of future results. You are solely responsible for any actions you take based on this information.

**5. "AS-IS" SOFTWARE WARRANTY**

**THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT. IN NO EVENT SHALL THE AUTHOR OR COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT, OR OTHERWISE, ARISING FROM, OUT OF, OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.**

**BY USING THIS SOFTWARE, YOU AGREE TO ASSUME ALL RISKS ASSOCIATED WITH YOUR INVESTMENT DECISIONS, RELEASING THE AUTHOR (PARVAUX) FROM ANY LIABILITY REGARDING YOUR FINANCIAL OUTCOMES.**

====================================================================================

# **License**

Released under the [MIT License](LICENSE).
