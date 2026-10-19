import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import radar_daily as daily
import codex_editorial as editorial


def store(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def item(domain="ai", url="https://example.org/story"):
    entry = dict(domain=domain, url=url, source="Example", source_title="Title", source_excerpt="Evidence", published_at=None)
    entry["key"] = editorial.source_key(entry)
    return entry


def test_open_source_projects_are_a_separate_category_and_not_falsely_dated(tmp_path):
    url = "https://github.com/example/tool"
    store(tmp_path / "data/today-projects.json", {"items": [{"project_name": "example/tool", "url": url, "summary": "Tool", "observed_at": "2026-10-18T00:00:00Z"}]})
    store(tmp_path / "data/latest-24h.json", {"items": [{"url": url, "title": "Same tool"}]})
    result = editorial.candidates(tmp_path, 20, datetime.now(timezone.utc), 10)
    assert len(result) == 1
    assert result[0]["domain"] == "project"
    assert result[0]["source_title"] == "example/tool"
    assert result[0]["published_at"] is None


def test_changed_source_is_an_update_but_identical_source_is_skipped(tmp_path, monkeypatch):
    repo, reports, day = tmp_path / "repo", tmp_path / "reports", tmp_path / "reports/2026-10-18"
    current = item()
    other = item("math", "https://example.org/math")
    store(reports / "reviewed.json", {current["url"]: {"key": "old", "date": "2026-10-17"}, other["url"]: {"key": other["key"], "date": "2026-10-17"}})
    monkeypatch.setattr(daily, "sync", lambda _: None)
    monkeypatch.setattr(editorial, "candidates", lambda *args: [current, other])
    monkeypatch.setattr(editorial, "context", lambda value: value)
    daily.prepare(repo, reports, day)
    bundle = daily.read(day / "bundle.json")
    assert bundle["selected"] == [current]
    assert bundle["changes"][current["url"]] == "updated"


def test_crashed_delivery_claim_prevents_next_day_automatic_resend(tmp_path, monkeypatch):
    repo, reports, day = tmp_path / "repo", tmp_path / "reports", tmp_path / "reports/2026-10-18"
    current = item()
    store(reports / "2026-10-17/delivery.json", {"channels": {"qqbot": {"state": "pending"}}})
    store(reports / "2026-10-17/manifest.json", {"date": "2026-10-17", "selected": [current]})
    monkeypatch.setattr(daily, "sync", lambda _: None)
    monkeypatch.setattr(editorial, "candidates", lambda *args: [current])
    daily.prepare(repo, reports, day)
    assert daily.read(day / "bundle.json")["selected"] == []


@pytest.mark.parametrize("channels,status", [({}, "FAILED"), ({"qqbot": {"success": True}}, "PARTIAL"), ({"qqbot": {"success": True}, "wechat": {"success": True}}, "COMPLETE")])
def test_each_channel_needs_explicit_confirmation(channels, status):
    assert daily.delivery_status({"channels": channels}) == status


def test_pending_receipt_stops_all_retries_without_contacting_channels(tmp_path, monkeypatch):
    day = tmp_path / "2026-10-18"
    store(day / "delivery.json", {"channels": {"wechat": {"state": "pending", "success": False}}})
    monkeypatch.setattr(daily, "invoke", lambda _: pytest.fail("must never contact a channel"))
    assert daily.deliver(tmp_path, day) == 1


def test_digest_has_all_three_sections_and_no_fake_publication_date():
    entry = {**item("project"), "title_zh": "工具", "summary_zh": "材料说明工具功能。", "recommend_reason_zh": "了解使用场景。"}
    bundle = dict(date="2026-10-18", selected=[entry], changes={entry["url"]: "new"}, deferred={})
    rendered = daily.render(bundle, [entry])
    assert all(label in rendered for label in daily.LABELS.values())
    assert "不代表新发布" in rendered
    assert entry["url"] in rendered


def test_daily_digest_includes_rankings_separately_from_substantive_updates():
    url = "https://gitlab.com/team/math"
    payload = {"items": [{"url": url, "project_name": "team/math"}], "boards": [
        {"platform": "gitlab", "period": period, "basis": "current_snapshot", "metric": "total_stars",
         "label": "累计 Star", "generated_at": "2026-10-19T00:00:00Z", "entries": [{"url": url, "value": 100}]}
        for period in ("daily", "weekly", "monthly")]}
    overview = daily.ranking_digest(payload)
    assert len(overview) == 1
    rendered = daily.render(dict(date="2026-10-19", selected=[], changes={}, deferred={}, project_rankings=overview), [])
    assert "等待对应历史" in rendered and "100 累计 Star" in rendered
    assert "今日暂无新增或内容变化" in rendered


def test_missing_model_result_rejected_before_publication_or_delivery(tmp_path, monkeypatch):
    day = tmp_path / "2026-10-18"
    store(day / "bundle.json", {"date": daily.now().date().isoformat(), "pending": [item()], "selected": [item()]})
    monkeypatch.setattr(daily, "sync", lambda _: pytest.fail("must validate before publishing"))
    with pytest.raises(ValueError, match="omitted"):
        daily.finalize(tmp_path, tmp_path, day)


def test_delivery_archives_and_claims_before_any_channel_and_never_retries_partial(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import hashlib
    moment = datetime(2026, 10, 18, 9, tzinfo=timezone(timedelta(hours=8)))
    monkeypatch.setattr(daily, "now", lambda: moment)
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    sender = home / ".codex/plugins/cache/personal/codex-wechat-channel/1/skills/codex-wechat-channel/scripts/wechat_channel.py"
    sender.parent.mkdir(parents=True)
    sender.write_text("# fake sender", encoding="utf-8")
    day = tmp_path / "2026-10-18"
    day.mkdir()
    text = "个人信息雷达日报｜2026-10-18\nAI、开源和数学。\n"
    (day / "digest.txt").write_text(text, encoding="utf-8")
    article = item()
    store(day / "manifest.json", {"date": "2026-10-18", "sha256": hashlib.sha256(text.encode()).hexdigest(), "selected": [article]})
    archived = []
    monkeypatch.setattr(daily, "archive", lambda *args: archived.append(args) or "safe-archive.md")
    calls = []

    def fake_invoke(command):
        assert archived and (day / "delivery.json").exists()
        calls.append(command)
        if "list" in command:
            return SimpleNamespace(returncode=0, stdout='{"peers": ["paired-test-peer"]}', stderr="")
        success = "qqbot" in command
        return SimpleNamespace(returncode=0 if success else 1, stdout=json.dumps({"success": success}), stderr="")

    monkeypatch.setattr(daily, "invoke", fake_invoke)
    assert daily.deliver(tmp_path, day) == 1
    receipt = daily.read(day / "delivery.json")
    assert receipt["status"] == "PARTIAL"
    assert daily.read(tmp_path / "reviewed.json")[article["url"]]["key"] == article["key"]
    assert len(calls) == 3
    assert daily.deliver(tmp_path, day) == 1
    assert len(calls) == 3


def test_collection_processes_have_no_model_credentials_and_keep_categories(tmp_path, monkeypatch):
    from types import SimpleNamespace
    checked = []
    monkeypatch.setattr(daily, "sync", lambda _: None)
    monkeypatch.setattr(editorial, "git", lambda *args: "")
    monkeypatch.setattr(editorial, "candidates", lambda *args: [item(domain, f"https://example.org/{domain}") for domain in daily.LABELS])
    def fake_run(command, **kwargs):
        assert kwargs["env"]["DEEPSEEK_API_KEY"] == kwargs["env"]["OPENAI_API_KEY"] == ""
        assert all("codex" not in str(value).lower() for value in command[3:4])
        checked.append(command)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(daily.subprocess, "run", fake_run)
    assert daily.collect(tmp_path / "repo", tmp_path / "reports") == 0
    assert len(checked) == 5
    history = daily.read(tmp_path / "reports/observed.json")
    assert {entry["domain"] for entry in history.values()} == set(daily.LABELS)


def test_archive_preserves_provenance_is_idempotent_and_refuses_conflicts(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    vault = tmp_path / "Documents/Obsidian Vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "网页资料/_inbox").mkdir(parents=True)
    text = "个人信息雷达日报｜2026-10-18\n链接：https://example.org/proof\n"
    path = Path(daily.archive(text, "2026-10-18"))
    before = path.read_bytes()
    assert not before.startswith(b"\xef\xbb\xbf")
    assert "content_origin: external-adapted" in before.decode("utf-8")
    assert "> [!source]" in before.decode("utf-8")
    assert "https://example.org/proof" in before.decode("utf-8")
    assert daily.archive(text, "2026-10-18") == str(path)
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match="conflict"):
        daily.archive(text + "different", "2026-10-18")
    assert path.read_bytes() == before
