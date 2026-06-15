// chat.js — 发送循环 + 消息 / 流式渲染。
// W1:用本地 setInterval 模拟逐字流式(非真实 SSE,W2 换 postChatStream);富事件卡片留 W2。
import { renderMarkdown } from './markdown.js';

let _seq = 0;
const uid = (p) => `${p}-${Date.now()}-${++_seq}`;

/** 新建一条消息对象。 */
export function createMessage(role, raw = '') {
  return { id: uid(role), role, raw, streamText: raw, html: '', streaming: false };
}

/** 把增量 token 追加到消息(纯函数,供流式与 selftest 复用)。 */
export function appendToken(msg, token) {
  msg.raw += token;
  msg.streamText = msg.raw;
  return msg;
}

// W1 本地演示回复(含 Markdown + 代码块,用于验证渲染 / 高亮 / 复制)。
const DEMO_REPLY = [
  '这是一条**模拟流式**回复(W1 本地 `setInterval`,非真实 SSE;真实对接在 W2)。',
  '',
  '它支持:',
  '- Markdown 渲染与消毒',
  '- 代码高亮与一键复制',
  '',
  '```python',
  'def plan_funds(rows):',
  '    """按到期日聚合资金缺口"""',
  '    return sorted(rows, key=lambda r: r["due_date"])',
  '```',
  '',
  '完成后打字光标消失。',
].join('\n');

/** 创建聊天相关的 Alpine 状态与方法(由 app.js 合入根组件)。 */
export function createChat() {
  return {
    messages: [],
    draft: '',
    hasMessages: false,
    sendStatus: 'idle', // idle | streaming
    stuckToBottom: true,
    conversationTitle: '新对话',
    _timer: null,

    // 注意:用方法而非 getter —— app.js 以对象展开 (...createChat()) 合入根组件,getter 会在展开时被求值成静态值。
    canSend() {
      return this.draft.trim().length > 0 && this.sendStatus !== 'streaming';
    },

    sendMessage() {
      const text = this.draft.trim();
      if (!text || this.sendStatus === 'streaming') return;
      if (!this.hasMessages) {
        this.hasMessages = true;
        this.conversationTitle = text.length > 24 ? text.slice(0, 24) + '…' : text;
      }
      this.messages.push(createMessage('user', text));
      this.draft = '';
      this._resetComposerHeight();

      this.messages.push(createMessage('assistant', ''));
      // 取数组内的响应式引用:直接 mutate push 进去的原始对象不会触发 Alpine 更新。
      const am = this.messages[this.messages.length - 1];
      am.streaming = true;
      this.sendStatus = 'streaming';
      this.stuckToBottom = true;
      this.$nextTick(() => this.scrollToBottom());
      this._simulateStream(am);
    },

    _simulateStream(am) {
      const full = DEMO_REPLY;
      let i = 0;
      this._timer = setInterval(() => {
        appendToken(am, full.slice(i, i + 2)); // 每帧 2 字符,自然打字速度
        i += 2;
        if (this.stuckToBottom) this.scrollToBottom();
        if (i >= full.length) this._finishStream(am);
      }, 18);
    },

    _finishStream(am) {
      if (this._timer) { clearInterval(this._timer); this._timer = null; }
      am.html = renderMarkdown(am.raw); // 完成后一次性富渲染(避免半截 Markdown 抖动)
      am.streaming = false;
      this.sendStatus = 'idle';
      if (this.stuckToBottom) this.$nextTick(() => this.scrollToBottom());
    },

    stopStream() {
      const am = this.messages[this.messages.length - 1];
      if (am && am.streaming) this._finishStream(am);
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
      const ok = () => {
        const orig = btn.textContent;
        btn.textContent = '已复制';
        setTimeout(() => { btn.textContent = orig; }, 1200);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(ok).catch(() => {});
      } else {
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); ok(); } catch (e2) { /* ignore */ } finally { ta.remove(); }
      }
    },

    newConversation() {
      if (this._timer) { clearInterval(this._timer); this._timer = null; }
      this.messages = [];
      this.hasMessages = false;
      this.sendStatus = 'idle';
      this.draft = '';
      this.conversationTitle = '新对话';
      this._resetComposerHeight();
      if (window.innerWidth < 1024) this.sidebarOpen = false;
    },
  };
}
