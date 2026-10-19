# 个人开源与社区热榜

在原页面切换到「开源 · 热榜」，选择日、周、月，以及 AI、数学、科研、Skills、Agent 架构、MCP / 插件。
各平台分别排名，保留原文描述、链接、观察时间和许可信息；每天的 Codex 编辑结果匹配原文版本后叠加。

页面沿用 AI 资讯的领域标签、精选/全量、搜索、紧凑热点与卡片列表。
日/周/月可直接切换；具体来源、接口状态和统计说明收进高级筛选。
精选按各平台内部名次轮换展示至多 30 个项目，全量包含榜外社区发现，按 URL 去重。
不同平台的计数不合并成总分；卡片展示平台内名次和原始指标，许可与实际统计区间可展开查看。

| 平台 | 公开接口与范围 | 排名口径 |
| --- | --- | --- |
| GitHub | Trending 的 daily / weekly / monthly 页面；补充 ai-for-science、theorem-proving、agent-skills 主题搜索 | 原站提供的区间新增 Star；搜索结果的累计 Star 只用于观测基线 |
| GitLab | 官方公开 projects API，按配置关键词搜索 | 初始累计 Star，积累后按历史观测升星 |
| Codeberg | 官方 Forgejo repos/search API，按配置关键词搜索 | 初始累计 Star，积累后按历史观测升星 |
| Hugging Face | 官方 models / datasets / spaces API，趋势样本及数学模型搜索 | 初始当前 trendingScore，积累后按点赞变化；不称 Star |
| npm | 官方 registry 搜索与 api.npmjs.org 下载接口，重点 MCP、Agent、Claude Code、科研包 | 日下载量用有明确起止日期的 last-day；周/月使用搜索接口原始 rolling downloads；不称升星 |

这些是经过主题筛选的采样榜，**不是全平台完整排名**，不将不同指标混合成一个总分。
GitHub 按区间新增 Star 排序，卡片同时保留原站 Trending 名次。
npm 日下载只补充周下载靠前的 20 个候选，每个包缓存六小时；数据发布有延迟，卡片展示接口实际统计日期。
Hugging Face 包含模型权重、数据集和演示项目，不保证每个条目采用开源许可证；限制许可和 gated 状态保留。

历史计数每个项目最多每六小时记录一次，保留 33 天，公开文件只包含 URL、时间、计数。
日 / 周 / 月使用 1 / 7 / 30 天前、偏差最多六小时的基线，逐项提供实际起止时间。
首次观测不能计算历史升星，界面明确显示当前快照；持续采集约 1 / 7 / 30 天后相应观测榜开始可用。
基线断档时继续显示当前快照，不将三天的变化冒充一天；负增长保留。

Windows 的 `Personal Radar Source Collection` 每 30 分钟运行 `project_radar.py`，不调用模型。
每天 09:00 的原生 Codex 任务从更广的项目池按平台和主题平衡挑选，沿用每日最多十个项目的设置。
来源标题和摘录不变时复用 AI 编辑；当天的热榜摘要单独进入原有 Obsidian、QQ、微信日报流程。
这次增加来源不触发即时测试推送，也不重试历史投递。

配置 `feeds/project-radar.json`：

- `platforms`：启停平台。
- `search_terms`：GitLab / Codeberg 搜索词。
- `github_queries` / `npm_queries`：官方搜索条件。
- `topics`：关注领域的正则匹配；`exclude_patterns` 排除代理包等同名噪声。
- `max_per_source`：每个平台候选上限，当前为 60；Hugging Face 三类分别计数。

运行：`python scripts/project_radar.py --output-dir data`。公开输出是 `data/project-radar.json`；
`data/project-history.json` 留在 Git 仓库存储历史，不打包进网页，也不需要浏览器下载。
原有 Product Hunt 和四卡 `today-projects.json` 保留。

每个适配器失败时保留该适配器上次成功的条目；旧榜标注 stale 并保留旧时间，旧计数不采样为新历史。
来源状态按接口分别记录，成功但没有主题匹配与接口故障有区别。
GitHub Actions 保留手动采集后备入口，日常推送只构建发布，不重复抓取。

Agent 可直接读取自己的 `data/project-radar.json`，筛选 `boards[].period` 和 `items[].topics`，
从 `boards[].entries[].url` 关联项目描述；回答前检查 `generated_at`、board 的 `stale` 和 `basis`。
