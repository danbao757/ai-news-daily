// RSS 输出：每期日报一条 digest item，构建产物为 dist/rss.xml
import { getIssues } from '../lib/issues';
import { BASE } from '../lib/url';

const SITE = (import.meta.env.SITE || '').replace(/\/+$/, '');

function esc(s) {
  return String(s ?? '').replace(
    /[<>&'"]/g,
    (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', "'": '&apos;', '"': '&quot;' })[c],
  );
}

function digestHtml(issue) {
  const parts = [];
  if (issue.lead?.paragraph) {
    parts.push(`<p><b>${esc(issue.lead.title ?? '')}</b>${issue.lead.title ? '<br/>' : ''}${esc(issue.lead.paragraph)}</p>`);
  }
  if (issue.headlines.length) {
    parts.push('<h3>头条</h3><ol>');
    for (const h of issue.headlines) {
      parts.push(
        `<li><a href="${esc(h.url)}">${esc(h.title_zh || h.title_orig)}</a>（${esc(h.source)} · 评分 ${h.score ?? '—'}）`,
      );
      if (h.summary_zh) parts.push(`<br/>${esc(h.summary_zh)}`);
      parts.push('</li>');
    }
    parts.push('</ol>');
  }
  if (issue.briefing.length) {
    parts.push('<h3>速览</h3><ul>');
    for (const b of issue.briefing) {
      parts.push(`<li><a href="${esc(b.url)}">${esc(b.title_zh || b.title_orig)}</a>（${esc(b.source)}）</li>`);
    }
    parts.push('</ul>');
  }
  return parts.join('');
}

export function GET() {
  const items = getIssues().map((issue) => {
    const link = `${SITE}${BASE}/issue/${issue.date}/`;
    return [
      '<item>',
      `  <title>${esc(issue.lead?.title || `AI 日报 · 第 ${issue.issue} 期（${issue.date}）`)}</title>`,
      `  <link>${link}</link>`,
      `  <guid isPermaLink="true">${link}</guid>`,
      `  <pubDate>${new Date(issue.generated_at).toUTCString()}</pubDate>`,
      `  <description>${esc(digestHtml(issue))}</description>`,
      '</item>',
    ].join('\n');
  });

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>AI 日报</title>
    <link>${SITE}${BASE}/</link>
    <description>全网 AI 资讯每日精选：模型发布、产品更新、行业动态，每天一期。</description>
    <language>zh-cn</language>
    <atom:link href="${SITE}${BASE}/rss.xml" rel="self" type="application/rss+xml"/>
${items.join('\n')}
  </channel>
</rss>`;

  return new Response(xml, {
    headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' },
  });
}
