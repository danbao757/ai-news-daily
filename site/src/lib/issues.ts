// v2 数据层：读 data/{issues,items,events} 三层结构。
//   issues/YYYY-MM-DD.json  日报（headline_ids/briefing_ids 引用式）
//   items/YYYY-MM-DD.jsonl  当日全量分析条目（id 为 sha1(url)[:10]）
//   events/YYYY-MM-DD.json  当日聚类事件（member_ids 引用条目）
// 页面展示用 hydrateIssue() 把 id join 回条目。
// 注意相对路径：本文件在 site/src/lib/ → 项目根 data/ 共三级（../../..）。

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export interface Fact {
  title: string | null;
  subject: string | null;
  action: string | null;
  object: string | null;
  occurred_at: string | null;
}

export interface NewsItem {
  id: string;
  url: string;
  source_id: string;
  source: string;
  tier: string;
  first_party: boolean;
  lang: string;
  priority: number;
  published_at: string | null;
  collected_at: string;
  title_orig: string;
  summary_orig: string;
  prefilter: string;
  scores: number[] | null;
  score: number | null;
  threshold: number | null;
  selected: boolean;
  category: string | null;
  item_type: string | null;
  author_role: string | null;
  tags: string[];
  subjects: string[];
  fact: Fact | null;
  title_zh: string;
  summary_zh: string;
  reason_zh: string | null;
  writer_kind: string;
  event_id: string | null;
  event_role: string | null;
  date?: string; // 由文件名注入
}

export interface Lead {
  title: string | null;
  paragraph: string | null;
  highlights: string[];
}

export interface IssueStats {
  collected: number;
  duplicates: number;
  analyzed: number;
  blocked: number;
  selected: number;
  events: number;
  sources: string[];
}

export interface IssueRecord {
  issue: number;
  date: string;
  generated_at: string;
  stats: IssueStats;
  lead: Lead | null;
  headline_ids: string[];
  briefing_ids: string[];
}

export interface Issue extends Omit<IssueRecord, 'stats'> {
  stats: Partial<IssueStats>;
  headlines: NewsItem[];
  briefing: NewsItem[];
}

export interface EventRecord {
  id: string;
  title_zh: string;
  digest_zh: string;
  representative_id: string;
  member_ids: string[];
  member_urls?: string[];
  sources: string[];
  source_count: number;
  score_max: number;
  continued_from: string | null;
  first_seen: string;
  latest_published_at: string;
  date?: string; // 由文件名注入
}

// 与 collector/taxonomy.py 的 CATEGORIES 保持一致
export const CATEGORY_LABELS: Record<string, string> = {
  'ai-models': '模型',
  'ai-products': '产品',
  'industry': '行业',
  paper: '论文',
  'open-source': '开源',
  policy: '政策',
  opinion: '观点',
};

const dataRoot = fileURLToPath(new URL('../../../data', import.meta.url));
const issuesDir = path.join(dataRoot, 'issues');
const itemsDir = path.join(dataRoot, 'items');
const eventsDir = path.join(dataRoot, 'events');

function listJson(dir: string): string[] {
  return fs.existsSync(dir)
    ? fs.readdirSync(dir).filter((f) => f.endsWith('.json')).sort()
    : [];
}

// ── 条目全量索引 ─────────────────────────────────────────────────────────────

let _itemIndex: Map<string, NewsItem> | null = null;

export function getItemIndex(): Map<string, NewsItem> {
  if (_itemIndex) return _itemIndex;
  const idx = new Map<string, NewsItem>();
  if (fs.existsSync(itemsDir)) {
    for (const f of fs.readdirSync(itemsDir).filter((f) => f.endsWith('.jsonl')).sort()) {
      const date = f.replace(/\.jsonl$/, '');
      for (const line of fs.readFileSync(path.join(itemsDir, f), 'utf-8').split('\n')) {
        const s = line.trim();
        if (!s) continue;
        try {
          const it = JSON.parse(s) as NewsItem;
          it.date = it.date || date;
          idx.set(it.id, it); // 同 id 后写覆盖（重跑日以最新为准）
        } catch {
          /* 跳过坏行 */
        }
      }
    }
  }
  _itemIndex = idx;
  return idx;
}

// ── 事件 ─────────────────────────────────────────────────────────────────────

let _events: EventRecord[] | null = null;

export function getEvents(): EventRecord[] {
  if (_events) return _events;
  const out: EventRecord[] = [];
  for (const f of listJson(eventsDir)) {
    const date = f.replace(/\.json$/, '');
    try {
      const data = JSON.parse(fs.readFileSync(path.join(eventsDir, f), 'utf-8'));
      for (const ev of data.events ?? []) {
        out.push({ ...ev, date });
      }
    } catch {
      /* 跳过坏文件 */
    }
  }
  _events = out;
  return out;
}

/** 多源事件（≥2 家独立来源才有独立事件页），热榜排序：来源数 → 最高分 → 时间。 */
export function getHotEvents(): EventRecord[] {
  const multi = getEvents().filter((e) => e.source_count >= 2);
  return multi.sort((a, b) =>
    b.source_count - a.source_count ||
    b.score_max - a.score_max ||
    (b.latest_published_at || '').localeCompare(a.latest_published_at || ''),
  );
}

export function getEventById(id: string): EventRecord | undefined {
  // 同一事件跨日续接沿用 id，取最新一天的定义
  return getEvents().filter((e) => e.id === id).sort((a, b) =>
    (b.date ?? '').localeCompare(a.date ?? ''))[0];
}

// ── 日报 ─────────────────────────────────────────────────────────────────────

export function getRawIssues(): IssueRecord[] {
  return listJson(issuesDir)
    .map((f) => {
      try {
        return JSON.parse(fs.readFileSync(path.join(issuesDir, f), 'utf-8')) as IssueRecord;
      } catch {
        return null;
      }
    })
    .filter(Boolean)
    .sort((a, b) => b.date.localeCompare(a.date) || b.issue - a.issue);
}

export function hydrateIssue(rec: IssueRecord): Issue {
  const idx = getItemIndex();
  const pick = (ids: string[]): NewsItem[] =>
    ids.map((id) => idx.get(id)).filter(Boolean) as NewsItem[];
  return {
    ...rec,
    stats: rec.stats ?? {},
    headlines: pick(rec.headline_ids ?? []),
    briefing: pick(rec.briefing_ids ?? []),
  };
}

export function getIssues(): Issue[] {
  return getRawIssues().map(hydrateIssue);
}

// ── 工具 ─────────────────────────────────────────────────────────────────────

export function fmtDate(iso: string): string {
  const [y, m, d] = iso.split('-');
  return `${y} 年 ${Number(m)} 月 ${Number(d)} 日`;
}

export function fmtTime(at: string | null): string {
  if (!at) return '';
  const m = at.match(/T(\d{2}:\d{2})/);
  return m ? m[1] : '';
}

export function catLabel(key: string | null): string {
  return (key && CATEGORY_LABELS[key]) || '资讯';
}
