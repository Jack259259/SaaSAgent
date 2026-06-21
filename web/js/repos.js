// repos.js — 代码仓管理(§12 item3 的 UI 化)API 客户端 + 角色门控/校验 + Alpine 模块。
// 后端 /admin/repos*(内部管理员 + FP_REPO_ADMIN);前端**不 clone、不解压**——git/解压/索引在后端。
// 凭据二步流:匿名 clone 失败(AUTH_REQUIRED)→ 弹窗收账号密码 → 带凭据重试(红线 3 透传 user_ctx)。
import { getUserCtx } from './sse.js';

// 可管理代码仓的角色(内部/管理员;与后端 auth._REPO_ADMIN_ROLES 同口径)。
export const REPO_ADMIN_ROLES = ['admin', 'repo_admin', 'internal', 'internal_support', 'internal_dev'];
export function canManageRepos(roles) {
  return Array.isArray(roles) && roles.some((r) => REPO_ADMIN_ROLES.includes(r));
}

export const REPO_ARCHIVE_EXTS = ['.zip', '.tar', '.tar.gz', '.tar.bz2', '.tgz', '.tbz2'];
export const REPO_UPLOAD_LIMIT = { maxBytes: 300 * 1024 * 1024 };

export function validateRepoName(name) {
  const n = (name || '').trim();
  if (!n) return { ok: false, reason: '名称不能为空' };
  if (!/^[A-Za-z0-9_-]{2,64}$/.test(n)) return { ok: false, reason: '名称仅限字母 / 数字 / 下划线 / 连字符,2–64 字符' };
  return { ok: true };
}
export function validateRepoUrl(url) {
  if (!/^https?:\/\/.+/.test((url || '').trim())) return { ok: false, reason: '仓库地址需为 http(s)://' };
  return { ok: true };
}
export function validateRepoArchive(file) {
  const name = ((file && file.name) || '').toLowerCase();
  if (!REPO_ARCHIVE_EXTS.some((e) => name.endsWith(e))) return { ok: false, reason: '仅支持 .zip / .tar / .tar.gz / .tar.bz2' };
  if ((file.size || 0) > REPO_UPLOAD_LIMIT.maxBytes) return { ok: false, reason: '超过 ' + Math.round(REPO_UPLOAD_LIMIT.maxBytes / 1048576) + 'MB 上限' };
  return { ok: true };
}

// ---- 统一 http(带 user_ctx 透传;错误带 status+code 供凭据流判定)----
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
  if (!res.ok) {
    const err = new Error((data && data.message) || ('HTTP ' + res.status));
    err.status = res.status; err.code = data && data.code; err.data = data;
    throw err;
  }
  return data;
}

export const listRepos = () => http('GET', '/admin/repos');
export const cloneRepo = (payload) => http('POST', '/admin/repos', { json: payload });
export const updateGitRepo = (name, creds) => http('POST', '/admin/repos/' + encodeURIComponent(name) + '/update', { json: creds || {} });
export const deleteRepo = (name) => http('DELETE', '/admin/repos/' + encodeURIComponent(name));
export function uploadRepoArchive(name, file) {
  const fd = new FormData();
  fd.append('name', name);
  fd.append('file', file);
  return http('POST', '/admin/repos/upload', { formData: fd });
}

export function repoErr(e) {
  if (!e) return '操作失败';
  if (e.status === 403) return '无权操作(仅内部管理员)';
  if (e.status === 401 && e.code === 'AUTH_REQUIRED') return '该仓需要认证';
  if (e.status === 401) return '未登录或缺少身份信息';
  if (e.status === 404) return '代码仓管理未启用(FP_REPO_ADMIN)或后端待部署';
  return (e.data && e.data.message) || e.message || '操作失败';
}

/** 创建代码仓管理相关的 Alpine 状态与方法(由 app.js 合入根组件)。 */
export function createRepos() {
  return {
    reposOpen: false,
    reposList: [],
    reposLoading: false,
    reposError: '',
    repoView: 'list', // list | new | upload
    repoForm: { name: '', url: '', branch: 'main' },
    repoFormError: '',
    repoUploadName: '',
    repoUploadError: '',
    repoBusy: false,
    repoBusyHint: '',
    // 凭据二次流
    repoCredOpen: false,
    repoCred: { username: '', password: '' },
    repoPending: null, // { kind:'clone', payload } | { kind:'update', name }

    repoAdmin() { const ctx = getUserCtx(); return ctx ? canManageRepos(ctx.roles) : false; },

    openRepos() {
      if (!this.repoAdmin()) return; // 双保险:非授权不进面板
      this.reposOpen = true; this.repoView = 'list';
      this.reposError = ''; this.repoCredOpen = false; this.repoPending = null;
      this.refreshRepos();
      if (typeof window !== 'undefined' && window.innerWidth < 1024) this.sidebarOpen = false;
    },
    closeRepos() { this.reposOpen = false; this.repoCredOpen = false; },

    async refreshRepos() {
      this.reposLoading = true; this.reposError = '';
      try { this.reposList = await listRepos(); }
      catch (e) { this.reposError = repoErr(e); this.reposList = []; }
      finally { this.reposLoading = false; }
    },

    startNewRepo() { this.repoForm = { name: '', url: '', branch: 'main' }; this.repoFormError = ''; this.repoView = 'new'; },
    startUploadRepo() { this.repoUploadName = ''; this.repoUploadError = ''; this.repoView = 'upload'; },
    backToList() { this.repoView = 'list'; this.repoFormError = ''; this.repoUploadError = ''; },

    async submitClone() {
      const vn = validateRepoName(this.repoForm.name); if (!vn.ok) { this.repoFormError = vn.reason; return; }
      const vu = validateRepoUrl(this.repoForm.url); if (!vu.ok) { this.repoFormError = vu.reason; return; }
      this.repoFormError = '';
      await this._doClone({
        name: this.repoForm.name.trim(),
        url: this.repoForm.url.trim(),
        branch: (this.repoForm.branch || 'main').trim(),
      });
    },
    async _doClone(payload) {
      this.repoBusy = true; this.repoBusyHint = '正在拉取并建索引…';
      try {
        await cloneRepo(payload);
        this.repoCredOpen = false; this.repoPending = null;
        await this.refreshRepos(); this.repoView = 'list';
      } catch (e) {
        if (e.status === 401 && e.code === 'AUTH_REQUIRED') {
          this.repoPending = { kind: 'clone', payload };
          this.repoCred = { username: '', password: '' };
          this.repoCredOpen = true;
        } else { this.repoFormError = repoErr(e); }
      } finally { this.repoBusy = false; this.repoBusyHint = ''; }
    },

    async submitCred() {
      if (!this.repoPending) { this.repoCredOpen = false; return; }
      const creds = { username: this.repoCred.username, password: this.repoCred.password };
      const pending = this.repoPending;
      this.repoBusy = true; this.repoBusyHint = '正在认证并拉取…';
      try {
        if (pending.kind === 'clone') await cloneRepo({ ...pending.payload, ...creds });
        else await updateGitRepo(pending.name, creds);
        this.repoCredOpen = false; this.repoPending = null;
        await this.refreshRepos(); this.repoView = 'list';
      } catch (e) {
        this.repoCredOpen = false; this.repoPending = null;
        this.reposError = repoErr(e);
      } finally { this.repoBusy = false; this.repoBusyHint = ''; }
    },
    cancelCred() { this.repoCredOpen = false; this.repoPending = null; },

    async updateRepo(repo) {
      if (!repo) return;
      if (repo.source === 'archive') { this.repoUploadName = repo.name; this.repoUploadError = ''; this.repoView = 'upload'; return; }
      this.repoBusy = true; this.repoBusyHint = '正在更新…';
      try { await updateGitRepo(repo.name, {}); await this.refreshRepos(); }
      catch (e) {
        if (e.status === 401 && e.code === 'AUTH_REQUIRED') {
          this.repoPending = { kind: 'update', name: repo.name };
          this.repoCred = { username: '', password: '' };
          this.repoCredOpen = true;
        } else { this.reposError = repoErr(e); }
      } finally { this.repoBusy = false; this.repoBusyHint = ''; }
    },

    async removeRepo(name) {
      if (!window.confirm('删除代码仓「' + name + '」?将删除其本地目录并重建索引,此操作不可恢复。')) return;
      this.repoBusy = true; this.repoBusyHint = '正在删除…';
      try { await deleteRepo(name); await this.refreshRepos(); }
      catch (e) { this.reposError = repoErr(e); }
      finally { this.repoBusy = false; this.repoBusyHint = ''; }
    },

    pickRepoArchive(e) { const f = e.target.files && e.target.files[0]; e.target.value = ''; if (f) this.submitUpload(f); },
    async submitUpload(file) {
      const vn = validateRepoName(this.repoUploadName); if (!vn.ok) { this.repoUploadError = vn.reason; return; }
      const vf = validateRepoArchive(file); if (!vf.ok) { this.repoUploadError = vf.reason; return; }
      this.repoUploadError = ''; this.repoBusy = true; this.repoBusyHint = '正在上传、安全解压并建索引…';
      try { await uploadRepoArchive(this.repoUploadName.trim(), file); await this.refreshRepos(); this.repoView = 'list'; }
      catch (e) { this.repoUploadError = repoErr(e); }
      finally { this.repoBusy = false; this.repoBusyHint = ''; }
    },

    repoFmtTime(t) { try { return t ? new Date(t).toLocaleString('zh-CN') : ''; } catch (e) { return ''; } },
    repoSourceLabel(s) { return { git: 'Git', archive: '压缩包' }[s] || s; },
  };
}
