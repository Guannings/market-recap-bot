#!/usr/bin/env python3
"""
market_recap.py
----------------
Fetches real EU + US market data for the most recent completed session and
emails an HTML recap to you via Gmail (auto-send over SMTP).

Covers: major indices, FX, rates, commodities, and top market-moving headlines.

Source policy (hard-coded): no China-based outlets, no Elon-Musk-firm services
(X/Twitter, etc.), no content-farm domains. Data comes from Yahoo Finance
(market data) and reputable finance RSS feeds (headlines).

Usage:
    python market_recap.py            # fetch + send email
    python market_recap.py --dry-run  # fetch + print, do NOT send
    python market_recap.py --save out.html   # also save the HTML body

Configuration is read from environment variables (see .env.example):
    GMAIL_ADDRESS         your gmail, e.g. you@gmail.com   (the sender)
    GMAIL_APP_PASSWORD    a 16-char Gmail App Password (NOT your login password)
    RECIPIENTS            comma-separated list; defaults to GMAIL_ADDRESS
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ----------------------------------------------------------------------------
# Source policy: block these substrings in any news link/publisher.
# (China-based outlets, Musk-firm services, common content farms.)
# ----------------------------------------------------------------------------
BLOCKED_SOURCE_SUBSTRINGS = [
    # Elon's AI + X/Twitter as a SOURCE (news ABOUT Tesla/SpaceX is fine).
    "x.com", "twitter.com", "t.co", "grok", "xai.com", "x.ai",
    # China-based outlets
    "xinhua", "globaltimes", "chinadaily", "cgtn", "people.com.cn",
    "scmp.com", "caixin", "yicai", "sina.com", "163.com", "qq.com",
    # common content farms / low-quality aggregators
    "msn.com", "benzinga", "zacks", "fool.com", "marketbeat",
    "investorplace", "tipranks", "simplywall",
]

# ----------------------------------------------------------------------------
# What to pull. Yahoo Finance tickers.
# ----------------------------------------------------------------------------
US_INDICES = [
    ("S&P 500", "^GSPC"),
    ("Nasdaq Composite", "^IXIC"),
    ("Dow Jones", "^DJI"),
    ("Russell 2000", "^RUT"),
]
EU_INDICES = [
    ("STOXX Europe 600", "^STOXX"),
    ("Euro STOXX 50", "^STOXX50E"),
    ("DAX (Germany)", "^GDAXI"),
    ("FTSE 100 (UK)", "^FTSE"),
    ("CAC 40 (France)", "^FCHI"),
]
FX = [
    ("EUR/USD", "EURUSD=X"),
    ("GBP/USD", "GBPUSD=X"),
    ("US Dollar Index (DXY)", "DX-Y.NYB"),
]
RATES = [  # Yahoo reports these as percentage yields
    ("US 10Y Treasury", "^TNX"),
    ("US 5Y Treasury", "^FVX"),
    ("US 30Y Treasury", "^TYX"),
]
COMMODITIES = [
    ("Gold", "GC=F"),
    ("Brent Crude", "BZ=F"),
    ("WTI Crude", "CL=F"),
]

NEWS_FEEDS = [
    # Major-media + finance feeds (reputable, non-blocked). Failures degrade gracefully.
    # Note: CNN's public RSS feeds are defunct (they serve years-old content), so
    # BBC and The Guardian are used as the major-media sources instead.
    "https://www.cnbc.com/id/20910258/device/rss/rss.html",    # CNBC Markets
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",   # CNBC Top News
    "https://www.cnbc.com/id/10000664/device/rss/rss.html",    # CNBC Economy
    "https://www.cnbc.com/id/15839069/device/rss/rss.html",    # CNBC Investing
    "https://finance.yahoo.com/news/rssindex",                 # Yahoo Finance
    "https://feeds.bbci.co.uk/news/business/rss.xml",          # BBC Business
    "https://feeds.bbci.co.uk/news/business/economy/rss.xml",  # BBC Economy
    "https://feeds.bbci.co.uk/news/business/companies/rss.xml",# BBC Companies
    "https://www.theguardian.com/uk/business/rss",             # Guardian Business
    "https://www.theguardian.com/business/economics/rss",      # Guardian Economics
    "https://rss.dw.com/rdf/rss-en-bus",                       # Deutsche Welle Business (Germany)
    "https://www.france24.com/en/business/rss",               # France24 Business (France)
    "https://www.cnbc.com/id/19794221/device/rss/rss.html",    # CNBC Europe
    "https://www.theguardian.com/business/eurozone/rss",       # Guardian Eurozone (ECB/euro)
    "https://www.euractiv.com/feed/",                          # Euractiv (EU policy/economy)
]

# Reputable crypto desks for the institutional-flows section.
CRYPTO_FEEDS = [
    "https://www.theblock.co/rss.xml",          # The Block
    "https://decrypt.co/feed",                  # Decrypt
    "https://bitcoinmagazine.com/feed",         # Bitcoin Magazine
    "https://www.coindesk.com/arc/outboundfeeds/rss/",  # CoinDesk (if/when live)
]

# A crypto headline is kept for the flows section only if it mentions BOTH a
# crypto asset AND an institutional/flow term (so it's "what the big players are
# doing", not price action or unrelated VC funding rounds).
CRYPTO_ASSET_TERMS = [
    "bitcoin", "btc", "ether", "ethereum", "crypto", "solana", "stablecoin",
    "digital asset", "ibit", "gbtc", "fbtc",
]
CRYPTO_FLOW_TERMS = [
    "etf", "etfs", "inflow", "inflows", "outflow", "outflows", "institution",
    "institutional", "treasury", "accumulate", "accumulated", "accumulation",
    "holdings", "buys", "bought", "purchase", "purchased", "acquire", "acquired",
    "adds", "added", "aum", "reserve", "reserves", "stake", "allocation",
    "net flows", "spot etf", "fund", "blackrock", "fidelity", "grayscale",
    "franklin templeton", "saylor", "microstrategy",
]
# Legal/governance/security drama that isn't an institutional flow — dropped.
CRYPTO_EXCLUDE = [
    "sue", "sues", "sued", "lawsuit", "lawsuits", "charged", "charges", "fraud",
    "indict", "indicted", "settlement", "court", "judge", "hack", "hacked",
    "exploit", "breach", "scam", "ponzi", "probe", "investigation", "sentenced",
]

# A headline is kept only if it mentions one of these (filters out lifestyle/junk).
MARKET_KEYWORDS = [
    "stock", "stocks", "share", "shares", "market", "markets", "wall street",
    "dow", "nasdaq", "s&p", "ftse", "dax", "cac", "nikkei", "index", "indexes",
    "equity", "equities", "bond", "bonds", "yield", "yields", "treasury",
    "treasuries", "rate", "rates", "fed", "federal reserve", "ecb", "boe",
    "central bank", "interest", "inflation", "cpi", "ppi", "gdp", "jobs",
    "payrolls", "unemployment", "earnings", "profit", "profits", "revenue",
    "guidance", "ipo", "merger", "buyout", "takeover", "oil", "crude", "brent",
    "opec", "gold", "commodity", "commodities", "dollar", "euro", "currency",
    "forex", "recession", "tariff", "tariffs", "trade war", "sanctions",
    "economy", "economic", "growth", "debt", "deficit", "bank", "banks",
    "banking", "investor", "investors", "selloff", "rally", "rout", "surge",
    "slump", "plunge", "soar", "soars", "dividend",
]

# Story types that are NOT market news even if a market word appears (crime,
# accidents, disasters, lifestyle). Dropped before the keyword check.
NOISE_PATTERNS = [
    "killed", "death", "dead", "dies in", "car crash", "plane crash", "fatal",
    "injured", "murder", "manslaughter", "shooting", "stabbing", "arrested",
    "assault", "rape", "abuse", "missing", "rescue", "wildfire", "earthquake",
    "flood", "hurricane", "heatwave", "weather", "football", "soccer", "match",
    "celebrity", "royal family", "wedding", "recipe", "holiday tips",
]

# Promotional / listicle / SEO patterns to drop (not real market news).
JUNK_PATTERNS = [
    "stocks to buy", "stock to buy", "to buy now", "to buy for", "should you buy",
    "ultra-high dividend", "high dividend", "dividend stocks", "income investors",
    "best stock", "top stock", "is it too late", "here's why you should",
    "motley", "could make you", "millionaire", "price target", "analysts say",
    "reasons to", "things to know", "stocks to watch", "is a buy", "buy rating",
    "advocacy lab", "sponsored", "advertorial", "[promoted", "[partner",
]

# Market-wrap / live-blog patterns to surface FIRST (these explain the day).
WRAP_PATTERNS = [
    "stock market today", "stocks close", "stocks end", "markets close",
    "market wrap", "wall street", "as it happened", "markets live", "live:",
    "dow closes", "s&p closes", "nasdaq closes", "closing bell", "market recap",
    "stocks rise", "stocks fall", "stocks slip", "stocks jump",
]

# How far back a headline can be (hours) to count as "overnight / recent".
NEWS_MAX_AGE_HOURS = 48


def _blocked(text: str) -> bool:
    t = (text or "").lower()
    return any(b in t for b in BLOCKED_SOURCE_SUBSTRINGS)


# ----------------------------------------------------------------------------
# Market data
# ----------------------------------------------------------------------------
def fetch_quote(ticker: str, retries: int = 3):
    """Return (last_close, prev_close, as_of_date) or (None, None, None).
    Retries a few times because Yahoo occasionally returns empty/ratelimited."""
    import time as _time
    try:
        import yfinance as yf
    except Exception as e:  # noqa: BLE001
        print(f"  ! yfinance import failed: {e}", file=sys.stderr)
        return None, None, None
    for attempt in range(1, retries + 1):
        try:
            hist = yf.Ticker(ticker).history(period="7d", interval="1d")
            closes = hist["Close"].dropna()
            if len(closes) >= 2:
                return float(closes.iloc[-1]), float(closes.iloc[-2]), closes.index[-1].date()
            if len(closes) == 1:
                return float(closes.iloc[-1]), None, closes.index[-1].date()
            # empty result -> retry
        except Exception as e:  # noqa: BLE001
            if attempt == retries:
                print(f"  ! {ticker}: {e}", file=sys.stderr)
        _time.sleep(1.5 * attempt)
    return None, None, None


def collect(group):
    rows = []
    for name, ticker in group:
        last, prev, asof = fetch_quote(ticker)
        rows.append({"name": name, "ticker": ticker, "last": last, "prev": prev, "asof": asof})
    return rows


def pct_change(last, prev):
    if last is None or prev in (None, 0):
        return None
    return (last - prev) / prev * 100.0


def bps_change(last, prev):
    if last is None or prev is None:
        return None
    return (last - prev) * 100.0  # yields are in percentage points


# ----------------------------------------------------------------------------
# Headlines
# ----------------------------------------------------------------------------
# Stories matching these are GLOBAL (cross-border drivers) regardless of nation.
GLOBAL_KEYWORDS = [
    "oil", "crude", "brent", "wti", "opec", "gold", "commodit", "global",
    "world ", "worldwide", "bitcoin", "crypto", "bond market", "supply chain",
]

# Per-region keyword sets. A story is filed under a region if it matches that
# region's words and isn't global / multi-region.
REGION_KEYWORDS = {
    "United States": ["wall street", "u.s.", "us ", " us", "america", "american",
                       "fed", "federal reserve", "dow", "nasdaq", "s&p", "treasury",
                       "washington", "trump", "powell", "white house", "sec "],
    "United Kingdom": ["uk", "u.k.", "britain", "british", "ftse", "bank of england",
                        "boe", "sterling", "pound", "brexit", "starmer", "miliband",
                        "london", "gilt"],
    "Europe": ["euro", "eurozone", "ecb", "dax", "cac", "stoxx", "germany", "german",
               "france", "french", "spain", "italy", "italian", "brussels", "bund"],
    "Japan & Korea": ["japan", "japanese", "tokyo", "nikkei", "yen", "boj",
                       "korea", "korean", "south korea", "seoul", "kospi"],
    "Australia": ["australia", "australian", "asx", "sydney"],
    "Middle East": ["iran", "israel", "saudi", "gulf", "hormuz", "tehran", "opec+"],
}

REGION_ORDER = ["Global", "United States", "United Kingdom", "Europe",
                "Japan & Korea", "Middle East", "Australia", "Other"]

# Which regions each email shows AND in what order (top = highest priority), so
# the EU email leads with Europe and the US email leads with the US. "Global" +
# "Middle East" (macro/oil) appear in both, but below the home regions.
SESSION_REGIONS = {
    "europe": ["Europe", "United Kingdom", "Global", "Middle East"],
    "us": ["United States", "Global", "Japan & Korea", "Australia",
           "Middle East", "Other"],
}

# Per-region caps so low-priority buckets can't dominate. Home regions (US, UK,
# Europe) are uncapped; shared macro and the catch-all "Other" are limited.
REGION_CAPS = {"Global": 5, "Middle East": 3, "Other": 4}

# Major companies -> home region, used when a headline names a firm but no
# country. Keep names distinctive to avoid false matches.
COMPANY_REGION = {
    "United States": ["oracle", "intel", "nvidia", "apple", "microsoft", "amazon",
                       "spacex", "target ", "zuckerberg", "kalshi",
                       "google", "alphabet", "meta ", "tesla", "jpmorgan", "goldman",
                       "morgan stanley", "boeing", "walmart", "exxon", "chevron",
                       "pfizer", "disney", "netflix", "broadcom", "micron",
                       "wells fargo", "bank of america", "citigroup", "kayne anderson",
                       "mach natural", "general motors"],
    "United Kingdom": ["barclays", "hsbc", "lloyds", "natwest", "bp ", "shell",
                        "glencore", "rolls-royce", "vodafone", "astrazeneca",
                        "unilever", "tesco", "easyjet", "rio tinto", "diageo"],
    "Europe": ["asml", "sap ", "siemens", "volkswagen", "bmw", "mercedes", "lvmh",
               "hermes", "ferrari", "totalenergies", "nestle", "novartis", "prosus",
               "airbus", "stellantis", "adidas", "santander"],
    "Japan & Korea": ["sony", "toyota", "honda", "nintendo", "softbank", "nissan",
                       "panasonic", "samsung", "hyundai", "kia", "sk hynix", "lg "],
    "Australia": ["bhp", "fortescue", "qantas", "commonwealth bank", "woolworths",
                  "westpac"],
    "Middle East": ["aramco"],
}


def classify_region(title: str) -> str:
    t = title.lower()
    if any(g in t for g in GLOBAL_KEYWORDS):
        return "Global"
    matched = [region for region, kws in REGION_KEYWORDS.items()
               if any(k in t for k in kws)]
    if len(matched) == 1:
        return matched[0]
    if len(matched) > 1:          # spans several countries -> treat as global
        return "Global"
    # No country named: fall back to the home region of any company mentioned.
    for region, firms in COMPANY_REGION.items():
        if any(f in t for f in firms):
            return region
    return "Other"


def group_news(items, order=None):
    """Return [(region, [items])] in the given order, only non-empty groups."""
    order = order or REGION_ORDER
    buckets = {}
    for h in items:
        buckets.setdefault(classify_region(h["title"]), []).append(h)
    # listed regions first (in order), then any leftover regions
    seen = list(order) + [r for r in REGION_ORDER if r not in order]
    return [(r, buckets[r]) for r in seen if r in buckets]


def _word_hit(text: str, terms) -> bool:
    """True if any term appears as a whole word/phrase (not inside another word).
    e.g. 'fed' matches 'fed' but NOT 'federal'; 'rate' won't match 'corporate'."""
    for kw in terms:
        if re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", text):
            return True
    return False


def _is_market_news(title: str) -> bool:
    t = title.lower()
    if _word_hit(t, NOISE_PATTERNS):           # crime / accident / lifestyle
        return False
    if any(j in t for j in JUNK_PATTERNS):     # promotional / listicle
        return False
    return _word_hit(t, MARKET_KEYWORDS)


def _is_wrap(title: str) -> bool:
    t = title.lower()
    return any(w in t for w in WRAP_PATTERNS)


def _entry_age_hours(entry):
    """Hours since publication, or None if no date is available."""
    import calendar
    import time as _time
    tm = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not tm:
        return None
    return (_time.time() - calendar.timegm(tm)) / 3600.0


def fetch_headlines(limit=8):
    out = []
    try:
        import feedparser
    except Exception:
        return out
    for url in NEWS_FEEDS:
        try:
            feed = feedparser.parse(url)
            feed_src = feed.feed.get("title", "")
            for entry in feed.entries:
                link = getattr(entry, "link", "")
                title = getattr(entry, "title", "").strip()
                src = getattr(getattr(entry, "source", None), "title", "") or feed_src
                if not title or _blocked(link) or _blocked(src) or _blocked(title):
                    continue
                if not _is_market_news(title):       # drop lifestyle / non-market items
                    continue
                age = _entry_age_hours(entry)
                if age is not None and age > NEWS_MAX_AGE_HOURS:  # drop stale items
                    continue
                out.append({"title": title, "link": link, "source": src,
                            "age": age if age is not None else 9e9,
                            "wrap": _is_wrap(title)})
        except Exception as e:  # noqa: BLE001
            print(f"  ! feed {url}: {e}", file=sys.stderr)
    # de-dupe by title
    seen, deduped = set(), []
    for h in out:
        key = h["title"].lower()
        if key not in seen:
            seen.add(key)
            deduped.append(h)
    # market-wrap / live-blog stories first, then freshest
    deduped.sort(key=lambda h: (0 if h["wrap"] else 1, h["age"]))
    return deduped[:limit]


# ----------------------------------------------------------------------------
# Cross-run de-dup: remember recently-sent headlines so the EU and US emails
# (and day-to-day runs) don't repeat the same stories. State lives in a small
# committed JSON file; the workflow commits it after each send.
# ----------------------------------------------------------------------------
STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".sent_news.json")
SENT_WINDOW_HOURS = 36


def _key(h):
    # Global de-dup key (not session-qualified): a story shown in the EU email is
    # suppressed in the US email so the two don't repeat. Region scoping (below)
    # is what keeps the US email from being starved — US stories are never in the
    # EU email to begin with, so global de-dup can't drain them.
    return h.get("link") or h.get("title", "")


def load_sent(window_hours=SENT_WINDOW_HOURS):
    import json
    import time as _time
    try:
        with open(STATE_PATH) as f:
            data = json.load(f)
    except Exception:
        return {}
    cutoff = _time.time() - window_hours * 3600
    return {k: v for k, v in data.items() if isinstance(v, (int, float)) and v >= cutoff}


def save_sent(sent):
    import json
    try:
        with open(STATE_PATH, "w") as f:
            json.dump(sent, f, indent=0)
    except Exception as e:  # noqa: BLE001
        print(f"  ! could not save sent-state: {e}", file=sys.stderr)


def drop_seen(items, sent):
    return [h for h in items if _key(h) not in sent]


def fetch_crypto_flows(limit=8, max_age_hours=72):
    """Headlines about what institutions are doing in crypto: ETF in/outflows,
    treasury/corporate BTC buys, fund allocations — NOT price action."""
    out = []
    try:
        import feedparser
    except Exception:
        return out
    for url in CRYPTO_FEEDS:
        try:
            feed = feedparser.parse(url)
            feed_src = feed.feed.get("title", "")
            for entry in feed.entries:
                link = getattr(entry, "link", "")
                title = getattr(entry, "title", "").strip()
                src = getattr(getattr(entry, "source", None), "title", "") or feed_src
                t = title.lower()
                if not title or _blocked(link) or _blocked(src) or _blocked(title):
                    continue
                if _word_hit(t, NOISE_PATTERNS) or _word_hit(t, CRYPTO_EXCLUDE):
                    continue
                # must mention a crypto asset AND an institutional/flow term
                if not (_word_hit(t, CRYPTO_ASSET_TERMS) and _word_hit(t, CRYPTO_FLOW_TERMS)):
                    continue
                age = _entry_age_hours(entry)
                if age is not None and age > max_age_hours:
                    continue
                out.append({"title": title, "link": link, "source": src,
                            "age": age if age is not None else 9e9})
        except Exception as e:  # noqa: BLE001
            print(f"  ! crypto feed {url}: {e}", file=sys.stderr)
    seen, deduped = set(), []
    for h in out:
        key = h["title"].lower()
        if key not in seen:
            seen.add(key)
            deduped.append(h)
    deduped.sort(key=lambda h: h["age"])
    return deduped[:limit]


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------
def fmt(v, nd=2):
    return "n/a" if v is None else f"{v:,.{nd}f}"


def color(v):
    if v is None:
        return "#666"
    return "#1e8449" if v >= 0 else "#c0392b"


def sign(v, suffix="%", nd=2):
    if v is None:
        return "n/a"
    return f"{'+' if v >= 0 else ''}{v:.{nd}f}{suffix}"


def index_table(rows):
    body = ""
    for r in rows:
        ch = pct_change(r["last"], r["prev"])
        body += (
            f'<tr><td style="padding:5px 0">{r["name"]}</td>'
            f'<td style="text-align:right">{fmt(r["last"])}</td>'
            f'<td style="text-align:right;color:{color(ch)}">{sign(ch)}</td></tr>'
        )
    return (
        '<table style="width:100%;border-collapse:collapse;font-size:14px;margin:0 0 18px">'
        + body + "</table>"
    )


def rates_table(rows):
    body = ""
    for r in rows:
        ch = bps_change(r["last"], r["prev"])
        body += (
            f'<tr><td style="padding:5px 0">{r["name"]}</td>'
            f'<td style="text-align:right">{fmt(r["last"])}%</td>'
            f'<td style="text-align:right;color:{color(ch)}">{sign(ch, " bps", 1)}</td></tr>'
        )
    return (
        '<table style="width:100%;border-collapse:collapse;font-size:14px;margin:0 0 18px">'
        + body + "</table>"
    )


def headlines_html(items, order=None):
    if not items:
        return '<div style="font-size:13px;color:#777">No new market headlines since the last recap.</div>'
    out = ""
    for region, group in group_news(items, order):
        li = "".join(
            f'<li style="margin-bottom:5px"><a href="{h["link"]}" style="color:#2c5fb3;text-decoration:none">{h["title"]}</a></li>'
            for h in group
        )
        out += (
            f'<div style="font-weight:600;font-size:13px;color:#444;'
            f'text-transform:uppercase;letter-spacing:.04em;margin:12px 0 4px">{region}</div>'
            f'<ul style="font-size:14px;margin:0;padding-left:18px">{li}</ul>'
        )
    return out + '<div style="margin-bottom:14px"></div>'


def crypto_html(items):
    if not items:
        return '<div style="font-size:13px;color:#777">No new institutional crypto-flow headlines since the last recap.</div>'
    li = "".join(
        f'<li style="margin-bottom:5px"><a href="{h["link"]}" style="color:#2c5fb3;text-decoration:none">{h["title"]}</a></li>'
        for h in items
    )
    return f'<ul style="font-size:14px;margin:0 0 18px;padding-left:18px">{li}</ul>'


def _eu_uk_first(rows):
    """Put FTSE 100 (UK) at the top of the European table for the Europe run."""
    return sorted(rows, key=lambda r: 0 if "FTSE" in r["name"] else 1)


DISCLAIMER = ("For informational/educational purposes only — NOT financial advice. "
              "Data from public sources may be delayed or inaccurate; verify before "
              "acting. No warranty. See repository disclaimer.")


def build_html(data, asof_label, session="us"):
    h3 = 'margin:0 0 6px;border-bottom:2px solid #eee;padding-bottom:4px'

    def sec(title, html):
        return f'<h3 style="{h3}">{title}</h3>{html}'

    order = SESSION_REGIONS.get(session, REGION_ORDER)
    news = sec("Market News — what moved things", headlines_html(data["news"], order))
    crypto = sec("Crypto — Institutional Flows", crypto_html(data["crypto"]))
    if session == "europe":
        title = "Europe &amp; UK Market Recap"
        body = (news + crypto
                + sec("Europe &amp; UK (close)", index_table(_eu_uk_first(data["eu"])))
                + sec("FX (EUR, GBP)", index_table(data["fx"]))
                + sec("Rates", rates_table(data["rates"]))
                + sec("Commodities", index_table(data["commodities"]))
                + sec("US (prior close, reference)", index_table(data["us"])))
    else:
        title = "Market Recap"
        body = (news + crypto
                + sec("US Indices (close)", index_table(data["us"]))
                + sec("Europe (close)", index_table(data["eu"]))
                + sec("FX", index_table(data["fx"]))
                + sec("Rates", rates_table(data["rates"]))
                + sec("Commodities", index_table(data["commodities"])))

    return f"""<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:640px;color:#1a1a1a;line-height:1.5">
<h2 style="margin:0 0 2px">{title}</h2>
<div style="color:#666;font-size:13px;margin-bottom:18px">{asof_label}</div>
{body}
<div style="font-size:12px;color:#888;border-top:1px solid #eee;padding-top:10px">
{DISCLAIMER}<br>Auto-generated by market_recap.py. Market data: Yahoo Finance. Headlines: reputable finance RSS
(China outlets, X/Twitter as a source, Grok/xAI content, and content farms excluded).
</div></div>"""


def build_text(data, asof_label, session="us"):
    title = "EUROPE & UK MARKET RECAP" if session == "europe" else "MARKET RECAP"
    lines = [f"{title} — {asof_label}", ""]
    order = SESSION_REGIONS.get(session, REGION_ORDER)
    lines.append("MARKET NEWS — what moved things")
    if data["news"]:
        for region, group in group_news(data["news"], order):
            lines.append(f"  [{region}]")
            for h in group:
                lines.append(f"    - {h['title']} ({h['link']})")
    else:
        lines.append("  No new market headlines since the last recap.")
    lines.append("")

    lines.append("CRYPTO — INSTITUTIONAL FLOWS")
    if data["crypto"]:
        for h in data["crypto"]:
            lines.append(f"  - {h['title']} ({h['link']})")
    else:
        lines.append("  No new institutional crypto-flow headlines since the last recap.")
    lines.append("")

    def block(heading, rows, rate=False):
        lines.append(heading.upper())
        for r in rows:
            if rate:
                ch = bps_change(r["last"], r["prev"])
                lines.append(f"  {r['name']}: {fmt(r['last'])}%  ({sign(ch, ' bps', 1)})")
            else:
                ch = pct_change(r["last"], r["prev"])
                lines.append(f"  {r['name']}: {fmt(r['last'])}  ({sign(ch)})")
        lines.append("")

    if session == "europe":
        block("Europe & UK (close)", _eu_uk_first(data["eu"]))
        block("FX (EUR, GBP)", data["fx"])
        block("Rates", data["rates"], rate=True)
        block("Commodities", data["commodities"])
        block("US (prior close, reference)", data["us"])
    else:
        block("US Indices (close)", data["us"])
        block("Europe (close)", data["eu"])
        block("FX", data["fx"])
        block("Rates", data["rates"], rate=True)
        block("Commodities", data["commodities"])

    lines += [DISCLAIMER, "Data: Yahoo Finance + reputable finance RSS."]
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# Email
# ----------------------------------------------------------------------------
def send_email(subject, text_body, html_body):
    sender = os.environ.get("GMAIL_ADDRESS")
    app_pw = os.environ.get("GMAIL_APP_PASSWORD")
    recipients = os.environ.get("RECIPIENTS", sender or "")
    if not sender or not app_pw:
        raise SystemExit("Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD env vars (see .env.example).")
    to_list = [r.strip() for r in recipients.split(",") if r.strip()]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to_list)
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    import time as _time
    last_err = None
    for attempt in range(1, 4):  # retry transient SMTP/network failures
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
                server.login(sender, app_pw)
                server.sendmail(sender, to_list, msg.as_string())
            print(f"Sent to: {', '.join(to_list)}")
            return
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"  ! send attempt {attempt} failed: {e}", file=sys.stderr)
            _time.sleep(5 * attempt)
    raise SystemExit(f"Email send failed after retries: {last_err}")


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Email a EU+US market recap.")
    ap.add_argument("--dry-run", action="store_true", help="print instead of sending")
    ap.add_argument("--save", metavar="PATH", help="also write the HTML body to PATH")
    ap.add_argument("--session", choices=["us", "europe"], default="us",
                    help="us = full recap after the US close (default); "
                         "europe = UK/Europe-led recap after the European close")
    args = ap.parse_args()

    print("Fetching market data...", file=sys.stderr)
    data = {
        "us": collect(US_INDICES),
        "eu": collect(EU_INDICES),
        "fx": collect(FX),
        "rates": collect(RATES),
        "commodities": collect(COMMODITIES),
        "news": fetch_headlines(limit=45),
        "crypto": fetch_crypto_flows(limit=8),
    }

    # Sanity guard: if the data source is fully down (every quote n/a), fail the
    # run so the workflow's failure alert fires instead of sending an empty email.
    quote_groups = ("us", "eu", "fx", "rates", "commodities")
    got = sum(1 for g in quote_groups for r in data[g] if r["last"] is not None)
    if got == 0:
        raise SystemExit("All market data came back empty — aborting so the alert fires.")

    # Scope the news to this email's regions (EU email = UK/Europe/Global, etc.)
    # so the EU email isn't full of US stories and the US email keeps its US news.
    allowed = SESSION_REGIONS[args.session]
    data["news"] = [h for h in data["news"] if classify_region(h["title"]) in allowed]

    # Drop anything already sent in a recent recap (incl. the earlier EU email),
    # so the EU and US emails never repeat the same story.
    sent = load_sent()
    data["news"] = drop_seen(data["news"], sent)
    data["crypto"] = drop_seen(data["crypto"], sent)

    # Cap low-priority buckets (macro, Other) so home-region news dominates.
    counts, kept = {}, []
    for h in data["news"]:
        r = classify_region(h["title"])
        cap = REGION_CAPS.get(r)
        if cap is not None:
            counts[r] = counts.get(r, 0) + 1
            if counts[r] > cap:
                continue
        kept.append(h)
    data["news"] = kept

    # Date label: Europe run keys off EU data; US run keys off US data.
    if args.session == "europe":
        asof = next((r["asof"] for r in data["eu"] if r["asof"]), dt.date.today())
        asof_label = asof.strftime("%A, %B %d, %Y") + " (UK & Europe close)"
        subject = f"Europe & UK Market Recap — {asof.strftime('%a, %b %d, %Y')}"
    else:
        asof = next((r["asof"] for r in data["us"] if r["asof"]), dt.date.today())
        asof_label = asof.strftime("%A, %B %d, %Y") + " (EU + US sessions)"
        subject = f"Market Recap — {asof.strftime('%a, %b %d, %Y')} (EU + US sessions)"

    html = build_html(data, asof_label, args.session)
    text = build_text(data, asof_label, args.session)

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Saved HTML to {args.save}", file=sys.stderr)

    if args.dry_run:
        print("\n" + text)
        print("\n[dry-run] Email not sent. (state file unchanged)")
        return

    send_email(subject, text, html)

    # Record what we just sent so the next recap can skip it.
    import time as _time
    now = _time.time()
    for h in data["news"] + data["crypto"]:
        sent[_key(h)] = now
    save_sent(sent)


if __name__ == "__main__":
    main()
