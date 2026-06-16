// sse.js — /chat SSE 主循环。事实来源:docs/dev/sse-protocol.md。
// postChatStream:fetch + ReadableStream 解析 text/event-stream,按事件名分发 onEvent;支持 AbortController。
// confirm_request / ask_user 后本段流结束(无 done),用响应头 X-Session-Id + POST /chat/confirm 续传。

let _userCtx = null;
/** 开发态注入 X-User-Ctx(§12-D4;生产同源走 cookie/session,前端不自造权限)。 */
export function setUserCtx(ctx) { _userCtx = ctx; }
export function getUserCtx() { return _userCtx; }

export class HttpError extends Error {
  constructor(status, message) {
    super(message || ('HTTP ' + status));
    this.name = 'HttpError';
    this.status = status;
  }
}

/** 初始发送体(契约:{message, page_context?};attachments 为 W3 真正启用)。 */
export function buildChatBody(message, attachments, pageContext) {
  const body = { message };
  if (attachments && attachments.length) body.attachments = attachments;
  if (pageContext) body.page_context = pageContext;
  return body;
}
/** confirm 恢复体(契约:confirmation.confirmed 布尔)。 */
export function buildConfirmBody(sessionId, confirmed) {
  return { session_id: sessionId, confirmation: { confirmed: !!confirmed } };
}
/** ask_user 恢复体(契约:answers 对象;键名未在协议定义,前端按 questionIndex 键,标注假定)。 */
export function buildAskBody(sessionId, answers) {
  return { session_id: sessionId, answers: answers || {} };
}

/** 解析单个 SSE 帧 → {event,data};纯函数。 */
export function parseFrame(frame) {
  const t = (frame || '').trim();
  if (!t) return null;
  let event = 'message';
  const dataLines = [];
  for (const line of t.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
  }
  let data = dataLines.join('\n');
  try { data = JSON.parse(data); } catch (e) { /* 非 JSON 保留原文 */ }
  return { event, data };
}

/**
 * 发送并消费一段 SSE 流,按事件分发 onEvent。
 * @param {object} payload 请求体
 * @param {{url?:string, onEvent?:(type:string,data:any)=>void, signal?:AbortSignal}} opts
 * @returns {Promise<{sessionId:string, sawDone:boolean, aborted:boolean}>}
 */
export async function postChatStream(payload, { url = '/chat', onEvent, signal } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (_userCtx) headers['X-User-Ctx'] = JSON.stringify(_userCtx); // 缺则不带 → 真实后端按 401 处理(§12-D4)

  let res;
  try {
    res = await fetch(url, { method: 'POST', headers, body: JSON.stringify(payload), signal });
  } catch (e) {
    if (e && e.name === 'AbortError') return { sessionId: '', sawDone: false, aborted: true };
    throw e; // 网络错误 → 调用方映射 ErrorBanner
  }
  if (!res.ok) throw new HttpError(res.status); // 401/403/404/5xx;不暴露内部细节

  const sessionId = res.headers.get('X-Session-Id') || '';
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let sawDone = false;

  const emit = (frame) => {
    const ev = parseFrame(frame);
    if (!ev) return;
    if (ev.event === 'done') sawDone = true;
    if (onEvent) onEvent(ev.event, ev.data);
  };

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf('\n\n')) !== -1) {
        emit(buf.slice(0, nl));
        buf = buf.slice(nl + 2);
      }
    }
    emit(buf); // 末尾残帧
  } catch (e) {
    if (e && e.name === 'AbortError') return { sessionId, sawDone, aborted: true };
    throw e;
  }
  return { sessionId, sawDone, aborted: false };
}
