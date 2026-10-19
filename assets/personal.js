(() => {
  "use strict";
  const main = document.querySelector("main.shell");
  if (!main) return;
  const KEY = "personalMathRadarPreferencesV1";
  let preferences = { channel: "ai" };
  try { preferences = { ...preferences, ...JSON.parse(localStorage.getItem(KEY) || "{}") }; } catch {}
  if (!Array.isArray(preferences.excluded)) preferences.excluded = [];
  let refreshing = false, lastCheck = 0;
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
  for (const [id, name] of [["ai", "AI 资讯"], ["project", "开源 · 热榜"], ["math", "数学 · AI for Math"]]) {
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
  const reader = window.PersonalMathRadar.create();
  const hero = main.querySelector(".hero");
  if (hero) hero.after(channels); else main.prepend(channels);
  channels.after(reader);

  function renderChannel() {
    const selected = ["math", "project"].includes(preferences.channel) ? preferences.channel : "ai";
    document.body.dataset.informationChannel = selected;
    for (const [id, button] of Object.entries(buttons)) button.setAttribute("aria-pressed", String(id === selected));
    for (const [id, button] of Object.entries(buttons)) button.classList.toggle("active", id === selected);
    reader.hidden = selected !== "math";
    document.dispatchEvent(new CustomEvent("personalRadar:channel"));
  }
  async function refreshData(force = false) {
    if (refreshing || (!force && Date.now() - lastCheck < 60000)) return;
    refreshing = true; lastCheck = Date.now(); refresh.disabled = true;
    refreshNote.textContent = "正在检查更新…";
    let failed = false;
    const tasks = [window.PersonalMathRadar.refresh()];
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
    if (window.PersonalProjectRadar) tasks.push(window.PersonalProjectRadar.refresh());
    const results = await Promise.allSettled(tasks);
    if (results[0].status === "rejected") {
      failed = true;
      window.PersonalMathRadar.failed();
    }
    if (results.some(result => result.status === "rejected")) failed = true;
    refreshNote.textContent = `${failed ? "部分更新暂不可用" : "已检查"} ${date(new Date().toISOString())} · 每 5 分钟自动检查`;
    refresh.disabled = false; refreshing = false;
  }
  renderChannel();
  refreshData(true);
  setInterval(() => { if (!document.hidden) refreshData(); }, 5 * 60000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshData(); });
  window.addEventListener("online", () => refreshData());
})();
