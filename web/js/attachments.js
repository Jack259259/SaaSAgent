// attachments.js — 文件上传子系统(§8)。前端只校验/上传/展示;业务文档解析在后端 parse_user_file(红线:前端不解析)。
// 上传走 fetch('/files')(mock 模式被 mock-sse 拦截;真实模式后端暂无 /files → 404,卡片友好提示,D2 待补)。
import { getUserCtx } from './sse.js';

export const ATTACH_LIMITS = { maxBytes: 20 * 1024 * 1024, maxCount: 10 }; // 默认 20MB / 10 个,可配

// 扩展名 → 允许 MIME(双白名单;浏览器给空 MIME 时回退到扩展名)。覆盖设计 §8.1 全部格式。
export const WHITELIST = {
  docx: ['application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
  odt: ['application/vnd.oasis.opendocument.text'],
  rtf: ['application/rtf', 'text/rtf'],
  epub: ['application/epub+zip'],
  html: ['text/html'], htm: ['text/html'],
  md: ['text/markdown', 'text/x-markdown'], markdown: ['text/markdown', 'text/x-markdown'],
  txt: ['text/plain'],
  xlsx: ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
  csv: ['text/csv', 'application/vnd.ms-excel'],
  json: ['application/json'],
  jpeg: ['image/jpeg'], jpg: ['image/jpeg'], png: ['image/png'], gif: ['image/gif'],
};

export function fileExt(name) {
  const m = /\.([^.]+)$/.exec(name || '');
  return m ? m[1].toLowerCase() : '';
}
export function humanSize(n) {
  if (n == null) return '';
  const u = ['B', 'KB', 'MB', 'GB']; let i = 0; let x = n;
  while (x >= 1024 && i < u.length - 1) { x /= 1024; i++; }
  return (i === 0 ? x : x.toFixed(1)) + u[i];
}
export function isImageExt(ext) { return /^(jpe?g|png|gif)$/i.test(ext); }

/** 双白名单 + 大小 + 去重校验。纯函数,供 selftest 复用。 */
export function validateFile(file, existing = []) {
  const ext = fileExt(file.name);
  if (!WHITELIST[ext]) return { ok: false, reason: '不支持的类型(.' + (ext || '?') + ')' };
  if (file.type && !WHITELIST[ext].includes(file.type)) return { ok: false, reason: 'MIME 与扩展名不符' };
  if (file.size > ATTACH_LIMITS.maxBytes) return { ok: false, reason: '超过 ' + Math.round(ATTACH_LIMITS.maxBytes / 1024 / 1024) + 'MB 上限' };
  if (existing.some((a) => a.name === file.name && a.size === file.size)) return { ok: false, reason: '重复文件' };
  return { ok: true };
}

/** 上传到 POST /files(multipart)→ { file_id, filename, mime, size, status, parse_supported }。 */
export function uploadFile(file, { signal } = {}) {
  const fd = new FormData();
  fd.append('file', file);
  const headers = {};
  const ctx = getUserCtx();
  if (ctx) headers['X-User-Ctx'] = JSON.stringify(ctx);
  return fetch('/files', { method: 'POST', body: fd, headers, signal }).then(async (res) => {
    if (!res.ok) throw new Error(res.status === 404 ? '后端 /files 待实现(D2)' : ('上传失败(' + res.status + ')'));
    return res.json();
  });
}

// 原始 File 与 AbortController 存于响应式状态「外」—— Alpine 用 Proxy 包裹会破坏 FormData.append /
// AbortController.abort(内部槽 brand 检查拒绝 Proxy)。响应式 att 只存可序列化原始值(也利于持久化)。
const _fileStore = new Map(); // localId -> File
const _abortStore = new Map(); // localId -> AbortController

/** 创建附件相关的 Alpine 状态与方法(由 app.js 合入根组件)。 */
export function createAttachments() {
  return {
    attachments: [],
    dragover: false,
    _attSeq: 0,
    humanSize,

    onDragOver(e) { if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files')) { e.preventDefault(); this.dragover = true; } },
    onDragLeave() { this.dragover = false; },
    onDrop(e) { e.preventDefault(); this.dragover = false; if (e.dataTransfer) this.addFiles(e.dataTransfer.files); },
    pickFiles(e) { this.addFiles(e.target.files); e.target.value = ''; },

    addFiles(fileList) {
      for (const file of Array.from(fileList || [])) {
        if (this.attachments.length >= ATTACH_LIMITS.maxCount) break;
        const v = validateFile(file, this.attachments);
        const ext = fileExt(file.name);
        const att = {
          localId: 'a' + (++this._attSeq), name: file.name, size: file.size, mime: file.type, ext,
          status: v.ok ? 'queued' : 'error', progress: 0, file_id: '', parse_supported: null,
          error: v.ok ? '' : v.reason, thumbUrl: '',
        };
        if (v.ok && isImageExt(ext)) { try { att.thumbUrl = URL.createObjectURL(file); } catch (e) { /* ignore */ } }
        _fileStore.set(att.localId, file); // File 不进响应式状态
        this.attachments.push(att);
        if (v.ok) this._upload(this.attachments[this.attachments.length - 1]); // 取响应式引用
      }
    },

    _upload(att) {
      att.status = 'uploading'; att.progress = 8; att.error = '';
      const ctrl = new AbortController();
      _abortStore.set(att.localId, ctrl);
      const tick = setInterval(() => { if (att.progress < 90) att.progress += Math.random() * 22; }, 90); // mock 即时;进度为视觉反馈
      uploadFile(_fileStore.get(att.localId), { signal: ctrl.signal })
        .then((res) => { clearInterval(tick); att.progress = 100; att.status = 'uploaded'; att.file_id = res.file_id || ''; att.parse_supported = res.parse_supported; })
        .catch((err) => { clearInterval(tick); if (err && err.name === 'AbortError') return; att.status = 'error'; att.error = (err && err.message) || '上传失败'; });
    },
    retryAttachment(localId) {
      const a = this.attachments.find((x) => x.localId === localId);
      if (a && _fileStore.has(localId)) this._upload(a);
    },
    removeAttachment(localId) {
      const i = this.attachments.findIndex((x) => x.localId === localId);
      if (i < 0) return;
      const a = this.attachments[i];
      if (a.thumbUrl) { try { URL.revokeObjectURL(a.thumbUrl); } catch (e) { /* ignore */ } }
      if (a.status === 'uploading' && _abortStore.has(localId)) { try { _abortStore.get(localId).abort(); } catch (e) { /* ignore */ } }
      _fileStore.delete(localId); _abortStore.delete(localId);
      this.attachments.splice(i, 1);
    },
    clearAttachments() {
      this.attachments.forEach((a) => {
        if (a.thumbUrl) { try { URL.revokeObjectURL(a.thumbUrl); } catch (e) { /* ignore */ } }
        _fileStore.delete(a.localId); _abortStore.delete(a.localId);
      });
      this.attachments = [];
    },
    pendingFileIds() { return this.attachments.filter((a) => a.status === 'uploaded' && a.file_id).map((a) => a.file_id); },
    attachmentsSnapshot() {
      // 不带 thumbUrl:blob: URL 在 clearAttachments 后会被 revoke(消息内引用会失效);
      // 已发送/持久化的消息内图片统一显示图标(与刷新恢复后的行为一致)。
      return this.attachments.map((a) => ({ file_id: a.file_id, name: a.name, size: a.size, mime: a.mime, ext: a.ext, status: a.status, parse_supported: a.parse_supported }));
    },
    hasPendingUploads() { return this.attachments.some((a) => a.status === 'uploading' || a.status === 'queued'); },
  };
}
