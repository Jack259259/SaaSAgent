// mock-repos.js — 开发期 mock 的代码仓管理端点(由 mock-sse.js 在 mock 模式下分发 /admin/repos*)。
// 纯内存态,演示 UI 全流程(含私有仓凭据二次流:url 含 "private" 且未带凭据 → 401 AUTH_REQUIRED)。
// 真实后端见 agent-gateway /admin/repos*(内部管理员 + FP_REPO_ADMIN;git/解压/索引在后端)。

let _repos = [];
const _now = () => new Date().toISOString().slice(0, 19).replace('T', ' ');
const _NAME_RE = /^[A-Za-z0-9_-]{2,64}$/;
const _ARCHIVE_RE = /\.(zip|tar|tar\.gz|tar\.bz2|tgz|tbz2)$/;

function _json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

/** mock 分发:命中 /admin/repos* 返回 Response,否则返回 null(透传)。 */
export function handleRepos(method, path, init) {
  if (!path.startsWith('/admin/repos')) return null;
  init = init || {};

  if (method === 'GET' && path === '/admin/repos') {
    return _json(_repos.map((r) => ({ ...r, present: true })));
  }

  if (method === 'POST' && path === '/admin/repos') {
    let body = {};
    try { body = JSON.parse(init.body || '{}'); } catch (e) { body = {}; }
    const name = (body.name || '').trim();
    if (!_NAME_RE.test(name)) return _json({ code: 'INVALID_NAME', message: '名称非法' }, 400);
    if (_repos.some((r) => r.name === name)) return _json({ code: 'REPO_EXISTS', message: '仓已存在' }, 409);
    if (/private/i.test(body.url || '') && !body.username) {
      return _json({ code: 'AUTH_REQUIRED', message: '仓库需要认证' }, 401); // 演示凭据二次流
    }
    const rec = { name, source: 'git', url: body.url || '', branch: body.branch || 'main', created_at: _now(), updated_at: _now(), present: true };
    _repos.push(rec);
    return _json(rec);
  }

  const upd = path.match(/^\/admin\/repos\/([^/]+)\/update$/);
  if (method === 'POST' && upd) {
    const r = _repos.find((x) => x.name === decodeURIComponent(upd[1]));
    if (!r) return _json({ code: 'REPO_NOT_FOUND', message: '仓不存在' }, 404);
    r.updated_at = _now();
    return _json({ ...r });
  }

  const del = path.match(/^\/admin\/repos\/([^/]+)$/);
  if (method === 'DELETE' && del) {
    const name = decodeURIComponent(del[1]);
    _repos = _repos.filter((x) => x.name !== name);
    return _json({ name, deleted: true });
  }

  if (method === 'POST' && path === '/admin/repos/upload') {
    const fd = init.body;
    const name = ((fd && fd.get && fd.get('name')) || '').trim();
    const file = fd && fd.get && fd.get('file');
    if (!_NAME_RE.test(name)) return _json({ code: 'INVALID_NAME', message: '名称非法' }, 400);
    if (!_ARCHIVE_RE.test(((file && file.name) || '').toLowerCase())) {
      return _json({ code: 'INVALID_INPUT', message: '格式不支持' }, 400);
    }
    const existing = _repos.find((r) => r.name === name);
    if (existing) { existing.updated_at = _now(); return _json({ ...existing }); }
    const rec = { name, source: 'archive', url: '', branch: '', created_at: _now(), updated_at: _now(), present: true };
    _repos.push(rec);
    return _json(rec);
  }

  return _json({ code: 'NOT_FOUND', message: '未知端点' }, 404);
}

/** selftest 复用:重置内存态。 */
export function _resetRepos() { _repos = []; }
