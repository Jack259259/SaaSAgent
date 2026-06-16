// app.js — Alpine 根组件:主题 + 抽屉 + 聊天 + 附件 + 会话历史;开发态装载 mock + 注入 X-User-Ctx。
import { installMockSSE } from '../mock/mock-sse.js';
import { icon } from '../vendor/lucide/icons.js';
import { createChat } from './chat.js';
import { createAttachments } from './attachments.js';
import { createSkills } from './skills.js';
import { setUserCtx } from './sse.js';

// 异步装载 mock:探测 /healthz,真实后端(agent-gateway)在则不装(fire-and-forget,首次发送前完成)。
installMockSSE();

// 开发态注入 X-User-Ctx(§12-D4;生产同源走 cookie/session)。对齐 contracts.UserCtx。
// dev 角色可经 localStorage.fp_dev_roles 覆盖(演示/测试 Skill 管理入口的角色门控)。
let _devRoles = ['analyst', 'skill_admin'];
try { const r = JSON.parse(localStorage.getItem('fp_dev_roles') || 'null'); if (Array.isArray(r)) _devRoles = r; } catch (e) { /* ignore */ }
setUserCtx({ tenant_id: 'demo-tenant', user_id: 'demo-user', roles: _devRoles, data_scope: { regions: ['*'] }, permissions: ['*'] });

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
    ...createAttachments(),
    ...createSkills(),

    init() {
      applyHljsTheme(this.theme);
      this.initChat(); // 恢复最近会话(刷新可回看)
    },
    toggleTheme() {
      this.theme = this.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', this.theme);
      applyHljsTheme(this.theme);
      try { localStorage.setItem('fp_theme', this.theme); } catch (e) { /* 忽略 */ }
    },
  }));
});
