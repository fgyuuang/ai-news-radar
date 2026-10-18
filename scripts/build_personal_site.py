"""Build only public site files, excluding caches, feeds and local state."""
from pathlib import Path
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist"
PUBLIC_DATA = (
    "latest-24h.json", "latest-24h-all.json", "daily-brief.json",
    "stories-merged.json", "top3-personas.json", "source-status.json",
    "service-status.json", "waytoagi-7d.json", "today-projects.json",
    "feed.xml", "feed-en.xml", "math-news.json", "math-source-status.json", "math-feed.xml",
)


def main():
    # Rebuild by copying named public outputs; never delete a prior output tree.
    OUTPUT.mkdir(exist_ok=True)
    for name in ("index.html", "site.webmanifest"):
        shutil.copy2(ROOT / name, OUTPUT / name)
    for name in ("assets", "classic"):
        shutil.copytree(ROOT / name, OUTPUT / name, dirs_exist_ok=True)
    (OUTPUT / "data").mkdir(exist_ok=True)
    for name in PUBLIC_DATA:
        source = ROOT / "data" / name
        if source.exists():
            shutil.copy2(source, OUTPUT / "data" / name)
        elif name in {"latest-24h.json", "math-news.json"}:
            raise FileNotFoundError(f"Required public data is missing: {name}")
    (OUTPUT / ".nojekyll").write_text("", encoding="utf-8")
    (OUTPUT / ".openai").mkdir(exist_ok=True)
    config = {"project_id": "appgprj_6ab2a96abc708191828840b07c5e7e05", "static": {"directory": "dist", "not_found_handling": "none"}}
    (OUTPUT / ".openai" / "hosting.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"Public static site prepared: {OUTPUT}")


if __name__ == "__main__":
    main()
