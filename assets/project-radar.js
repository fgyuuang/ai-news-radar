(() => {
  "use strict";
  const main = document.querySelector("main.shell");
  if (!main) return;
  const names = { github: "GitHub", gitlab: "GitLab", codeberg: "Codeberg", hf_models: "Hugging Face · 模型", hf_datasets: "Hugging Face · 数据集", hf_spaces: "Hugging Face · Spaces", npm: "npm" };
  const topics = { ai: "AI", math: "数学", research: "科研", skills: "Skills", agents: "Agent 架构", plugins: "MCP · 插件" };
  const units = { stars: "新增 Star", likes: "点赞变化", downloads: "次下载", total_stars: "累计 Star", trending_score: "趋势分" };
  let payload, loading = false, preferences = { period: "daily", topic: "", platform: "", query: "" };
  try { preferences = { ...preferences, ...JSON.parse(localStorage.getItem("personalProjectRadarV1") || "{}") }; } catch {}
  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function save() { try { localStorage.setItem("personalProjectRadarV1", JSON.stringify(preferences)); } catch {} }
  function date(value) {
    if (!value) return "日期未提供";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? "日期未提供" : parsed.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" });
  }
  const reader = el("section", undefined, "math-reader project-reader");
  reader.setAttribute("aria-label", "开源与社区热度榜");
  reader.id = "projectRadar";
  const heading = el("div", undefined, "list-head math-heading");
  heading.append(el("h2", "开源与社区热度榜"), el("span", "AI · 数学 · 科研 · Agent", "math-status"));
  const status = el("p", "正在加载跨平台榜单…", "math-status");
  const toolbar = el("div", undefined, "math-toolbar project-toolbar");
  function select(label, key, values) {
    const wrapper = el("label", label), input = el("select");
    for (const [value, title] of values) { const option = el("option", title); option.value = value; input.append(option); }
    input.value = preferences[key];
    if (!input.value) preferences[key] = input.value;
    input.addEventListener("change", () => { preferences[key] = input.value; save(); render(); });
    wrapper.append(input); toolbar.append(wrapper);
  }
  select("榜单周期", "period", [["daily", "日榜 · 约 1 天"], ["weekly", "周榜 · 约 7 天"], ["monthly", "月榜 · 约 30 天"]]);
  select("关注领域", "topic", [["", "全部关注领域"], ...Object.entries(topics)]);
  select("社区平台", "platform", [["", "全部平台 · 分别排名"], ...Object.entries(names)]);
  const searchLabel = el("label", "搜索项目与来源摘录", "project-search-label"), search = el("input");
  search.type = "search"; search.placeholder = "例如：Lean、MCP、科学计算"; search.value = preferences.query;
  search.addEventListener("input", () => { preferences.query = search.value; save(); render(); });
  searchLabel.append(search); toolbar.append(searchLabel);
  const note = el("p", "Star、点赞、趋势分与下载量分别排名。榜单为主题筛选样本；模型、数据集和软件的许可请查看原站。", "math-status");
  const count = el("p", "", "math-count"); count.setAttribute("aria-live", "polite");
  const list = el("div", undefined, "project-boards");
  const health = el("details"), healthTitle = el("summary", "来源状态与排名口径"), healthBody = el("div", undefined, "math-health-wrap");
  health.append(healthTitle, healthBody);
  reader.append(heading, status, toolbar, note, count, list, health);
  main.querySelector(".personal-channels")?.after(reader);
  function channel() { reader.hidden = document.body.dataset.informationChannel !== "project"; }
  function safeLink(url, title, className) {
    try {
      const parsed = new URL(url);
      if (parsed.protocol !== "https:") return null;
      const link = el("a", title, className); link.href = parsed.href; link.target = "_blank"; link.rel = "noopener noreferrer";
      return link;
    } catch { return null; }
  }
  function render() {
    if (!payload) return;
    list.replaceChildren();
    const byUrl = new Map(payload.items.map(p => [p.url, p]));
    let total = 0, boardCount = 0;
    for (const board of payload.boards) {
      if (board.period !== preferences.period || (preferences.platform && board.platform !== preferences.platform)) continue;
      if (board.platform === "github" && board.basis === "observed_growth" && payload.boards.some(b => b.platform === "github" && b.period === board.period && b.basis === "platform_window")) continue;
      const words = preferences.query.trim().toLowerCase().split(/\s+/).filter(Boolean);
      const rows = board.entries.map((row, rank) => ({ ...row, rank: rank + 1, project: byUrl.get(row.url) })).filter(row => {
        const p = row.project;
        if (!p || (preferences.topic && !p.topics.includes(preferences.topic))) return false;
        const review = window.PersonalCodexEditorial?.get(p);
        const text = [p.project_name, p.summary, review?.title_zh, review?.summary_zh, ...p.topics.map(t => topics[t])].join(" ").toLowerCase();
        return words.every(word => text.includes(word));
      });
      if (!rows.length) continue;
      total += rows.length; boardCount++;
      const section = el("section", undefined, "project-board"), title = el("h3", `${names[board.platform]} · ${board.label}`);
      const basis = el("p", `${board.scope}${board.stale ? ` · 来源暂不可用，保留 ${date(board.generated_at)} 的榜单` : ""}`, "math-status");
      section.append(title, basis);
      if (board.history_pending) section.append(el("p", "对应周期历史尚未积累完整，以下显示当前快照。", "project-history-note"));
      const cards = el("div", undefined, "math-timeline");
      let visible = 10;
      const more = el("button", "展开更多项目", "project-more"); more.type = "button";
      function renderRows() {
        cards.replaceChildren();
        for (const row of rows.slice(0, visible)) {
          const p = row.project, review = window.PersonalCodexEditorial?.get(p);
          const link = safeLink(p.url, review?.title_zh || p.project_name, "title"); if (!link) continue;
          const card = el("article", undefined, "news-card math-card"), body = el("div", undefined, "news-card-body");
          const meta = el("div", undefined, "meta-row math-card-meta");
          meta.append(el("span", `#${row.rank}`, "site"), el("strong", `${Number(row.value).toLocaleString("zh-CN")} ${units[board.metric]}`));
          if (row.source_rank) meta.append(el("span", `原站 Trending #${row.source_rank}`));
          const title = el("h4", undefined, "math-card-heading"); title.append(link);
          if (review?.title_zh && review.title_zh !== p.project_name) title.append(el("span", p.project_name, "title-sub"));
          body.append(meta, title, el("p", review?.summary_zh || p.summary || "来源未提供描述，请查看项目原站。", "news-summary"));
          body.append(el("p", p.topics.map(t => topics[t]).join(" · "), "project-tags"));
          const details = [`观察于 ${date(p.observed_at)}`];
          if (p.total_stars != null && board.metric !== "total_stars") details.push(`累计 ${Number(p.total_stars).toLocaleString("zh-CN")} Star`);
          if (row.from) details.push(`统计区间 ${row.from} 至 ${row.to}${row.hours ? `（${row.hours} 小时）` : ""}`);
          if (p.version) details.push(`版本 ${p.version}`);
          if (p.license) details.push(`许可 ${p.license}`);
          if (p.gated) details.push("访问需申请 / 同意原站条款");
          body.append(el("p", details.join(" · "), "math-original"));
          if (review) body.append(el("p", `阅读价值：${review.recommend_reason_zh}`, "news-summary"), window.PersonalCodexEditorial.details(review));
          card.append(body); cards.append(card);
        }
        more.hidden = visible >= rows.length;
      }
      more.addEventListener("click", () => { visible += 10; renderRows(); });
      renderRows(); section.append(cards, more); list.append(section);
    }
    count.textContent = `${boardCount} 组榜单 · ${total} 个上榜条目（跨榜单可重复） · 按各自指标排序`;
    if (!total) list.append(el("p", "当前筛选条件下没有上榜项目，可以切换领域或扩大搜索。"));
  }
  function renderHealth() {
    healthBody.replaceChildren();
    for (const note of payload.notes || []) healthBody.append(el("p", note));
    const table = el("table", undefined, "math-health-table"), header = el("tr");
    for (const value of ["来源", "采集状态", "主题匹配", "检查时间"]) header.append(el("th", value));
    table.append(header);
    for (const source of payload.sources) {
      const row = el("tr"), link = safeLink(source.url, source.id), cell = el("td");
      if (link) cell.append(link); else cell.textContent = source.id;
      row.append(cell, el("td", source.ok ? "正常" : "暂不可用，保留旧榜"), el("td", String(source.count)), el("td", date(source.checked_at)));
      table.append(row);
    }
    healthBody.append(table);
  }
  async function refresh() {
    if (loading) return;
    loading = true;
    try {
      const response = await fetch(`${dataUrl("data/project-radar.json")}?t=${Date.now()}`, { signal: AbortSignal.timeout(25000) });
      if (!response.ok) throw new Error("榜单获取失败");
      const next = await response.json();
      if (![next.items, next.boards, next.sources].every(Array.isArray)) throw new Error("榜单格式不完整");
      payload = next;
      status.textContent = `采集于 ${date(next.generated_at)}（北京时间） · ${next.sources.filter(s => s.ok).length}/${next.sources.length} 接口正常 · Windows 每 30 分钟采集，Codex 每日点评`;
      render(); renderHealth();
    } catch (error) {
      status.textContent = payload ? "榜单更新暂不可用，保留上次加载内容。" : "榜单暂不可用，请稍后检查更新。";
      throw error;
    } finally { loading = false; }
  }
  document.addEventListener("personalRadar:channel", channel);
  document.addEventListener("personalRadar:editorial", render);
  window.PersonalProjectRadar = { refresh };
  channel(); refresh().catch(() => {});
})();
