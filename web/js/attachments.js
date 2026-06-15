// attachments.js — 文件上传、校验、附件卡片状态(W3 实现)。
// 占位:前端仅校验 / 上传 / 展示;业务文档解析在后端 parse_user_file(前端不在浏览器解析,见设计 §2/§8)。

/**
 * 校验文件(扩展名 + MIME 双白名单 + 大小 / 条数上限 + 去重)。
 * @returns {{ok:boolean, reason?:string}}
 */
export function validateFile(/* file, opts */) {
  // TODO(W3): 双白名单覆盖 DOCX/ODT/RTF/EPUB/HTML/MD/TXT/XLSX/CSV/JSON/JPEG/PNG/GIF;大小上限默认 20MB(可配)。
  return { ok: false, reason: 'not implemented until W3' };
}

/**
 * 上传到 POST /files(multipart)→ { file_id, filename, mime, size, status }。
 * @returns {Promise<object>}
 */
export async function uploadFile(/* file, opts */) {
  // TODO(W3): fetch('/files',{method:'POST', body:FormData}) + 进度 + 取消;同源无 CORS。
  throw new Error('uploadFile not implemented until W3');
}
