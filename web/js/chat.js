// chat.js — 发送/恢复轮次循环 + 消息(blocks)+ 富事件卡片 + currentRun 投影 + 附件 + 会话历史持久化。
import { renderMarkdown } from './markdown.js';
import { icon } from '../vendor/lucide/icons.js';
import { postChatStream, buildChatBody, buildConfirmBody, buildAskBody } from './sse.js';
import {
  newRun, applyPlan, applyStep, applyToolCall, applyToolResult,
  applyErrorToRun, completeRunSteps, snapshotRun, runSummaryLine, FOLD,
} from './run.js';
import { createConversationStore, groupByTime } from './store.js';

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

// 「是否展示推理过程」全局偏好。本架构后端 SSE 无模型思维链 token,"推理过程"=Agent 运行过程
// (顶部任务进展区 + 工具调用时间线,见 frontend-design §7.5)。开关只控渲染、不碰事件数据。
// 默认=关(只看结果);改此常量即调整默认值。
export const DEFAULT_SHOW_REASONING = false;
const REASONING_KEY = 'fp_show_reasoning';
/** 读全局偏好:'1'→true、'0'→false、未设置→fallback(默认)。隐私/配额异常回退默认。 */
export function loadShowReasoning(fallback = DEFAULT_SHOW_REASONING) {
  try {
    const v = localStorage.getItem(REASONING_KEY);
    if (v === '1') return true;
    if (v === '0') return false;
    return fallback;
  } catch (e) { return fallback; }
}
/** 写全局偏好('1'/'0');隐私/配额异常忽略。 */
export function saveShowReasoning(val) {
  try { localStorage.setItem(REASONING_KEY, val ? '1' : '0'); } catch (e) { /* 忽略 */ }
}

/** 创建聊天相关的 Alpine 状态与方法(由 app.js 合入根组件)。 */
export function createChat() {
  return {
    messages: [],
    draft: '',
    hasMessages: false,
    sendStatus: 'idle',     // idle | streaming | error
    currentRun: null,
    showReasoning: DEFAULT_SHOW_REASONING, // 是否展示推理过程(Agent 运行过程);全局偏好,见 initReasoning
    sessionId: '',
    pendingResume: null,
    lastUserText: '',
    stuckToBottom: true,
    conversationTitle: '新对话',
    conversations: [],      // 会话索引(Sidebar)
    activeConvId: null,
    editingId: null,        // 正在编辑的用户消息 id(null=普通发送)
    feedbackEndpoint: null, // 反馈上报端点(后端就绪后置 '/feedback';null=仅本地暂存,见 backend-gaps §F)
    FOLD,
    _store: createConversationStore(),
    _abort: null,
    _turnErrored: false,

    canSend() {
      if (this.sendStatus === 'streaming') return false;
      if (this.draft.trim().length === 0) return false;
      if (this.hasPendingUploads && this.hasPendingUploads()) return false; // 等附件上传完成
      return true;
    },

    _assistant() {
      const m = this.messages[this.messages.length - 1];
      return m && m.role === 'assistant' ? m : null;
    },
    _pushUser(text, attachments) {
      this.messages.push({ id: uid('user'), role: 'user', raw: text, attachments: attachments || [], created_at: Date.now() });
    },
    _pushAssistant() {
      this.messages.push({ id: uid('asst'), role: 'assistant', blocks: [], streaming: true, created_at: Date.now() });
      return this._assistant();
    },

    sendMessage() {
      const text = this.draft.trim();
      if (!text || this.sendStatus === 'streaming') return;
      if (this.hasPendingUploads && this.hasPendingUploads()) return;
      if (this.editingId) return this._sendEdit(text);
      if (!this.hasMessages) {
        this.hasMessages = true;
        this.conversationTitle = text.length > 24 ? text.slice(0, 24) + '…' : text;
      }
      this._ensureConversation();
      const atts = this.attachmentsSnapshot ? this.attachmentsSnapshot() : [];
      const fileIds = this.pendingFileIds ? this.pendingFileIds() : [];
      this._pushUser(text, atts);
      if (this.clearAttachments) this.clearAttachments();
      this.draft = '';
      this._resetComposerHeight();
      this._beginAssistantTurn(text, fileIds);
    },

    /** 推入助手占位并起一轮(发送/编辑/重试共用)。 */
    _beginAssistantTurn(text, fileIds) {
      this.lastUserText = text;
      this._pushAssistant();
      this.currentRun = newRun();
      this.stuckToBottom = true;
      this.$nextTick(() => this.scrollToBottom());
      this._startTurn('/chat', buildChatBody(text, fileIds || []));
    },

    /** 编辑覆盖重发(D:截断该消息之后所有轮次,从编辑后的文本重生成)。 */
    _sendEdit(text) {
      const id = this.editingId;
      this.editingId = null;
      const i = this.messages.findIndex((m) => m.id === id);
      if (i < 0) { this.draft = ''; this._resetComposerHeight(); return; }
      const target = this.messages[i];
      target.raw = text;
      target.created_at = Date.now();
      this._truncateAfter(i);            // 覆盖:丢弃该用户消息之后的所有轮次
      this.draft = '';
      this._resetComposerHeight();
      this._beginAssistantTurn(text, this._fileIdsOf(target));
    },

    retry() {
      if (this.sendStatus === 'streaming' || !this.lastUserText) return;
      if (this._assistant()) this.messages.pop();
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
      this._finishDone();
    },

    _onEvent(type, data) {
      const am = this._assistant();
      data = data || {};
      switch (type) {
        case 'plan': applyPlan(this.currentRun, data); break;
        case 'step': applyStep(this.currentRun, data); break;
        case 'tool_call': this._closeOpenText(); applyToolCall(this.currentRun, data); break;
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
        last = am.blocks[am.blocks.length - 1];
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
    /**
     * citation.ref 协议白名单(FB-1)。citation 来源是检索内容,按红线 7 不可信,且经 :href 直绑
     * 绕过 DOMPurify。仅放行 http(s)/相对路径/锚点;javascript:/data:/vbscript: 等一律归 '#'。
     */
    safeHref(url) {
      const s = String(url == null ? '' : url).trim();
      if (!s) return '#';
      if (s[0] === '#' || s[0] === '/') return s; // 锚点 / 绝对或协议相对路径(导航,非执行)
      const stripped = s.replace(/[\u0000-\u0020]+/g, ''); // 去控制字符/空白,防 java\tscript: 绕过
      if (/^https?:\/\//i.test(stripped)) return s; // 仅 http(s) 显式协议放行
      if (/^[a-z][a-z0-9+.-]*:/i.test(stripped)) return '#'; // 其余任何协议拒
      return s; // 无协议的相对引用放行
    },

    _normCitations(data) {
      const arr = (data && data.items) || [];
      return arr.map((c) => ({
        title: c.title || c.source || '来源',
        source: c.source || '',
        ref: this.safeHref(c.ref || c.url || ''),
      }));
    },

    _pause() {
      this._closeOpenText();
      const am = this._assistant();
      if (am) am.streaming = false;
      this.sendStatus = 'idle';
      this._persist();
    },
    _finishDone() {
      this._closeOpenText();
      const am = this._assistant();
      completeRunSteps(this.currentRun);
      const snap = snapshotRun(this.currentRun);
      if (snap && am) am.blocks.push(snap);
      if (am) am.streaming = false;
      this.currentRun = null;
      this.pendingResume = null;
      this.sendStatus = 'idle';
      this._abort = null;
      if (this.stuckToBottom) this.$nextTick(() => this.scrollToBottom());
      this._persist();
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
      this._persist();
    },
    _finishError() {
      this._closeOpenText();
      const am = this._assistant();
      if (am) am.streaming = false;
      this.sendStatus = 'error';
      this.pendingResume = null;
      this._abort = null;
      this._persist();
    },
    _onError(e) {
      const am = this._assistant();
      if (am) am.blocks.push({ type: 'error', code: (e && e.status) || 'network', message: friendlyError(e) });
      applyErrorToRun(this.currentRun);
      if (am) am.streaming = false;
      this.sendStatus = 'error';
      this.pendingResume = null;
      this._abort = null;
      this._persist();
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
    askPick(block, qIndex, option) { block.selected[qIndex] = option; },
    askComplete(block) { return block.questions.length > 0 && Object.keys(block.selected).length >= block.questions.length; },
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
    stopStream() { if (this._abort) this._abort.abort(); },
    onComposerKeydown(e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.sendMessage(); }
      else if (e.key === 'Escape' && this.sendStatus === 'streaming') { e.preventDefault(); this.stopStream(); }
    },
    autogrow(e) { const t = e.target; t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 200) + 'px'; },
    _resetComposerHeight() { document.querySelectorAll('.composer-input').forEach((t) => { t.style.height = 'auto'; }); },

    // ---- 推理过程(Agent 运行过程)显隐总开关 ----
    /** 从 localStorage 恢复全局偏好(app.js init 调用;刷新 / 新对话保持)。 */
    initReasoning() { this.showReasoning = loadShowReasoning(); },
    /** 切换并落库。实时生效:仅改渲染条件,不动 currentRun / 留痕数据(中途开关不丢数据)。 */
    toggleReasoning() { this.showReasoning = !this.showReasoning; saveShowReasoning(this.showReasoning); },
    /** 当前助手消息是否已有答案正文(决定关闭态最小指示是否仍需显示)。 */
    hasStreamingAnswerText() {
      const am = this._assistant();
      return !!(am && (am.blocks || []).some((b) => b.type === 'text' && (b.raw || '').length > 0));
    },
    /** 关闭态最小指示条件:本轮进行中且尚无答案正文(答案一开始流式即收起)。 */
    reasoningBusy() { return this.sendStatus === 'streaming' && !this.hasStreamingAnswerText(); },

    // ---- 进展区 / 时间线 ----
    toggleCollapse(o) { if (o) o.collapsed = !o.collapsed; },
    runSummary(run) { return runSummaryLine(run); },
    stepLabel(status) { return { pending: '待执行', running: '进行中', done: '完成', failed: '失败' }[status] || status; },
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
    onScroll(e) { const el = e.target; this.stuckToBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 48; },
    scrollToBottom() { const el = this.$refs.scroller; if (el) el.scrollTop = el.scrollHeight; },
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

    /** 助手 text 块的 Markdown 源拼接(保留,供既有断言;复制 Md 源亦用 messageMarkdown)。 */
    copyTextOf(msg) {
      if (msg.role === 'user') return msg.raw || '';
      return (msg.blocks || [])
        .filter(b => b.type === 'text')
        .map(b => b.raw || '')
        .join('\n');
    },

    /**
     * 该消息的可复制**纯文本**(默认):用户取 raw;助手仅拼接 text 块的**渲染后纯文本**
     * (去 Markdown 标记),**排除**进展区/工具时间线/confirm/ask/citation/error/note 等 UI。
     */
    messageText(msg) {
      if (!msg) return '';
      if (msg.role === 'user') return msg.raw || '';
      return (msg.blocks || [])
        .filter((b) => b.type === 'text')
        .map((b) => {
          if (b.html && typeof document !== 'undefined') {
            const el = document.createElement('div');
            el.innerHTML = b.html; // html 已经 DOMPurify 消毒,仅取 textContent
            return (el.textContent || '').trim();
          }
          return (b.raw || '').trim();
        })
        .filter(Boolean)
        .join('\n\n');
    },
    /** 该消息的 **Markdown 源**(可选复制):仅拼接 text 块的 raw。 */
    messageMarkdown(msg) {
      if (!msg) return '';
      if (msg.role === 'user') return msg.raw || '';
      return (msg.blocks || []).filter((b) => b.type === 'text').map((b) => b.raw || '').join('\n\n');
    },

    /** 复制整段消息(mode='md' 复制 Markdown 源,否则纯文本);按钮短暂反馈"已复制"。 */
    copyMessage(e, msg, mode) {
      const text = mode === 'md' ? this.messageMarkdown(msg) : this.messageText(msg);
      const btn = (e && (e.currentTarget || (e.target && e.target.closest && e.target.closest('.act-btn')))) || null;
      this._writeClipboard(text, () => this._flashCopied(btn));
    },
    _writeClipboard(text, ok) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(ok).catch(() => {});
      } else {
        const ta = document.createElement('textarea');
        ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
        document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); ok(); } catch (e2) { /* ignore */ } finally { ta.remove(); }
      }
    },
    _flashCopied(btn) {
      if (!btn) return;
      const ico = btn.querySelector('.act-ico');
      const origHtml = ico ? ico.innerHTML : '';
      const origTitle = btn.getAttribute('title') || '';
      if (ico) ico.innerHTML = icon('check');
      btn.classList.add('copied'); btn.setAttribute('title', '已复制');
      setTimeout(() => {
        if (ico) ico.innerHTML = origHtml;
        btn.classList.remove('copied'); btn.setAttribute('title', origTitle);
      }, 1500);
    },

    // ---- 消息操作:点赞点踩 / 反馈 / 编辑 / 重试(截断重生成)----
    /** 点赞点踩互斥 toggle(再点同一个=取消)。点踩浮出意见框。 */
    setVote(msg, vote) {
      if (!msg) return;
      msg.vote = (msg.vote === vote) ? null : vote;
      msg.showComment = (msg.vote === 'down');
      this._postFeedback(msg);
      this._persist();
    },
    submitFeedbackComment(msg) {
      if (!msg) return;
      msg.feedbackComment = (msg.feedbackComment || '').trim().slice(0, 500);
      msg.showComment = false;
      this._postFeedback(msg);
      this._persist();
    },
    cancelFeedbackComment(msg) { if (msg) msg.showComment = false; },
    /**
     * 上报反馈。后端 /feedback 端点尚未实现(backend-gaps §F):默认**仅本地暂存**(localStorage),
     * 不发网络请求(避免对不存在端点 POST 产生控制台错误)。端点就绪后置 `feedbackEndpoint`,
     * 改走网络上报 + 失败回退暂存。
     */
    _postFeedback(msg) {
      const payload = { message_id: msg.id, session_id: this.sessionId || null, vote: msg.vote || null };
      const c = (msg.feedbackComment || '').slice(0, 500); if (c) payload.comment = c;
      const stash = () => this._stashFeedback(payload);
      if (!this.feedbackEndpoint || typeof fetch !== 'function') { stash(); return; }
      try {
        fetch(this.feedbackEndpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
          .then((r) => { if (!r || !r.ok) stash(); }).catch(stash);
      } catch (e) { stash(); }
    },
    _stashFeedback(payload) {
      try {
        const KEY = 'fp_feedback_queue';
        const arr = JSON.parse(localStorage.getItem(KEY) || '[]');
        arr.push({ ...payload, ts: Date.now() });
        localStorage.setItem(KEY, JSON.stringify(arr));
      } catch (e) { /* 配额/隐私模式忽略 */ }
    },

    _indexOf(msg) { return this.messages.findIndex((m) => m.id === (msg && msg.id)); },
    _truncateAfter(i) { if (i >= 0) this.messages.splice(i + 1); },
    _fileIdsOf(msg) { return (((msg && msg.attachments) || []).map((a) => a.file_id)).filter(Boolean); },
    hasTextBlock(msg) { return !!(msg && (msg.blocks || []).some((b) => b.type === 'text')); },

    /** 重试用户消息:截断其后所有轮次,从该提问重新生成。 */
    retryUserMessage(msg) {
      if (this.sendStatus === 'streaming' || !msg || msg.role !== 'user') return;
      const i = this._indexOf(msg);
      if (i < 0) return;
      this._truncateAfter(i);
      this._beginAssistantTurn(msg.raw || '', this._fileIdsOf(msg));
    },
    /** 重新生成模型回复:定位其前一条用户消息并重试。 */
    retryAssistant(msg) {
      if (this.sendStatus === 'streaming' || !msg || msg.role !== 'assistant') return;
      const i = this._indexOf(msg);
      for (let k = i - 1; k >= 0; k--) {
        if (this.messages[k].role === 'user') return this.retryUserMessage(this.messages[k]);
      }
    },
    /** 编辑用户消息:内容载入 composer,进入"编辑中"态(发送即覆盖重发)。
     *  注:命名避开 skills.js 的 startEdit/cancelEdit(同根组件合并,名字会互相覆盖)。 */
    editMessage(msg) {
      if (this.sendStatus === 'streaming' || !msg || msg.role !== 'user') return;
      this.draft = msg.raw || '';
      this.editingId = msg.id;
      this.$nextTick(() => {
        const t = document.querySelector('.composer-bar .composer-input');
        if (t) { t.focus(); this.autogrow({ target: t }); }
      });
    },
    cancelMessageEdit() { this.editingId = null; this.draft = ''; this._resetComposerHeight(); },

    // ---- 会话历史(§12-D1)----
    initChat() {
      this.loadConversations();
      if (this.conversations.length) this.switchConversation(this.conversations[0].id);
    },
    loadConversations() { this.conversations = this._store.listConversations(); },
    convGroups() { return groupByTime(this.conversations); },
    _ensureConversation() {
      if (!this.activeConvId) { this.activeConvId = this._store.createConversation(this.conversationTitle).id; }
    },
    _persist() {
      if (!this.activeConvId) return;
      this._store.saveMessages(this.activeConvId, this.messages);
      this._store.rename(this.activeConvId, this.conversationTitle);
      this.loadConversations();
    },
    switchConversation(id) {
      if (this._abort) this._abort.abort();
      const c = this._store.getConversation(id);
      if (!c) return;
      this.activeConvId = id;
      this.messages = c.messages || [];
      this.conversationTitle = c.title || '新对话';
      this.hasMessages = this.messages.length > 0;
      this.currentRun = null;
      this.pendingResume = null;
      this.sendStatus = 'idle';
      if (typeof window !== 'undefined' && window.innerWidth < 1024) this.sidebarOpen = false;
      this.$nextTick(() => this.scrollToBottom());
    },
    renameConversation(id) {
      const cur = this.conversations.find((c) => c.id === id);
      const name = window.prompt('重命名会话', cur ? cur.title : '');
      if (name && name.trim()) {
        this._store.rename(id, name.trim());
        if (id === this.activeConvId) this.conversationTitle = name.trim();
        this.loadConversations();
      }
    },
    deleteConversation(id) {
      if (!window.confirm('删除该会话?此操作不可恢复。')) return;
      this._store.remove(id);
      if (id === this.activeConvId) this.newConversation();
      this.loadConversations();
    },
    clearHistory() {
      if (!window.confirm('清除全部本地会话历史?此操作不可恢复。')) return;
      this._store.clearAll();
      this.newConversation();
      this.loadConversations();
    },

    newConversation() {
      if (this._abort) this._abort.abort();
      if (this.clearAttachments) this.clearAttachments();
      this.messages = [];
      this.hasMessages = false;
      this.sendStatus = 'idle';
      this.currentRun = null;
      this.pendingResume = null;
      this.draft = '';
      this.sessionId = '';
      this.activeConvId = null;
      this.conversationTitle = '新对话';
      this._resetComposerHeight();
      if (typeof window !== 'undefined' && window.innerWidth < 1024) this.sidebarOpen = false;
    },
  };
}
