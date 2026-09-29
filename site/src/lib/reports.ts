// 报告体系数据层（参照 AIHOT reports）：日报 / 周报 / 月报 三种刊物。
//   日报 = data/issues 的一天；周报/月报 = 构建期由日报聚合而成（无 LLM，导读由数据拼装）。
// 版面（sections）= 精选条目按分类分组；头版大标题 = 编辑导语标题（无则最高分头条）。

import { getIssues, getEvents, CATEGORY_LABELS } from './issues';
import type { Issue, NewsItem, EventRecord } from './issues';
import { withBase } from './url';

export type ReportKind = 'daily' | 'weekly' | 'monthly';

export const KINDS: ReportKind[] = ['daily', 'weekly', 'monthly'];
export const KIND_LABEL: Record<ReportKind, string> = { daily: '日报', weekly: '周报', monthly: '月报' };
export const KIND_PATH: Record<ReportKind, string> = { daily: '/daily', weekly: '/weekly', monthly: '/monthly' };
export const KIND_MOTTO: Record<ReportKind, string> = {
  daily: '人工智能 · 每日要闻',
  weekly: '人工智能 · 每周综述',
  monthly: '人工智能 · 每月盘点',
};
export const KIND_EDITION: Record<ReportKind, string> = {
  daily: '每天 08:00 出刊',
  weekly: '每周一出刊',
  monthly: '每月 1 日出刊',
};

/** 版面顺序：与 collector/taxonomy.py 的分类一致。 */
const SECTION_ORDER = ['ai-models', 'ai-products', 'industry', 'paper', 'open-source', 'policy', 'opinion'];
/** 一个版面最多收录的条数，超出转入「快讯」。 */
const SECTION_CAP = 8;

const pad = (n: number) => String(n).padStart(2, '0');
const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
export const weekdayOf = (iso: string) => WEEKDAYS[new Date(`${iso}T12:00:00+08:00`).getUTCDay()] ?? '';

// ── 周期工具 ─────────────────────────────────────────────────────────────────

/** ISO 周键（YYYY-Www），如 2026-09-28 → 2026-W40。 */
export function isoWeekOf(day: string): string {
  const d = new Date(`${day}T00:00:00Z`);
  const thursday = new Date(d.getTime() + (3 - ((d.getUTCDay() + 6) % 7)) * 86400000);
  const jan1 = new Date(Date.UTC(thursday.getUTCFullYear(), 0, 1));
  const week = Math.floor((thursday.getTime() - jan1.getTime()) / 604800000) + 1;
  return `${thursday.getUTCFullYear()}-W${pad(week)}`;
}

/** ISO 周键的周一与周日（YYYY-MM-DD）。 */
export function isoWeekRange(key: string): [string, string] {
  const [y, w] = key.split('-W').map(Number) as [number, number];
  const jan4 = new Date(Date.UTC(y, 0, 4));
  const monday = new Date(jan4.getTime() - ((jan4.getUTCDay() + 6) % 7) * 86400000 + (w - 1) * 7 * 86400000);
  const ymd = (d: Date) => `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
  return [ymd(monday), ymd(new Date(monday.getTime() + 6 * 86400000))];
}

/** 月键（YYYY-MM）的首日与末日。 */
export function monthRange(key: string): [string, string] {
  const [y, m] = key.split('-').map(Number) as [number, number];
  const last = new Date(Date.UTC(y, m, 0));
  return [`${key}-01`, `${last.getUTCFullYear()}-${pad(last.getUTCMonth() + 1)}-${pad(last.getUTCDate())}`];
}

const inRange = (day: string, [a, b]: [string, string]) => day >= a && day <= b;

// ── 纸面模型 ─────────────────────────────────────────────────────────────────

export interface PaperSection {
  id: string;
  label: string;
  items: NewsItem[];
}

export interface NavEntry {
  key: string;
  title: string;
}

export interface PaperLink {
  key: string;
  label: string; // 「前一日 · 9月27日」
  title: string;
  href: string;
}

export interface Paper {
  kind: ReportKind;
  key: string;
  issueNo: number | null;   // 第 N 期（该类刊物自身序列）
  dateline: string;         // 「2026 年 9 月 28 日 · 周一」
  headlineTitle: string;    // 头版大标题
  leadParagraph: string | null;
  leadStory: NewsItem | null; // 无编辑导语时以最高分头条领街
  highlights: NewsItem[];
  sections: PaperSection[];
  flashes: NewsItem[];
  metrics: Array<{ value: number | string; unit: string }>;
  minutes: number;
  mark: { figure: string; top: string; bottom: string }; // 报眼
  prev: PaperLink | null;
  next: PaperLink | null;
}

// ── 条目整理 ─────────────────────────────────────────────────────────────────

const selectedOf = (issue: Issue): NewsItem[] => [...issue.headlines, ...issue.briefing];

const uniqSources = (items: NewsItem[]): number =>
  new Set(items.map((it) => it.source)).size;

/** 版面切分：按分类分组（顺序固定），单版超出 SECTION_CAP 的部分转入快讯。 */
function makeSections(items: NewsItem[]): { sections: PaperSection[]; flashes: NewsItem[] } {
  const flashes: NewsItem[] = [];
  const sections: PaperSection[] = [];
  for (const cat of SECTION_ORDER) {
    const group = items.filter((it) => it.category === cat);
    if (group.length === 0) continue;
    const keep = group.slice(0, SECTION_CAP);
    flashes.push(...group.slice(SECTION_CAP));
    sections.push({ id: `s-${cat}`, label: CATEGORY_LABELS[cat], items: keep });
  }
  const uncategorized = items.filter((it) => !it.category || !SECTION_ORDER.includes(it.category));
  if (uncategorized.length > 0) {
    const keep = uncategorized.slice(0, SECTION_CAP);
    flashes.push(...uncategorized.slice(SECTION_CAP));
    sections.push({ id: 's-misc', label: '资讯', items: keep });
  }
  return { sections, flashes };
}

const minutesOf = (items: NewsItem[]): number =>
  Math.max(1, Math.round(items.reduce((n, it) => n + (it.summary_zh?.length ?? 0), 0) / 400));

/** 无编辑导语时的领街条目：最高分优先，其次最新。 */
const leadStoryOf = (items: NewsItem[]): NewsItem | null =>
  [...items].sort(
    (a, b) => (b.score ?? 0) - (a.score ?? 0) || (b.published_at ?? '').localeCompare(a.published_at ?? ''),
  )[0] ?? null;

const topEvents = (range: [string, string]): EventRecord[] =>
  getEvents()
    .filter((e) => e.source_count >= 2 && e.date && inRange(e.date, range))
    .sort((a, b) => b.source_count - a.source_count || b.score_max - a.score_max);

/** 周报/月报导读：由数据拼装（构建期无 LLM）。 */
function periodOverview(kind: ReportKind, range: [string, string], issues: Issue[], items: NewsItem[]): string {
  const days = issues.length;
  const srcs = uniqSources(items);
  const parts = [`本期收录 ${range[0]} 至 ${range[1]} 的 ${days} 期日报`];
  const ev = topEvents(range)[0];
  const top = leadStoryOf(items);
  if (ev) {
    parts.push(`共精选 ${items.length} 条资讯、来自 ${srcs} 个独立来源。期间讨论最广的事件是「${ev.title_zh}」（${ev.source_count} 家来源报道）`);
  } else if (top) {
    parts.push(`共精选 ${items.length} 条资讯、来自 ${srcs} 个独立来源。评分最高的条目是《${top.title_zh || top.title_orig}》`);
  } else {
    parts.push('暂无精选内容');
  }
  return parts.join('，') + '。';
}

// ── 日报 ─────────────────────────────────────────────────────────────────────

const allIssues = () => getIssues(); // date 倒序

/** 期题：优先编辑导语标题，退回首条头条。 */
function issueTitle(issue: Issue): string {
  return issue.lead?.title || issue.headlines[0]?.title_zh || issue.headlines[0]?.title_orig || `AI 日报 · ${issue.date}`;
}

export function getDailyIndex(): NavEntry[] {
  return allIssues().map((i) => ({ key: i.date, title: issueTitle(i) }));
}

export function getDailyPaper(date: string): Paper | null {
  const issues = allIssues();
  const idx = issues.findIndex((i) => i.date === date);
  if (idx < 0) return null;
  const issue = issues[idx];
  const items = selectedOf(issue);
  const hasEditorLead = Boolean(issue.lead?.title || issue.lead?.paragraph);
  const leadStory = hasEditorLead ? null : leadStoryOf(issue.headlines.length > 0 ? issue.headlines : items);
  const rest = leadStory ? items.filter((it) => it.id !== leadStory.id) : items;

  const byId = new Map(items.map((it) => [it.id, it]));
  const highlights = (issue.lead?.highlights ?? [])
    .map((id) => byId.get(id))
    .filter(Boolean)
    .slice(0, 3) as NewsItem[];
  const fallbackHl = [...rest]
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
    .filter((it) => !leadStory || it.id !== leadStory.id)
    .slice(0, 3);

  const { sections, flashes } = makeSections(rest);
  const metric: Paper['metrics'] = [
    { value: items.length, unit: '件大事' },
    { value: uniqSources(items), unit: '个来源' },
    { value: items.filter((it) => it.first_party).length, unit: '件一手' },
  ];
  const ev = issue.stats.events;
  if (typeof ev === 'number') metric.push({ value: ev, unit: '个事件' });

  const link = (i: number, direction: 'prev' | 'next'): PaperLink | null => {
    const other = issues[idx + (direction === 'prev' ? 1 : -1)];
    if (!other) return null;
    return {
      key: other.date,
      label: `${direction === 'prev' ? '前一日' : '后一日'} · ${Number(other.date.slice(5, 7))}月${Number(other.date.slice(8, 10))}日`,
      title: issueTitle(other),
      href: withBase(`/daily/${other.date}/`),
    };
  };

  return {
    kind: 'daily',
    key: date,
    issueNo: issue.issue,
    dateline: `${date.slice(0, 4)} 年 ${Number(date.slice(5, 7))} 月 ${Number(date.slice(8, 10))} 日 · ${weekdayOf(date)}`,
    headlineTitle: issue.lead?.title || leadStory?.title_zh || leadStory?.title_orig || `这一天的 ${items.length} 件 AI 大事`,
    leadParagraph: issue.lead?.paragraph ?? leadStory?.summary_zh ?? null,
    leadStory,
    highlights: highlights.length > 0 ? highlights : fallbackHl,
    sections,
    flashes,
    metrics: metric,
    minutes: minutesOf(items),
    mark: {
      figure: date.slice(8, 10),
      top: `${date.slice(0, 4)} 年 ${Number(date.slice(5, 7))} 月`,
      bottom: weekdayOf(date),
    },
    prev: link(idx, 'prev'),
    next: link(idx, 'next'),
  };
}

// ── 周报 / 月报 ──────────────────────────────────────────────────────────────

interface Period {
  key: string;
  range: [string, string];
  issues: Issue[];
}

function periods(kind: 'weekly' | 'monthly'): Period[] {
  const map = new Map<string, Issue[]>();
  for (const issue of allIssues()) {
    const key = kind === 'weekly' ? isoWeekOf(issue.date) : issue.date.slice(0, 7);
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(issue);
  }
  return [...map.entries()]
    .map(([key, issues]) => ({
      key,
      range: kind === 'weekly' ? isoWeekRange(key) : monthRange(key),
      issues: issues.sort((a, b) => b.date.localeCompare(a.date)),
    }))
    .sort((a, b) => b.key.localeCompare(a.key));
}

function periodIndex(kind: 'weekly' | 'monthly'): NavEntry[] {
  return periods(kind).map((p) => {
    const count = p.issues.reduce((n, i) => n + selectedOf(i).length, 0);
    return { key: p.key, title: periodHeadline(kind, p.key, count) };
  });
}
export const getWeeklyIndex = () => periodIndex('weekly');
export const getMonthlyIndex = () => periodIndex('monthly');

function periodHeadline(kind: 'weekly' | 'monthly', key: string, count: number): string {
  return kind === 'weekly'
    ? `本周的 ${count} 件 AI 大事`
    : `${Number(key.slice(5, 7))} 月的 ${count} 件 AI 大事`;
}

function periodPaper(kind: 'weekly' | 'monthly', key: string): Paper | null {
  const list = periods(kind);
  const idx = list.findIndex((p) => p.key === key);
  if (idx < 0) return null;
  const p = list[idx];
  // 周期报头版用统计式大标题 + 数据导读，全部条目留在版面内（AIHOT 周报模式）
  const items = p.issues.flatMap((i) => [...i.headlines, ...i.briefing]);
  const { sections, flashes } = makeSections(items);
  const count = items.length;

  const link = (i: number, direction: 'prev' | 'next'): PaperLink | null => {
    const other = list[idx + (direction === 'prev' ? 1 : -1)];
    if (!other) return null;
    const otherCount = other.issues.reduce((n, iss) => n + selectedOf(iss).length, 0);
    return {
      key: other.key,
      label:
        direction === 'prev' ? '上一期' : '下一期',
      title: periodHeadline(kind, other.key, otherCount),
      href: withBase(`${KIND_PATH[kind]}/${other.key}/`),
    };
  };

  const [a, b] = p.range;
  const dot = (s: string) => s.slice(5).replace('-', '.');
  return {
    kind,
    key,
    issueNo: list.length - idx, // 起始为第 1 期
    dateline:
      kind === 'weekly'
        ? `${a.slice(0, 4)} 年第 ${Number(key.slice(6))} 周 · ${dot(a)} — ${dot(b)}`
        : `${a.slice(0, 4)} 年 ${Number(a.slice(5, 7))} 月`,
    headlineTitle: periodHeadline(kind, key, count),
    leadParagraph: periodOverview(kind, p.range, p.issues, items),
    leadStory: null,
    highlights: [...p.issues.flatMap((i) => i.headlines)]
      .sort((x, y) => (y.score ?? 0) - (x.score ?? 0))
      .slice(0, 3),
    sections,
    flashes,
    metrics: [
      { value: p.issues.length, unit: '期日报' },
      { value: count, unit: '件大事' },
      { value: uniqSources(items), unit: '个来源' },
    ],
    minutes: minutesOf(items),
    mark:
      kind === 'weekly'
        ? { figure: key.slice(6), top: `${a.slice(0, 4)} 年第 ${Number(key.slice(6))} 周`, bottom: `${dot(a)} — ${dot(b)}` }
        : { figure: key.slice(5, 7), top: `${a.slice(0, 4)} 年`, bottom: `${Number(a.slice(5, 7))} 月` },
    prev: link(idx, 'prev'),
    next: link(idx, 'next'),
  };
}

export const getWeeklyPaper = (key: string) => periodPaper('weekly', key);
export const getMonthlyPaper = (key: string) => periodPaper('monthly', key);

// ── 左侧归档栏 ───────────────────────────────────────────────────────────────

export interface ArchiveEntry {
  key: string;
  href: string;
  title: string;
  big: string;  // 大号数字（日/周号/月号）
  small: string | null; // 数字下的小字
}

export interface ArchiveGroup {
  id: string;
  label: string; // 「2026 年 9 月」
  entries: ArchiveEntry[];
}

export function reportPath(kind: ReportKind, key: string): string {
  return withBase(`${KIND_PATH[kind]}/${key}/`);
}

/** 归档分组：日报按月、周报按周一所在月（「第N周」）、月报按年。 */
export function archiveGroups(kind: ReportKind, index: NavEntry[]): ArchiveGroup[] {
  const groups: ArchiveGroup[] = [];
  const push = (g: ArchiveGroup) => {
    const last = groups[groups.length - 1];
    if (last && last.id === g.id) last.entries.push(...g.entries);
    else groups.push(g);
  };
  if (kind === 'weekly') {
    const byMonth = new Map<string, string[]>();
    for (const e of index) {
      const m = isoWeekRange(e.key)[0].slice(0, 7);
      byMonth.set(m, [...(byMonth.get(m) ?? []), e.key].sort());
    }
    for (const e of index) {
      const m = isoWeekRange(e.key)[0].slice(0, 7);
      const short = `第${(byMonth.get(m) ?? []).indexOf(e.key) + 1}周`;
      const [a] = isoWeekRange(e.key);
      push({
        id: m,
        label: `${m.slice(0, 4)} 年 ${Number(m.slice(5))} 月`,
        entries: [{
          key: e.key, href: reportPath(kind, e.key), title: e.title,
          big: e.key.slice(6), small: `${Number(a.slice(5, 7))}.${Number(a.slice(8, 10))} 起`,
        }],
      });
    }
    return groups;
  }
  for (const e of index) {
    if (kind === 'daily') {
      push({
        id: e.key.slice(0, 7),
        label: `${e.key.slice(0, 4)} 年 ${Number(e.key.slice(5, 7))} 月`,
        entries: [{
          key: e.key, href: reportPath(kind, e.key), title: e.title,
          big: e.key.slice(8, 10), small: weekdayOf(e.key),
        }],
      });
    } else {
      push({
        id: e.key.slice(0, 4),
        label: `${e.key.slice(0, 4)} 年`,
        entries: [{
          key: e.key, href: reportPath(kind, e.key), title: e.title,
          big: e.key.slice(5, 7), small: null,
        }],
      });
    }
  }
  return groups;
}

/** 手机端期次胶囊的短标签：「9月28日 / 第 40 周 / 9 月」。 */
export function chipLabel(kind: ReportKind, key: string): string {
  if (kind === 'daily') return `${Number(key.slice(5, 7))}月${Number(key.slice(8, 10))}日`;
  if (kind === 'monthly') return `${Number(key.slice(5, 7))} 月`;
  return `第 ${Number(key.slice(6))} 周`;
}
