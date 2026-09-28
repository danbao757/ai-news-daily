// GitHub Pages 项目站带 base 路径（/ai-news-daily），
// 站内链接一律经 withBase() 拼接，否则部署后指向站点根目录 404。
export const BASE = (import.meta.env.BASE_URL || '/').replace(/\/+$/, '');

export function withBase(path: string): string {
  return `${BASE}${path.startsWith('/') ? path : `/${path}`}`;
}
