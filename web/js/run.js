// run.js — 顶部任务进展区 + 工具调用时间线的「纯前端状态投影」(currentRun)。
// 把 plan / step / tool_call / tool_result_summary 投影到 currentRun;不做业务判断、不发网络请求。
// 契约缺口(记入 docs/integration/backend-gaps.md,W3 汇总):
//  · step{index,note} 无每步状态枚举 → 按到达顺序投影(index 进行中、前置完成),note=焦点;
//  · tool_result_summary 无成功/失败与内容类型 → 收到即 ✓,失败经 error 事件转 ✗;折叠分档按 summary 启发式。

// 折叠分档阈值(集中可配)
export const FOLD = { MAX_INLINE_LINES: 3, MAX_INLINE_CHARS: 200, CONTAINER_MAX_H: 280 };

// 工具名 → 友好文案(无映射回退原名)
const TOOL_NAMES = {
  query_finance_data: '查询资金数据',
  search_knowledge: '检索知识库',
  ask_codebase: '分析代码',
  find_sop: '查找页面操作',
  run_sop: '执行页面操作',
  run_analysis: '运行分析',
  read_workspace: '读取工作区',
  write_workspace: '写入工作区',
};
export function toolDisplayName(tool) {
  return TOOL_NAMES[tool] || tool || '工具';
}

/** 结果折叠分档:inline(短)/ long(长文本)/ structured(表格/代码/JSON/长列表)。 */
export function classifyResult(summary, workspaceRef) {
  const text = typeof summary === 'string' ? summary : '';
  const lines = text ? text.split('\n').length : 0;
  const chars = text.length;
  const structured = /```/.test(text)                               // 代码围栏
    || /(^|\n)\s*[[{]/.test(text)                                   // JSON 形状
    || /\|.*\|/.test(text)                                          // 表格
    || /(^|\n)\s*[-*]\s+.*(\n\s*[-*]\s+.*){4,}/.test(text);         // 长列表(>4 项)
  if (structured) return { tier: 'structured', lines, chars };
  if (lines > FOLD.MAX_INLINE_LINES || chars > FOLD.MAX_INLINE_CHARS) return { tier: 'long', lines, chars };
  return { tier: 'inline', lines, chars };
}

function summarizeArgs(args) {
  if (!args || typeof args !== 'object') return '';
  try {
    const s = JSON.stringify(args);
    return s.length > 80 ? s.slice(0, 80) + '…' : s;
  } catch (e) { return ''; }
}

/** 新建一轮进展投影。 */
export function newRun() {
  return { plan: null, toolTimeline: [], focus: '', collapsed: false };
}

/** plan 事件:首版设置;replan(version 更高)原地替换 steps。 */
export function applyPlan(run, data) {
  if (!run) return run;
  const steps = (data.steps || []).map((s) => ({
    id: s.id,
    goal: s.goal || '',
    needs_confirmation: !!s.needs_confirmation,
    status: s.status || 'pending', // pending | running | done | failed
  }));
  const version = data.version != null ? data.version : (run.plan ? run.plan.version + 1 : 1);
  run.plan = { version, steps };
  return run;
}

/** step 事件:契约为 {index,note};按到达顺序投影(index 进行中、前置完成),note=焦点。 */
export function applyStep(run, data) {
  if (!run) return run;
  const idx = data.index != null ? data.index : 0;
  run.focus = data.note || '';
  if (run.plan && run.plan.steps.length) {
    run.plan.steps.forEach((s, i) => {
      if (i < idx && s.status !== 'failed') s.status = 'done';
      else if (i === idx && s.status !== 'failed' && s.status !== 'done') s.status = 'running';
    });
  }
  return run;
}

/** tool_call 事件:新增时间线条目(进行中)。 */
export function applyToolCall(run, data) {
  if (!run) return run;
  run.toolTimeline.push({
    id: data.id,
    tool: data.tool,
    displayName: toolDisplayName(data.tool),
    argsSummary: summarizeArgs(data.arguments),
    status: 'running',
    resultSummary: '',
    workspaceRef: '',
    tier: 'inline',
    expanded: false,
  });
  return run;
}

/** tool_result_summary 事件:对应条目转完成 + 折叠分档。 */
export function applyToolResult(run, data) {
  if (!run) return run;
  const it = run.toolTimeline.find((t) => t.id === data.id);
  if (it) {
    it.status = 'done';
    it.resultSummary = data.summary || '';
    it.workspaceRef = data.workspace_ref || '';
    it.tier = classifyResult(it.resultSummary, it.workspaceRef).tier;
  }
  return run;
}

/** error 事件:把仍在运行的工具条目标记失败(契约无 tool 级失败字段)。 */
export function applyErrorToRun(run) {
  if (!run) return run;
  run.toolTimeline.forEach((t) => { if (t.status === 'running') t.status = 'failed'; });
  return run;
}

/** done:仍 running 的步骤标记完成(本轮结束)。 */
export function completeRunSteps(run) {
  if (run && run.plan) run.plan.steps.forEach((s) => { if (s.status === 'running') s.status = 'done'; });
  return run;
}

/** 折叠摘要行:"计划 N 步 · 进行到 k/N · <focus>"。 */
export function runSummaryLine(run) {
  if (!run || !run.plan) return '';
  const total = run.plan.steps.length;
  const doneN = run.plan.steps.filter((s) => s.status === 'done').length;
  const failed = run.plan.steps.some((s) => s.status === 'failed');
  const cur = Math.min(doneN + 1, total);
  const focus = run.focus ? ` · ${run.focus}` : '';
  return failed ? `计划 ${total} 步 · 已失败${focus}` : `计划 ${total} 步 · 进行到 ${cur}/${total}${focus}`;
}

/** done:把 currentRun 快照为留痕块(并入助手消息 content_blocks);调用方随后清空 currentRun。 */
export function snapshotRun(run) {
  if (!run || !run.plan) return null;
  return {
    type: 'run',
    plan: JSON.parse(JSON.stringify(run.plan)),
    toolTimeline: JSON.parse(JSON.stringify(run.toolTimeline)),
    collapsed: true,
  };
}
