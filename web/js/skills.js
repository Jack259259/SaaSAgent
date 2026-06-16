// skills.js — Skill 管理(§8.5)API 客户端 + 角色门控/校验 + Alpine 模块。
// Skill 是产品级治理资产(后端红线 10:改动过 schema + 评估回归 + git 评审;§9.1 仅内部角色)。
// 前端只做 CRUD/上传 UI + 角色门控 + 预览消毒;解压/校验/入库与鉴权在后端(W4 对 mock 开发,后端待补见 backend-gaps)。
import { getUserCtx } from './sse.js';
import { renderMarkdown } from './markdown.js';

// 可管理 Skill 的角色(内部/管理员;租户业务用户无)。可按部署调整。
export const ADMIN_ROLES = ['admin', 'skill_admin', 'internal', 'internal_support', 'internal_dev'];
export function canManageSkills(roles) {
  return Array.isArray(roles) && roles.some((r) => ADMIN_ROLES.includes(r));
}

export const SKILL_ZIP_LIMITS = { maxBytes: 20 * 1024 * 1024 };

export function validateSkillName(name) {
  const n = (name || '').trim();
  if (!n) return { ok: false, reason: '名称不能为空' };
  if (!/^[A-Za-z0-9_-]{2,64}$/.test(n)) return { ok: false, reason: '名称仅限字母 / 数字 / 下划线 / 连字符,2–64 字符' };
  return { ok: true };
}
export function validateSkillZip(file) {
  if (!file || !/\.zip$/i.test(file.name || '')) return { ok: false, reason: '仅支持 .zip' };
  if ((file.size || 0) > SKILL_ZIP_LIMITS.maxBytes) return { ok: false, reason: '超过 ' + Math.round(SKILL_ZIP_LIMITS.maxBytes / 1024 / 1024) + 'MB 上限' };
  return { ok: true };
}

/** 拆分 SKILL.md 的 YAML frontmatter 与正文。纯函数,供详情/预览/ selftest。 */
export function splitFrontmatter(content) {
  const m = /^---\s*\n([\s\S]*?)\n---\s*\n?([\s\S]*)$/.exec(content || '');
  if (!m) return { meta: {}, body: content || '' };
  const meta = {};
  m[1].split('\n').forEach((line) => { const mm = /^(\w+):\s*(.*)$/.exec(line.trim()); if (mm) meta[mm[1]] = mm[2]; });
  return { meta, body: m[2] };
}

// ---- 统一 http(带 user_ctx 透传)----
async function http(method, url, { json, formData } = {}) {
  const headers = {};
  const ctx = getUserCtx();
  if (ctx) headers['X-User-Ctx'] = JSON.stringify(ctx);
  let body;
  if (json !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(json); }
  else if (formData) body = formData;
  const res = await fetch(url, { method, headers, body });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }
  if (!res.ok) { const err = new Error((data && data.message) || ('HTTP ' + res.status)); err.status = res.status; err.data = data; throw err; }
  return data;
}

export const listSkills = () => http('GET', '/skills');
export const getSkill = (id) => http('GET', '/skills/' + encodeURIComponent(id));
export const createSkill = (name, content) => http('POST', '/skills', { json: { name, content } });
export const updateSkill = (id, name, content) => http('PUT', '/skills/' + encodeURIComponent(id), { json: { name, content } });
export const deleteSkill = (id) => http('DELETE', '/skills/' + encodeURIComponent(id));
export const setSkillStatus = (id, status) => http('POST', '/skills/' + encodeURIComponent(id) + '/status', { json: { status } });
export function uploadSkillZip(file) { const fd = new FormData(); fd.append('file', file); return http('POST', '/skills/upload', { formData: fd }); }

function skillErr(e) {
  if (!e) return '操作失败';
  if (e.status === 401) return '未登录或缺少身份信息';
  if (e.status === 403) return '无权操作(仅管理员 / 内部角色)';
  if (e.status === 404) return '后端 /skills 待实现(D6)';
  return (e.data && e.data.message) || e.message || '操作失败';
}

/** 创建 Skill 管理相关的 Alpine 状态与方法(由 app.js 合入根组件)。 */
export function createSkills() {
  return {
    skillsOpen: false,
    skillsList: [],
    skillsLoading: false,
    skillsError: '',
    skillView: 'list', // list | detail | edit | new
    skillCurrent: null,
    skillForm: { name: '', content: '' },
    skillFormError: '',
    skillSchemaErrors: [],
    skillSaving: false,
    skillSaveHint: '',
    skillUploadResults: null,
    skillUploadError: '',

    skillAdmin() { const ctx = getUserCtx(); return ctx ? canManageSkills(ctx.roles) : false; },

    openSkills() {
      if (!this.skillAdmin()) return; // 双保险:非授权不进面板
      this.skillsOpen = true;
      this.skillView = 'list';
      this.skillCurrent = null;
      this.skillUploadResults = null; this.skillUploadError = '';
      this.refreshSkills();
      if (typeof window !== 'undefined' && window.innerWidth < 1024) this.sidebarOpen = false;
    },
    closeSkills() { this.skillsOpen = false; },

    async refreshSkills() {
      this.skillsLoading = true; this.skillsError = '';
      try { this.skillsList = await listSkills(); }
      catch (e) { this.skillsError = skillErr(e); this.skillsList = []; }
      finally { this.skillsLoading = false; }
    },
    async viewSkill(id) {
      this.skillsError = '';
      try { this.skillCurrent = await getSkill(id); this.skillView = 'detail'; }
      catch (e) { this.skillsError = skillErr(e); }
    },
    startNew() {
      this.skillForm = { name: '', content: '---\nname: \ndescription: \n---\n\n# 用法\n\n' };
      this.skillFormError = ''; this.skillSchemaErrors = []; this.skillSaveHint = '';
      this.skillView = 'new';
    },
    startEdit() {
      if (!this.skillCurrent) return;
      this.skillForm = { name: this.skillCurrent.name, content: this.skillCurrent.content || '' };
      this.skillFormError = ''; this.skillSchemaErrors = []; this.skillSaveHint = '';
      this.skillView = 'edit';
    },
    cancelEdit() { this.skillView = this.skillCurrent ? 'detail' : 'list'; },

    async submitSkill() {
      const v = validateSkillName(this.skillForm.name);
      if (!v.ok) { this.skillFormError = v.reason; return; }
      this.skillFormError = ''; this.skillSchemaErrors = []; this.skillSaving = true; this.skillSaveHint = '';
      try {
        if (this.skillView === 'edit' && this.skillCurrent) await updateSkill(this.skillCurrent.id, this.skillForm.name, this.skillForm.content);
        else await createSkill(this.skillForm.name, this.skillForm.content);
        this.skillSaveHint = '已保存为草稿,待管理员审核。';
        await this.refreshSkills();
        this.skillView = 'list';
        this.skillCurrent = null;
      } catch (e) {
        if (e && e.status === 422 && e.data && Array.isArray(e.data.errors)) this.skillSchemaErrors = e.data.errors;
        else this.skillFormError = skillErr(e);
      } finally { this.skillSaving = false; }
    },
    async publishSkill() {
      if (!this.skillCurrent) return;
      try { this.skillCurrent = await setSkillStatus(this.skillCurrent.id, 'active'); await this.refreshSkills(); }
      catch (e) { this.skillsError = skillErr(e); }
    },
    async removeSkill(id) {
      if (!window.confirm('删除该 Skill?此操作不可恢复。')) return;
      try {
        await deleteSkill(id);
        if (this.skillCurrent && this.skillCurrent.id === id) { this.skillCurrent = null; this.skillView = 'list'; }
        await this.refreshSkills();
      } catch (e) { this.skillsError = skillErr(e); }
    },

    pickSkillZip(e) { const f = e.target.files && e.target.files[0]; e.target.value = ''; if (f) this.uploadZip(f); },
    async uploadZip(file) {
      this.skillUploadResults = null; this.skillUploadError = '';
      const v = validateSkillZip(file);
      if (!v.ok) { this.skillUploadError = v.reason; return; }
      try { const res = await uploadSkillZip(file); this.skillUploadResults = (res && res.results) || []; await this.refreshSkills(); }
      catch (e) { this.skillUploadError = skillErr(e); }
    },

    skillContentHtml() { return renderMarkdown(splitFrontmatter((this.skillCurrent && this.skillCurrent.content) || '').body); },
    skillPreviewHtml() { return renderMarkdown(splitFrontmatter(this.skillForm.content || '').body); },
    skillMeta() { return this.skillCurrent ? splitFrontmatter(this.skillCurrent.content || '').meta : {}; },
    statusLabel(s) { return { active: '生效', draft: '草稿待审', review: '待审', pending: '待审' }[s] || s; },
    skillFmtTime(t) { try { return t ? new Date(t).toLocaleString('zh-CN') : ''; } catch (e) { return ''; } },
  };
}
