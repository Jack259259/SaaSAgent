// markdown.js — marked + highlight.js + DOMPurify 封装(W1 实现)。
// 占位:renderMarkdown 必须经 DOMPurify 消毒后返回安全 HTML(禁 <script>/事件属性/HTML 注入);
// 助手输出与工具结果同一安全标准(设计 §2 前端红线 / §11,对齐后端红线 7「内容不可信」)。

/**
 * 渲染并消毒 Markdown 为安全 HTML 字符串。
 * @param {string} text
 * @returns {string} 经 DOMPurify 消毒的 HTML
 */
export function renderMarkdown(text) {
  // TODO(W1): marked.parse(text) → highlight.js 高亮代码块 → DOMPurify.sanitize(html, 严格白名单);
  //           代码块语言标注 + 复制按钮。vendor 已就位(marked / highlight.js / dompurify)。
  throw new Error('renderMarkdown not implemented until W1');
}
