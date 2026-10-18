"""Rule-only collection and a once-daily native-Codex review/delivery workflow.

This module never invokes a model. Native Codex writes structured review results
between prepare and finalize. Delivery receipts and all private state stay local.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import codex_editorial as editorial

ROOT = Path(__file__).resolve().parents[1]
SHANGHAI = timezone(timedelta(hours=8))
LABELS = {"ai": "AI 资讯", "project": "开源项目", "math": "数学与 AI for Math"}


def now():
    return datetime.now(SHANGHAI)


def read(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def configure_network(runtime):
    proxy_file = runtime / ".local-codex/network-proxy.txt"
    if proxy_file.exists():
        from urllib.parse import urlparse
        proxy = proxy_file.read_text(encoding="utf-8").strip()
        parsed = urlparse(proxy)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password:
            raise ValueError("Proxy must be a local URL without credentials")
        os.environ["HTTPS_PROXY"] = proxy


def sync(repo):
    if editorial.git(repo, "status", "--porcelain"):
        raise ValueError("Dedicated checkout has unpublished changes; preserve and inspect them first")
    editorial.git(repo, "pull", "--rebase", "origin", "master")


def collect(repo, reports):
    """Windows entry: fetch public sources with model integrations disabled."""
    print("Syncing the dedicated source collection checkout.", flush=True)
    sync(repo)
    environment = os.environ.copy()
    environment.update(DEEPSEEK_API_KEY="", OPENAI_API_KEY="", EMAIL_DIGEST_ENABLED="0",
                       X_API_ENABLED="0", SOCIALDATA_ENABLED="0", TIKHUB_ENABLED="0",
                       PYTHONIOENCODING="utf-8")
    opml = ROOT / "feeds/follow.opml"
    if not opml.exists():
        opml = ROOT / "feeds/follow.example.opml"
    steps = [
        ["update_news.py", "--output-dir", "data", "--window-hours", "24", "--archive-days", "21", "--rss-opml", str(opml)],
        ["update_math.py", "--output-dir", "data"],
        ["persona_score.py", "--data-dir", "data"],
        ["generate_feed.py", "--data-dir", "data"],
    ]
    outcomes = {}
    for step in steps:
        if step[0] in {"persona_score.py", "generate_feed.py"} and outcomes.get("update_news.py") != 0:
            continue
        try:
            print(f"Collecting with {step[0]} (model credentials disabled).", flush=True)
            timeout = 1200 if step[0] == "update_news.py" else 240 if step[0] == "update_math.py" else 120
            result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / step[0]), *step[1:]],
                                    cwd=repo, env=environment, timeout=timeout, check=False)
            outcomes[step[0]] = result.returncode
        except subprocess.TimeoutExpired:
            outcomes[step[0]] = -1
    # Accumulate observed candidates across runs so a changing daily top list
    # does not silently discard articles before the next Codex review.
    history_path = reports / "observed.json"
    history = read(history_path, {})
    timestamp = now().isoformat()
    for item in editorial.candidates(repo, 100, now(), 100):
        identity = item["url"]
        previous = history.get(identity, {})
        history[identity] = {**item, "first_seen": previous.get("first_seen", timestamp), "last_seen": timestamp}
    history = {url: item for url, item in history.items()
               if datetime.fromisoformat(item["last_seen"]) >= now() - timedelta(days=7)}
    write(history_path, history)
    dirty = editorial.git(repo, "status", "--porcelain").splitlines()
    if any(not line.strip().split(maxsplit=1)[-1].startswith("data/") for line in dirty):
        raise ValueError("Collector generated an unexpected non-data change")
    if dirty:
        editorial.git(repo, "add", "--", "data/")
        editorial.git(repo, "-c", "user.name=Personal Radar Collector", "-c", "user.email=49341249+fgyuuang@users.noreply.github.com",
                      "commit", "-m", "chore: publish local collected radar sources")
        editorial.git(repo, "pull", "--rebase", "origin", "master")
        editorial.git(repo, "push", "origin", "HEAD:master")
    status = {"checked_at": timestamp, "outcomes": outcomes, "observed": len(history), "model_calls": 0}
    write(reports / "collection-status.json", status)
    print(json.dumps(status))
    return 0 if outcomes.get("update_news.py") == outcomes.get("update_math.py") == 0 else 1


def delivery_status(receipt):
    channels = receipt.get("channels", {})
    successes = sum(channels.get(name, {}).get("success") is True for name in ("qqbot", "wechat"))
    return "COMPLETE" if successes == 2 else "PARTIAL" if successes else "FAILED"


def prepare(repo, reports, day):
    receipt = read(day / "delivery.json")
    if receipt is not None:
        status = delivery_status(receipt)
        print(json.dumps({"status": "ALREADY_COMPLETE" if status == "COMPLETE" else status,
                          "stop": True, "receipt": str(day / "delivery.json"), "retry": False}))
        return 0
    if (day / "bundle.json").exists():
        print(json.dumps({"bundle": str(day / "bundle.json"), "resume": True, "stop": False}))
        return 0
    sync(repo)
    config = read(ROOT / "feeds/daily-digest.json")
    selected = editorial.candidates(repo, 100, now(), 100)
    observed = read(reports / "observed.json", {})
    by_url = {item["url"]: item for item in selected}
    # Keep the freshest actual source text when the cloud collection is newer.
    for url, item in observed.items():
        if url not in by_url and datetime.fromisoformat(item["last_seen"]) >= now() - timedelta(hours=72):
            by_url[url] = item
    previous = read(reports / "reviewed.json", {})
    # Recover attempts after a crash between sending and the reviewed-state write.
    # Any durable daily claim means delivery might already have happened.
    for receipt_path in reports.glob("????-??-??/delivery.json"):
        manifest = read(receipt_path.parent / "manifest.json", {})
        for item in manifest.get("selected", []):
            existing = previous.get(item["url"], {})
            if existing.get("date", "") <= manifest.get("date", ""):
                previous[item["url"]] = {**item, "date": manifest["date"]}
    grouped = {domain: [] for domain in LABELS}
    for item in by_url.values():
        if previous.get(item["url"], {}).get("key") == item["key"]:
            continue
        grouped[item["domain"]].append(item)
    selected = []
    for domain, items in grouped.items():
        limit = config["max_per_day"].get(domain, 0)
        selected.extend(items if limit == 0 else items[:limit])
    cache = {item["key"]: item for item in read(repo / editorial.OUTPUT, {"entries": []})["entries"]}
    with ThreadPoolExecutor(max_workers=6) as pool:
        pending = list(pool.map(editorial.context, [item for item in selected if item["key"] not in cache]))
    bundle = {"date": now().date().isoformat(), "prepared_at": now().isoformat(), "model": config["model"],
              "selected": selected, "pending": pending,
              "cached": [cache[item["key"]] for item in selected if item["key"] in cache],
              "changes": {item["url"]: "updated" if item["url"] in previous else "new" for item in selected},
              "source_generated_at": {name: read(repo / "data" / name, {}).get("generated_at")
                                      for name in ("latest-24h.json", "math-news.json", "today-projects.json")},
              "deferred": {domain: max(0, len(items) - (config["max_per_day"].get(domain) or len(items)))
                           for domain, items in grouped.items()}}
    write(day / "bundle.json", bundle)
    for index in range(0, len(pending), 12):
        write(day / f"batch-{index // 12 + 1:03d}.json", {"entries_to_review": pending[index:index + 12]})
    print(json.dumps({"bundle": str(day / "bundle.json"), "result": str(day / "model-result.json"),
                      "pending": len(pending), "selected": len(selected), "stop": False}, ensure_ascii=False))
    return 0


def render(bundle, entries):
    by_key = {entry["key"]: entry for entry in entries}
    lines = [f"个人信息雷达日报｜{bundle['date']}（上海时间）", ""]
    for domain, label in LABELS.items():
        lines.extend([label, ""])
        items = [item for item in bundle["selected"] if item["domain"] == domain]
        if not items:
            lines.extend(["今日暂无新增或内容变化。", ""])
        for index, item in enumerate(items, 1):
            entry = by_key[item["key"]]
            change = "新增" if bundle["changes"][item["url"]] == "new" else "更新（来源标题或摘录有变化）"
            date = item.get("published_at") or "原站未提供；本次观察到，不代表新发布"
            lines.extend([f"{index}. 【{change}｜{item['source']}】{entry['title_zh']}",
                          f"日期：{date}", f"摘要：{entry['summary_zh']}",
                          f"阅读价值：{entry['recommend_reason_zh']}",
                          f"依据：{'原文正文' if entry.get('context_kind') == 'article_text' else '来源摘录'}",
                          f"链接：{item['url']}", ""])
        deferred = bundle["deferred"].get(domain, 0)
        if deferred:
            lines.extend([f"另有 {deferred} 条待筛选，保留在采集记录中。", ""])
    lines.extend(["完整雷达：https://fgyuuang.github.io/ai-news-radar/",
                  "仅比较来源标题和摘录；未变化条目不重复推送。"])
    return "\n".join(lines) + "\n"


def finalize(repo, reports, day):
    if (day / "manifest.json").exists():
        print(json.dumps({"manifest": str(day / "manifest.json"), "resume": True}))
        return 0
    bundle = read(day / "bundle.json")
    if not bundle or bundle["date"] != now().date().isoformat():
        raise ValueError("Missing or stale daily bundle")
    result = read(day / "model-result.json")
    if result is None:
        result = {"entries": [entry for batch in sorted(day.glob("result-???.json"))
                               for entry in read(batch)["entries"]]}
    generated = editorial.validate(result, bundle["pending"])
    for entry in generated:
        entry.pop("context", None)
        entry.update(provider="codex-native", model=bundle["model"], generated_at=now().astimezone(timezone.utc).isoformat())
    entries = [*bundle["cached"], *generated]
    # Preserve attribution and enforce the same strict validation for cache hits.
    editorial.validate({"entries": entries}, bundle["selected"])
    sync(repo)
    cache = {entry["key"]: entry for entry in read(repo / editorial.OUTPUT, {"entries": []})["entries"]}
    cache.update({entry["key"]: entry for entry in entries})
    if generated:
        editorial.save_public(repo, cache, [item["key"] for item in bundle["selected"]], bundle["model"])
        editorial.publish(repo)
    digest = render(bundle, entries)
    digest_path = day / "digest.txt"
    digest_path.write_text(digest, encoding="utf-8")
    write(day / "manifest.json", {"date": bundle["date"], "digest": str(digest_path),
                                 "sha256": hashlib.sha256(digest.encode("utf-8")).hexdigest(),
                                 "selected": [{key: item[key] for key in ("url", "key", "domain")} for item in bundle["selected"]],
                                 "generated": len(generated)})
    print(json.dumps({"manifest": str(day / "manifest.json"), "generated": len(generated)}))
    return 0


def archive(digest, date):
    vault = Path.home() / "Documents/Obsidian Vault"
    inbox = vault / "网页资料/_inbox"
    if not (vault / ".obsidian").is_dir() or not inbox.is_dir():
        raise ValueError("The configured Obsidian inbox is unavailable")
    target = inbox / f"个人信息雷达日报-{date}.md"
    metadata = ("---\ntype: source\nsource_id: src-personal-radar-" + date.replace("-", "") +
                "\nsource_kind: document\ncontent_origin: external-adapted\nplatform: personal-radar\n"
                'url: "https://fgyuuang.github.io/ai-news-radar/"\nauthor: ""\npublished: ""\n' +
                f"clipped: {date}\ntopic: 科技与数学\nsubtopic: 信息雷达日报\nstatus: archived\n" +
                "reliability: unreviewed\nassets_status: remote\nderived_notes: []\narchive_policy: retain-only\n" +
                f"digest_date: {date}\ncreated: {date}\nupdated: {date}\ntags: [信息雷达日报]\naliases: []\n---\n\n")
    content = metadata + digest
    if target.exists():
        if target.read_text(encoding="utf-8") != content:
            raise ValueError("Archive conflict; refusing to overwrite")
    else:
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    return str(target)


def invoke(command):
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    return subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", timeout=180, **kwargs)


def deliver(reports, day):
    receipt_path = day / "delivery.json"
    existing = read(receipt_path)
    if existing is not None:
        status = delivery_status(existing)
        print(json.dumps({"status": "ALREADY_COMPLETE" if status == "COMPLETE" else status, "retry": False}))
        return 0 if status == "COMPLETE" else 1
    manifest = read(day / "manifest.json")
    if not manifest or manifest["date"] != now().date().isoformat() or now().hour < 9:
        raise ValueError("Delivery requires today's finalized digest at or after 09:00 Shanghai")
    path = day / "digest.txt"
    digest = path.read_text(encoding="utf-8")
    if hashlib.sha256(digest.encode("utf-8")).hexdigest() != manifest["sha256"]:
        raise ValueError("Digest changed after validation")
    if not digest.startswith(f"个人信息雷达日报｜{manifest['date']}"):
        raise ValueError("Digest date or format is invalid")
    archive_path = archive(digest, manifest["date"])
    # Exclusive date claim is persisted BEFORE contacting either channel.
    receipt = {"date": manifest["date"], "archive": archive_path, "channels": {}, "started_at": now().isoformat()}
    with receipt_path.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False)
    hermes = Path.home() / "AppData/Local/hermes/hermes-agent/venv/Scripts/hermes.exe"
    plugins = Path.home() / ".codex/plugins/cache/personal/codex-wechat-channel"
    senders = sorted(plugins.glob("*/skills/codex-wechat-channel/scripts/wechat_channel.py"), key=lambda p: p.stat().st_mtime, reverse=True)
    python = Path(r"C:\Python38\python.exe")
    for channel in ("qqbot", "wechat"):
        receipt["channels"][channel] = {"state": "pending", "success": False}
        write(receipt_path, receipt)
        try:
            if channel == "qqbot":
                output = invoke([str(hermes), "send", "--to", "qqbot", "--file", str(path), "--json"])
            else:
                if not senders:
                    raise ValueError("Configured WeChat plugin is missing")
                peers = invoke([str(python), "-X", "utf8", str(senders[0]), "list"])
                contacts = json.loads(peers.stdout).get("peers", []) if peers.returncode == 0 else []
                if len(contacts) != 1:
                    raise ValueError("Expected exactly one previously paired WeChat contact")
                output = invoke([str(python), "-X", "utf8", str(senders[0]), "send", "--to", contacts[0], "--text-file", str(path), "--json"])
            # Raw receipt is private and never enters the digest or public data.
            (day / f"{channel}-receipt.log").write_text(output.stdout + "\n" + output.stderr, encoding="utf-8")
            try:
                ack = json.loads(output.stdout)
            except ValueError:
                ack = {}
            success = output.returncode == 0 and isinstance(ack, dict) and ack.get("success") is True
            receipt["channels"][channel] = {"state": "confirmed" if success else "unconfirmed", "success": success, "exit": output.returncode}
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            receipt["channels"][channel] = {"state": "unconfirmed", "success": False, "error_type": type(error).__name__}
        write(receipt_path, receipt)
    # Mark attempted article versions even on partial/unknown delivery: never
    # resend them automatically on a later day after a possibly successful send.
    reviewed = read(reports / "reviewed.json", {})
    for item in manifest["selected"]:
        reviewed[item["url"]] = {"key": item["key"], "date": manifest["date"], "domain": item["domain"]}
    write(reports / "reviewed.json", reviewed)
    receipt["status"] = delivery_status(receipt)
    write(receipt_path, receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(receipt_path), "archive": archive_path}))
    return 0 if receipt["status"] == "COMPLETE" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("collect", "prepare", "finalize", "deliver"))
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--reports", type=Path, default=ROOT.parent / "reports/personal-radar")
    args = parser.parse_args()
    configure_network(args.repo)
    args.reports.mkdir(parents=True, exist_ok=True)
    day = args.reports / now().date().isoformat()
    day.mkdir(exist_ok=True)
    if args.action == "collect":
        return collect(args.repo, args.reports)
    return globals()[args.action](args.repo, args.reports, day) if args.action in {"prepare", "finalize"} else deliver(args.reports, day)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "FAILED", "error_type": type(error).__name__, "delivery_retried": False}))
        raise SystemExit(1)
