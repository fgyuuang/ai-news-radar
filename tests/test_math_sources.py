from datetime import datetime, timedelta, timezone

from scripts.update_math import merge_items, parse_matharena, parse_rss, fetch_source

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
