# 个人 AI 与数学信息系统

- GitHub： https://github.com/fgyuuang/ai-news-radar
- GitHub Pages： https://fgyuuang.github.io/ai-news-radar/
- GPT Sites： https://ai-news-radar.ingtningl.chatgpt.site

## 更新与筛选

`Personal AI and Math Radar` 每 30 分钟运行一次，也支持在 GitHub Actions 手动运行。
AI 采集沿用仓库的公开来源与评分逻辑，在自己的 fork 运行，不依赖作者的数据更新。
数学独立写入 `data/math-news.json`，不经过 AI 相关性筛选。
两个网站读取同一份个人仓库数据；页面在可见时每 5 分钟、切回页面时检查更新。
网页代码变更需要分别发布；数据更新无需重新发布 GPT Sites。

数学默认显示最近 72 小时，可切换 7/30/90 天，并按来源、关键词筛选和排除词过滤。
网页偏好保存在当前浏览器；跨设备长期采集配置在 `feeds/math-sources.json`。
关闭某个源：将对应 `enabled` 改为 `false`。加公开 RSS：追加相同结构的源。
私人订阅仍使用未跟踪的 `feeds/follow.opml`，不得提交凭据或私人订阅。
云端使用 `FOLLOW_OPML_B64` Secret 解码 OPML；未设置时使用公开示例。`RSS_MAX_FEEDS`
Variable 默认 0，表示处理全部配置的订阅。GitHub cron 可能延迟，不保证整点精确执行。

## 对照 Fork 指南

1. 已 Fork 到 `fgyuuang/ai-news-radar`。
2. Actions 已启用，由 `personal-radar.yml` 每 30 分钟统一采集 AI 与数学、发布 Pages。
   原版 `update-news.yml` 保留手动运行入口，避免两个定时器同时改写同一份数据。
3. `DEEPSEEK_API_KEY` 是可选 Secret，当前未配置模型密钥。个人工作流将
   `DEEPSEEK_MODEL` Variable（默认 `deepseek-v4-flash`）同时传给采集和 persona 步骤，
   将 `TITLE_ENHANCE_MAX_PER_RUN`（默认 30）传给标题增强步骤。密钥保留在 GitHub Secrets。
4. Pages 使用 Actions 构建输出 `dist` 发布；等价地提供静态网页，但不会把根目录中
   的源配置、翻译缓存等文件一起发布。云端运行，无需本机常开。
5. `skills/radar/SKILL.md` 的 `BASE_URL` 已改为自己的 Pages `/data` 地址。
   `personal-radar` Skill 也已指向自己的数据，补充数学查询。

## 原版怎样采集、筛选和调用模型

`scripts/update_news.py` 的 `collect_all` 请求官方 RSS、OPML、公开 JSON、
GitHub Trending、Product Hunt 和聚合网页，统一标题、URL、来源和原始时间。
随后进行 URL/标题去重、时间窗口筛选，并由 `scripts/ai_relevance.py` 评分。
评分依据标题、来源名、站点名和 URL 域名；包括 AI/科技关键词、噪音词、来源先验。
信任的垂直 AI 来源有默认保留逻辑。强相关阈值为 0.65，广义全量阈值为 0.3。
`merge_story_items` 再把同一事件的多个报道聚合为故事线，规则选择每日精选。

有密钥时才调用模型，使用服务端 `POST /chat/completions`：

- `DEEPSEEK_API_BASE_URL`：默认 `https://api.deepseek.com`。
- `DEEPSEEK_API_KEY`：请求 Authorization 中的 Bearer 凭据。
- `DEEPSEEK_MODEL`：请求的 `model` 字段。
- 模型完成标题增强、翻译、原文阅读后的推荐理由和 persona 点评；这些结果有缓存。
- 未配置密钥或调用失败时，基础抓取、去重和规则分照常运行，翻译回退或保留原标题。
- 原版采集侧模型默认 `deepseek-v4-flash`；persona 脚本的代码默认值却是
  `deepseek-chat`，因此本 fork 在工作流中统一传递 `DEEPSEEK_MODEL`。

结果保存为 `latest-24h.json`、`stories-merged.json`、`daily-brief.json` 等静态文件。
网页只读取这些结果；Skill 则把相同文件交给使用它的 Agent 整理简报。
数学走独立采集和摘录翻译流程，目前尚未调用上述 persona/全文推荐模型。

## GPT 与 Codex 的两种接入

读取侧：Codex 使用已安装的 `personal-radar` Skill 查询自己的 JSON，无需模型 API 密钥。
将网站发布到 GPT Sites 本身不会自动产生一个 GPT 数据连接器。

生成侧：原版支持的是 DeepSeek 的 Chat Completions 接口。更换 GPT 生成模型需要
另行适配 API 与凭据；只改 `DEEPSEEK_MODEL` 不代表已经接入 GPT。
也可以在已登录的本机使用 Codex CLI 对抓取结果生成简报，但不能由此认为 GitHub
云端拥有本机的登录权限。目前未配置 GPT API 或云端 Codex 凭据。

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
