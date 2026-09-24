import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export interface NewsItem {
  title_zh: string;
  title_orig: string;
  summary_zh: string;
  category: string;
  tags: string[];
  score: number;
  source: string;
  url: string;
  published_at: string | null;
}

export interface Issue {
  issue: number;
  date: string;
  generated_at: string;
  stats: {
    collected: number;
    duplicates: number;
    selected: number;
    sources: string[];
  };
  headlines: NewsItem[];
  briefing: NewsItem[];
}

// site/src/lib/issues.ts → 项目根 data/issues（lib → src → site → 根，共三级）
const dataDir = fileURLToPath(new URL('../../../data/issues', import.meta.url));

export function getIssues(): Issue[] {
  if (!fs.existsSync(dataDir)) return [];
  return fs
    .readdirSync(dataDir)
    .filter((f) => f.endsWith('.json'))
    .map((f) => JSON.parse(fs.readFileSync(path.join(dataDir, f), 'utf-8')) as Issue)
    .sort((a, b) => b.date.localeCompare(a.date) || b.issue - a.issue);
}

export function fmtDate(iso: string): string {
  const [y, m, d] = iso.split('-');
  return `${y} 年 ${Number(m)} 月 ${Number(d)} 日`;
}
