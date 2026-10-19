import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import project_radar as radar

NOW = datetime(2026, 10, 19, 2, tzinfo=timezone.utc)
CONFIG = radar.read(Path(__file__).resolve().parents[1] / "feeds/project-radar.json", {})


def repo(url="https://gitlab.com/team/math", stars=100, **extra):
    return radar.project("gitlab", "team/math", url, "Scientific theorem proving", NOW, CONFIG,
                         total_stars=stars, **extra)


@pytest.mark.parametrize("period,phrase,value", [("daily", "today", 123), ("weekly", "this week", 1234), ("monthly", "this month", 12345)])
def test_native_trending_counts_keep_their_period_and_global_rank(period, phrase, value):
    html = f'''<article class="Box-row"><h2><a href="/team/math">repo</a></h2>
    <p>Mathematical theorem proving with Lean</p><a href="/team/math/stargazers">45,678</a>
    <span>{value:,} stars {phrase}</span></article>'''
    row = radar.parse_github(html, period, NOW, CONFIG)[0]
    assert row["native_growth"] == {period: value}
    assert row["total_stars"] == 45678
    assert row["published_at"] is None
    board = next(b for b in radar.boards([row], NOW) if b["basis"] == "platform_window")
    assert board["period"] == period
    assert board["entries"][0]["source_rank"] == 1


def test_specialist_topics_survive_without_ai_word_and_user_agent_noise_does_not():
    assert "math" in radar.topics_for("Lean", "Theorem prover", [], CONFIG)
    assert "research" in radar.topics_for("simulation", "scientific computing", [], CONFIG)
    assert "plugins" in radar.topics_for("MCP", "Tools for agents", [], CONFIG)
    assert not radar.topics_for("User-Agent Switcher", "Browser agent extension", [], CONFIG)
    assert not radar.topics_for("agent-base", "Turn a function into an http.Agent instance", ["agent"], CONFIG)


def test_forges_use_native_star_counters_and_reject_foreign_urls():
    rows = [{"path_with_namespace": "team/math", "web_url": "https://gitlab.com/team/math", "description": "Mathematics", "star_count": 23},
            {"path_with_namespace": "bad/math", "web_url": "https://evil.example/math", "description": "Mathematics", "star_count": 90}]
    parsed = radar.parse_forge(rows, "gitlab", NOW, CONFIG)
    assert len(parsed) == 1 and parsed[0]["total_stars"] == 23
    codeberg = radar.parse_forge({"data": [{"full_name": "team/math", "html_url": "https://codeberg.org/team/math", "description": "Mathematics", "stars_count": 8}]}, "codeberg", NOW, CONFIG)
    assert codeberg[0]["total_stars"] == 8


def test_huggingface_retains_likes_gating_license_and_native_artifact_type():
    row = radar.parse_huggingface([{"id": "team/math", "likes": 21, "downloads": 900, "trendingScore": 7,
                                   "tags": ["math", "license:other"], "gated": "manual"}], "datasets", NOW, CONFIG)[0]
    assert row["url"] == "https://huggingface.co/datasets/team/math"
    assert "total_stars" not in row
    assert row["license"] == "other" and row["gated"] == "manual"
    board = radar.boards([row], NOW)[0]
    assert board["metric"] == "trending_score"
    assert board["history_pending"] is True


def test_merge_deduplicates_repos_but_preserves_all_native_windows():
    a = {**repo(), "native_growth": {"daily": 4}, "native_rank": {"daily": 2}}
    b = {**repo(), "native_growth": {"weekly": 7}, "native_rank": {"weekly": 9}}
    assert radar.merge_items([a, b])[0]["native_growth"] == {"daily": 4, "weekly": 7}


def test_first_observation_never_fabricates_growth_or_fills_missing_history():
    row = repo()
    history = radar.observe([row], {}, NOW)
    assert all(value is None for value in row["observed_growth"].values())
    assert history[row["url"]] == [[int(NOW.timestamp()), 100]]
    assert all(b["basis"] == "current_snapshot" for b in radar.boards([row], NOW))


def test_growth_uses_actual_baseline_and_preserves_counter_decreases():
    row = repo(stars=80)
    history = {row["url"]: [[int((NOW - timedelta(hours=25)).timestamp()), 100],
                             [int((NOW - timedelta(days=7, hours=2)).timestamp()), 70]]}
    history[row["url"]].sort()
    radar.observe([row], history, NOW)
    assert row["observed_growth"]["daily"]["value"] == -20
    assert row["observed_growth"]["daily"]["hours"] == 25
    assert row["observed_growth"]["weekly"]["value"] == 10
    assert row["observed_growth"]["monthly"] is None


def test_gap_is_not_relabelled_as_one_day_growth_and_samples_are_bounded():
    row = repo()
    old = int((NOW - timedelta(days=3)).timestamp())
    history = {row["url"]: [[old, 10]]}
    radar.observe([row], history, NOW)
    radar.observe([repo(stars=101)], history, NOW + timedelta(minutes=30))
    assert row["observed_growth"]["daily"] is None
    assert len(history[row["url"]]) == 2


def test_platform_metrics_are_never_mixed_in_one_ranking():
    a = repo(stars=200)
    b = radar.project("hf_models", "x/math", "https://huggingface.co/x/math", "Math model", NOW, CONFIG, likes=20, trending_score=6)
    c = radar.project("npm", "mcp-tool", "https://www.npmjs.com/package/mcp-tool", "MCP tool", NOW, CONFIG,
                      downloads_by_period={"weekly": 9999})
    result = radar.boards([a, b, c], NOW)
    assert {r["metric"] for r in result} == {"total_stars", "trending_score", "downloads"}
    assert all(len(r["entries"]) == 1 for r in result)


def test_npm_uses_native_rolling_downloads_and_safe_scoped_names():
    row = radar.parse_npm({"objects": [{"package": {"name": "@math/mcp", "description": "Scientific MCP", "version": "1.2"},
                                       "downloads": {"weekly": 700, "monthly": 3000}}]}, NOW, CONFIG)[0]
    assert row["downloads_by_period"] == {"weekly": 700, "monthly": 3000}
    assert row["version"] == "1.2"


def test_npm_daily_reads_dated_point_metric_and_caches_it(monkeypatch):
    row = radar.project("npm", "@math/mcp", "https://www.npmjs.com/package/@math/mcp", "MCP", NOW, CONFIG,
                        downloads_by_period={"weekly": 99})
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"downloads": 12, "start": "2026-10-18", "end": "2026-10-18"}
    calls = []
    monkeypatch.setattr(radar.requests, "get", lambda url, **_: calls.append(url) or Response())
    assert radar.npm_daily([row], {}, NOW)["ok"]
    assert "%40math%2Fmcp" in calls[0]
    second = copy.deepcopy(row)
    radar.npm_daily([second], {"items": [row]}, NOW + timedelta(minutes=30))
    assert len(calls) == 1
    assert second["downloads_by_period"]["daily"] == 12


def test_adapter_outage_retains_exact_old_board_and_timestamp(tmp_path, monkeypatch):
    row = repo()
    board = radar.boards([row], NOW)[0]
    radar.write(tmp_path / "project-radar.json", {"generated_at": radar.iso(NOW), "items": [row], "boards": [board],
                                                "source_batches": {"gitlab:math": [row]}})
    monkeypatch.setattr(radar, "jobs", lambda _: [("gitlab:math", "unused", {}, None)])
    monkeypatch.setattr(radar, "fetch_job", lambda task, moment: ([], {"id": task[0], "ok": False, "checked_at": radar.iso(moment)}))
    result = radar.collect(tmp_path, CONFIG, NOW + timedelta(hours=1))
    assert result["generated_at"] == radar.iso(NOW)
    assert result["items"][0]["stale"]
    assert result["boards"][0]["stale"]
    assert result["boards"][0]["generated_at"] == radar.iso(NOW)
    assert radar.read(tmp_path / "project-history.json", {}) == {}


def test_editorial_selection_balances_platforms_and_covers_math():
    items = [repo(), radar.project("npm", "mcp", "https://www.npmjs.com/package/mcp", "MCP skill agent", NOW, CONFIG)]
    items.extend(radar.project("hf_models", f"team/ai-{i}", f"https://huggingface.co/team/ai-{i}", "AI model", NOW, CONFIG) for i in range(30))
    selected = radar.editorial_items({"items": items}, 5)
    assert {p["platform"] for p in selected} == {"gitlab", "npm", "hf_models"}
    assert any("math" in p["topics"] for p in selected)
