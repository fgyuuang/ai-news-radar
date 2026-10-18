# 个人 AI 与数学信息系统

- GitHub： https://github.com/fgyuuang/ai-news-radar
- GitHub Pages： https://fgyuuang.github.io/ai-news-radar/
- GPT Sites： https://ai-news-radar.ingtningl.chatgpt.site

## 更新与筛选

`Personal AI and Math Radar` 每 3 小时运行一次，也支持在 GitHub Actions 手动运行。
AI 采集沿用仓库的公开来源与评分逻辑，在自己的 fork 运行，不依赖作者的数据更新。
数学独立写入 `data/math-news.json`，不经过 AI 相关性筛选。
两个网站读取同一份个人仓库数据；页面在可见时每 5 分钟、切回页面时检查更新。
网页代码变更需要分别发布；数据更新无需重新发布 GPT Sites。

数学默认显示最近 72 小时，可切换 7/30/90 天，并按来源、关键词筛选和排除词过滤。
网页偏好保存在当前浏览器；跨设备长期采集配置在 `feeds/math-sources.json`。
关闭某个源：将对应 `enabled` 改为 `false`。加公开 RSS：追加相同结构的源。
私人订阅仍使用未跟踪的 `feeds/follow.opml`，不得提交凭据或私人订阅。

## 数学来源

Terence Tao、Proofs and Prompts、VibeMathed、Gowers、Xena 使用各站真实 RSS。
MathArena 没有可用 RSS，解析其 `/blogs` 中带日期、标题和摘录的文章卡片。
不把导航页、账号链接或抓取时间作为新文章及发表日期。
失败来源保留以前成功抓取的文章，并在来源状态中显示故障；零篇近期文章不等于故障。
文章按原文规范 URL 去重；数学内容保留 90 天，缺日期内容只显示于存档范围。
译文来自公开机器翻译服务并缓存；不可用时展示原文，错误不会进入摘要。
展示内容标为“来源摘录”，不把自动翻译说成模型核实过的数学结论。

原有数学定时任务仅用作来源、72 小时窗口和逐篇阅读方式参考。
本系统不读写它的投递去重状态，不会调用 QQ/微信发送脚本。

## Codex 使用

在此仓库打开 Codex，读取 `.agents/skills/personal-radar/SKILL.md`，可以查询自己的
AI 和数学资讯、按关键词出中文简报、调整公开信源与刷新配置。
无需 MCP 或 API Key 即可读取静态 JSON。

```powershell
.\.venv\Scripts\python.exe scripts/update_math.py
.\.venv\Scripts\python.exe scripts/update_news.py --output-dir data --window-hours 24
.\.venv\Scripts\python.exe scripts/build_personal_site.py
gh workflow run personal-radar.yml --repo fgyuuang/ai-news-radar
```

部署目录仅包含页面、静态资源和指定的公开 JSON/RSS；不发布翻译缓存、私人 OPML、密钥、完整邮件或本机状态。
