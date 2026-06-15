// chat.js — 发送循环与消息 / 富卡片渲染逻辑(W1 流式渲染 → W2 SSE 主循环 + 富事件卡片 + 进展区投影)。
// 占位:本阶段(W0)不含任何对话业务逻辑。

/**
 * Alpine 聊天组件工厂(W1/W2 实现)。
 * @returns {object} x-data:messages / sendStatus / currentRun / sendMessage 等。
 */
export function chatComponent() {
  // TODO(W1): 消息块、流式打字 append(不整列重绘)、Markdown 渲染插槽、自动滚动。
  // TODO(W2): sendMessage、postChatStream 接入、currentRun(plan/step/tool_* 投影)、ConfirmCard/AskUserCard/Citations。
  return {};
}
