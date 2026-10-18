(() => {
  "use strict";
  const main = document.querySelector("main.shell");
  if (!main) return;
  const KEY = "personalMathRadarPreferencesV1";
  let preferences = { channel: "ai", hours: 72, source: "", query: "", excluded: [], excludeWords: "" };
  try { preferences = { ...preferences, ...JSON.parse(localStorage.getItem(KEY) || "{}") }; } catch {}
  if (!Array.isArray(preferences.excluded)) preferences.excluded = [];
  let math = null, refreshing = false, lastCheck = 0;
  function node(tag, text, className) {
    const result = document.createElement(tag);
    if (text !== undefined) result.textContent = text;
    if (className) result.className = className;
    return result;
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(preferences)); } catch {} }
  function date(value, precision) {
    if (!value) return "日期未提供";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? "日期未提供" : new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai", dateStyle: "medium", ...(precision === "day" ? {} : { timeStyle: "short" }),
    }).format(parsed);
  }
  const channels = node("section", undefined, "personal-channels");
  channels.setAttribute("aria-label", "个人信息频道");
  const channelRow = node("div", undefined, "personal-channel-row");
  const channelSwitch = node("div", undefined, "mode-switch personal-channel-switch");
  channelSwitch.setAttribute("role", "group");
  channelSwitch.setAttribute("aria-label", "资讯频道切换");
  const buttons = {};
  for (const [id, name] of [["ai", "AI 资讯"], ["math", "数学 · AI for Math"]]) {
    const button = node("button", name, "mode-btn");
    button.type = "button";
    button.addEventListener("click", () => { preferences.channel = id; save(); renderChannel(); });
    buttons[id] = button;
    channelSwitch.append(button);
  }
  const refresh = node("button", "检查更新", "personal-refresh-button");
  refresh.type = "button";
  refresh.addEventListener("click", () => refreshData(true));
  const refreshNote = node("p", "每 5 分钟检查更新；回到页面时自动检查", "personal-refresh-note");
  channelRow.append(channelSwitch, refresh, refreshNote);
  channels.append(channelRow);
  const reader = node("section", undefined, "math-reader");
  reader.setAttribute("aria-label", "数学信息阅读器");
  const headingRow = node("div", undefined, "list-head math-heading");
  headingRow.append(node("h2", "数学与形式化证明"));
  const headingHint = node("span", "研究 · 证明 · AI for Math", "math-status");
  headingRow.append(headingHint);
  reader.append(headingRow);
  const status = node("p", "正在加载数学来源…", "math-status");
  reader.append(status);
  const toolbar = node("div", undefined, "math-toolbar");
  const rangeLabel = node("label", "时间范围");
  const range = node("select");
  for (const [value, label] of [[72, "最近 72 小时"], [168, "最近 7 天"], [720, "最近 30 天"], [2160, "近 90 天存档（含日期未提供）"]]) {
    const option = node("option", label); option.value = String(value); range.append(option);
  }
  range.value = String(preferences.hours);
  rangeLabel.append(range);
  const sourceLabel = node("label", "来源");
  const source = node("select"); sourceLabel.append(source);
  const searchLabel = node("label", "搜索标题、中文译文或原文摘录", "math-search-label");
  const search = node("input"); search.type = "search"; search.placeholder = "例如：Lean、证明、Tao"; search.value = preferences.query;
  searchLabel.append(search);
  toolbar.append(rangeLabel, sourceLabel, searchLabel);
  reader.append(toolbar);
  const settings = node("details");
  settings.append(node("summary", "我的筛选偏好 · 自动保存在当前浏览器"));
  const picks = node("div", undefined, "math-source-picks");
  const excludeLabel = node("label", "排除关键词（逗号分隔） ");
  const exclude = node("input"); exclude.type = "text"; exclude.placeholder = "例如：招聘,会议通知"; exclude.value = preferences.excludeWords;
  excludeLabel.append(exclude);
  const reset = node("button", "恢复全部来源"); reset.type = "button";
  reset.addEventListener("click", () => { preferences.excluded = []; preferences.excludeWords = ""; exclude.value = ""; save(); renderSources(); renderArticles(); });
  settings.append(picks, excludeLabel, reset);
  const health = node("details"); health.append(node("summary", "六个来源的采集状态"));
  const healthContent = node("div", undefined, "math-health-wrap"); health.append(healthContent);
  reader.append(settings, health);
  const count = node("p", undefined, "math-count");
  count.setAttribute("aria-live", "polite");
  const list = node("div", undefined, "math-timeline");
  reader.append(count, list);
  const hero = main.querySelector(".hero");
  if (hero) hero.after(channels); else main.prepend(channels);
  channels.after(reader);

  function renderChannel() {
    const selected = preferences.channel === "math" ? "math" : "ai";
    document.body.dataset.informationChannel = selected;
    for (const [id, button] of Object.entries(buttons)) button.setAttribute("aria-pressed", String(id === selected));
    for (const [id, button] of Object.entries(buttons)) button.classList.toggle("active", id === selected);
    reader.hidden = selected !== "math";
  }
  function renderSources() {
    source.replaceChildren(); picks.replaceChildren();
    const all = node("option", "全部数学来源"); all.value = ""; source.append(all);
    for (const s of math.sources) {
      const option = node("option", s.name); option.value = s.id; source.append(option);
      const label = node("label");
      const checkbox = node("input"); checkbox.type = "checkbox"; checkbox.checked = !preferences.excluded.includes(s.id);
      checkbox.addEventListener("change", () => {
        preferences.excluded = checkbox.checked ? preferences.excluded.filter(id => id !== s.id) : [...preferences.excluded, s.id];
        save(); renderArticles();
      });
      label.append(checkbox, document.createTextNode(s.name)); picks.append(label);
    }
    source.value = preferences.source;
    healthContent.replaceChildren();
    const table = node("table", undefined, "math-health-table");
    const head = node("tr");
    for (const title of ["来源", "状态", "最近 72 小时", "最新发表"]) head.append(node("th", title));
    table.append(head);
    for (const s of math.sources) {
      const row = node("tr");
      for (const text of [s.name, s.ok ? "正常" : "暂不可用，保留存档", String(s.recent_count || 0), date(s.latest_published_at)]) row.append(node("td", text));
      table.append(row);
    }
    healthContent.append(table);
  }
  function renderArticles() {
    if (!math) return;
    const since = Date.now() - Number(preferences.hours) * 3600000;
    const excluded = String(preferences.excludeWords).split(/[,，]/).map(s => s.trim().toLowerCase()).filter(Boolean);
    const words = String(preferences.query).trim().toLowerCase().split(/\s+/).filter(Boolean);
    const items = math.items.filter(item => {
      if (preferences.excluded.includes(item.source_id) || (preferences.source && item.source_id !== preferences.source)) return false;
      if (Number(preferences.hours) < 2160 && (!item.published_at || new Date(item.published_at).getTime() < since)) return false;
      const hay = [item.title, item.title_zh, item.excerpt, item.excerpt_zh, item.source].join(" ").toLowerCase();
      const editorial = window.PersonalCodexEditorial?.get(item);
      const searchable = `${hay} ${editorial?.title_zh || ""} ${editorial?.summary_zh || ""}`.toLowerCase();
      return words.every(word => searchable.includes(word)) && !excluded.some(word => searchable.includes(word));
    });
    count.textContent = `${items.length} 篇文章 · 以原始发表时间筛选`;
    list.replaceChildren();
    if (!items.length) list.append(node("p", "这个时间范围内没有符合筛选条件的文章。可以扩大时间范围或调整来源。"));
    for (const item of items) {
      const editorial = window.PersonalCodexEditorial?.get(item);
      const card = node("article", undefined, "news-card math-card");
      const body = node("div", undefined, "news-card-body");
      const meta = node("div", undefined, "meta-row math-card-meta");
      meta.append(node("span", item.source, "site"), node("span", date(item.published_at, item.date_precision), "source"));
      const sourceHealth = math.sources.find(s => s.id === item.source_id);
      if (sourceHealth && !sourceHealth.ok) meta.append(node("span", "来源暂不可用 · 已保存内容"));
      const heading = node("h3", undefined, "math-card-heading");
      const link = node("a", undefined, "title");
      const displayTitle = editorial?.title_zh || item.title_zh || item.title;
      link.append(node("span", displayTitle));
      if (displayTitle !== item.title) link.append(node("span", item.title, "title-sub"));
      // No HTML from feeds enters the DOM. Only public HTTP(S) article links.
      try { const url = new URL(item.url); if (!/^https?:$/.test(url.protocol)) continue; link.href = url.href; } catch { continue; }
      link.target = "_blank"; link.rel = "noopener noreferrer";
      const original = node("a", "查看原文 ↗", "original-link original-action");
      original.href = link.href; original.target = "_blank"; original.rel = "noopener noreferrer";
      meta.append(original);
      heading.append(link); body.append(meta, heading);
      body.append(node("p", editorial?.summary_zh || item.excerpt_zh || item.excerpt || "该来源没有提供文章摘要，请打开原文阅读。", "news-summary"));
      if (editorial) {
        body.append(node("p", `推荐理由：${editorial.recommend_reason_zh}`, "news-summary"));
        body.append(window.PersonalCodexEditorial.details(editorial));
      } else {
        body.append(node("p", item.excerpt_zh ? "来源摘录 · 中文机器翻译" : "来源原文摘录", "math-original"));
      }
      card.append(body);
      list.append(card);
    }
  }
  for (const [element, key, event] of [[range, "hours", "change"], [source, "source", "change"], [search, "query", "input"], [exclude, "excludeWords", "input"]]) {
    element.addEventListener(event, () => { preferences[key] = element.value; save(); renderArticles(); });
  }
  async function loadMath() {
    const response = await fetch(`${dataUrl("data/math-news.json")}?t=${Date.now()}`, { signal: AbortSignal.timeout(25000) });
    if (!response.ok) throw new Error("数学数据暂时无法获取");
    const next = await response.json();
    if (!Array.isArray(next.items) || !Array.isArray(next.sources)) throw new Error("数学数据格式不完整");
    math = next;
    status.textContent = `更新于 ${date(math.generated_at)}（北京时间） · ${math.sources.filter(s => s.ok).length}/${math.sources.length} 源正常 · 默认 72 小时，存档 90 天`;
    renderSources(); renderArticles();
  }
  async function refreshData(force = false) {
    if (refreshing || (!force && Date.now() - lastCheck < 60000)) return;
    refreshing = true; lastCheck = Date.now(); refresh.disabled = true;
    refreshNote.textContent = "正在检查更新…";
    let failed = false;
    const tasks = [loadMath()];
    tasks.push((async () => {
      const response = await fetch(`${dataUrl("data/latest-24h.json")}?t=${Date.now()}`, { signal: AbortSignal.timeout(25000) });
      if (!response.ok) throw new Error("AI 数据暂不可用");
      const next = await response.json();
      if (!Array.isArray(next.items)) throw new Error("AI 数据格式不完整");
      if (next.generated_at !== state.generatedAt) {
        const allMode = state.mode === "all";
        await init();
        if (allMode) { await loadAllModeData(); if (typeof rerenderCurrentView === "function") rerenderCurrentView(); else { renderHotBoard(); renderMainList(); } }
        if (typeof initTodayProjects === "function") await initTodayProjects();
      }
    })());
    if (window.PersonalCodexEditorial) tasks.push(window.PersonalCodexEditorial.refresh());
    const results = await Promise.allSettled(tasks);
    if (results[0].status === "rejected") {
      failed = true;
      status.textContent = math ? "数学更新暂不可用，正在显示上次成功加载的内容。" : "数学数据暂不可用，请稍后检查更新。";
    }
    if (results[1].status === "rejected") failed = true;
    refreshNote.textContent = `${failed ? "部分更新暂不可用" : "已检查"} ${date(new Date().toISOString())} · 每 5 分钟自动检查`;
    refresh.disabled = false; refreshing = false;
  }
  renderChannel();
  document.addEventListener("personalRadar:editorial", renderArticles);
  refreshData(true);
  setInterval(() => { if (!document.hidden) refreshData(); }, 5 * 60000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshData(); });
  window.addEventListener("online", () => refreshData());
})();
