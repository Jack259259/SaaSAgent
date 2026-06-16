// app.js — Alpine 根组件:主题 + 抽屉 + 聊天(合入 chat.js);开发态装载 mock + 注入 X-User-Ctx。
import { installMockSSE } from '../mock/mock-sse.js';
import { icon } from '../vendor/lucide/icons.js';
import { createChat } from './chat.js';
import { setUserCtx } from './sse.js';

installMockSSE(); // 开发态装载 mock(拦截 /chat 与 /chat/confirm)

// 开发态注入 X-User-Ctx(§12-D4;生产同源走 cookie/session,前端不自造权限)。
setUserCtx({ tenant_id: 'demo-tenant', user_id: 'demo-user', roles: ['analyst'], data_scope: { regions: ['*'] } });

const HLJS_THEME = {
  light: 'vendor/highlight/github.min.css',
  dark: 'vendor/highlight/github-dark.min.css',
};
function applyHljsTheme(theme) {
  const link = document.getElementById('hljs-theme');
  if (link) link.setAttribute('href', HLJS_THEME[theme] || HLJS_THEME.light);
}

document.addEventListener('alpine:init', () => {
  window.Alpine.data('app', () => ({
    theme: document.documentElement.getAttribute('data-theme') || 'light',
    sidebarOpen: false,
    icon,
    ...createChat(),

    init() {
      applyHljsTheme(this.theme);
    },
    toggleTheme() {
      this.theme = this.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', this.theme);
      applyHljsTheme(this.theme);
      try { localStorage.setItem('fp_theme', this.theme); } catch (e) { /* 忽略 */ }
    },
  }));
});
