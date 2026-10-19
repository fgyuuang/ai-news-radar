const test = require('node:test');
const assert = require('node:assert/strict');
const { periodRows, balanced, metricText, recommend } = require('../assets/project-radar.js');
const project = (platform, name) => ({ platform, project_name: name, url: `https://example.org/${platform}/${name}`, topics: ['ai'] });
const board = (period, basis, projects, metric = 'stars', stale = false) => ({
  platform: projects[0]?.platform, period, basis, metric, stale,
  entries: projects.map((p, i) => ({ url: p.url, value: 100 - i })),
});

test('period changes use matching metrics and deduplicate native/observed boards', () => {
  const p = project('github', 'agent');
  const data = { items: [p], boards: [board('daily', 'observed_growth', [p]), board('weekly', 'platform_window', [p]), board('daily', 'platform_window', [p])] };
  const daily = periodRows(data, 'daily');
  assert.equal(daily.length, 1);
  assert.equal(daily[0].board.basis, 'platform_window');
  assert.equal(periodRows(data, 'weekly')[0].board.period, 'weekly');
  assert.equal(periodRows(data, 'monthly').length, 0);
});

test('unavailable native board cannot displace a current observed board', () => {
  const p = project('github', 'agent');
  const data = { items: [p], boards: [board('daily', 'platform_window', [p], 'stars', true), board('daily', 'observed_growth', [p])] };
  assert.equal(periodRows(data, 'daily')[0].board.stale, false);
});

test('all mode includes discoveries exactly once without manufacturing a period rank', () => {
  const a = project('github', 'agent'), b = { ...project('gitlab', 'math'), total_stars: 123 };
  const data = { items: [a, b], boards: [board('daily', 'platform_window', [a])] };
  assert.equal(periodRows(data, 'daily').length, 1);
  const rows = periodRows(data, 'daily', true);
  assert.equal(rows.length, 2);
  assert.equal(rows[1].rank, null);
  assert.equal(rows[1].board.basis, 'current_snapshot');
  assert.equal(metricText(rows[1]), '123 累计 Star');
});

test('balanced feed respects source ranks rather than comparing different counters', () => {
  const gh = [project('github', 'a'), project('github', 'b')], npm = [project('npm', 'c')];
  const data = { items: [...gh, ...npm], boards: [board('daily', 'platform_window', gh), { ...board('daily', 'platform_window', npm, 'downloads'), entries: [{ url: npm[0].url, value: 1e9 }] }] };
  const rows = balanced(periodRows(data, 'daily'));
  assert.deepEqual(rows.map(r => r.project.platform), ['github', 'npm', 'github']);
  assert.equal(rows[0].rank, 1);
  assert.equal(rows[2].rank, 2);
  assert.equal(new Set(rows.map(r => r.project.url)).size, rows.length);
});

test('Hugging Face is one platform family and decreases retain their sign', () => {
  const items = [project('hf_models', 'a'), project('hf_datasets', 'b'), project('gitlab', 'c')];
  const data = { items, boards: items.map(p => board('weekly', 'observed_growth', [p], p.platform.startsWith('hf_') ? 'likes' : 'stars')) };
  const rows = balanced(periodRows(data, 'weekly'), 2);
  assert.equal(rows[1].project.platform, 'gitlab');
  assert.equal(metricText({ ...rows[0], entry: { value: -7 } }), '-7 点赞 / 周');
});

test('personal picks require Luna and balance specialist topics without duplicates', () => {
  const items = [project('github', 'ai'), { ...project('gitlab', 'proof'), topics: ['math'] },
    { ...project('github', 'skill'), topics: ['skills'] }, project('codeberg', 'other'), project('npm', 'stale')];
  items[4].stale = true;
  const rows = periodRows({ items, boards: items.map(p => board('daily', 'current_snapshot', [p])) }, 'daily');
  const get = p => ({ model: p.project_name === 'other' ? 'other-model' : 'gpt-6-luna',
    project_insight: { recommendation_score: p.project_name === 'ai' ? 90 : 75 }, generated_at: '2026-10-19T00:00:00Z' });
  const result = recommend(rows, get);
  assert.equal(result.total, 3);
  assert.deepEqual(result.chosen.map(p => p.project.project_name), ['ai', 'proof', 'skill']);
  assert.equal(recommend(rows, () => null).chosen.length, 0);
});
