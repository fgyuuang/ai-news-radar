/* Project reader shares the AI news navigation, focus rows and card components. */
(() => {
  'use strict';
  const NAMES = { github: 'GitHub', gitlab: 'GitLab', codeberg: 'Codeberg', hf_models: 'Hugging Face · 模型', hf_datasets: 'Hugging Face · 数据集', hf_spaces: 'Hugging Face · Spaces', npm: 'npm' };
  const TOPICS = { '': '全部', ai: 'AI', math: '数学', research: '科研', skills: 'Skills', agents: 'Agent 架构', plugins: 'MCP · 插件' };
  const PERIODS = { daily: '日榜', weekly: '周榜', monthly: '月榜' };
  const family = platform => platform.startsWith('hf_') ? 'huggingface' : platform;
  function periodRows(data, period, includeDiscovery = false) {
    const projects = new Map(data.items.map(p => [p.url, p])), rows = new Map();
    const priority = b => (b.stale ? 10 : 0) + ({ platform_window: 0, observed_growth: 1, current_snapshot: 2 }[b.basis] ?? 3);
    for (const board of data.boards.filter(b => b.period === period).sort((a, b) => priority(a) - priority(b))) {
      board.entries.forEach((entry, i) => {
        const project = projects.get(entry.url);
        if (project && !rows.has(entry.url) && Number.isFinite(entry.value)) rows.set(entry.url, { project, board, entry, rank: i + 1 });
      });
    }
    if (includeDiscovery) for (const project of projects.values()) if (!rows.has(project.url)) {
      const metric = project.total_stars != null ? 'total_stars' : project.likes != null ? 'likes_total' : 'discovery';
      rows.set(project.url, { project, rank: null, entry: { value: project.total_stars ?? project.likes ?? null },
        board: { platform: project.platform, period, basis: 'current_snapshot', metric, stale: project.stale, discovery: true } });
    }
    return [...rows.values()];
  }
  // Rotate platform ranks. Downloads and stars are never compared to each other.
  function balanced(rows, max = rows.length) {
    const buckets = new Map();
    for (const row of rows) { const key = family(row.project.platform); if (!buckets.has(key)) buckets.set(key, []); buckets.get(key).push(row); }
    for (const pool of buckets.values()) pool.sort((a, b) => Number(Boolean(a.board.stale)) - Number(Boolean(b.board.stale)) || (a.rank ?? 10000) - (b.rank ?? 10000) || a.project.url.localeCompare(b.project.url));
    const result = [];
    while (result.length < max && [...buckets.values()].some(b => b.length)) for (const pool of buckets.values()) if (pool.length && result.length < max) result.push(pool.shift());
    return result;
  }
  function metricText(row) {
    const { board, entry } = row;
    if (!Number.isFinite(entry.value)) return '社区发现';
    const value = Number(entry.value).toLocaleString('zh-CN');
    if (board.metric === 'total_stars') return `${value} 累计 Star`;
    if (board.metric === 'likes_total') return `${value} 点赞`;
    if (board.metric === 'trending_score') return `${value} 趋势分`;
    if (board.metric === 'downloads') return `${value} ${PERIODS[board.period][0]}下载`;
    return `${entry.value >= 0 ? '+' : ''}${value} ${board.metric === 'likes' ? '点赞' : 'Star'} / ${PERIODS[board.period][0]}`;
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { periodRows, balanced, metricText };
  if (typeof document === 'undefined') return;
  const main = document.querySelector('main.shell'); if (!main) return;
  const DEFAULT = { period: 'daily', topic: '', platform: '', query: '', mode: 'selected' };
  let prefs = { ...DEFAULT }, data, loading = false, visible = 20;
  try { prefs = { ...prefs, ...JSON.parse(localStorage.getItem('personalProjectRadarV1') || '{}') }; } catch {}
  if (!(prefs.period in PERIODS)) prefs.period = 'daily';
  if (!(prefs.topic in TOPICS)) prefs.topic = '';
  if (prefs.platform && !(prefs.platform in NAMES)) prefs.platform = '';
  if (!['selected', 'all'].includes(prefs.mode)) prefs.mode = 'selected';
  prefs.query = String(prefs.query || '');
  const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
  const save = () => { try { localStorage.setItem('personalProjectRadarV1', JSON.stringify(prefs)); } catch {} };
  const date = value => Number.isFinite(Date.parse(value)) ? new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', dateStyle: 'medium', timeStyle: 'short' }).format(Date.parse(value)) : '日期未提供';
  function update(key, value) { prefs[key] = value; visible = 20; save(); render(); }
  function button(text, action, cls = 'mode-btn') { const b = el('button', text, cls); b.type = 'button'; b.addEventListener('click', action); return b; }
  function link(url, text, cls) {
    try { const u = new URL(url); if (u.protocol !== 'https:' || u.username || u.password) return null;
      const a = el('a', text, cls); a.href = u.href; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a;
    } catch { return null; }
  }
  const review = p => window.PersonalCodexEditorial?.get(p);
  const title = p => review(p)?.title_zh || p.project_name;
  const reader = el('section', undefined, 'project-reader project-radar-v2'); reader.id = 'projectRadar'; reader.setAttribute('aria-label', '开源项目与社区热榜');
  const nav = el('nav', undefined, 'section-nav-wrap project-navigation'); nav.setAttribute('aria-label', '开源项目分类');
  const tabs = el('div', undefined, 'section-tabs'); tabs.setAttribute('role', 'group'); tabs.setAttribute('aria-label', '项目关注领域');
  const topicButtons = new Map();
  for (const [id, name] of Object.entries(TOPICS)) { const b = button('', () => update('topic', id), 'section-tab'); b.append(el('span', name), el('strong', '0')); topicButtons.set(id, b); tabs.append(b); }
  nav.append(tabs);
  const controls = el('div', undefined, 'primary-controls project-primary');
  const modes = el('div', undefined, 'mode-switch curation-mode-switch'); modes.setAttribute('role', 'group'); modes.setAttribute('aria-label', '项目精选或全量');
  const selected = button('✦ 精选', () => update('mode', 'selected')), all = button('☰ 全量', () => update('mode', 'all')); modes.append(selected, all);
  const query = el('input'); query.type = 'search'; query.placeholder = '搜索项目、Skills、Agent / 来源'; query.setAttribute('aria-label', '搜索开源项目'); query.value = prefs.query; query.addEventListener('input', () => update('query', query.value));
  const periods = el('div', undefined, 'mode-switch project-period-switch'); periods.setAttribute('role', 'group'); periods.setAttribute('aria-label', '热榜周期');
  const periodButtons = new Map();
  for (const [id, name] of Object.entries(PERIODS)) { const b = button(name, () => update('period', id)); periodButtons.set(id, b); periods.append(b); }
  controls.append(modes, query, periods);
  const status = el('p', '正在加载开源项目…', 'project-data-status'); status.setAttribute('role', 'status');
  const advanced = el('details', undefined, 'advanced-panel project-advanced');
  const advancedTitle = el('summary'); advancedTitle.append(el('span', '高级筛选'), el('span', '选择社区平台 · 查看来源和统计口径', 'advanced-hint')); advanced.append(advancedTitle);
  const advancedBody = el('div', undefined, 'advanced-content');
  const platformLabel = el('label', undefined, 'field'); platformLabel.append(el('span', '具体来源'));
  const platform = el('select'); platform.setAttribute('aria-label', '项目来源');
  for (const [id, name] of [['', '全部社区平台'], ...Object.entries(NAMES)]) { const o = el('option', name); o.value = id; platform.append(o); }
  platform.value = prefs.platform; platform.addEventListener('change', () => update('platform', platform.value)); platformLabel.append(platform);
  const clear = button('清除筛选', () => { prefs = { ...DEFAULT, period: prefs.period }; query.value = ''; platform.value = ''; visible = 20; save(); render(); }, 'clear-filters-btn');
  const advancedRow = el('div', undefined, 'project-advanced-controls'); advancedRow.append(platformLabel, clear);
  const health = el('details', undefined, 'source-detail-panel project-health'); health.append(el('summary', '查看来源状态与排名说明'));
  const healthBody = el('div', undefined, 'project-health-body'); health.append(healthBody); advancedBody.append(advancedRow, health); advanced.append(advancedBody);
  const focus = el('section', undefined, 'list-wrap hot-board-wrap project-focus'); focus.setAttribute('aria-label', '开源当前热点');
  const focusHead = el('div', undefined, 'list-head'); focusHead.append(el('h2', '当前热点'), el('span', '各平台前列 · 交替展示', 'project-muted'));
  const focusList = el('div', undefined, 'hot-board-list'); focus.append(focusHead, focusList);
  const feed = el('section', undefined, 'list-wrap project-feed'); feed.setAttribute('aria-label', '开源项目列表');
  const feedHead = el('div', undefined, 'list-head'), feedTitle = el('h2', '精选项目'), count = el('span', '', 'project-muted'); count.setAttribute('aria-live', 'polite'); feedHead.append(feedTitle, count);
  const hint = el('p', '', 'project-reading-hint'), list = el('div', undefined, 'project-timeline');
  const more = button('加载更多项目', () => { visible += 20; render(); }, 'list-more-btn'); feed.append(feedHead, hint, list, more);
  reader.append(nav, controls, status, advanced, focus, feed); main.querySelector('.personal-channels')?.after(reader);
  function channel() {
    reader.hidden = document.body.dataset.informationChannel !== 'project';
    const skip = document.querySelector('.skip-link'); if (!skip) return;
    if (!reader.hidden) { skip.href = '#projectRadar'; skip.textContent = '跳到开源项目'; }
    else if (skip.getAttribute('href') === '#projectRadar') { skip.href = '#hotBoardWrap'; skip.textContent = '跳到当前热点'; }
  }
  function searchable(row) {
    const p = row.project, r = review(p);
    return [p.project_name, p.summary, NAMES[p.platform], r?.title_zh, r?.summary_zh, ...(p.topics || []).map(t => TOPICS[t])].join(' ').toLowerCase();
  }
  function rowCard(row) {
    const p = row.project, r = review(p), a = link(p.url, title(p), 'title'); if (!a) return null;
    const wrapper = el('div', undefined, 'timeline-item project-timeline-item'), rail = el('div', undefined, 'timeline-rail');
    const short = { github: 'GH', gitlab: 'GL', codeberg: 'CB', npm: 'npm' }[p.platform] || 'HF'; rail.append(el('span', short, 'timeline-time'), el('span', '', 'timeline-dot'));
    const card = el('article', undefined, 'news-card project-card'), body = el('div', undefined, 'news-card-body');
    const meta = el('div', undefined, 'meta-row'); meta.append(el('span', NAMES[p.platform], 'site'));
    if (row.rank) meta.append(el('span', `平台内 #${row.rank}`, 'project-rank'));
    meta.append(el('strong', metricText(row), 'project-metric'));
    if (row.board.stale || p.stale) meta.append(el('span', '保留的旧榜', 'project-warning'));
    else if (row.board.basis === 'current_snapshot') meta.append(el('span', '当前快照', 'project-snapshot'));
    const heading = el('h3', undefined, 'project-card-heading'); heading.append(a);
    if (r?.title_zh && r.title_zh !== p.project_name) a.append(el('span', p.project_name, 'title-sub'));
    const summary = el('p', r?.summary_zh || p.summary || '来源未提供介绍，可打开原站了解项目。', 'news-summary');
    const tags = el('div', undefined, 'project-topic-tags'); for (const topic of p.topics || []) if (TOPICS[topic]) tags.append(el('span', TOPICS[topic], 'signal-tag'));
    body.append(meta, heading, summary, tags);
    if (r) body.append(el('p', `推荐理由：${r.recommend_reason_zh}`, 'project-recommend'));
    const footer = el('div', undefined, 'project-card-footer'); footer.append(el('span', `观察于 ${date(p.observed_at)}`, 'project-muted'));
    const original = link(p.url, '查看项目 ↗', 'original-link'); if (original) footer.append(original); body.append(footer);
    const details = el('details', undefined, 'project-evidence'); details.append(el('summary', '指标详情与许可'));
    const info = [row.board.label, row.board.basis === 'current_snapshot' ? '当前快照不代表该周期新增；历史积累后显示增长数据。' : '仅统计本雷达采样项目，排名属于原平台。'];
    if (row.entry.source_rank) info.push(`原站 Trending 排名：#${row.entry.source_rank}`);
    if (row.entry.from) info.push(`实际统计区间：${row.entry.from} 至 ${row.entry.to}${row.entry.hours ? `（${row.entry.hours} 小时）` : ''}`);
    if (p.total_stars != null && row.board.metric !== 'total_stars') info.push(`累计 Star：${Number(p.total_stars).toLocaleString('zh-CN')}`);
    if (p.version) info.push(`版本：${p.version}`);
    info.push(`许可：${p.license || '来源未提供，请查看原站'}`); if (p.gated) info.push('访问需申请或同意原站条款。');
    for (const line of info.filter(Boolean)) details.append(el('p', line)); body.append(details);
    if (r) body.append(window.PersonalCodexEditorial.details(r)); card.append(body); wrapper.append(rail, card); return wrapper;
  }
  function render() {
    for (const [id, b] of periodButtons) { b.classList.toggle('active', prefs.period === id); b.setAttribute('aria-pressed', String(prefs.period === id)); }
    for (const [b, mode] of [[selected, 'selected'], [all, 'all']]) { b.classList.toggle('active', prefs.mode === mode); b.setAttribute('aria-pressed', String(prefs.mode === mode)); }
    if (!data) return;
    const words = prefs.query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const pool = periodRows(data, prefs.period, prefs.mode === 'all').filter(row => (!prefs.platform || row.project.platform === prefs.platform) && words.every(word => searchable(row).includes(word)));
    for (const [id, b] of topicButtons) { b.classList.toggle('active', prefs.topic === id); b.setAttribute('aria-pressed', String(prefs.topic === id)); b.querySelector('strong').textContent = String(pool.filter(row => !id || row.project.topics?.includes(id)).length); }
    const matching = pool.filter(row => !prefs.topic || row.project.topics?.includes(prefs.topic)), ordered = balanced(matching);
    const rows = prefs.mode === 'selected' ? ordered.slice(0, 30) : ordered;
    list.replaceChildren(); focusList.replaceChildren();
    for (const row of balanced(matching.filter(row => row.rank && !row.board.stale && !row.project.stale), 5)) {
      const item = el('div', undefined, 'hot-row project-hot-row'), a = link(row.project.url, title(row.project), 'hot-row-title'); if (!a) continue;
      item.append(el('span', `#${row.rank}`, 'hot-row-rank'), a, el('span', `${NAMES[row.project.platform]} · ${metricText(row)}`, 'hot-row-meta')); focusList.append(item);
    }
    focus.hidden = !focusList.childElementCount; feedTitle.textContent = prefs.mode === 'selected' ? '精选项目' : '全部项目'; count.textContent = `${rows.length} 个项目 · ${PERIODS[prefs.period]}`;
    hint.textContent = `${prefs.mode === 'selected' ? '平台内按热度排序，跨平台交替展示' : '每个项目仅展示一次，包含榜单与社区发现'}${rows.some(row => row.board.basis === 'current_snapshot') ? ' · 含当前快照' : ''}`;
    for (const row of rows.slice(0, visible)) { const card = rowCard(row); if (card) list.append(card); }
    more.hidden = visible >= rows.length; clear.hidden = !prefs.query && !prefs.topic && !prefs.platform;
    if (!rows.length) { const empty = el('div', undefined, 'project-empty'); empty.append(el('h3', '没有符合条件的项目'), el('p', '试试其他关键词、领域或社区平台。'), button('清除筛选', () => clear.click(), 'clear-filters-btn')); list.append(empty); }
  }
  function renderHealth() {
    healthBody.replaceChildren(); healthBody.append(el('p', 'Star、点赞、趋势分和下载量分别解读。当前快照不代表区间增长；实际区间可在项目详情中查看。'));
    for (const note of data.notes || []) healthBody.append(el('p', note));
    const table = el('table', undefined, 'math-health-table'), head = el('tr'); for (const text of ['来源', '状态', '匹配项目', '检查时间']) head.append(el('th', text)); table.append(head);
    for (const source of data.sources) { const row = el('tr'), name = el('td'), a = link(source.url, source.id); name.append(a || document.createTextNode(source.id)); row.append(name, el('td', source.ok ? '正常' : '暂不可用，保留旧内容'), el('td', String(source.count)), el('td', date(source.checked_at))); table.append(row); }
    healthBody.append(table);
  }
  async function refresh() {
    if (loading) return; loading = true;
    try {
      const response = await fetch(`${dataUrl('data/project-radar.json')}?t=${Date.now()}`, { signal: AbortSignal.timeout(25000) }); if (!response.ok) throw new Error('Source unavailable');
      const next = await response.json(); if (![next.items, next.boards, next.sources].every(Array.isArray)) throw new Error('Invalid data'); data = next;
      status.textContent = `更新于 ${date(next.generated_at)} · ${new Set(next.items.map(p => family(p.platform))).size} 个社区平台 · ${next.items.length} 个项目${next.sources.some(s => !s.ok) ? ' · 部分来源暂不可用' : ''}`;
      render(); renderHealth();
    } catch (error) { status.textContent = data ? '更新暂不可用，保留上次加载的项目。' : '项目暂时加载失败，请使用「检查更新」重试。'; throw error; }
    finally { loading = false; }
  }
  document.addEventListener('personalRadar:channel', channel); document.addEventListener('personalRadar:editorial', render);
  window.PersonalProjectRadar = { refresh }; channel(); render(); refresh().catch(() => {});
})();
