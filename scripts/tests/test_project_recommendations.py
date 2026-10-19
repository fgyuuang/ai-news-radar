import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import project_recommendations as projects


def sources():
    return [{"key": str(i), "url": f"https://github.com/team/project-{i}", "domain": "project",
             "source_title": "工具", "source_excerpt": "科学研究工具"} for i in range(3)]


def generated(batch):
    return [{**p, "model": projects.MODEL, "generated_at": datetime.now(timezone.utc).isoformat(),
             "project_insight": {"one_liner_zh": "研究工具"}} for p in batch]


def test_luna_only_daily_cache_resumes_without_publishing_partial_batches(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    path = tmp_path / projects.editorial.OUTPUT
    before = '{"entries": []}\n'
    path.write_text(before, encoding="utf-8")
    monkeypatch.setattr(projects.editorial, "candidates", lambda *args: sources())
    monkeypatch.setattr(projects, "context", lambda item: item)
    calls = []
    def generate(batch, model, *args):
        assert model == "gpt-6-luna"
        calls.append([p["key"] for p in batch])
        if len(calls) == 2:
            raise ValueError("Interrupted")
        return generated(batch)
    monkeypatch.setattr(projects.editorial, "generate", generate)
    with pytest.raises(ValueError, match="Interrupted"):
        projects.run(tmp_path, 3, 2)
    assert path.read_text(encoding="utf-8") == before
    assert projects.run(tmp_path, 3, 2) == 0
    assert calls == [["0", "1"], ["2"], ["2"]]
    assert len(json.loads(path.read_text(encoding="utf-8"))["entries"]) == 3
    monkeypatch.setattr(projects.editorial, "generate", lambda *args: pytest.fail("must reuse completed day"))
    assert projects.run(tmp_path, 3, 2) == 0


def test_other_model_cache_is_not_treated_as_luna(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    rows = generated(sources())
    for row in rows:
        row["model"] = "other-model"
    (tmp_path / projects.editorial.OUTPUT).write_text(json.dumps({"entries": rows}), encoding="utf-8")
    monkeypatch.setattr(projects.editorial, "candidates", lambda *args: sources())
    monkeypatch.setattr(projects, "context", lambda item: item)
    calls = []
    monkeypatch.setattr(projects.editorial, "generate", lambda batch, model, *args: calls.append(model) or generated(batch))
    projects.run(tmp_path, 3, 3)
    assert calls == ["gpt-6-luna"]


def test_source_context_prefers_readme_and_keeps_evidence_url(monkeypatch):
    class Response:
        headers = {"Content-Type": "text/plain"}
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def raise_for_status(self): pass
        def iter_content(self, _): yield ("# Research tool\n" + "Verified source documentation. " * 8).encode()
    monkeypatch.setattr(projects.requests, "get", lambda *args, **kwargs: Response())
    item = projects.context(sources()[0])
    assert item["context_kind"] == "repository_readme"
    assert item["context_url"] == "https://api.github.com/repos/team/project-0/readme"
    assert "Verified source documentation" in item["context"]
