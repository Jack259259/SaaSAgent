// app.js — Alpine 根组件:主题 + 抽屉 + 聊天(合入 chat.js);开发态装载 mock。
import { installMockSSE } from '../mock/mock-sse.js';
import { icon } from '../vendor/lucide/icons.js';
import { createChat } from './chat.js';

installMockSSE(); // 开发态装载 mock(W1 未走 /chat,W2 接入真实流时即生效)

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
