// mock-sse.js — 开发期本地 mock(无构建链下的验证手段)。
// 包裹 window.fetch:拦截 POST /chat 与 POST /chat/confirm,按场景返回预设 SSE 序列;非这两者一律透传。
// 帧格式事实来源:docs/dev/sse-protocol.md。confirm_request/ask_user 后本段结束(无 done),用 X-Session-Id 续传。
// W3 关闭(localStorage fp_mock='0')后相对路径直连真实后端,前端零改动。

/** 是否启用 mock:?mock=1 / localStorage fp_mock='1' 强开;'0' 强关;默认在 localhost / file 下开启。 */
export function isMockEnabled() {
  try {
    const u = new URL(location.href);
    if (u.searchParams.get('mock') === '1') return true;
    const flag = localStorage.getItem('fp_mock');
    if (flag === '1') return true;
    if (flag === '0') return false;
  } catch (e) { /* file:// / 无 localStorage,落到 host 判断 */ }
  const h = (typeof location !== 'undefined' && location.hostname) || '';
  return h === 'localhost' || h === '127.0.0.1' || h === '';
}

// ---- 事件工厂 ----
const ev = (event, data, delay) => ({ event, data, delay });
const ad = (text, delay) => ev('answer_delta', { text }, delay);

const LONG_TEXT = '资金计划是企业对未来一定期间内资金收支的预测与安排,需结合经营计划、投融资安排与到期债务,'
  + '逐月滚动测算资金缺口与盈余,并据此安排筹融资与资金调度;口径上区分经营性、投资性与筹资性现金流,'
  + '并对大额收支单独标注与复核,确保资金安全与流动性。在执行层面,还应建立滚动预测与偏差分析机制,'
  + '对实际收支与计划的差异按科目归因,定期复盘并调整后续月度的资金摆布,必要时提前安排授信额度与短期融资,'
  + '同时关注集团内部资金归集与调拨的合规性,确保在满足流动性的前提下尽量降低资金成本。';
const TABLE = '| 科目 | 金额(万元) |\n| --- | --- |\n| 经营性净流入 | 1200 |\n| 投资性净流出 | -300 |\n| 筹资性净流入 | 500 |';

// ---- 场景:每个场景是「分段数组」,段边界 = 暂停点(confirm/ask)----
const SCENARIOS = {
  simple: [
    [ad('你好,'), ad('我是资金计划助手,'), ad('这是一条 mock 回复。'), ev('done', { stop_reason: 'end_turn', used_steps: 0 })],
  ],

  complex: [
    [
      ev('plan', { version: 1, steps: [
        { id: 's1', goal: '解析问题与口径', needs_confirmation: false, status: 'pending' },
        { id: 's2', goal: '核对资金数据与知识', needs_confirmation: false, status: 'pending' },
        { id: 's3', goal: '生成结论(需复核确认)', needs_confirmation: true, status: 'pending' },
      ] }),
      ev('step', { index: 0, note: '解析问题与口径' }),
      ev('tool_call', { id: 'c1', tool: 'query_finance_data', arguments: { period: '2026-06' } }),
      ev('tool_result_summary', { id: 'c1', tool: 'query_finance_data', summary: '查询资金数据 ✓ 返回 3 行:6月计划流入 1200、流出 900、净额 300。', workspace_ref: 'ws://query/1' }),
      ev('step', { index: 1, note: '核对知识库口径' }),
      ev('tool_call', { id: 'c2', tool: 'search_knowledge', arguments: { q: '资金计划 复核 口径' } }),
      ev('tool_result_summary', { id: 'c2', tool: 'search_knowledge', summary: LONG_TEXT, workspace_ref: 'ws://kb/2' }),
      ev('step', { index: 2, note: '待确认:标记已复核' }),
      ev('confirm_request', { id: 'cf1', prompt: '将把「2026年6月资金计划」标记为“已复核”,该操作会写回业务系统。是否继续?', options: ['确认', '取消'] }),
    ],
    [
      ev('step', { index: 2, note: '生成结论' }),
      ad('已为你核对 6 月资金计划:'), ad('净流入约 300 万元,口径与制度一致。'),
      ev('citation', { items: [{ title: '资金计划管理制度 v3', source: '知识库', ref: '#/doc/123' }] }),
      ev('done', { stop_reason: 'completed', used_steps: 3 }),
    ],
  ],

  parallel: [
    [
      ev('plan', { version: 1, steps: [
        { id: 'p-a', goal: '并行取数', status: 'pending' },
        { id: 'p-b', goal: '汇总作答', status: 'pending' },
      ] }),
      ev('step', { index: 0, note: '并行调用取数与检索' }),
      ev('tool_call', { id: 'p1', tool: 'query_finance_data', arguments: { period: '2026-06' } }),
      ev('tool_call', { id: 'p2', tool: 'search_knowledge', arguments: { q: '现金流 分类' } }),
      ev('tool_result_summary', { id: 'p1', tool: 'query_finance_data', summary: '返回 3 行。', workspace_ref: 'ws://q/3' }),
      ev('tool_result_summary', { id: 'p2', tool: 'search_knowledge', summary: TABLE, workspace_ref: 'ws://kb/4' }),
      ev('step', { index: 1, note: '汇总作答' }),
      ad('已并行完成取数与检索,详见上方时间线。'),
      ev('done', { stop_reason: 'completed', used_steps: 2 }),
    ],
  ],

  replan: [
    [
      ev('plan', { version: 1, steps: [
        { id: 'r1', goal: '直接作答', status: 'pending' },
        { id: 'r2', goal: '收尾', status: 'pending' },
      ] }),
      ev('step', { index: 0, note: '发现需要补取数,准备重规划' }),
      ev('plan', { version: 2, steps: [
        { id: 'r1', goal: '取数', status: 'pending' },
        { id: 'r2', goal: '核对', status: 'pending' },
        { id: 'r3', goal: '作答', status: 'pending' },
      ] }),
      ev('step', { index: 0, note: '取数' }),
      ev('tool_call', { id: 'rc1', tool: 'query_finance_data', arguments: {} }),
      ev('tool_result_summary', { id: 'rc1', tool: 'query_finance_data', summary: '返回 5 行。', workspace_ref: 'ws://q/5' }),
      ev('step', { index: 1, note: '核对' }),
      ev('step', { index: 2, note: '作答' }),
      ad('已按重规划后的 3 步完成。'),
      ev('done', { stop_reason: 'completed', used_steps: 3 }),
    ],
  ],

  error: [
    [
      ev('step', { index: 0, note: '尝试取数' }),
      ev('tool_call', { id: 'e1', tool: 'query_finance_data', arguments: {} }),
      ev('error', { code: 'TOOL_TIMEOUT', message: '查询超时,请稍后重试。' }),
    ],
  ],

  longdelay: [
    [ad('正在思考', 400), ad('… 这是一段较慢的流', 700), ad('… 你可以点停止', 900), ev('done', { stop_reason: 'end_turn', used_steps: 0 }, 500)],
  ],

  ask: [
    [
      ev('ask_user', { id: 'a1', questions: [{ question: '你指的是哪个口径?', options: ['现金流量表', '资金计划表'] }] }),
    ],
    [
      ad('按「资金计划表」口径,'), ad('6 月净流入约 300 万元。'),
      ev('done', { stop_reason: 'completed', used_steps: 0 }),
    ],
  ],
};

/** 按 message 关键词选场景(开发自测用)。 */
export function pickScenario(message) {
  const m = String(message || '');
  if (/并行|parallel/i.test(m)) return 'parallel';
  if (/replan|重规划/i.test(m)) return 'replan';
  if (/错误|报错|error|失败/i.test(m)) return 'error';
  if (/延迟|停止|慢/i.test(m)) return 'longdelay';
  if (/澄清|哪个|问我/i.test(m)) return 'ask';
  if (/复杂|确认|复核/i.test(m)) return 'complex';
  return 'simple';
}

/** 把事件列表编码为 text/event-stream 帧文本(对齐 sse-protocol.md)。 */
function encodeFrame(e) { return `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`; }

/** 解析 SSE 帧文本为 [{event,data}]。纯函数,供 selftest 复用。 */
export function parseSSE(text) {
  const out = [];
  for (const frame of String(text).split('\n\n')) {
    const trimmed = frame.trim();
    if (!trimmed) continue;
    let evName = 'message';
    const dataLines = [];
    for (const line of trimmed.split('\n')) {
      if (line.startsWith('event:')) evName = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
    }
    let data = dataLines.join('\n');
    try { data = JSON.parse(data); } catch (e) { /* 保留原文 */ }
    out.push({ event: evName, data });
  }
  return out;
}

const DEFAULT_DELAY = 22;
const sessions = new Map(); // sid -> { scenario, segIndex }

function streamResponse(events, sid, signal) {
  const stream = new ReadableStream({
    start(controller) {
      const enc = new TextEncoder();
      let aborted = false;
      const onAbort = () => { aborted = true; try { controller.error(new DOMException('Aborted', 'AbortError')); } catch (e) { /* 已关闭 */ } };
      if (signal) {
        if (signal.aborted) { onAbort(); return; }
        signal.addEventListener('abort', onAbort);
      }
      (async () => {
        for (const e of events) {
          if (aborted) return;
          try { controller.enqueue(enc.encode(encodeFrame(e))); } catch (err) { return; }
          await new Promise((r) => setTimeout(r, e.delay != null ? e.delay : DEFAULT_DELAY));
        }
        if (!aborted) { try { controller.close(); } catch (e) { /* noop */ } }
        if (signal) signal.removeEventListener('abort', onAbort);
      })();
    },
  });
  return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream', 'X-Session-Id': sid } });
}

function handleChat(body, signal) {
  const name = pickScenario(body && body.message);
  const scenario = SCENARIOS[name] || SCENARIOS.simple;
  const sid = 'mock-' + Date.now() + '-' + Math.floor(Math.random() * 1e4);
  if (scenario.length > 1) sessions.set(sid, { scenario: name, segIndex: 1 });
  return streamResponse(scenario[0], sid, signal);
}

function handleConfirm(body, signal) {
  const sid = body && body.session_id;
  const st = sid && sessions.get(sid);
  if (!st) return streamResponse([ev('error', { code: 'NOT_FOUND', message: '会话不存在或已过期。' })], sid || 'mock-unknown', signal);
  const scenario = SCENARIOS[st.scenario];
  const seg = scenario[st.segIndex] || [ev('done', { stop_reason: 'end_turn', used_steps: 0 })];
  if (st.segIndex + 1 < scenario.length) sessions.set(sid, { ...st, segIndex: st.segIndex + 1 });
  else sessions.delete(sid);
  return streamResponse(seg, sid, signal);
}

let installed = false;

/** 安装 mock:包裹 window.fetch。仅当 isMockEnabled() 为真时生效;幂等。 */
export function installMockSSE() {
  if (installed) return true;
  if (typeof window === 'undefined' || !isMockEnabled()) return false;

  const original = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const method = (init.method || (input && input.method) || 'GET').toUpperCase();
    let path = url;
    try { path = new URL(url, location.href).pathname; } catch (e) { /* 保留原 url */ }

    if (method === 'POST' && (path === '/chat' || path === '/chat/confirm')) {
      let body = {};
      try { body = JSON.parse(init.body || '{}'); } catch (e) { body = {}; }
      const signal = init.signal || (input && input.signal);
      return path === '/chat' ? handleChat(body, signal) : handleConfirm(body, signal);
    }
    return original(input, init);
  };

  installed = true;
  if (typeof console !== 'undefined') console.info('[mock-sse] installed — POST /chat & /chat/confirm intercepted');
  return true;
}
