"""Model-free, public multi-platform discovery with honest ranking windows.

Native Trending stars, measured counter growth and rolling downloads are separate
boards. Historical observations are public counters only, never private state.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from urllib.parse import quote, urlparse

import requests

try:
    from scripts.project_sources import clean_text, parse_github_trending
except ModuleNotFoundError:
    from project_sources import clean_text, parse_github_trending

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
PERIODS = {"daily": 1, "weekly": 7, "monthly": 30}
NAMES = {"github": "GitHub", "gitlab": "GitLab", "codeberg": "Codeberg",
         "hf_models": "Hugging Face Models", "hf_datasets": "Hugging Face Datasets",
         "hf_spaces": "Hugging Face Spaces", "npm": "npm"}


def iso(moment):
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def read(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def topics_for(name, description, tags, config):
    value = " ".join((name, description, " ".join(str(x) for x in tags)))
    if any(re.search(pattern, value, re.I) for pattern in config.get("exclude_patterns", [])):
        return []
    return [topic for topic, pattern in config["topics"].items() if re.search(pattern, value, re.I)]


def integer(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def project(platform, name, url, summary, now, config, *, tags=(), **fields):
    host = {"github": "github.com", "gitlab": "gitlab.com", "codeberg": "codeberg.org",
            "npm": "www.npmjs.com"}.get(platform, "huggingface.co")
    parsed = urlparse(str(url))
    if parsed.scheme != "https" or parsed.hostname != host or parsed.username or parsed.password or not parsed.path.strip("/"):
        return None
    summary = clean_text(summary)[:1200]
    topics = topics_for(name, summary, tags, config)
    if not topics:
        return None
    return {"project_name": name, "url": url, "summary": summary, "platform": platform,
            "site_name": NAMES[platform], "topics": topics, "observed_at": iso(now),
            "published_at": None, **fields}


def parse_github(html, period, now, config):
    # Reuse the original strict repository-link and description parser.
    from bs4 import BeautifulSoup
    rows = BeautifulSoup(html, "html.parser").select("article.Box-row")
    metrics = {}
    suffix = {"daily": "today", "weekly": "this week", "monthly": "this month"}[period]
    for row in rows:
        anchor = row.select_one("h2 a[href]")
        if anchor is None:
            continue
        metric = re.search(r"([\d,]+)\s+stars?\s+" + suffix, row.get_text(" ", strip=True), re.I)
        total = row.select_one('a[href$="/stargazers"]')
        metrics[str(anchor.get("href"))] = (
            int(metric.group(1).replace(",", "")) if metric else None,
            int(total.get_text(strip=True).replace(",", "")) if total and re.fullmatch(r"[\d,]+", total.get_text(strip=True)) else None,
        )
    items = []
    for row in parse_github_trending(html, now):
        growth, total = metrics.get("/" + row["project_name"], (None, None))
        item = project("github", row["project_name"], row["url"], row["summary"], now, config,
                       total_stars=total, native_growth={period: growth}, native_rank={period: row["source_rank"]})
        if item:
            items.append(item)
    return items


def parse_forge(payload, platform, now, config):
    rows = payload.get("data") if platform == "codeberg" and isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("Invalid forge list")
    result = []
    for row in rows:
        if row.get("archived") or row.get("private") or row.get("empty"):
            continue
        codeberg = platform == "codeberg"
        item = project(platform, row.get("full_name" if codeberg else "path_with_namespace", ""),
                       row.get("html_url" if codeberg else "web_url"), row.get("description"), now, config,
                       tags=row.get("topics") or row.get("tag_list") or [],
                       total_stars=integer(row.get("stars_count" if codeberg else "star_count")),
                       updated_at=row.get("updated_at" if codeberg else "last_activity_at"),
                       license=None)
        if item:
            result.append(item)
    return result


def parse_huggingface(rows, kind, now, config):
    if not isinstance(rows, list) or not rows:
        raise ValueError("Invalid Hugging Face list")
    result = []
    for rank, row in enumerate(rows, 1):
        if row.get("private") or row.get("disabled"):
            continue
        card = row.get("cardData") or {}
        name = row.get("id", "")
        tags = row.get("tags") or []
        description = row.get("description") or card.get("short_description") or " · ".join(tags[:16])
        prefix = {"models": "", "datasets": "datasets/", "spaces": "spaces/"}[kind]
        item = project("hf_" + kind, name, "https://huggingface.co/" + prefix + name, description, now, config,
                       tags=[*tags, "ai" if kind != "datasets" else "dataset"],
                       likes=integer(row.get("likes")), downloads=integer(row.get("downloads")),
                       trending_score=row.get("trendingScore"), source_rank=rank,
                       updated_at=row.get("lastModified"), license=card.get("license") or next((x[8:] for x in tags if x.startswith("license:")), None),
                       gated=row.get("gated", False), artifact_kind=kind)
        if item:
            result.append(item)
    return result


def parse_npm(payload, now, config):
    if not isinstance(payload, dict) or not isinstance(payload.get("objects"), list):
        raise ValueError("Invalid npm search")
    result = []
    for row in payload["objects"]:
        package = row.get("package") or {}
        name = package.get("name", "")
        if not name or not re.fullmatch(r"(?:@[\w.-]+/)?[\w.-]+", name):
            continue
        item = project("npm", name, "https://www.npmjs.com/package/" + name,
                       package.get("description"), now, config, tags=package.get("keywords") or [],
                       version=package.get("version"), updated_at=package.get("date"),
                       license=package.get("license"), downloads_by_period={
                           key: integer((row.get("downloads") or {}).get(key)) for key in ("weekly", "monthly")})
        if item:
            result.append(item)
    return result


def merge_items(items):
    result = {}
    for item in items:
        old = result.get(item["url"])
        if old is None:
            result[item["url"]] = dict(item)
        else:
            for key in ("native_growth", "native_rank"):
                if key in item:
                    old[key] = {**old.get(key, {}), **item[key]}
            old["topics"] = sorted(set(old["topics"]) | set(item["topics"]))
    return list(result.values())


def observe(items, history, now):
    """At most one public counter sample / 6h; keep 33 days, no filled gaps."""
    timestamp = int(now.timestamp())
    cutoff = timestamp - 33 * 86400
    for url in list(history):
        history[url] = [sample for sample in history[url] if sample[0] >= cutoff]
        if not history[url]:
            del history[url]
    for item in items:
        counter = item.get("likes") if item["platform"].startswith("hf_") else item.get("total_stars")
        if integer(counter) is None:
            continue
        samples = history.setdefault(item["url"], [])
        if not samples or timestamp - samples[-1][0] >= 6 * 3600:
            samples.append([timestamp, counter])
        growth = {}
        for period, days in PERIODS.items():
            target = timestamp - days * 86400
            baseline = next((sample for sample in reversed(samples) if target - 6 * 3600 <= sample[0] <= target), None)
            growth[period] = ({"value": counter - baseline[1], "from": iso(datetime.fromtimestamp(baseline[0], UTC)),
                               "to": iso(now), "hours": round((timestamp - baseline[0]) / 3600, 1)}
                              if baseline else None)
        item["observed_growth"] = growth
    return history


def boards(items, now):
    result = []
    for platform in NAMES:
        pool = [item for item in items if item["platform"] == platform and not item.get("stale")]
        if not pool:
            continue
        for period in PERIODS:
            def emit(basis, metric, label, entries, **extra):
                if entries:
                    result.append({"platform": platform, "period": period, "basis": basis, "metric": metric,
                                   "label": label, "generated_at": iso(now), "entries": entries, **extra})
            if platform == "github":
                native = sorted([{"url": p["url"], "value": p.get("native_growth", {}).get(period),
                                  "source_rank": p.get("native_rank", {}).get(period)} for p in pool
                                 if integer(p.get("native_growth", {}).get(period)) is not None],
                                key=lambda r: (-r["value"], r["source_rank"]))
                emit("platform_window", "stars", "GitHub Trending 区间新增 Star", native,
                     scope="仅主题筛选后的 Trending 样本，不是 GitHub 全站升星排名")
            if platform == "npm":
                rows = [{"url": p["url"], "value": p.get("downloads_by_period", {}).get(period),
                         **p.get("download_windows", {}).get(period, {})} for p in pool]
                rows = sorted([p for p in rows if integer(p["value"]) is not None], key=lambda r: -r["value"])
                emit("platform_window", "downloads", "npm 区间下载量", rows, scope="关键词搜索样本；下载量不等于独立用户数")
                continue
            observed = [{"url": p["url"], **p["observed_growth"][period]} for p in pool
                        if p.get("observed_growth", {}).get(period) is not None]
            if observed:
                emit("observed_growth", "likes" if platform.startswith("hf_") else "stars",
                     "历史观测点赞变化" if platform.startswith("hf_") else "历史观测升星",
                     sorted(observed, key=lambda r: -r["value"]), scope="仅持续观测样本；区间约为指定天数，实际起止时间逐项提供")
            elif platform != "github":
                field = "trending_score" if platform.startswith("hf_") else "total_stars"
                rows = [{"url": p["url"], "value": p.get(field)} for p in pool if isinstance(p.get(field), (int, float))]
                emit("current_snapshot", field, "当前趋势分" if platform.startswith("hf_") else "累计 Star（等待历史）",
                     sorted(rows, key=lambda r: -r["value"]), history_pending=True,
                     scope="不是日/周/月新增；积累足够的历史后展示对应观测榜")
    return result


def npm_daily(items, previous, now):
    """Official last-day counts for a bounded sample; cache six hours per package."""
    old = {item["url"]: item for item in previous.get("items", [])}
    selected = sorted([p for p in items if p["platform"] == "npm"],
                      key=lambda p: -int(p.get("downloads_by_period", {}).get("weekly") or 0))[:20]
    def fetch(item):
        cached = old.get(item["url"], {})
        if cached.get("daily_download_checked_at"):
            checked = datetime.fromisoformat(cached["daily_download_checked_at"].replace("Z", "+00:00"))
            if now - timedelta(hours=6) <= checked <= now:
                return item, cached.get("downloads_by_period", {}).get("daily"), cached.get("download_windows", {}).get("daily", {}), iso(checked)
        try:
            response = requests.get("https://api.npmjs.org/downloads/point/last-day/" + quote(item["project_name"], safe=""), timeout=(8, 20))
            response.raise_for_status()
            value = response.json()
            count = integer(value.get("downloads"))
            if count is None or not value.get("start") or not value.get("end"):
                raise ValueError("Invalid daily downloads")
            return item, count, {"from": value["start"], "to": value["end"]}, iso(now)
        except (requests.RequestException, ValueError):
            return item, None, {}, None
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(fetch, selected))
    for item, count, window, checked in outcomes:
        if count is not None:
            item["downloads_by_period"]["daily"] = count
            item.setdefault("download_windows", {})["daily"] = window
            item["daily_download_checked_at"] = checked
    return {"id": "npm:daily-downloads", "ok": all(x[1] is not None for x in outcomes),
            "count": sum(x[1] is not None for x in outcomes), "requested": len(selected),
            "checked_at": iso(now), "url": "https://api.npmjs.org/downloads/point/last-day"}


def editorial_items(payload, limit=100):
    """Prioritize ranked projects, then balance platforms and specialist topics."""
    pools = [p for p in payload.get("items", []) if not p.get("stale")]
    ranks = {}
    for board in payload.get("boards", []):
        if board.get("stale"):
            continue
        for rank, row in enumerate(board["entries"], 1):
            ranks[row["url"]] = min(ranks.get(row["url"], 100), rank)
    selected, platforms, topics = [], {}, {}
    while pools and len(selected) < limit:
        def score(p):
            tags = set(p["topics"]) - {"ai"}
            diversity = sum(5 / (1 + topics.get(t, 0)) for t in tags)
            return (diversity + 12 / (1 + platforms.get(p["platform"], 0))
                    + 6 / ranks.get(p["url"], 50))
        chosen = max(pools, key=score)
        pools.remove(chosen)
        platforms[chosen["platform"]] = platforms.get(chosen["platform"], 0) + 1
        for topic in chosen["topics"]:
            topics[topic] = topics.get(topic, 0) + 1
        selected.append(chosen)
    return selected


def jobs(config):
    tasks = []
    enabled = config["platforms"]
    if enabled.get("github"):
        for period in PERIODS:
            tasks.append(("github:" + period, "https://github.com/trending", {"since": period},
                          lambda r, n, p=period: parse_github(r.text, p, n, config)))
        for query in config.get("github_queries", []):
            def parse_search(r, now):
                payload = r.json()
                if not isinstance(payload.get("items"), list):
                    raise ValueError("Invalid GitHub search")
                return [p for row in payload["items"] if not row.get("archived") for p in [
                    project("github", row["full_name"], row["html_url"], row.get("description"), now, config,
                            tags=row.get("topics") or [], total_stars=integer(row.get("stargazers_count")),
                            updated_at=row.get("pushed_at"), license=(row.get("license") or {}).get("spdx_id"))] if p]
            tasks.append(("github:search:" + query, "https://api.github.com/search/repositories",
                          {"q": query + " archived:false", "sort": "stars", "per_page": 20}, parse_search))
    for platform in ("gitlab", "codeberg"):
        if not enabled.get(platform):
            continue
        for term in config["search_terms"]:
            url = "https://gitlab.com/api/v4/projects" if platform == "gitlab" else "https://codeberg.org/api/v1/repos/search"
            params = ({"search": term, "order_by": "star_count", "sort": "desc", "simple": "true", "per_page": 25}
                      if platform == "gitlab" else {"q": term, "sort": "stars", "order": "desc", "limit": 25})
            tasks.append((platform + ":" + term, url, params,
                          lambda r, n, p=platform: parse_forge(r.json(), p, n, config)))
    if enabled.get("huggingface"):
        for kind in ("models", "datasets", "spaces"):
            tasks.append(("hf_" + kind, "https://huggingface.co/api/" + kind,
                          {"sort": "trendingScore", "limit": 40, "full": "true"},
                          lambda r, n, k=kind: parse_huggingface(r.json(), k, n, config)))
        # Target mathematics too, even when it is absent from the global top 40.
        tasks.append(("hf_models:math", "https://huggingface.co/api/models",
                      {"search": "math", "sort": "trendingScore", "limit": 20, "full": "true"},
                      lambda r, n: parse_huggingface(r.json(), "models", n, config)))
    if enabled.get("npm"):
        for query in config["npm_queries"]:
            tasks.append(("npm:" + query, "https://registry.npmjs.org/-/v1/search",
                          {"text": query, "size": 20, "popularity": 1, "quality": 0, "maintenance": 0},
                          lambda r, n: parse_npm(r.json(), n, config)))
    return tasks


def fetch_job(task, now):
    key, url, params, parser = task
    try:
        response = requests.get(url, params=params, timeout=(8, 30), headers={"User-Agent": "PersonalRadar/1.1 (public project discovery)"})
        response.raise_for_status()
        items = parser(response, now)
        return items, {"id": key, "ok": True, "count": len(items), "checked_at": iso(now), "url": response.url}
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        return [], {"id": key, "ok": False, "count": 0, "checked_at": iso(now), "url": url, "error": type(error).__name__}


def collect(output, config, now):
    previous = read(output / "project-radar.json", {})
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda task: fetch_job(task, now), jobs(config)))
    statuses = [status for _, status in results]
    # Carry forward each failed adapter's exact last-success rows. Never re-date
    # them, sample them as fresh counters, or silently replace a board with zero.
    old_batches = previous.get("source_batches", {})
    batches, fresh = {}, []
    for rows, status in results:
        old = old_batches.get(status["id"], [])
        batch = rows if status["ok"] else old
        batches[status["id"]] = batch
        fresh.extend(rows)
    items = merge_items(fresh)
    # Cap each platform while giving specific math/research/tooling topics room.
    def priority(item):
        tags = set(item["topics"])
        return (-len(tags - {"ai"}), -int(item.get("trending_score") or 0), -int(item.get("total_stars") or 0), item["url"])
    items = [p for platform in NAMES for p in sorted([x for x in items if x["platform"] == platform], key=priority)[:config["max_per_source"]]]
    if any(p["platform"] == "npm" for p in items):
        statuses.append(npm_daily(items, previous, now))
    history = observe(items, read(output / "project-history.json", {}), now)
    known = {item["url"] for item in items}
    retained = merge_items([row for status in statuses if not status["ok"] for row in batches.get(status["id"], [])])
    items.extend({**item, "stale": True} for item in retained if item["url"] not in known)
    rankings = boards(items, now)
    # Native-window failure must retain its former board with a visible date.
    failed = {s["id"] for s in statuses if not s["ok"]}
    current = {(b["platform"], b["period"], b["basis"]) for b in rankings}
    for board in previous.get("boards", []):
        identity = (board["platform"], board["period"], board["basis"])
        platform_failed = not any(s["ok"] for s in statuses if s["id"].split(":")[0] == board["platform"])
        native_failed = (("github:" + board["period"] in failed and board["platform"] == "github")
                         or (board["platform"] == "npm" and board["period"] == "daily" and "npm:daily-downloads" in failed)) and board["basis"] == "platform_window"
        if identity not in current and (platform_failed or native_failed):
            rankings.append({**board, "stale": True})
    payload = {"generated_at": iso(now), "period_days": PERIODS, "items": items, "boards": rankings,
               "sources": statuses, "source_batches": batches,
               "notes": ["榜单仅涵盖主题筛选后的采样项目，不代表全平台完整排行。",
                         "Star、点赞、趋势分、下载量分别排名；模型和数据集许可需查看原站。",
                         "历史榜不补造数据；首次采集从当前计数起积累，断档或不足时保留当前热度。"]}
    if not any(s["ok"] for s in statuses):
        # Keep last generated_at so an all-source outage cannot look fresh.
        payload["generated_at"] = previous.get("generated_at")
    write(output / "project-history.json", history)
    write(output / "project-radar.json", payload)
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument("--config", type=Path, default=ROOT / "feeds/project-radar.json")
    args = parser.parse_args()
    payload = collect(args.output_dir, read(args.config, {}), datetime.now(UTC))
    healthy = sum(s["ok"] for s in payload["sources"])
    print(json.dumps({"sources_ok": healthy, "sources_total": len(payload["sources"]),
                      "items": len(payload["items"]), "boards": len(payload["boards"]), "model_calls": 0}))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
