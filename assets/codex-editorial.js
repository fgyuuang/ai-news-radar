(() => {
  "use strict";
  let entries = new Map(), generatedAt = null;
  const clean = value => {
    const doc = new DOMParser().parseFromString(String(value || ""), "text/html");
    doc.querySelectorAll("script,style,iframe,form,nav,footer").forEach(el => el.remove());
    doc.querySelectorAll("img[alt]").forEach(el => el.replaceWith(el.getAttribute("alt")));
    const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT), parts = [];
    while (walker.nextNode()) {
      const value = walker.currentNode.textContent.trim();
      if (value) parts.push(value);
    }
    return parts.join(" ").replace(/\s+/g, " ").trim();
  };
  function get(item) {
    if (!item) return null;
    const versions = entries.get(item.url || item.primary_url) || [];
    return versions.find(entry => entry.source_title === (item.title_original || item.title || item.project_name || "")
      && clean(entry.domain === "math" ? item.excerpt : item.summary).slice(0, 1600) === entry.source_excerpt) || null;
  }
  function details(entry) {
    const panel = document.createElement("details");
    panel.className = "codex-reviews";
    const title = document.createElement("summary");
    title.textContent = "Codex 点评 · 实用派 / 审慎派 / 较真党";
    panel.append(title);
    for (const [id, name] of [["pragmatic", "实用派"], ["cynic", "审慎派"], ["paper", "较真党"]]) {
      const line = document.createElement("p");
      line.textContent = `${name} ${entry[`${id}_score`]}：${entry[`${id}_review`]}`;
      panel.append(line);
    }
    const attribution = document.createElement("p");
    attribution.className = "codex-attribution";
    attribution.textContent = `${entry.model} · 基于${entry.context_kind === "article_text" ? "抓取正文或摘要" : entry.context_kind === "source_metadata" ? "论文元信息（未取得摘要）" : "来源摘录"} · ${new Date(entry.generated_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}（北京时间）`;
    panel.append(attribution);
    return panel;
  }
  const wrap = (name, resolve, field) => {
    if (typeof window[name] !== "function") return;
    const original = window[name];
    window[name] = function (...args) {
      const entry = get(resolve(args[0]));
      return entry?.[field] || original.apply(this, args);
    };
  };
  wrap("itemTitleText", item => item, "title_zh");
  wrap("itemTitleTextZh", item => item, "title_zh");
  wrap("storyPrimaryTitleText", story => story?.primary_item, "title_zh");
  wrap("signalSummaryText", row => row?.item || row?.story?.primary_item, "summary_zh");
  wrap("feedSummaryText", item => item, "summary_zh");
  wrap("whyImportantText", row => row?.item || row?.story?.primary_item, "recommend_reason_zh");
  if (typeof window.renderItemNode === "function") {
    const original = window.renderItemNode;
    window.renderItemNode = function (...args) {
      const card = original.apply(this, args);
      const entry = get(args[0]?.item || args[0]);
      if (entry) (card.querySelector(".news-card-body") || card).append(details(entry));
      return card;
    };
  }
  async function refresh() {
    try {
      const response = await fetch(`${dataUrl("data/codex-editorial.json")}?t=${Date.now()}`, { signal: AbortSignal.timeout(25000) });
      if (!response.ok) return;
      const payload = await response.json();
      if (payload.provider !== "codex-cli" || !Array.isArray(payload.entries)) return;
      const next = new Map();
      for (const entry of [...payload.entries].sort((a, b) => String(b.generated_at).localeCompare(String(a.generated_at)))) {
        if (!next.has(entry.url)) next.set(entry.url, []);
        next.get(entry.url).push(entry);
      }
      entries = next;
      generatedAt = payload.generated_at;
      if (typeof rerenderCurrentView === "function") rerenderCurrentView();
      document.dispatchEvent(new CustomEvent("personalRadar:editorial"));
    } catch { /* Keep the last successful editorial layer when offline. */ }
  }
  window.PersonalCodexEditorial = { get, details, refresh, get generatedAt() { return generatedAt; } };
})();
