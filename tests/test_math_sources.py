from datetime import datetime, timedelta, timezone

from scripts.update_math import merge_items, parse_matharena, parse_rss, fetch_source, parse_arxiv_recent

NOW = datetime(2026, 10, 18, 7, tzinfo=timezone.utc)
SOURCE = {"id": "example", "name": "Mathematics", "url": "https://example.com/", "feed": "https://example.com/feed", "type": "rss"}


def test_pure_mathematics_is_not_filtered_and_undated_is_not_new():
    xml = '''<rss><channel><item><title>Prime gaps and compactness</title>
    <link>https://example.com/paper?utm_source=rss</link>
    <description><![CDATA[<p>A proof about prime gaps.</p><script>bad()</script>]]></description>
    </item></channel></rss>'''
    item = parse_rss(xml, SOURCE)[0]
    assert item["published_at"] is None
    assert item["url"] == "https://example.com/paper"
    assert item["excerpt"] == "A proof about prime gaps."
    assert item["domain"] == "mathematics"


def test_matharena_only_parses_dated_article_cards_and_retains_day_precision():
    html = '''<a href="/models">Models</a><a class="blog-card" href="/paper/">
    <span>2026-10-15</span><h3 class="card__title">Research mathematics</h3>
    <p class="blog-card__tldr">Counterexamples to a theorem.</p></a>'''
    item = parse_matharena(html, SOURCE)[0]
    assert item["url"] == "https://example.com/paper"
    assert item["date_precision"] == "day"
    assert item["published_at"].startswith("2026-10-15")


def test_repeated_runs_retain_translation_and_dedupe_by_url():
    previous = {"source_id": "example", "url": "https://example.com/paper", "title": "Prime gaps",
                "excerpt": "A proof", "title_zh": "素数间距", "excerpt_zh": "一份证明",
                "published_at": NOW.isoformat(), "first_seen_at": NOW.isoformat()}
    fetched = {k: v for k, v in previous.items() if k not in {"title_zh", "excerpt_zh", "first_seen_at"}}
    items = merge_items([previous], [fetched], NOW + timedelta(hours=1), 90, {"example"})
    assert len(items) == 1
    assert items[0]["title_zh"] == "素数间距"
    assert items[0]["first_seen_at"] == NOW.isoformat()
    changed = {**fetched, "title": "Updated prime gaps"}
    assert "title_zh" not in merge_items([previous], [changed], NOW, 90, {"example"})[0]


def test_failed_source_keeps_cached_articles_without_fabricating_publication_dates(monkeypatch):
    from scripts import update_math
    import requests
    def fail(*args, **kwargs):
        raise requests.Timeout("private/internal diagnostic")
    monkeypatch.setattr(update_math.requests, "get", fail)
    fetched, status = fetch_source(SOURCE, NOW)
    assert fetched == []
    assert status["ok"] is False and status["error"] == "Timeout"
    assert "private/internal" not in str(status)
    previous = {"source_id": "example", "url": "https://example.com/paper", "title": "Prime gaps", "excerpt": "",
                "published_at": None, "first_seen_at": NOW.isoformat()}
    assert merge_items([previous], fetched, NOW, 90, {"example"})[0]["published_at"] is None


def test_retention_drops_future_and_expired_and_disabled_sources():
    base = {"source_id": "example", "url": "https://example.com/paper", "title": "Paper", "excerpt": ""}
    for date in [NOW + timedelta(days=1), NOW - timedelta(days=91)]:
        assert merge_items([], [{**base, "published_at": date.isoformat()}], NOW, 90, {"example"}) == []
    assert merge_items([], [{**base, "published_at": NOW.isoformat()}], NOW, 90, set()) == []


def test_arxiv_empty_announcement_feed_is_healthy_but_html_is_not():
    import pytest
    source = {**SOURCE, "allow_empty": True}
    assert parse_rss('<rss version="2.0"><channel><title>math.NT updates</title></channel></rss>', source) == []
    with pytest.raises(ValueError):
        parse_rss('<html><body>Service unavailable</body></html>', source)


def test_mixed_research_feed_filters_ai_hype_but_keeps_mathematical_work():
    source = {**SOURCE, "topics": ["ai_math"], "filter": "math_ai"}
    xml = '''<rss><channel>
    <item><title>A new language model</title><link>https://example.com/model</link><description>Faster inference.</description></item>
    <item><title>Neural theorem proving</title><link>https://example.com/proof</link><description>Lean proofs.</description></item>
    </channel></rss>'''
    items = parse_rss(xml, source)
    assert len(items) == 1
    assert set(items[0]["topics"]) == {"ai_math", "formal"}


def test_dated_arxiv_listing_never_invents_abstracts_or_dates():
    source = {**SOURCE, "content_type": "paper", "recency_basis": "announced"}
    html = '''<dl id="articles"><h3>Fri, 16 Oct 2026 (2 entries)</h3>
    <dt><a title="Abstract" href="/abs/2610.10000">arXiv:2610.10000</a></dt>
    <dd><div class="list-title">Title: Prime gaps</div><div class="list-authors">A. Author</div>
    <div class="list-subjects">Subjects: Number Theory</div></dd>
    <h3>Undated announcements</h3><dt><a title="Abstract" href="/abs/2610.10001">ID</a></dt>
    <dd><div class="list-title">Title: Undated paper</div></dd></dl>'''
    items = parse_arxiv_recent(html, source)
    assert len(items) == 1 and items[0]["date_precision"] == "day"
    assert items[0]["published_at"].startswith("2026-10-16")
    assert items[0]["summary_kind"] == "source_metadata"
    assert "metadata" in items[0]["excerpt"] and "A. Author" in items[0]["authors"]


def test_cross_listed_papers_merge_sources_and_keep_real_abstract():
    base = {"url": "https://example.com/paper", "title": "Paper", "published_at": NOW.isoformat()}
    old = {**base, "source_id": "number", "source": "Number Theory", "topics": ["frontier"],
           "excerpt": "The actual abstract.", "summary_kind": "source_excerpt", "excerpt_zh": "真实摘要。"}
    new = {**base, "source_id": "logic", "source": "Logic", "topics": ["formal"],
           "excerpt": "Authors only", "summary_kind": "source_metadata"}
    item = merge_items([old], [new], NOW, 90, {"number", "logic"})[0]
    assert item["excerpt"] == "The actual abstract."
    assert item["excerpt_zh"] == "真实摘要。"
    assert set(item["topics"]) == {"frontier", "formal"}
    assert {ref["id"] for ref in item["source_refs"]} == {"number", "logic"}


def test_release_update_time_is_explicit_and_fallback_handles_failed_rss(monkeypatch):
    from scripts import update_math
    from types import SimpleNamespace
    import requests
    atom = '''<feed xmlns="http://www.w3.org/2005/Atom"><title>Releases</title>
    <entry><title>v4.0</title><link href="https://example.com/release"/>
    <updated>2026-10-16T10:00:00Z</updated></entry></feed>'''
    assert parse_rss(atom, SOURCE)[0]["recency_basis"] == "updated"
    html = '<dl id="articles"><h3>Fri, 16 Oct 2026</h3><dt><a title="Abstract" href="/abs/2610.1">ID</a></dt><dd><div class="list-title">Title: Prime gaps</div></dd></dl>'
    def get(url, **kwargs):
        if url == SOURCE["feed"]:
            raise requests.Timeout()
        return SimpleNamespace(content=html, raise_for_status=lambda: None)
    monkeypatch.setattr(update_math.requests, "get", get)
    items, status = fetch_source({**SOURCE, "recent_url": "https://example.com/recent"}, NOW)
    assert items and status["ok"] and status["rss_error"] == "Timeout"
