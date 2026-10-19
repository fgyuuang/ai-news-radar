/* Mathematics is a subject reader, independent of the AI relevance gate. */
(() => {
  "use strict";
  const KEY = "personalMathRadarReaderV2";
  const TOPICS = [["", "全部"], ["frontier", "数学前沿"], ["ai_math", "AI for Math"], ["formal", "形式化证明"], ["tools", "工具与开源"]];
  const KINDS = { paper: "论文预印本", blog: "研究博客", analysis: "数学解读", research: "机构研究", benchmark: "评测研究", release: "版本发布", discussion: "研究讨论" };
  const DEFAULT = { hours: 168, topic: "", mode: "selected", sort: "priority", source: "", kind: "", query: "", excluded: [], excludeWords: "" };
  let prefs = { ...DEFAULT }, data = null, limit = 20, ui;
  try {
    const saved = localStorage.getItem(KEY);
    if (saved) prefs = { ...prefs, ...JSON.parse(saved) };
    else {
      const old = JSON.parse(localStorage.getItem("personalMathRadarPreferencesV1") || "{}");
      for (const key of ["source", "query", "excluded", "excludeWords"]) if (old[key] !== undefined) prefs[key] = old[key];
    }
  } catch { /* Browser storage is optional. */ }
  if (!Array.isArray(prefs.excluded)) prefs.excluded = [];
  if (!TOPICS.some(([id]) => id === prefs.topic)) prefs.topic = "";
  if (![72, 168, 720, 2160].includes(Number(prefs.hours))) prefs.hours = 168;
  const el = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch {} };
  const time = value => { const n = Date.parse(value); return Number.isFinite(n) ? n : null; };
  const date = (value, day = false) => time(value) === null ? "日期未提供" : new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", dateStyle: "medium", ...(day ? {} : { timeStyle: "short" }),
  }).format(new Date(value));
  const safeUrl = value => { try { const u = new URL(value); return /^https?:$/.test(u.protocol) && !u.username && !u.password ? u.href : ""; } catch { return ""; } };
  const topics = item => Array.isArray(item.topics) ? item.topics : ["frontier"];
  const title = item => window.PersonalCodexEditorial?.get(item)?.title_zh || item.title_zh || item.title;
  const refs = item => item.source_refs?.length ? item.source_refs : [{ id: item.source_id, name: item.source }];
  const activeRefs = item => refs(item).filter(ref => !prefs.excluded.includes(ref.id));
  const score = item => {
    const age = time(item.published_at) === null ? 90 : Math.max(0, (Date.now() - time(item.published_at)) / 86400000);
    return Number(item.priority || 70) + 20 / (1 + age / 7);
  };
  const byPriority = (a, b) => score(b) - score(a) || (time(b.published_at) || 0) - (time(a.published_at) || 0) || a.url.localeCompare(b.url);
  function update(key, value) { prefs[key] = value; limit = 20; save(); render(); }
  function button(text, fn, cls = "mode-btn") {
    const b = el("button", text, cls); b.type = "button"; b.addEventListener("click", fn); return b;
  }
  function select(label, key, options) {
    const field = el("label", undefined, "field"); field.append(el("span", label));
    const input = el("select"); input.setAttribute("aria-label", label);
    for (const [value, name] of options) { const opt = el("option", name); opt.value = value; input.append(opt); }
    input.value = prefs[key]; input.addEventListener("change", () => update(key, input.value));
    field.append(input); return { field, input };
  }
  function reset() {
    prefs = { ...DEFAULT, excluded: [] }; limit = 20; save();
    syncControls(); renderSources(); render();
  }
  function syncControls() {
    for (const key of ["hours", "sort", "source", "kind", "query", "excludeWords"]) if (ui[key]) ui[key].value = prefs[key];
  }
  function create() {
    const reader = el("section", undefined, "math-reader math-radar-v2"); reader.id = "mathRadar";
    reader.setAttribute("aria-label", "数学与 AI for Math 雷达");
    const intro = el("div", undefined, "math-intro");
    intro.append(el("h2", "数学与 AI for Math"), el("p", "跟踪数学研究、机器辅助发现与形式化证明，从论文、研究者和工具更新中筛选值得读的内容。"));
    const tabs = el("div", undefined, "section-tabs math-topic-tabs"); tabs.setAttribute("role", "group"); tabs.setAttribute("aria-label", "数学分类");
    const topicButtons = new Map();
    for (const [id, name] of TOPICS) {
      const b = button("", () => update("topic", id), "section-tab");
      b.append(el("span", name), el("strong", "0")); topicButtons.set(id, b); tabs.append(b);
    }
    const controls = el("div", undefined, "primary-controls math-primary");
    const modes = el("div", undefined, "mode-switch"); modes.setAttribute("role", "group"); modes.setAttribute("aria-label", "数学精选或全量");
    const selected = button("✦ 精选", () => update("mode", "selected"));
    const all = button("☰ 全量", () => update("mode", "all")); modes.append(selected, all);
    const query = el("input"); query.type = "search"; query.placeholder = "搜索数学、论文、研究者 / 来源"; query.setAttribute("aria-label", "搜索数学资讯");
    query.addEventListener("input", () => update("query", query.value));
    const range = select("时间范围", "hours", [[72, "最近 72 小时"], [168, "最近 7 天"], [720, "最近 30 天"], [2160, "90 天存档 · 含无日期"]]);
    controls.append(modes, query, range.field);
    const status = el("p", "正在加载数学资讯…", "math-status math-data-status"); status.setAttribute("role", "status");
    const advanced = el("details", undefined, "advanced-panel math-advanced");
    const summary = el("summary"); summary.append(el("span", "高级筛选"), el("span", "来源、内容类型、排除词与采集状态", "advanced-hint")); advanced.append(summary);
    const content = el("div", undefined, "advanced-content");
    const toolbar = el("div", undefined, "math-toolbar");
    const source = select("具体来源", "source", [["", "全部数学来源"]]);
    const kind = select("内容类型", "kind", [["", "全部内容"], ...Object.entries(KINDS)]);
    const sort = select("排序方式", "sort", [["priority", "研究优先"], ["newest", "最新发表"]]); toolbar.append(source.field, kind.field, sort.field);
    const excludeLabel = el("label", undefined, "field math-exclude"); excludeLabel.append(el("span", "排除关键词 · 用逗号分隔"));
    const exclude = el("input"); exclude.type = "text"; exclude.placeholder = "例如：招聘,会议通知"; exclude.addEventListener("input", () => update("excludeWords", exclude.value)); excludeLabel.append(exclude);
    const sourcePrefs = el("details", undefined, "math-source-preferences"); sourcePrefs.append(el("summary", "订阅偏好 · 保存在当前浏览器"));
    const picks = el("div", undefined, "math-source-picks"); sourcePrefs.append(picks);
    const health = el("details", undefined, "math-health"); const healthSummary = el("summary", "查看来源状态");
    const healthContent = el("div", undefined, "math-health-wrap"); health.append(healthSummary, healthContent);
    content.append(toolbar, excludeLabel, sourcePrefs, health, button("恢复默认筛选", reset, "clear-filters-btn")); advanced.append(content);
    const focus = el("section", undefined, "list-wrap math-focus"); focus.setAttribute("aria-label", "本期关注");
    const focusHead = el("div", undefined, "list-head"); focusHead.append(el("h2", "本期关注"), el("span", "兼顾主题与来源", "math-status"));
    const focusList = el("div", undefined, "hot-board-list"); focus.append(focusHead, focusList);
    const feed = el("section", undefined, "list-wrap math-feed");
    const head = el("div", undefined, "list-head"); const feedTitle = el("h2", "数学精选"); const count = el("span", "", "math-status"); count.setAttribute("aria-live", "polite"); head.append(feedTitle, count);
    const hint = el("p", "", "math-reading-hint");
    const list = el("div", undefined, "math-timeline");
    const more = button("加载更多", () => { limit += 20; render(); }, "math-more");
    feed.append(head, hint, list, more);
    reader.append(intro, tabs, controls, status, advanced, focus, feed);
    ui = { reader, topicButtons, selected, all, query, hours: range.input, source: source.input, kind: kind.input, sort: sort.input, excludeWords: exclude,
      status, picks, healthSummary, healthContent, focus, focusList, feedTitle, count, hint, list, more };
    syncControls();
    document.addEventListener("personalRadar:editorial", render);
    document.addEventListener("personalRadar:channel", () => {
      const skip = document.querySelector(".skip-link");
      if (skip && document.body.dataset.informationChannel === "math") { skip.href = "#mathRadar"; skip.textContent = "跳到数学资讯"; }
      else if (skip && skip.getAttribute("href") === "#mathRadar") { skip.href = "#hotBoardWrap"; skip.textContent = "跳到当前热点"; }
    });
    return reader;
  }
  function renderSources() {
    if (!data) return;
    ui.source.replaceChildren(el("option", "全部数学来源")); ui.source.firstChild.value = ""; ui.picks.replaceChildren();
    if (!data.sources.some(s => s.id === prefs.source)) prefs.source = "";
    for (const source of data.sources) {
      const opt = el("option", source.name); opt.value = source.id; ui.source.append(opt);
      const label = el("label"); const checkbox = el("input"); checkbox.type = "checkbox"; checkbox.checked = !prefs.excluded.includes(source.id);
      checkbox.addEventListener("change", () => { prefs.excluded = checkbox.checked ? prefs.excluded.filter(id => id !== source.id) : [...prefs.excluded, source.id]; limit = 20; save(); render(); });
      label.append(checkbox, document.createTextNode(source.name)); ui.picks.append(label);
    }
    ui.source.value = prefs.source;
    const healthy = data.sources.filter(s => s.ok).length;
    ui.healthSummary.textContent = `查看 ${data.sources.length} 个来源状态 · ${healthy} 正常`;
    const table = el("table", undefined, "math-health-table"); const tr = el("tr");
    for (const title of ["来源", "采集状态", "最近 7 天", "最后检查"]) tr.append(el("th", title)); table.append(tr);
    for (const source of data.sources) {
      const row = el("tr"); const name = el("td"); const link = el("a", source.name); link.href = safeUrl(source.url); link.target = "_blank"; link.rel = "noopener noreferrer"; name.append(link); row.append(name);
      const recent = data.items.filter(item => refs(item).some(r => r.id === source.id) && time(item.published_at) !== null && time(item.published_at) >= Date.now() - 168 * 3600000).length;
      for (const text of [source.ok ? (source.fallback_error ? "RSS 正常 · 近期列表暂不可用" : source.item_count ? "正常" : "正常 · 本次无匹配公告") : "暂不可用 · 保留存档", String(recent), date(source.checked_at)]) row.append(el("td", text));
      table.append(row);
    }
    ui.healthContent.replaceChildren(table);
  }
  function baseItems() {
    const now = Date.now(), since = now - Number(prefs.hours) * 3600000;
    const query = String(prefs.query).trim().toLowerCase().split(/\s+/).filter(Boolean);
    const excluded = String(prefs.excludeWords).split(/[,，]/).map(s => s.trim().toLowerCase()).filter(Boolean);
    return data.items.filter(item => {
      if (!safeUrl(item.url) || !activeRefs(item).length || (prefs.source && !activeRefs(item).some(ref => ref.id === prefs.source))) return false;
      if (prefs.kind && item.content_type !== prefs.kind) return false;
      const published = time(item.published_at);
      if (published !== null && (published < since || published > now)) return false;
      if (published === null && Number(prefs.hours) !== 2160) return false;
      const editorial = window.PersonalCodexEditorial?.get(item);
      const hay = [item.title, item.title_zh, item.excerpt, item.excerpt_zh, ...refs(item).map(r => r.name), editorial?.title_zh, editorial?.summary_zh].join(" ").toLowerCase();
      return query.every(word => hay.includes(word)) && !excluded.some(word => hay.includes(word));
    });
  }
  function balanced(items, max, sourceCap) {
    const ranked = [...items].sort(byPriority), selected = [], seen = new Set(), sources = new Map();
    const eligible = item => !seen.has(item.url) && (sources.get(activeRefs(item)[0]?.id) || 0) < sourceCap;
    const take = item => {
      if (!item || seen.has(item.url)) return false;
      const sourceId = activeRefs(item)[0]?.id;
      if ((sources.get(sourceId) || 0) >= sourceCap) return false;
      selected.push(item); seen.add(item.url); sources.set(sourceId, (sources.get(sourceId) || 0) + 1); return true;
    };
    // Reserve space for every populated subject before filling by priority.
    for (const [topic] of TOPICS.slice(1)) take(ranked.find(item => topics(item).includes(topic) && eligible(item)));
    for (const kind of ["paper", "research"]) {
      if (selected.length < max) take(ranked.find(item => item.content_type === kind && eligible(item)));
    }
    for (const item of ranked) { if (selected.length >= max) break; take(item); }
    return selected.slice(0, max);
  }
  function reason(item) {
    if (item.content_type === "paper") return "数学与计算研究的一手预印本，建议结合摘要判断相关性，留意其审稿与证明状态。";
    if (item.content_type === "release") return "跟踪证明工具的实际版本变化，可从发布说明判断是否影响自己的形式化工作流。";
    if (topics(item).includes("ai_math")) return "关注 AI 参与数学研究的方法、评测与边界，阅读时区分实验结果和数学结论。";
    if (topics(item).includes("formal")) return "追踪形式化证明实践与证明助手生态，原文可作为进一步核查的入口。";
    return "来自数学研究者或专业解读的更新，适合沿原文继续跟踪问题与研究脉络。";
  }
  function card(item, selected) {
    const editorial = window.PersonalCodexEditorial?.get(item);
    const card = el("article", undefined, "news-card math-card"); const body = el("div", undefined, "news-card-body");
    const meta = el("div", undefined, "meta-row math-card-meta");
    if (selected) meta.append(el("span", "精选", "curated-badge"));
    meta.append(el("span", activeRefs(item).map(ref => ref.name).join(" · "), "site"), el("span", KINDS[item.content_type] || "研究博客", "math-kind"));
    const published = el("time", `${item.recency_basis === "announced" ? "公告 " : item.recency_basis === "updated" ? "更新 " : ""}${date(item.published_at, item.date_precision === "day")}`, "source");
    if (time(item.published_at) !== null) published.dateTime = item.published_at;
    meta.append(published);
    if (activeRefs(item).every(ref => data.sources.find(s => s.id === ref.id)?.ok === false)) meta.append(el("span", "来源暂不可用 · 存档", "math-source-warning"));
    const heading = el("h3", undefined, "math-card-heading"); const link = el("a", undefined, "title");
    link.href = safeUrl(item.url); link.target = "_blank"; link.rel = "noopener noreferrer";
    link.append(el("span", title(item)));
    if (title(item) !== item.title) link.append(el("span", item.title, "title-sub")); heading.append(link);
    body.append(meta, heading);
    const tags = el("div", undefined, "math-tags"); for (const [id, name] of TOPICS.slice(1)) if (topics(item).includes(id)) tags.append(el("span", name)); body.append(tags);
    const summary = editorial?.summary_zh || item.excerpt_zh || item.excerpt || "来源未提供摘要，打开原文继续阅读。";
    body.append(el("p", summary, "news-summary"));
    if (selected || editorial) {
      const why = el("div", undefined, "why-box"); why.append(el("span", editorial ? "推荐理由：" : "关注线索：", "why-label"), el("span", editorial?.recommend_reason_zh || reason(item), "why-text")); body.append(why);
    }
    if (editorial) body.append(window.PersonalCodexEditorial.details(editorial));
    const footer = el("div", undefined, "math-card-footer");
    footer.append(el("span", editorial ? "Codex 每日编辑 · 点评不代表证明认证" : item.summary_kind === "source_metadata" ? "论文元信息 · 列表未提供摘要" : item.excerpt_zh ? "来源摘录 · 中文机器翻译" : "来源原文摘录", "math-original"));
    const original = el("a", "查看原文 ↗", "original-link"); original.href = link.href; original.target = "_blank"; original.rel = "noopener noreferrer"; footer.append(original); body.append(footer); card.append(body);
    return card;
  }
  function render() {
    if (!data || !ui) return;
    const pool = baseItems();
    for (const [id, b] of ui.topicButtons) {
      b.classList.toggle("active", prefs.topic === id); b.setAttribute("aria-pressed", String(prefs.topic === id));
      b.querySelector("strong").textContent = pool.filter(item => !id || topics(item).includes(id)).length;
    }
    const filtered = pool.filter(item => !prefs.topic || topics(item).includes(prefs.topic));
    const selected = prefs.mode !== "all";
    const items = selected ? balanced(filtered, 24, prefs.source ? 24 : 3) : [...filtered];
    items.sort(prefs.sort === "newest" ? (a, b) => (time(b.published_at) || 0) - (time(a.published_at) || 0) || byPriority(a, b) : byPriority);
    ui.selected.classList.toggle("active", selected); ui.all.classList.toggle("active", !selected);
    ui.selected.setAttribute("aria-pressed", String(selected)); ui.all.setAttribute("aria-pressed", String(!selected));
    ui.feedTitle.textContent = `${prefs.topic ? TOPICS.find(([id]) => id === prefs.topic)[1] : "数学"}${selected ? "精选" : "资讯"}`;
    ui.count.textContent = selected ? `精选 ${items.length} / ${filtered.length} 条` : `${items.length} 条 · 已按原文去重`;
    ui.hint.textContent = selected ? "按来源优先级与时效筛选，兼顾不同主题；每源最多 3 条。可切换全量查看所有内容。" : "按原始发表或论文公告时间筛选；无日期内容仅在 90 天存档中展示。";
    if (prefs.source && selected) ui.hint.textContent = "正在查看单一来源的精选，最多展示 24 条；可切换全量继续阅读。";
    const focusItems = balanced(filtered.filter(item => time(item.published_at) !== null), 5, 1);
    ui.focus.hidden = !selected || !focusItems.length;
    ui.focusList.replaceChildren();
    focusItems.forEach((item, index) => {
      const row = el("div", undefined, "hot-row math-focus-row");
      const link = el("a", title(item), "hot-row-title"); link.href = safeUrl(item.url); link.target = "_blank"; link.rel = "noopener noreferrer";
      row.append(el("span", String(index + 1).padStart(2, "0"), "hot-row-rank"), link, el("span", activeRefs(item)[0]?.name, "math-focus-source")); ui.focusList.append(row);
    });
    ui.list.replaceChildren();
    if (!items.length) {
      const empty = el("div", undefined, "math-empty"); empty.append(el("h3", "当前筛选下没有新内容"), el("p", "数学研究的更新节奏不同于日常新闻。可以查看 30 天内容，或恢复筛选。"));
      empty.append(button("查看最近 30 天", () => { prefs.hours = 720; ui.hours.value = "720"; update("hours", 720); }, "empty-reset-btn"), button("恢复默认筛选", reset, "clear-filters-btn")); ui.list.append(empty);
    }
    for (const item of items.slice(0, limit)) ui.list.append(card(item, selected));
    ui.more.hidden = items.length <= limit;
    ui.more.textContent = `加载更多 · 还有 ${Math.max(0, items.length - limit)} 条`;
  }
  async function refresh() {
    const url = new URL(dataUrl("data/math-news.json"), location.href); url.searchParams.set("t", Date.now());
    const response = await fetch(url, { signal: AbortSignal.timeout(25000) });
    if (!response.ok) throw new Error("Mathematics data unavailable");
    const next = await response.json();
    if (!Array.isArray(next.items) || !Array.isArray(next.sources)) throw new Error("Invalid mathematics data");
    data = next;
    const healthy = data.sources.filter(source => source.ok).length;
    const stale = time(data.generated_at) === null || Date.now() - time(data.generated_at) > 6 * 3600000;
    ui.status.textContent = `${healthy}/${data.sources.length} 源正常 · 采集于 ${date(data.generated_at)}（北京时间）${stale ? " · 数据较旧，等待下次采集" : ""} · 默认 7 天，存档 90 天`;
    renderSources(); render();
  }
  function failed() { if (ui) ui.status.textContent = data ? "更新暂不可用，正在显示上次成功加载的数学内容。" : "数学数据暂不可用，请稍后检查更新。"; }
  window.PersonalMathRadar = { create, refresh, failed };
})();
