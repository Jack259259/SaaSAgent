// chat.js — 发送/恢复轮次循环 + 消息(blocks)+ 富事件卡片 + currentRun 进展投影。
// W2:真实 postChatStream(对 mock-sse 多场景);confirm_request/ask_user 暂停→ /chat/confirm 续传。
import { renderMarkdown } from './markdown.js';
import {
  postChatStream, buildChatBody, buildConfirmBody, buildAskBody,
} from './sse.js';
import {
  newRun, applyPlan, applyStep, applyToolCall, applyToolResult,
  applyErrorToRun, completeRunSteps, snapshotRun, runSummaryLine, FOLD,
} from './run.js';

let _seq = 0;
const uid = (p) => `${p}-${Date.now()}-${++_seq}`;

/** 增量 append(纯函数,供 selftest 复用)。 */
export function appendToken(msg, token) {
  msg.raw += token;
  msg.streamText = msg.raw;
  return msg;
}

function friendlyError(e) {
  const s = e && e.status;
  if (s === 401) return '未登录或缺少身份信息,请重新登录。';
  if (s === 403) return '无权访问该会话或资源。';
  if (s === 404) return '会话不存在或已过期。';
  if (s >= 500) return '服务暂时不可用,请稍后重试。';
  return '网络错误,请重试。';
}

/** 创建聊天相关的 Alpine 状态与方法(由 app.js 合入根组件)。 */
export function createChat() {
  return {
    messages: [],
    draft: '',
    hasMessages: false,
    sendStatus: 'idle',     // idle | streaming | error
    currentRun: null,       // { plan, toolTimeline, focus, collapsed }
    sessionId: '',
    pendingResume: null,    // { kind:'confirm'|'ask', id } | null
    lastUserText: '',
    stuckToBottom: true,
    conversationTitle: '新对话',
    FOLD,
    _abort: null,
    _turnErrored: false,

    canSend() {
      return this.draft.trim().length > 0 && this.sendStatus !== 'streaming';
    },

    _assistant() {
      const m = this.messages[this.messages.length - 1];
      return m && m.role === 'assistant' ? m : null;
    },
    _pushUser(text) {
      this.messages.push({ id: uid('user'), role: 'user', raw: text });
    },
    _pushAssistant() {
      this.messages.push({ id: uid('asst'), role: 'assistant', blocks: [], streaming: true });
      return this._assistant();
    },

    sendMessage() {
      const text = this.draft.trim();
      if (!text || this.sendStatus === 'streaming') return;
      if (!this.hasMessages) {
        this.hasMessages = true;
        this.conversationTitle = text.length > 24 ? text.slice(0, 24) + '…' : text;
      }
      this.lastUserText = text;
      this._pushUser(text);
      this.draft = '';
      this._resetComposerHeight();
      this._pushAssistant();
      this.currentRun = newRun();
      this.stuckToBottom = true;
      this.$nextTick(() => this.scrollToBottom());
      this._startTurn('/chat', buildChatBody(text));
    },

    retry() {
      if (this.sendStatus === 'streaming' || !this.lastUserText) return;
      const am = this._assistant();
      if (am) this.messages.pop(); // 移除尾部失败的助手消息
      this._pushAssistant();
      this.currentRun = newRun();
      this.stuckToBottom = true;
      this.$nextTick(() => this.scrollToBottom());
      this._startTurn('/chat', buildChatBody(this.lastUserText));
    },

    async _startTurn(url, body) {
      this._turnErrored = false;
      this.pendingResume = null;
      this.sendStatus = 'streaming';
      this._abort = new AbortController();
      let result;
      try {
        result = await postChatStream(body, { url, onEvent: (t, d) => this._onEvent(t, d), signal: this._abort.signal });
      } catch (e) {
        this._onError(e);
        return;
      }
      if (result.sessionId) this.sessionId = result.sessionId;
      if (result.aborted) return this._finishStopped();
      if (result.sawDone) return this._finishDone();
      if (this.pendingResume) return this._pause();
      if (this._turnErrored) return this._finishError();
      this._finishDone(); // 无 done 的优雅结束
    },

    _onEvent(type, data) {
      const am = this._assistant();
      data = data || {};
      switch (type) {
        case 'plan': applyPlan(this.currentRun, data); break;
        case 'step': applyStep(this.currentRun, data); break;
        case 'tool_call': applyToolCall(this.currentRun, data); break;
        case 'tool_result_summary': applyToolResult(this.currentRun, data); break;
        case 'answer_delta': this._appendAnswer(data.text || ''); break;
        case 'confirm_request':
          this._closeOpenText();
          if (am) am.blocks.push({ type: 'confirm', id: data.id, prompt: data.prompt || '', options: data.options || [], resolved: false, confirmed: null });
          this.pendingResume = { kind: 'confirm', id: data.id };
          break;
        case 'ask_user':
          this._closeOpenText();
          if (am) am.blocks.push({ type: 'ask', id: data.id, questions: data.questions || [], selected: {}, resolved: false });
          this.pendingResume = { kind: 'ask', id: data.id };
          break;
        case 'citation':
          this._closeOpenText();
          if (am) am.blocks.push({ type: 'citation', items: this._normCitations(data) });
          break;
        case 'done': this._lastStop = data; break;
        case 'error':
          this._turnErrored = true;
          applyErrorToRun(this.currentRun);
          if (am) am.blocks.push({ type: 'error', code: data.code || 'error', message: data.message || '发生错误' });
          break;
        default: break; // 未知事件忽略(TODO:协议新增事件时在此补)
      }
      if (this.stuckToBottom) this.scrollToBottom();
    },

    _appendAnswer(text) {
      const am = this._assistant();
      if (!am) return;
      let last = am.blocks[am.blocks.length - 1];
      if (!last || last.type !== 'text' || !last.open) {
        am.blocks.push({ type: 'text', raw: '', html: '', open: true });
        last = am.blocks[am.blocks.length - 1]; // 取响应式引用
      }
      last.raw += text;
    },

    _closeOpenText() {
      const am = this._assistant();
      if (!am) return;
      for (let i = 0; i < am.blocks.length; i++) {
        const b = am.blocks[i];
        if (b.type === 'text' && b.open) { b.html = renderMarkdown(b.raw); b.open = false; }
      }
    },

    _normCitations(data) {
      const arr = (data && data.items) || [];
      return arr.map((c) => ({ title: c.title || c.source || '来源', source: c.source || '', ref: c.ref || c.url || '' }));
    },

    _pause() {
      this._closeOpenText();
      const am = this._assistant();
      if (am) am.streaming = false;
      this.sendStatus = 'idle'; // 等待用户在卡片上操作;currentRun 保留(区暂停)
    },

    _finishDone() {
      this._closeOpenText();
      const am = this._assistant();
      completeRunSteps(this.currentRun);
      const snap = snapshotRun(this.currentRun);
      if (snap && am) am.blocks.push(snap); // 留痕:计划 + 工具时间线沉入消息
      if (am) am.streaming = false;
      this.currentRun = null;
      this.pendingResume = null;
      this.sendStatus = 'idle';
      this._abort = null;
      if (this.stuckToBottom) this.$nextTick(() => this.scrollToBottom());
    },

    _finishStopped() {
      this._closeOpenText();
      const am = this._assistant();
      const snap = snapshotRun(this.currentRun);
      if (snap && am) am.blocks.push(snap);
      if (am) { am.streaming = false; am.blocks.push({ type: 'note', text: '已停止' }); }
      this.currentRun = null;
      this.pendingResume = null;
      this.sendStatus = 'idle';
      this._abort = null;
    },

    _finishError() {
      this._closeOpenText();
      const am = this._assistant();
      if (am) am.streaming = false;
      // 保留 currentRun(失败步骤标红可见,设计 §7.5.1);sendStatus=error 供重试
      this.sendStatus = 'error';
      this.pendingResume = null;
      this._abort = null;
    },

    _onError(e) {
      const am = this._assistant();
      if (am) am.blocks.push({ type: 'error', code: (e && e.status) || 'network', message: friendlyError(e) });
      applyErrorToRun(this.currentRun);
      if (am) am.streaming = false;
      this.sendStatus = 'error';
      this.pendingResume = null;
      this._abort = null;
    },

    // ---- 卡片操作(恢复)----
    confirmChoice(block, confirmed) {
      if (block.resolved) return;
      block.resolved = true;
      block.confirmed = confirmed;
      const am = this._assistant();
      if (am) am.streaming = true;
      this.stuckToBottom = true;
      this._startTurn('/chat/confirm', buildConfirmBody(this.sessionId, confirmed));
    },
    askPick(block, qIndex, option) {
      block.selected[qIndex] = option;
    },
    askComplete(block) {
      return block.questions.length > 0 && Object.keys(block.selected).length >= block.questions.length;
    },
    submitAsk(block) {
      if (block.resolved || !this.askComplete(block)) return;
      block.resolved = true;
      block.answers = { ...block.selected };
      const am = this._assistant();
      if (am) am.streaming = true;
      this.stuckToBottom = true;
      this._startTurn('/chat/confirm', buildAskBody(this.sessionId, block.answers));
    },

    // ---- Composer / 停止 ----
    stopStream() {
      if (this._abort) this._abort.abort();
    },
    onComposerKeydown(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.sendMessage();
      } else if (e.key === 'Escape' && this.sendStatus === 'streaming') {
        e.preventDefault();
        this.stopStream();
      }
    },
    autogrow(e) {
      const t = e.target;
      t.style.height = 'auto';
      t.style.height = Math.min(t.scrollHeight, 200) + 'px';
    },
    _resetComposerHeight() {
      document.querySelectorAll('.composer-input').forEach((t) => { t.style.height = 'auto'; });
    },

    // ---- 进展区 / 时间线交互 ----
    toggleCollapse(o) { if (o) o.collapsed = !o.collapsed; },
    runSummary(run) { return runSummaryLine(run); },
    stepLabel(status) {
      return { pending: '待执行', running: '进行中', done: '完成', failed: '失败' }[status] || status;
    },
    toolStatIcon(status) { return status === 'running' ? '⟳' : (status === 'failed' ? '✗' : '✓'); },
    toolOverview(t) {
      if (t.status === 'running' || t.tier === 'inline') return '';
      if (t.tier === 'structured') return '· 结构化结果(展开查看)';
      const first = (t.resultSummary || '').split('\n')[0];
      return '· ' + (first.length > 36 ? first.slice(0, 36) + '…' : first);
    },
    toggleTool(timeline, i) { timeline[i].expanded = !timeline[i].expanded; },
    expandAllTools(timeline, val) { for (let i = 0; i < timeline.length; i++) timeline[i].expanded = val; },
    toolResultHtml(item) { return renderMarkdown(item.resultSummary || ''); },

    // ---- 滚动 / 复制 ----
    onScroll(e) {
      const el = e.target;
      this.stuckToBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
    },
    scrollToBottom() {
      const el = this.$refs.scroller;
      if (el) el.scrollTop = el.scrollHeight;
    },
    onBodyClick(e) {
      const btn = e.target.closest && e.target.closest('.copy-btn');
      if (!btn) return;
      const block = btn.closest('.code-block');
      const code = block && block.querySelector('code');
      if (!code) return;
      const text = code.textContent || '';
      const ok = () => { const o = btn.textContent; btn.textContent = '已复制'; setTimeout(() => { btn.textContent = o; }, 1200); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(ok).catch(() => {});
      else {
        const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); ok(); } catch (e2) { /* ignore */ } finally { ta.remove(); }
      }
    },

    newConversation() {
      if (this._abort) this._abort.abort();
      this.messages = [];
      this.hasMessages = false;
      this.sendStatus = 'idle';
      this.currentRun = null;
      this.pendingResume = null;
      this.draft = '';
      this.sessionId = '';
      this.conversationTitle = '新对话';
      this._resetComposerHeight();
      if (window.innerWidth < 1024) this.sidebarOpen = false;
    },
  };
}
