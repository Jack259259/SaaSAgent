// store.js — 会话历史 Repository(§12-D1:localStorage;预留后端会话 API 接缝)。
// UI 只经此读写,不直接碰存储。持久化前脱敏:不存 File/objectURL/瞬时句柄,只存渲染所需的 blocks 与附件元信息。

const IDX_KEY = 'fp_conv_index';
const msgsKey = (id) => 'fp_conv_' + id;

function readJSON(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key) || ''); } catch (e) { return fallback; }
}
function writeJSON(key, val) {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) { /* 配额/隐私模式:忽略 */ }
}

function sanitizeAttachment(a) {
  return { file_id: a.file_id, name: a.name, size: a.size, mime: a.mime, ext: a.ext, status: a.status, parse_supported: a.parse_supported };
}
function sanitizeMessage(m) {
  const out = { id: m.id, role: m.role, created_at: m.created_at || Date.now() };
  if (m.role === 'user') {
    out.raw = m.raw;
    out.attachments = (m.attachments || []).map(sanitizeAttachment); // 不含 thumbUrl/_file
  } else {
    out.blocks = JSON.parse(JSON.stringify(m.blocks || [])); // 纯数据;丢弃函数/瞬时
    out.streaming = false;
    if (m.vote === 'up' || m.vote === 'down') out.vote = m.vote; // 点赞点踩持久化(刷新不丢)
    if (m.feedbackComment) out.feedbackComment = String(m.feedbackComment).slice(0, 500);
    // showComment 为瞬时 UI 态,不持久化
  }
  return out;
}

/**
 * 创建会话历史仓储(localStorage 实现)。
 * @returns Repository
 */
export function createConversationStore() {
  function readIndex() { const v = readJSON(IDX_KEY, []); return Array.isArray(v) ? v : []; }
  function writeIndex(arr) { writeJSON(IDX_KEY, arr); }
  function touch(id) { const idx = readIndex(); const c = idx.find((x) => x.id === id); if (c) { c.updated_at = Date.now(); writeIndex(idx); } }

  return {
    /** 列出会话元信息(按更新时间倒序)。 */
    listConversations() {
      return readIndex().slice().sort((a, b) => b.updated_at - a.updated_at);
    },
    /** 取单个会话(含 messages);不存在返回 null。 */
    getConversation(id) {
      const meta = readIndex().find((c) => c.id === id);
      if (!meta) return null;
      const messages = readJSON(msgsKey(id), []);
      return { ...meta, messages: Array.isArray(messages) ? messages : [] };
    },
    /** 新建空会话并返回其元信息。 */
    createConversation(title) {
      const now = Date.now();
      const c = { id: 'c-' + now + '-' + Math.floor(Math.random() * 1e4), title: title || '新对话', created_at: now, updated_at: now };
      const idx = readIndex(); idx.push(c); writeIndex(idx);
      writeJSON(msgsKey(c.id), []);
      return c;
    },
    /** 覆盖保存一条会话的消息(脱敏后);并更新 updated_at。 */
    saveMessages(id, messages) {
      writeJSON(msgsKey(id), (messages || []).map(sanitizeMessage));
      touch(id);
    },
    /** 重命名。 */
    rename(id, title) {
      const idx = readIndex(); const c = idx.find((x) => x.id === id);
      if (c) { c.title = title; c.updated_at = Date.now(); writeIndex(idx); }
    },
    /** 删除单个会话。 */
    remove(id) {
      writeIndex(readIndex().filter((c) => c.id !== id));
      try { localStorage.removeItem(msgsKey(id)); } catch (e) { /* ignore */ }
    },
    /** 清除全部本地历史(D1 衍生:退出时一键清空)。 */
    clearAll() {
      readIndex().forEach((c) => { try { localStorage.removeItem(msgsKey(c.id)); } catch (e) { /* ignore */ } });
      try { localStorage.removeItem(IDX_KEY); } catch (e) { /* ignore */ }
    },
  };
}

/** 把会话按时间分组(今天 / 7天内 / 更早),用于 Sidebar 渲染。纯函数,供 selftest 复用。 */
export function groupByTime(conversations, now = Date.now()) {
  const day = 24 * 3600 * 1000;
  const groups = { today: [], week: [], older: [] };
  for (const c of conversations) {
    const age = now - (c.updated_at || 0);
    if (age < day) groups.today.push(c);
    else if (age < 7 * day) groups.week.push(c);
    else groups.older.push(c);
  }
  return groups;
}
