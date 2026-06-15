// markdown.js — marked + highlight.js + DOMPurify 封装。
// 流程:marked 转 HTML → DOMPurify 严格消毒(禁 script/iframe/form/style + 默认去事件属性与 javascript: URI)
//       → 消毒「之后」再装饰代码块(hljs 高亮 + 语言标签 + 复制按钮,均为可信自有标记,后置注入)。
// 对齐设计 §11 与红线 7「检索/工具内容不可信」。vendor 库以 UMD 全局提供(window.marked/hljs/DOMPurify)。

const SANITIZE_CONFIG = {
  // 默认即去 <script>/事件属性/javascript: URI;这里再显式禁掉若干危险/无谓标签与内联样式。
  FORBID_TAGS: ['style', 'iframe', 'form', 'input', 'button', 'textarea', 'select', 'object', 'embed', 'script'],
  FORBID_ATTR: ['style'],
  ADD_ATTR: ['target'],
};

function ensureLibs() {
  if (typeof window === 'undefined' || !window.marked || !window.DOMPurify) {
    throw new Error('markdown libs (marked / DOMPurify) not loaded');
  }
}

/**
 * 渲染并消毒 Markdown 为安全 HTML 字符串(含代码块高亮 + 复制按钮)。
 * @param {string} text
 * @returns {string}
 */
export function renderMarkdown(text) {
  ensureLibs();
  const src = typeof text === 'string' ? text : '';
  const rawHtml = window.marked.parse(src, { gfm: true, breaks: true });
  const safe = window.DOMPurify.sanitize(rawHtml, SANITIZE_CONFIG);

  // 装饰阶段在消毒之后进行,注入的是可信的自有标记(高亮 span / 语言标签 / 复制按钮)。
  // 用 <template> 解析:其内容是惰性 DocumentFragment,装饰期间不会触发 <img> 等资源加载(副作用/性能)。
  const tpl = document.createElement('template');
  tpl.innerHTML = safe;
  const root = tpl.content;

  // 外链:新窗口打开并隔离 opener。
  root.querySelectorAll('a[href]').forEach((a) => {
    a.setAttribute('target', '_blank');
    a.setAttribute('rel', 'noopener noreferrer');
  });

  root.querySelectorAll('pre > code').forEach((codeEl) => {
    const cls = codeEl.getAttribute('class') || '';
    const m = cls.match(/language-([\w+-]+)/i);
    const lang = m ? m[1] : '';
    const codeText = codeEl.textContent || '';

    if (window.hljs) {
      try {
        const res = lang && window.hljs.getLanguage(lang)
          ? window.hljs.highlight(codeText, { language: lang, ignoreIllegals: true })
          : window.hljs.highlightAuto(codeText);
        codeEl.innerHTML = res.value; // hljs 输出为可信 span(源文本已消毒为纯文本)
      } catch (e) { /* 高亮失败则保留纯文本 */ }
    }
    codeEl.classList.add('hljs');

    const pre = codeEl.parentElement;
    const block = document.createElement('div');
    block.className = 'code-block';
    const head = document.createElement('div');
    head.className = 'code-head';
    const langSpan = document.createElement('span');
    langSpan.className = 'code-lang';
    langSpan.textContent = lang || 'text';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'copy-btn';
    btn.textContent = '复制';
    btn.setAttribute('aria-label', '复制代码');
    head.appendChild(langSpan);
    head.appendChild(btn);
    pre.replaceWith(block);
    block.appendChild(head);
    block.appendChild(pre);
  });

  return tpl.innerHTML;
}
