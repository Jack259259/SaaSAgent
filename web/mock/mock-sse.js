// mock-sse.js — 开发期本地 mock(无构建链下的验证手段)。
// 包裹 window.fetch:拦截 POST /chat 返回预设 SSE 序列;非 /chat 一律透传原 fetch。
// 帧格式事实来源:docs/dev/sse-protocol.md。W2 扩展多场景;W3 关闭(localStorage fp_mock='0')后相对路径直连真实后端。

/** 是否启用 mock:?mock=1 / localStorage fp_mock='1' 强开;'0' 强关;默认在 localhost / file 下开启。 */
export function isMockEnabled() {
  try {
    const u = new URL(location.href);
    if (u.searchParams.get('mock') === '1') return true;
    const flag = localStorage.getItem('fp_mock');
    if (flag === '1') return true;
    if (flag === '0') return false;
  } catch (e) { /* file:// / 无 localStorage 等场景,落到 host 判断 */ }
  const h = (typeof location !== 'undefined' && location.hostname) || '';
  return h === 'localhost' || h === '127.0.0.1' || h === '';
}

// W0 预设场景:answer_delta×3 + done(W2 按场景扩展 plan/step/tool_call/tool_result_summary 等)。
const SCENARIOS = {
  simple: [
    { event: 'answer_delta', data: { text: '你好,' } },
    { event: 'answer_delta', data: { text: '我是资金计划助手,' } },
    { event: 'answer_delta', data: { text: '这是一条 mock 回复。' } },
    { event: 'done', data: { stop_reason: 'end_turn', used_steps: 0 } },
  ],
};

/** 把事件列表编码为 text/event-stream 帧文本(对齐 sse-protocol.md:event/data 单行 JSON + 空行)。 */
function encodeSSE(events) {
  return events.map((e) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`).join('');
}

/** 解析 SSE 帧文本为 [{event,data}]。纯函数,供 sse.js(W2)与 selftest 复用。 */
export function parseSSE(text) {
  const out = [];
  for (const frame of String(text).split('\n\n')) {
    const trimmed = frame.trim();
    if (!trimmed) continue;
    let ev = 'message';
    const dataLines = [];
    for (const line of trimmed.split('\n')) {
      if (line.startsWith('event:')) ev = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
    }
    let data = dataLines.join('\n');
    try { data = JSON.parse(data); } catch (e) { /* 非 JSON 时保留原文 */ }
    out.push({ event: ev, data });
  }
  return out;
}

/** 构造一个 mock 的 text/event-stream Response(逐帧延迟推送,模拟流式)。 */
function makeStreamResponse(events, { delayMs = 60 } = {}) {
  const enc = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      for (const e of events) {
        controller.enqueue(enc.encode(encodeSSE([e])));
        if (delayMs) await new Promise((r) => setTimeout(r, delayMs));
      }
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream', 'X-Session-Id': 'mock-session' },
  });
}

let installed = false;

/**
 * 安装 mock:包裹 window.fetch。仅当 isMockEnabled() 为真时生效;幂等。
 * @returns {boolean} 是否已安装
 */
export function installMockSSE() {
  if (installed) return true;
  if (typeof window === 'undefined' || !isMockEnabled()) return false;

  const original = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const method = (init.method || (input && input.method) || 'GET').toUpperCase();
    let path = url;
    try { path = new URL(url, location.href).pathname; } catch (e) { /* 保留原 url 作 path */ }

    if (method === 'POST' && path === '/chat') {
      // W2 可按 init.body 的 scenario 字段选择不同序列;W0 固定 simple。
      return makeStreamResponse(SCENARIOS.simple);
    }
    return original(input, init);
  };

  installed = true;
  if (typeof console !== 'undefined') console.info('[mock-sse] installed — POST /chat intercepted');
  return true;
}
