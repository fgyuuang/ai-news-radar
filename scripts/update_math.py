"""Independent, timestamped mathematics reader; never touches delivery state."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from xml.etree import ElementTree as ET

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil.parser import parse as parse_datetime

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]


def timestamp(value):
    if not value:
        return None
    try:
        result = parse_datetime(str(value))
        return result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)
    except (ValueError, TypeError, OverflowError):
        return None


def clean(value):
    soup = BeautifulSoup(str(value or ""), "html.parser")
    for tag in soup.select("script, style, iframe, form"):
        tag.decompose()
    # WordPress renders some formulas as images; retain their alternative text.
    for image in soup.select("img[alt]"):
        image.replace_with(image.get("alt", ""))
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()


def public_url(value, base):
    url = urlparse(urljoin(base, str(value or "")))
    expected = urlparse(base).hostname
    if url.scheme not in {"https", "http"} or url.hostname != expected or url.username or url.password:
        return ""
    query = [(k, v) for k, v in parse_qsl(url.query) if not k.startswith("utm_") and k not in {"fbclid", "gclid"}]
    return urlunparse((url.scheme, url.netloc, url.path.rstrip("/") or "/", "", urlencode(query), ""))


def record(source, title, url, published, excerpt, precision="datetime"):
    return {
        "id": hashlib.sha256(url.encode("utf-8")).hexdigest()[:20],
        "source_id": source["id"], "source": source["name"],
        "title": clean(title), "url": url,
        "published_at": published.isoformat() if published else None,
        "date_precision": precision, "excerpt": clean(excerpt)[:1200],
        "summary_kind": "source_excerpt", "domain": "mathematics",
    }


def parse_rss(content, source):
    feed = feedparser.parse(content)
    if not feed.entries:
        raise ValueError("No feed entries")
    out = []
    for entry in feed.entries[:120]:
        url = public_url(entry.get("link"), source["url"])
        if not url or not entry.get("title"):
            continue
        fields = dict(entry)
        published = timestamp(fields.get("published") or fields.get("updated"))
        contents = entry.get("content") or []
        excerpt = entry.get("summary") or (contents[0].get("value") if contents else "")
        out.append(record(source, entry["title"], url, published, excerpt))
    if not out:
        raise ValueError("Feed contains no valid article links")
    return out


def parse_matharena(content, source):
    soup = BeautifulSoup(content, "html.parser")
    cards = soup.select("a.blog-card[href]")
    if not cards:
        raise ValueError("MathArena article cards were not found")
    out = []
    for card in cards:
        heading = card.select_one(".card__title") or card.select_one("h2, h3, h4")
        url = public_url(card.get("href"), source["url"])
        if heading is None or not url:
            continue
        date = re.search(r"\b20\d{2}-\d{2}-\d{2}\b", card.get_text(" ", strip=True))
        excerpt = card.select_one(".blog-card__tldr")
        out.append(record(source, heading.get_text(" ", strip=True), url,
                          timestamp(date.group()) if date else None,
                          excerpt.get_text(" ", strip=True) if excerpt else "", "day"))
    if not out:
        raise ValueError("MathArena cards contain no valid articles")
    return out


def fetch_source(source, now):
    started = datetime.now(UTC)
    status = {"id": source["id"], "name": source["name"], "url": source["url"],
              "method": source["type"], "checked_at": now.isoformat()}
    try:
        response = requests.get(source.get("feed") or source["url"], timeout=(10, 40),
                                headers={"User-Agent": "PersonalMathRadar/1.0 (+https://github.com/fgyuuang/ai-news-radar)"})
        response.raise_for_status()
        items = parse_matharena(response.content, source) if source["type"] == "matharena" else parse_rss(response.content, source)
        dated = [item["published_at"] for item in items if item["published_at"]]
        status.update(ok=True, item_count=len(items), latest_published_at=max(dated) if dated else None)
        return items, status
    except (requests.RequestException, ValueError) as error:
        # Error diagnostics are status metadata, never article summaries.
        status.update(ok=False, item_count=0, error=type(error).__name__)
        return [], status
    finally:
        status["duration_ms"] = int((datetime.now(UTC) - started).total_seconds() * 1000)


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def merge_items(previous, fetched, now, archive_days, source_ids):
    cutoff = now - timedelta(days=archive_days)
    combined = {}
    for item in [*previous, *fetched]:
        if item.get("source_id") not in source_ids or not item.get("url"):
            continue
        published = timestamp(item.get("published_at"))
        observed = timestamp(item.get("first_seen_at")) or now
        if (published and (published < cutoff or published > now)) or (not published and observed < cutoff):
            continue
        old = combined.get(item["url"], {})
        merged = {**old, **item}
        merged["first_seen_at"] = old.get("first_seen_at") or item.get("first_seen_at") or now.isoformat()
        # Cached translations belong to the exact current title/excerpt only.
        for field in ("title", "excerpt"):
            if old and old.get(field) != item.get(field):
                merged.pop(f"{field}_zh", None)
        combined[item["url"]] = merged
    return sorted(combined.values(), key=lambda item: item.get("published_at") or item["first_seen_at"], reverse=True)


def translate(text):
    if not text or re.search(r"[\u4e00-\u9fff]", text):
        return text
    response = requests.get("https://translate.googleapis.com/translate_a/single", timeout=(8, 18),
                            params={"client": "gtx", "sl": "auto", "tl": "zh-CN", "dt": "t", "q": text})
    response.raise_for_status()
    return "".join(part[0] for part in response.json()[0] if part and part[0])


def enrich(item):
    for field in ("title", "excerpt"):
        if item.get(field) and not item.get(f"{field}_zh"):
            try:
                item[f"{field}_zh"] = translate(item[field])
            except (requests.RequestException, ValueError, TypeError, IndexError):
                pass
    return item


def save(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_feed(path, payload):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    for key, value in {"title": "个人数学雷达", "link": "https://fgyuuang.github.io/ai-news-radar/",
                       "description": "数学、形式化证明与 AI for Math；来源原文摘录及中文译文"}.items():
        ET.SubElement(channel, key).text = value
    for item in payload["items"][:50]:
        node = ET.SubElement(channel, "item")
        for key, value in {"title": item.get("title_zh") or item["title"], "link": item["url"],
                           "guid": item["url"], "description": item.get("excerpt_zh") or item["excerpt"]}.items():
            ET.SubElement(node, key).text = value
        if item["published_at"]:
            from email.utils import format_datetime
            ET.SubElement(node, "pubDate").text = format_datetime(timestamp(item["published_at"]))
    ET.ElementTree(rss).write(path, encoding="utf-8", xml_declaration=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="data")
    parser.add_argument("--config", default=str(ROOT / "feeds/math-sources.json"))
    parser.add_argument("--no-translate", action="store_true")
    args = parser.parse_args()
    config = load_json(Path(args.config), {})
    sources = [s for s in config["sources"] if s.get("enabled", True)]
    now = datetime.now(UTC)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    old = load_json(output / "math-news.json", {"items": []})
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda source: fetch_source(source, now), sources))
    fetched = [item for items, _ in results for item in items]
    items = merge_items(old["items"], fetched, now, config.get("archive_days", 90), {s["id"] for s in sources})
    if config.get("translate_zh") and not args.no_translate:
        with ThreadPoolExecutor(max_workers=4) as pool:
            items = list(pool.map(enrich, items))
    window = config.get("window_hours", 72)
    since = now - timedelta(hours=window)
    for _, status in results:
        status["recent_count"] = sum(item["source_id"] == status["id"] and timestamp(item["published_at"]) is not None
                                     and timestamp(item["published_at"]) >= since for item in items)
    payload = {"generated_at": now.isoformat(), "window_hours": window,
               "archive_days": config.get("archive_days", 90),
               "recent_count": sum(timestamp(item["published_at"]) is not None and timestamp(item["published_at"]) >= since for item in items),
               "sources": [status for _, status in results], "items": items,
               "summary_policy": "Source excerpts; Chinese translations when available. Undated articles are excluded from recent windows."}
    save(output / "math-news.json", payload)
    save(output / "math-source-status.json", {key: payload[key] for key in ("generated_at", "sources")})
    write_feed(output / "math-feed.xml", payload)
    print(json.dumps({"items": len(items), "recent_count": payload["recent_count"],
                      "healthy": sum(s["ok"] for s in payload["sources"]), "sources": len(sources)}, ensure_ascii=False))
    # Keep last good articles on partial failure, but fail a fully broken run visibly.
    return 0 if any(status["ok"] for _, status in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
