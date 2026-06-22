// mock-kb.js — 开发期 mock 的知识库管理端点(由 mock-sse.js 在 mock 模式下分发 /admin/kb/*)。
// 纯内存态,演示 UI 全流程(上传 → 入库轮询 running→done → 已入库 + 下载 + IT 库细 ACL)。
// 真实后端见 agent-gateway /admin/kb/*(内部管理员;docx 解析与 ingest 在后端)。

const _KBS = ['business', 'it_design'];
const _INTERNAL_ROLES = ['internal', 'internal_support', 'internal_dev'];
const _FILE_RE = /\.(md|markdown|txt|docx)$/i;

// 每库:{ docs:[{name,size,mtime,indexed}], ingest:{status,task_id,_ticks} }
const _state = {};
function _fresh() { return { docs: [], ingest: { status: 'idle' } }; }
function _kb(kb) { if (!_state[kb]) _state[kb] = _fresh(); return _state[kb]; }
const _now = () => new Date().toISOString().slice(0, 19).replace('T', ' ');

function _json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function _ctxRoles(init) {
  try {
    const h = (init && init.headers) || {};
    const raw = h['X-User-Ctx'] || h['x-user-ctx'];
    if (!raw) return null;
    return (JSON.parse(raw).roles) || [];
  } catch (e) { return null; }
}
function _isInternal(roles) { return Array.isArray(roles) && roles.some((r) => _INTERNAL_ROLES.includes(r)); }

/** mock 分发:命中 /admin/kb/* 返回 Response,否则返回 null(透传)。 */
export function handleKb(method, path, init) {
  if (!path.startsWith('/admin/kb/')) return null;
  init = init || {};
  const roles = _ctxRoles(init);
  if (roles === null) return _json({ code: 'NO_PERMISSION', message: '缺少身份' }, 401);

  // 解析 /admin/kb/{kb}/...
  const m = path.match(/^\/admin\/kb\/([^/]+)\/(.+)$/);
  if (!m) return _json({ code: 'NOT_FOUND', message: '未知端点' }, 404);
  const kb = decodeURIComponent(m[1]);
  const rest = m[2];

  if (!_KBS.includes(kb)) return _json({ code: 'INVALID_KB', message: '未知知识库' }, 404);
  // IT 设计库细 ACL:仅内部角色(镜像后端 _check_kb_access)。
  if (kb === 'it_design' && !_isInternal(roles)) return _json({ code: 'NO_PERMISSION', message: 'IT 库仅内部角色' }, 403);

  const st = _kb(kb);

  if (method === 'GET' && rest === 'docs') {
    return _json(st.docs.map((d) => ({ ...d })));
  }

  if (method === 'POST' && rest === 'upload') {
    const fd = init.body;
    const file = fd && fd.get && fd.get('file');
    const name = (file && file.name) || '';
    if (!_FILE_RE.test(name)) return _json({ code: 'INVALID_INPUT', message: '格式不支持' }, 400);
    if ((file.size || 0) > 25 * 1024 * 1024) return _json({ code: 'TOO_LARGE', message: '超过上限' }, 413);
    const existing = st.docs.find((d) => d.name === name);
    if (existing) { existing.size = file.size || 0; existing.mtime = _now(); existing.indexed = false; return _json({ ...existing }); }
    const rec = { name, size: file.size || 0, mtime: _now(), indexed: false };
    st.docs.push(rec);
    return _json({ ...rec });
  }

  if (method === 'POST' && rest === 'ingest') {
    st.ingest = { status: 'running', task_id: 'mock-' + Date.now(), _ticks: 0 };
    return _json({ task_id: st.ingest.task_id, kb, status: 'running' });
  }

  if (method === 'GET' && rest === 'ingest/status') {
    const ing = st.ingest;
    if (ing.status === 'running') {
      ing._ticks = (ing._ticks || 0) + 1;
      if (ing._ticks >= 1) { ing.status = 'done'; st.docs.forEach((d) => { d.indexed = true; }); } // 一拍后完成
    }
    return _json({ kb, status: ing.status, task_id: ing.task_id });
  }

  const dl = rest.match(/^docs\/([^/]+)\/download$/);
  if (method === 'GET' && dl) {
    const name = decodeURIComponent(dl[1]);
    const doc = st.docs.find((d) => d.name === name);
    if (!doc) return _json({ code: 'NOT_FOUND', message: '文档不存在' }, 404);
    return new Response('mock content of ' + name, { status: 200, headers: { 'Content-Type': 'application/octet-stream' } });
  }

  return _json({ code: 'NOT_FOUND', message: '未知端点' }, 404);
}

/** selftest 复用:重置内存态。 */
export function _resetKb() { for (const k of Object.keys(_state)) delete _state[k]; }
