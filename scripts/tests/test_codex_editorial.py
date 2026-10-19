import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import codex_editorial as editorial


def article():
    item = {"url": "https://example.org/proof", "source_title": "A proof", "source_excerpt": "Some evidence."}
    item["key"] = editorial.source_key(item)
    return item


def result():
    entry = {"key": article()["key"], "title_zh": "一个证明", "summary_zh": "材料介绍一个证明。",
             "recommend_reason_zh": "可了解证明方法。"}
    for name in ("pragmatic", "cynic", "paper"):
        entry[name + "_score"] = 50
        entry[name + "_review"] = "目前只有来源摘录，证据不足。"
    return entry


def test_source_attribution_cannot_be_replaced_by_model():
    entry = {**result(), "url": "https://forged.example/", "source_title": "invented"}
    actual = editorial.validate({"entries": [entry]}, [article()])[0]
    assert actual["url"] == article()["url"]
    assert actual["source_title"] == "A proof"


@pytest.mark.parametrize("entries", [[], [result(), result()], [{**result(), "key": "unknown"}]])
def test_missing_duplicate_or_unknown_article_is_rejected(entries):
    with pytest.raises(ValueError):
        editorial.validate({"entries": entries}, [article()])


@pytest.mark.parametrize("field,value", [("paper_score", 101), ("paper_score", True),
                                         ("summary_zh", "Traceback 内部错误"), ("summary_zh", "English only")])
def test_bad_editorial_output_is_rejected(field, value):
    entry = result()
    entry[field] = value
    with pytest.raises(ValueError):
        editorial.validate({"entries": [entry]}, [article()])


def test_changed_source_has_a_different_cache_key():
    original = article()
    assert editorial.source_key({**original, "source_excerpt": "Revised evidence"}) != original["key"]


def test_proper_model_name_may_remain_in_latin_letters():
    entry = {**result(), "title_zh": "DeepSeek V4.1 Flash 1017"}
    assert editorial.validate({"entries": [entry]}, [article()])[0]["title_zh"] == entry["title_zh"]


def test_unknown_and_stale_dates_are_not_recent_math(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    items = [{**article(), "published_at": date} for date in (None, "bad", "2026-01-01T00:00:00", "2026-01-01T00:00:00Z")]
    (data / "math-news.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    assert editorial.candidates(tmp_path, 0, datetime(2026, 10, 18, tzinfo=timezone.utc)) == []


def test_radar_projects_enter_editorial_but_counter_changes_reuse_cache(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    item = {"url": "https://codeberg.org/team/math", "project_name": "team/math", "platform": "codeberg",
            "site_name": "Codeberg", "summary": "Scientific theorem proving", "topics": ["math", "research"],
            "total_stars": 100, "observed_at": "2026-10-19T00:00:00Z"}
    path = data / "project-radar.json"
    path.write_text(json.dumps({"items": [item]}), encoding="utf-8")
    before = editorial.candidates(tmp_path, 0, datetime(2026, 10, 19, 2, tzinfo=timezone.utc), 10)[0]
    item["total_stars"] = 120
    path.write_text(json.dumps({"items": [item]}), encoding="utf-8")
    after = editorial.candidates(tmp_path, 0, datetime(2026, 10, 19, 3, tzinfo=timezone.utc), 10)[0]
    assert before["key"] == after["key"]
    assert before["domain"] == "project" and before["topics"] == ["math", "research"]
    assert editorial.candidates(tmp_path, 0, datetime(2026, 10, 25, tzinfo=timezone.utc), 10) == []
