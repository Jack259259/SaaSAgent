// sse.js — SSE 主循环(W2 实现)。事实来源:docs/dev/sse-protocol.md(POST /chat → text/event-stream)。
// 占位:签名先定;W2 用 fetch + ReadableStream 解析并按事件名分发(plan/step/tool_call/tool_result_summary/
// confirm_request/ask_user/answer_delta/done/error),支持 AbortController 取消。帧解析可复用 mock/mock-sse.js 的 parseSSE。

/**
 * 消费 /chat 的 SSE 流,按事件类型回调。
 * @param {{message:string, page_context?:object, attachments?:string[]}} payload
 * @param {{onEvent:(type:string,data:object)=>void, signal?:AbortSignal}} [opts]
 * @returns {Promise<void>}
 */
export async function postChatStream(payload, { onEvent, signal } = {}) {
  // TODO(W2): fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json','X-User-Ctx':...},
  //           body:JSON.stringify(payload), signal}) → 读 response.body(ReadableStream)→ 按帧解析 → onEvent(type,data)。
  //           字段严格对齐 sse-protocol.md;对不上的标 TODO 并上报,不臆造默认值。
  throw new Error('postChatStream not implemented until W2');
}
