"""Daily GPT-6 project interpretation through logged-in Codex, never an API key.

Run from the native daily editorial task, not Windows source collection. Channel
delivery and its receipts are untouched. Results bind to exact source versions.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import base64
import re
from urllib.parse import quote, urlparse

import requests

import codex_editorial as editorial

MODEL = "gpt-6-luna"
SHANGHAI = timezone(timedelta(hours=8))


def context(item):
    """Prefer a repository's README to navigation-heavy project HTML."""
    parsed = urlparse(item["url"])
    path = parsed.path.strip("/")
    urls = []
    if parsed.hostname == "github.com" and re.fullmatch(r"[\w.-]+/[\w.-]+", path):
        urls.append((f"https://api.github.com/repos/{path}/readme", "github"))
    elif parsed.hostname == "gitlab.com" and len(path.split("/")) >= 2:
        urls.append((f"https://gitlab.com/api/v4/projects/{quote(path, safe='')}/repository/files/README.md/raw?ref=HEAD", "raw"))
    elif parsed.hostname == "codeberg.org" and re.fullmatch(r"[\w.-]+/[\w.-]+", path):
        urls.append((f"https://codeberg.org/api/v1/repos/{path}/contents/README.md", "codeberg"))
    elif parsed.hostname == "huggingface.co":
        urls.append((f"https://huggingface.co/{path}/raw/main/README.md", "raw"))
    elif parsed.hostname == "www.npmjs.com" and path.startswith("package/"):
        try:
            response = requests.get("https://registry.npmjs.org/" + quote(path[8:], safe="") + "/latest", timeout=(5, 12))
            response.raise_for_status()
            repository = response.json().get("repository", {})
            url = repository.get("url", "") if isinstance(repository, dict) else repository
            match = re.fullmatch(r"(?:git\+)?https://github.com/([\w.-]+/[\w.-]+?)(?:\.git)?", url)
            if match:
                urls.append((f"https://api.github.com/repos/{match[1]}/readme", "github"))
        except (requests.RequestException, ValueError, TypeError):
            pass
    for url, kind in urls:
        try:
            with requests.get(url, stream=True, timeout=(5, 15), headers={"Accept": "application/vnd.github.raw+json", "User-Agent": "PersonalRadar/1.1"}) as response:
                response.raise_for_status()
                raw = bytearray()
                for chunk in response.iter_content(65536):
                    raw.extend(chunk)
                    if len(raw) > 1500000:
                        raise ValueError("README too large")
                content = bytes(raw).decode("utf-8", errors="replace")
                if kind == "codeberg" or (kind == "github" and "json" in response.headers.get("Content-Type", "") and content.startswith("{")):
                    payload = json.loads(content)
                    content = base64.b64decode(payload["content"]).decode("utf-8", errors="replace")
                if len(content.strip()) >= 80:
                    return {**item, "context": content[:10000], "context_kind": "repository_readme", "context_url": url}
        except (requests.RequestException, ValueError, KeyError):
            pass
    return editorial.context(item)


def run(repo, maximum=18, batch_size=6, publish=False, sync=False):
    state = repo / ".local-codex"
    state.mkdir(exist_ok=True)
    # The project collector never calls this module. All model work is owned by
    # the native daily editorial task, with one frozen selection per local day.
    lock = (state / "project-recommendations.lock").open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            if lock.seek(0, 2) == 0:
                lock.write(b"0"); lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise ValueError("Project recommendation run already active")
        status_path = state / ("project-edition-" + datetime.now(SHANGHAI).date().isoformat() + ".json")
        cache_path = status_path.with_name(status_path.stem + "-cache.json")
        if sync:
            dirty = editorial.git(repo, "status", "--porcelain").splitlines()
            if any(line.strip().split(maxsplit=1)[-1] != editorial.OUTPUT for line in dirty):
                raise ValueError("Dedicated editorial checkout has unrelated changes")
            if dirty:
                if not publish:
                    raise ValueError("Unpublished editorial results require --publish before sync")
                editorial.publish(repo)
            editorial.git(repo, "pull", "--rebase", "origin", "master")
        edition = editorial.read(status_path, {})
        edition["model"] = MODEL
        cache = {entry["key"]: entry for entry in editorial.read(repo / editorial.OUTPUT, {"entries": []})["entries"]}
        cache.update({entry["key"]: entry for entry in editorial.read(cache_path, [])
                      if entry.get("model") == MODEL and entry.get("project_insight")})
        if edition.get("complete") and edition.get("keys") and all(cache.get(key, {}).get("model") == MODEL
                and cache[key].get("project_insight") for key in edition["keys"]):
            if publish:
                editorial.save_public(repo, cache, edition["keys"], MODEL)
                editorial.publish(repo)
            print(json.dumps({"status": "ALREADY_COMPLETE", "model": MODEL, "projects": len(edition["keys"])}))
            return 0
        if edition.get("selected"):
            selected = edition["selected"]
        else:
            selected = [p for p in editorial.candidates(repo, 0, datetime.now(timezone.utc), maximum)
                        if p["domain"] == "project"]
            edition = {"selected": selected, "model": MODEL, "complete": False}
            status_path.write_text(json.dumps(edition, ensure_ascii=False, indent=2), encoding="utf-8")
        if not selected:
            raise ValueError("No fresh project sources; retain the previous recommendation edition")
        pending = [p for p in selected if not (cache.get(p["key"], {}).get("project_insight")
                    and cache[p["key"]].get("model") == MODEL)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            contexts = list(pool.map(context, pending))
        for index in range(0, len(contexts), batch_size):
            batch = contexts[index:index + batch_size]
            print(f"GPT-6 project interpretation: batch {index // batch_size + 1}, {len(batch)} projects", flush=True)
            entries = editorial.generate(batch, MODEL, state, index // batch_size + 1)
            cache.update({entry["key"]: entry for entry in entries})
            cache_path.write_text(json.dumps([cache[p["key"]] for p in selected if p["key"] in cache
                                             and cache[p["key"]].get("model") == MODEL], ensure_ascii=False, indent=2), encoding="utf-8")
        editorial.save_public(repo, cache, [p["key"] for p in selected], MODEL)
        edition.update(complete=True, keys=[p["key"] for p in selected], generated_at=datetime.now(timezone.utc).isoformat())
        # Persist completion only after a requested publish succeeds. Cached
        # batches survive a failure and never need to be generated a second time.
        if publish:
            editorial.publish(repo)
        status_path.write_text(json.dumps(edition, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "COMPLETE", "model": MODEL, "projects": len(selected), "generated": len(pending), "published": publish}))
        return 0
    finally:
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--max-projects", type=int, default=18)
    parser.add_argument("--batch-size", type=int, default=6)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--sync", action="store_true")
    args = parser.parse_args()
    if not 3 <= args.max_projects <= 40 or not 1 <= args.batch_size <= 12:
        parser.error("Invalid project or batch count")
    return run(args.repo.resolve(), args.max_projects, args.batch_size, args.publish, args.sync)


if __name__ == "__main__":
    raise SystemExit(main())
