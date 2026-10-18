---
name: personal-radar
description: 查询和维护 fgyuuang 自己的 AI 与数学信息雷达。用于个人资讯、数学博客、Terence Tao、Proofs and Prompts、VibeMathed、Gowers、Xena、MathArena、形式化证明或信源筛选。
---

# 个人信息雷达

数据根地址：`https://raw.githubusercontent.com/fgyuuang/ai-news-radar/master/data`。
先检查 `generated_at`，陈旧数据如实标注。不能把抓取时间说成发表日期。

- AI：先读取 `daily-brief.json`；需要细节再读 `latest-24h.json`。
- 数学：读取 `math-news.json`，默认按 `published_at` 筛选最近 72 小时。
- 每篇保留原标题、中文译名、来源、发表时间、原文链接；用原文摘录总结，区分观点与已证明结论。
- `excerpt_zh` 是来源摘录的机器翻译；失败时使用 `excerpt`，不补造中文内容。
- 同时读取 `codex-editorial.json`。仅当 URL、`source_title` 与原标题、`source_excerpt` 与来源摘录匹配时，优先使用其中的中文标题、摘要、推荐理由和点评；标明模型与生成时间，点评不等于数学证明认证。
- 数学来源故障查 `math-source-status.json`；无近期新帖不代表故障。
- 用户指定其他窗口或来源时按其条件筛选；未知日期不纳入“最近新帖”。
- 不默认下载庞大 `archive.json`，不访问 QQ、微信或以前定时任务的投递状态。

配置源与自动更新先读 `docs/PERSONAL_RADAR.md` 和 `feeds/math-sources.json`。
Python 执行 `scripts/update_math.py` 仅采集数学；`scripts/update_news.py` 采集 AI。
网页代码修改后两端发布，数据自动更新通过 GitHub Actions `personal-radar.yml`。
模型增强由本机 Windows 任务 `Personal AI Math Radar Codex Editorial` 在登录后、每 30 分钟及每天 09:00 运行；09:00 触发会在更新编辑层后执行一次数学日报，并保留 Obsidian 归档与 QQ/微信发送。
维护参考 `scripts/codex_editorial.py` 与 `scripts/run_codex_editorial.ps1`；独立运行仓库为 `../ai-news-radar-codex-runtime`，`.local-codex/last-run.json` 记录最近结果。电脑关机时仅云端采集继续。
不要把私人订阅、API Key 或邮箱正文写入公开仓库。
