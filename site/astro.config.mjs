import { defineConfig } from 'astro/config';

// 部署前请修改：
//  - GitHub Pages 项目站（https://用户名.github.io/仓库名）需要同时设置 base: '/仓库名'
//  - 自定义域名 / Vercel 只需改 site
export default defineConfig({
  site: 'https://danbao757.github.io',
  base: '/ai-news-daily',
});
