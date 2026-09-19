"""Unit tests for the pure logic in market_recap.py.

These cover the parts that decide *what* ends up in the recap and *how it's
ranked* — region classification, the news admit/reject gate, importance
scoring, near-duplicate collapsing, the crypto-flow filter, and the number
formatting/movers helpers. Everything here is offline: no network, no Yahoo,
no RSS, no email. (yfinance/feedparser are imported lazily inside the fetch
functions, so importing the module for these tests needs neither installed.)

Run:  pytest -q
"""
import market_recap as m


# ---------------------------------------------------------------------------
# Number helpers
# ---------------------------------------------------------------------------
def test_pct_change_basic():
    assert m.pct_change(110, 100) == 10.0
    assert m.pct_change(90, 100) == -10.0


def test_pct_change_guards_none_and_zero():
    assert m.pct_change(None, 100) is None
    assert m.pct_change(100, None) is None
    assert m.pct_change(100, 0) is None      # no divide-by-zero


def test_bps_change_is_hundredths_of_a_point():
    # yields are percentage points; a 0.03pp move is 3.0 bps
    assert round(m.bps_change(4.20, 4.17), 4) == 3.0
    assert m.bps_change(None, 4.17) is None


def test_fmt_and_sign_formatting():
    assert m.fmt(None) == "n/a"
    assert m.fmt(1234.5) == "1,234.50"
    assert m.sign(1.234) == "+1.23%"
    assert m.sign(-1.2) == "-1.20%"
    assert m.sign(None) == "n/a"
    assert m.sign(3.0, " bps", 1) == "+3.0 bps"


def test_color_sign():
    assert m.color(1) == "#1e8449"      # green for >= 0
    assert m.color(-1) == "#c0392b"     # red for < 0
    assert m.color(None) == "#666"      # grey for missing


# ---------------------------------------------------------------------------
# Whole-word matching
# ---------------------------------------------------------------------------
def test_word_hit_respects_word_boundaries():
    assert m._word_hit("the fed met today", ["fed"]) is True
    assert m._word_hit("a federal holiday", ["fed"]) is False    # not inside 'federal'
    assert m._word_hit("corporate bonds", ["rate"]) is False     # not inside 'corporate'


def test_count_hits_counts_distinct_terms():
    t = "fed hikes rates as inflation surges"
    assert m._count_hits(t, ["fed", "inflation"]) == 2
    assert m._count_hits(t, ["fed", "nvidia"]) == 1             # missing term not counted
    assert m._count_hits(t, ["nvidia", "apple"]) == 0


# ---------------------------------------------------------------------------
# Region classification
# ---------------------------------------------------------------------------
def test_classify_single_market():
    assert m.classify_region("Fed cuts rates, Wall Street rallies") == "United States"
    assert m.classify_region("FTSE 100 climbs as the pound weakens") == "United Kingdom"
    assert m.classify_region("ECB signals a pause; DAX gains") == "Europe"


def test_classify_global_for_cross_border_drivers():
    assert m.classify_region("Oil surges on OPEC supply cut") == "Global"
    assert m.classify_region("Bitcoin jumps to record") == "Global"


def test_classify_multi_market_is_global():
    # names both a US and a UK market -> spans several real markets -> Global
    assert m.classify_region("Wall Street and the FTSE both rally") == "Global"


def test_classify_company_fallback_when_no_country():
    # no country word, but a mega-cap name maps to its home region
    assert m.classify_region("Nvidia earnings beat expectations") == "United States"
    assert m.classify_region("ASML books record orders") == "Europe"


def test_classify_other_when_no_signal():
    assert m.classify_region("A quiet day for local shops") == "Other"


def test_region_of_prefers_precomputed_region():
    h = {"title": "Totally ambiguous", "region": "Europe"}
    assert m.region_of(h) == "Europe"       # trusts the fetch-time region
    assert m.region_of({"title": "Fed hikes rates"}) == "United States"  # falls back


# ---------------------------------------------------------------------------
# News admit / reject gate
# ---------------------------------------------------------------------------
def test_market_news_admits_real_market_story():
    assert m._is_market_news("Dow closes higher as Treasury yields fall") is True


def test_market_news_rejects_noise_crime_lifestyle():
    assert m._is_market_news("Three killed in a car crash on the motorway") is False
    assert m._is_market_news("Nadal wins his match in straight sets") is False


def test_market_news_rejects_crypto_here():
    # crypto belongs ONLY in the crypto-flows section, never general news
    assert m._is_market_news("Bitcoin rallies as ETF inflows surge") is False


def test_market_news_rejects_promo_listicles():
    assert m._is_market_news("3 dividend stocks to buy now") is False


def test_market_news_rejects_yahoo_seo_templates():
    # names an index but is auto-generated filler, not news
    assert m._is_market_news("Is Tyson Foods Stock Underperforming the Nasdaq?") is False
    assert m._is_market_news("Is Marsh & McLennan Stock Outperforming the S&P 500?") is False


def test_market_news_requires_a_keyword_unless_trusted():
    assert m._is_market_news("Council debates a new bin collection schedule") is False
    # a trusted EU desk is kept even without an explicit market keyword...
    assert m._is_market_news("Council debates a new bin collection schedule", trusted=True) is True
    # ...but noise/crypto/junk are still dropped even when trusted
    assert m._is_market_news("Bitcoin ETF inflows surge", trusted=True) is False


def test_blocked_sources():
    assert m._blocked("https://www.benzinga.com/story") is True
    assert m._blocked("https://x.com/someone/status/1") is True
    assert m._blocked("https://www.reuters.com/markets") is False


# ---------------------------------------------------------------------------
# Importance scoring
# ---------------------------------------------------------------------------
def test_wrap_outranks_generic():
    wrap = {"title": "Stock market today: Wall Street closes higher", "wrap": True, "age": 3}
    generic = {"title": "A company opens a new regional office", "wrap": False, "age": 3}
    assert m.score_headline(wrap) > m.score_headline(generic)


def test_macro_outranks_generic():
    macro = {"title": "US inflation cools as CPI comes in below forecast", "wrap": False, "age": 5}
    generic = {"title": "A company opens a new regional office", "wrap": False, "age": 5}
    assert m.score_headline(macro) > m.score_headline(generic)


def test_fresher_breaks_ties():
    older = {"title": "Fed holds rates steady", "wrap": False, "age": 40}
    newer = {"title": "Fed holds rates steady", "wrap": False, "age": 1}
    assert m.score_headline(newer) > m.score_headline(older)


# ---------------------------------------------------------------------------
# Near-duplicate detection
# ---------------------------------------------------------------------------
def _nd(a, b):
    return m._near_dupe(m._title_tokens(a), m._title_tokens(b))


def test_near_dupe_catches_syndicated_suffix():
    assert _nd("Wall Street closes higher",
               "Wall Street closes higher after the Fed decision") is True


def test_near_dupe_catches_minor_rewording():
    assert _nd("Oil prices jump on OPEC supply cut",
               "Oil prices jump after OPEC supply cut") is True


def test_near_dupe_keeps_distinct_stories_apart():
    assert _nd("Apple unveils a new iPhone",
               "Tesla recalls thousands of cars") is False


def test_title_tokens_drop_stopwords_and_short_words():
    toks = m._title_tokens("The Fed is to hold on rates")
    assert "fed" in toks and "rates" in toks
    assert "the" not in toks and "is" not in toks and "to" not in toks


# ---------------------------------------------------------------------------
# Movers / snapshot
# ---------------------------------------------------------------------------
def _sample_data():
    return {
        "us": [{"name": "S&P 500", "last": 101, "prev": 100},
               {"name": "Nasdaq Composite", "last": 195, "prev": 200}],
        "eu": [{"name": "DAX (Germany)", "last": 150, "prev": 148}],
        "asia": [{"name": "Nikkei 225 (Japan)", "last": 310, "prev": 300}],
        "commodities": [{"name": "Brent Crude", "last": 77, "prev": 80},
                        {"name": "Gold", "last": 2010, "prev": 2000}],
        "fx": [{"name": "EUR/USD", "last": 1.10, "prev": 1.09}],
        "rates": [{"name": "US 10Y Treasury", "last": 4.20, "prev": 4.17}],
    }


def test_top_movers_orders_and_excludes_fx_rates():
    gainers, losers = m.top_movers(_sample_data(), n=2)
    assert gainers[0][0] == "Nikkei 225"      # +3.33% is the biggest gain
    assert losers[0][0] == "Brent Crude"      # -2.5% is the biggest drop
    names = {n for n, _ in gainers + losers}
    assert "EUR/USD" not in names and "US 10Y Treasury" not in names


def test_snapshot_text_has_tldr_and_movers():
    lines = m.snapshot_text(_sample_data(), "us")
    joined = "\n".join(lines)
    assert "TL;DR" in joined
    assert "Gainers:" in joined and "Losers:" in joined
    assert "S&P 500" in joined


def test_snapshot_empty_when_no_data():
    assert m.snapshot_text({"us": [], "rates": [], "commodities": []}, "us") == []
    assert m.snapshot_html({"us": [], "rates": [], "commodities": []}, "us") == ""


# ---------------------------------------------------------------------------
# End-to-end render (offline): build from canned data, assert structure
# ---------------------------------------------------------------------------
def test_build_html_and_text_render_without_network():
    data = _sample_data()
    data["news"] = [{"title": "Fed holds rates steady", "link": "http://x",
                     "source": "Test", "region": "United States", "wrap": False, "age": 2}]
    data["crypto"] = []
    html = m.build_html(data, "Test day", "us")
    text = m.build_text(data, "Test day", "us")
    assert "Market Recap" in html and "Snapshot" in html
    assert "Asia-Pacific" in html          # new section renders when asia present
    assert "TL;DR" in text and "ASIA-PACIFIC" in text.upper()
