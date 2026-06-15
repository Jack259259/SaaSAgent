// store.js — 会话历史 Repository(W3 实现,localStorage;预留切后端会话 API 的接缝,见设计 §9 / §12-D1)。
// 占位:UI 经 Repository 读写,不直接碰存储。

/**
 * 创建会话历史仓储。
 * @returns {{list:Function, get:Function, save:Function, remove:Function, clearAll:Function}}
 */
export function createConversationStore(/* backend */) {
  // TODO(W3): localStorage 实现 Conversation{id,title,created_at,updated_at} /
  //           Message{id,conv_id,role,content_blocks[],attachments[],created_at};
  //           「清除本地历史」一键清空(退出时可用);历史不写入敏感信息。
  const notReady = () => { throw new Error('conversation store not implemented until W3'); };
  return { list: notReady, get: notReady, save: notReady, remove: notReady, clearAll: notReady };
}
