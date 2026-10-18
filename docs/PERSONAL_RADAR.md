# 个人 AI 与数学信息系统

- GitHub： https://github.com/fgyuuang/ai-news-radar
- GitHub Pages： https://fgyuuang.github.io/ai-news-radar/
- GPT Sites： https://ai-news-radar.ingtningl.chatgpt.site

## 更新与筛选

Windows 任务 `Personal Radar Source Collection` 每 30 分钟采集一次，也支持在 GitHub Actions 手动采集。
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
2. Actions 已启用，`personal-radar.yml` 在本机采集数据推送后发布 Pages；定时采集由 Windows 执行。
   原版 `update-news.yml` 保留手动运行入口，避免两个定时器同时改写同一份数据。
3. 原版的 `DEEPSEEK_API_KEY` 为可选 Secret。本 fork 已选择本机 Codex 生成增强内容，
   个人云端工作流不再传入 DeepSeek 密钥。原版手动工作流仍保留上游接口作为备选。
4. Pages 使用 Actions 构建输出 `dist` 发布；不会把根目录中的源配置、翻译缓存等文件一起发布。
   网站托管在云端；按此分工，自动采集与 AI 编辑需要本机运行。
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
数学走独立采集和摘录翻译流程，之后由本机 Codex 生成独立的编辑层。

## GPT 与 Codex 的两种接入

读取侧：Codex 使用已安装的 `personal-radar` Skill 查询自己的 JSON，无需模型 API 密钥。
将网站发布到 GPT Sites 本身不会自动产生一个 GPT 数据连接器。

生成侧：由 Codex 原生自动任务每天上海时间 09:00 执行一次 AI 编辑，直接使用该任务的模型。
Windows 采集入口不调用 Codex CLI 或模型 API。`scripts/radar_daily.py prepare` 冻结候选并复用缓存；
Codex 读取分批正文，生成中文标题、摘要、具体推荐理由和三种 persona 点评，随后 finalize 验证并发布。
抓取不到正文时明确标记基于来源摘录；评分是模型阅读意见，不能作为证明正确性的认证。

Windows 任务 `Personal Radar Source Collection` 在登录后及每 30 分钟运行
`scripts/run_radar_collection.ps1`，只负责公开信源抓取、规则筛选、去重、记录和推送原始数据。
独立采集仓库位于 `../ai-news-radar-collection-runtime`。Codex 日报在原生自动任务中执行，
需要电脑开机且 Codex 应用运行，任务说明为 `docs/CODEX_DAILY_TASK.md`。
日报覆盖 AI、开源项目、数学；先归档 Obsidian，再发送到原 QQ 和唯一已配对微信联系人。
Codex 消耗当前登录账户的使用额度，无需新增模型 API Key。

运行仓库隔离在 `../ai-news-radar-codex-runtime`，不会重置维护仓库的未提交修改。
结果按 URL、原标题、来源摘录和模型缓存，已处理内容不重复调用模型；每批完成后保存本机进度，
失败的后续运行可继续。发布仅提交 `data/codex-editorial.json`，普通 Git push，绝不强推。
本机 `.local-codex/` 保存执行日志和进度，不发布登录凭据、提示词或 CLI 日志。
若需要本机代理，在各运行仓库 `.local-codex/network-proxy.txt` 保存不含凭据的 loopback 地址；
只为本次任务的子进程设置 `HTTPS_PROXY`，不改 Windows 全局环境。GitHub 拉取遇到短暂连接失败会重试三次。
两个网站每 5 分钟检查编辑层，只有来源内容匹配时才应用，失败时保留上次成功数据。
Codex 结果推送会触发 Pages 发布；GPT Sites 直接读取同一公开 JSON，不需要每次重新部署。

手动检查或运行：

```powershell
Get-ScheduledTask -TaskName 'Personal Radar Source Collection'
Get-ScheduledTaskInfo -TaskName 'Personal Radar Source Collection'
& .\scripts\run_radar_collection.ps1
Get-Content -LiteralPath ..\reports\personal-radar\collection-status.json -Encoding utf8
```

GitHub 云端不持有本机的 Codex 登录权限，也未配置 GPT API 或云端 Codex 凭据。

## 数学来源

Terence Tao、Proofs and Prompts、VibeMathed、Gowers、Xena 使用各站真实 RSS。
MathArena 没有可用 RSS，解析其 `/blogs` 中带日期、标题和摘录的文章卡片。
不把导航页、账号链接或抓取时间作为新文章及发表日期。
失败来源保留以前成功抓取的文章，并在来源状态中显示故障；零篇近期文章不等于故障。
文章按原文规范 URL 去重；数学内容保留 90 天，缺日期内容只显示于存档范围。
译文来自公开机器翻译服务并缓存；不可用时展示原文，错误不会进入摘要。
未生成 Codex 编辑内容时展示“来源摘录”，有编辑内容时标明模型、输入类型与生成时间。

统一日报沿用原 Obsidian 收件箱、QQ 与微信发送入口，归档命名为 `个人信息雷达日报-YYYY-MM-DD.md`。
每天默认精选 30 条 AI、10 个开源项目，以及窗口内全部未处理数学文章，限制可改 `feeds/daily-digest.json`（0 不限）。
`../reports/personal-radar/observed.json` 保留七天采集观察，`reviewed.json` 与每日 manifest/回执用于跟踪已处理版本。
标题或来源摘录变化标记“更新”；仅热度变化不重复推送。失败或不明投递不自动重试，包括跨日中断恢复。
原生数学日报任务已改为覆盖全部类别的每日任务；旧 Windows 编辑任务和独立数学日报任务均停用。

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
