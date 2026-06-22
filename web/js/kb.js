// kb.js — 知识库管理(§12 item2 的 UI 化)API 客户端 + 角色门控/校验 + Alpine 模块。
// 后端 /admin/kb/{kb}/*(内部管理员;IT 库叠加 internal 细 ACL,对齐红线 5/§9.1)。
// 前端**不解析文档、不解压**——docx 解析与入库(ingest)在后端(红线 14);上传后触发 ingest 并轮询状态。
// 「查看知识图谱」按钮打开独立的知识图谱面板(knowledge-graph.js,经根组件 spread)。
import { getUserCtx } from './sse.js';

// 可管理知识库的角色(内部/管理员;与后端 auth._KB_ADMIN_ROLES 同口径)。
export const KB_ADMIN_ROLES = ['admin', 'kb_admin', 'internal', 'internal_support', 'internal_dev'];
// 可见 IT 设计库的内部角色(与后端 rag_svc.acl._INTERNAL_ROLES 同口径)。
export const KB_INTERNAL_ROLES = ['internal', 'internal_support', 'internal_dev'];
export function canManageKb(roles) {
  return Array.isArray(roles) && roles.some((r) => KB_ADMIN_ROLES.includes(r));
}
export function isKbInternal(roles) {
  return Array.isArray(roles) && roles.some((r) => KB_INTERNAL_ROLES.includes(r));
}

// 知识库页签元信息(IT 页签仅内部角色可见,由 kbTabs() 过滤)。
export const KB_TABS = [
  { id: 'business', label: '业务知识库', internalOnly: false },
  { id: 'it_design', label: 'IT 知识库', internalOnly: true },
];

export const KB_FILE_EXTS = ['.md', '.markdown', '.txt', '.docx'];
export const KB_UPLOAD_LIMIT = { maxBytes: 25 * 1024 * 1024 };

export function validateKbName(name) {
  const n = (name || '').trim();
  if (!n) return { ok: false, reason: '文件名不能为空' };
  // 允许中文/空格等 unicode;仅拒路径穿越与分隔符(与后端 sanitize_doc_name 同口径)。
  if (n.includes('/') || n.includes('\\') || n.includes('..')) return { ok: false, reason: '文件名不得含路径分隔符' };
  if (n.length > 200) return { ok: false, reason: '文件名过长' };
  return { ok: true };
}
export function validateKbFile(file) {
  const name = ((file && file.name) || '').toLowerCase();
  if (!KB_FILE_EXTS.some((e) => name.endsWith(e))) return { ok: false, reason: '仅支持 .md / .markdown / .txt / .docx' };
  if ((file.size || 0) > KB_UPLOAD_LIMIT.maxBytes) return { ok: false, reason: '超过 ' + Math.round(KB_UPLOAD_LIMIT.maxBytes / 1048576) + 'MB 上限' };
  return { ok: true };
}

// ingest 状态机(纯函数,供 selftest):状态文案 + 是否需继续轮询。
export function ingestLabel(status) {
  return { running: '入库中…', done: '入库完成', failed: '入库失败', idle: '未入库', timeout: '入库超时' }[status] || '';
}
export function isIngestPolling(status) {
  return status === 'running';
}

// ---- 统一 http(带 user_ctx 透传;错误带 status+code)----
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

const enc = encodeURIComponent;
export const listKbDocs = (kb) => http('GET', '/admin/kb/' + enc(kb) + '/docs');
export const ingestKb = (kb) => http('POST', '/admin/kb/' + enc(kb) + '/ingest');
export const ingestStatus = (kb) => http('GET', '/admin/kb/' + enc(kb) + '/ingest/status');
export function uploadKbDoc(kb, file) {
  const fd = new FormData();
  fd.append('file', file);
  return http('POST', '/admin/kb/' + enc(kb) + '/upload', { formData: fd });
}
// 下载需带鉴权头 → fetch 成 blob 后触发浏览器下载(不能用裸 <a href>,否则丢 X-User-Ctx)。
export async function downloadKbDoc(kb, name) {
  const headers = {};
  const ctx = getUserCtx();
  if (ctx) headers['X-User-Ctx'] = JSON.stringify(ctx);
  const url = '/admin/kb/' + enc(kb) + '/docs/' + enc(name) + '/download';
  const res = await fetch(url, { method: 'GET', headers });
  if (!res.ok) { const err = new Error('HTTP ' + res.status); err.status = res.status; throw err; }
  const blob = await res.blob();
  const objUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objUrl; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(objUrl), 1000);
}

export function kbErr(e) {
  if (!e) return '操作失败';
  if (e.status === 401) return '未登录或缺少身份信息';
  if (e.status === 403) return '无权操作(仅内部管理员)';
  if (e.status === 404 && e.code === 'INVALID_KB') return '未知知识库';
  if (e.status === 404) return '知识库管理后端待部署';
  if (e.status === 409) return '该知识库正在入库,请稍候';
  if (e.status === 413) return '文件超过上限';
  return (e.data && e.data.message) || e.message || '操作失败';
}

/** 创建知识库管理相关的 Alpine 状态与方法(由 app.js 合入根组件)。 */
export function createKb() {
  return {
    kbOpen: false,
    kbTab: 'business',
    kbDocs: [],
    kbLoading: false,
    kbError: '',
    kbBusy: false,
    kbBusyHint: '',
    kbUploadError: '',
    kbIngest: { status: 'idle' }, // 当前页签的最近 ingest 状态
    _kbPollTimer: null,

    kbAdmin() { const ctx = getUserCtx(); return ctx ? canManageKb(ctx.roles) : false; },
    kbInternal() { const ctx = getUserCtx(); return ctx ? isKbInternal(ctx.roles) : false; },
    /** 当前角色可见的页签(IT 页签仅内部角色)。 */
    kbTabs() { return KB_TABS.filter((t) => !t.internalOnly || this.kbInternal()); },

    openKb() {
      if (!this.kbAdmin()) return; // 双保险:非授权不进面板
      this.kbOpen = true;
      this.kbTab = 'business';
      this.kbError = ''; this.kbUploadError = '';
      this.refreshKbDocs('business');
      if (typeof window !== 'undefined' && window.innerWidth < 1024) this.sidebarOpen = false;
    },
    closeKb() { this.kbOpen = false; this._stopKbPoll(); },

    switchKbTab(tab) {
      // it_design 页签仅内部角色(双保险:即便误点也不切换)。
      if (tab === 'it_design' && !this.kbInternal()) return;
      this.kbTab = tab;
      this.kbUploadError = ''; this.kbError = '';
      this.refreshKbDocs(tab);
    },

    async refreshKbDocs(kb) {
      kb = kb || this.kbTab;
      this.kbLoading = true; this.kbError = '';
      try {
        this.kbDocs = await listKbDocs(kb);
        // 拉一次 ingest 状态(可能上次入库仍在跑)。
        try { this.kbIngest = await ingestStatus(kb); if (isIngestPolling(this.kbIngest.status)) this._scheduleKbPoll(kb); }
        catch (e) { this.kbIngest = { status: 'idle' }; }
      } catch (e) { this.kbError = kbErr(e); this.kbDocs = []; }
      finally { this.kbLoading = false; }
    },

    pickKbFile(e) { const f = e.target.files && e.target.files[0]; e.target.value = ''; if (f) this.submitKbUpload(f); },
    async submitKbUpload(file) {
      const vn = validateKbName(file && file.name); if (!vn.ok) { this.kbUploadError = vn.reason; return; }
      const vf = validateKbFile(file); if (!vf.ok) { this.kbUploadError = vf.reason; return; }
      this.kbUploadError = ''; this.kbBusy = true; this.kbBusyHint = '正在上传…';
      const kb = this.kbTab;
      try {
        await uploadKbDoc(kb, file);
        await this.refreshKbDocs(kb);
        await this.triggerIngest(kb); // 上传成功自动入库
      } catch (e) { this.kbUploadError = kbErr(e); }
      finally { this.kbBusy = false; this.kbBusyHint = ''; }
    },

    async triggerIngest(kb) {
      kb = kb || this.kbTab;
      this.kbError = '';
      try {
        this.kbIngest = await ingestKb(kb); // {task_id,status:'running'}
        this._scheduleKbPoll(kb);
      } catch (e) { this.kbError = kbErr(e); }
    },

    _scheduleKbPoll(kb) {
      this._stopKbPoll();
      this._kbPollTimer = setTimeout(() => this._pollKbIngest(kb), 1500);
    },
    _stopKbPoll() { if (this._kbPollTimer) { clearTimeout(this._kbPollTimer); this._kbPollTimer = null; } },
    async _pollKbIngest(kb) {
      if (kb !== this.kbTab || !this.kbOpen) { this._stopKbPoll(); return; } // 已切走/已关闭则停
      try {
        this.kbIngest = await ingestStatus(kb);
        if (isIngestPolling(this.kbIngest.status)) { this._scheduleKbPoll(kb); }
        else { this._stopKbPoll(); await this.refreshKbDocs(kb); } // done/failed:刷新列表(indexed 翻新)
      } catch (e) { this._stopKbPoll(); }
    },

    async downloadKbFile(name) {
      try { await downloadKbDoc(this.kbTab, name); }
      catch (e) { this.kbError = kbErr(e); }
    },

    kbFileExtHint() { return KB_FILE_EXTS.join(' / '); },
    kbFmtSize(n) { if (!n && n !== 0) return ''; if (n < 1024) return n + 'B'; if (n < 1048576) return (n / 1024).toFixed(1) + 'KB'; return (n / 1048576).toFixed(1) + 'MB'; },
    kbIngestLabel() { return ingestLabel(this.kbIngest && this.kbIngest.status); },
  };
}
