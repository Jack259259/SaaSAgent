// app.js — Alpine 根组件:主题、初始化、默认装载 mock。
// W0 仅证明 Alpine 生效 + 主题切换 + 开发态装载 mock;对话业务逻辑见 chat.js(W1/W2),禁止在此实现。
import { installMockSSE } from '../mock/mock-sse.js';
import { icon } from '../vendor/lucide/icons.js';

// 开发态默认装载 mock(拦截 POST /chat);生产或 localStorage fp_mock='0' 时不装(见 mock-sse.js)。
const mockActive = installMockSSE();

document.addEventListener('alpine:init', () => {
  window.Alpine.data('app', () => ({
    theme: document.documentElement.getAttribute('data-theme') || 'light',
    alpineOk: true,
    mockNote: mockActive ? 'Mock SSE 已启用(开发态)' : 'Mock SSE 未启用',
    icon, // 暴露给模板:x-html="icon('sun')"(自有 SVG,非用户内容)

    toggleTheme() {
      this.theme = this.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', this.theme);
      try { localStorage.setItem('fp_theme', this.theme); } catch (e) { /* 忽略存储不可用 */ }
    },
  }));
});
