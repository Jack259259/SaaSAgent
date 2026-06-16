// mock-skills.js — 开发期 mock 的 Skill 管理端点(由 mock-sse.js 在 mock 模式下分发 /skills*)。
// 仅前端联调用;真实后端的 CRUD + 鉴权 + 安全解压见 docs/integration/backend-gaps.md(E)。

let _seq = 100;
const nid = () => 'sk-' + (++_seq);

function mk(name, description, status, body) {
  return {
    id: nid(), name, description, status,
    updated_at: Date.now() - Math.floor(Math.random() * 5) * 86400000,
    content: `---\nname: ${name}\ndescription: ${description}\n---\n\n${body}`,
  };
}

const store = [
  mk('fund-plan-helper', '资金计划编制与复核要点', 'active', '# 用法\n\n指导按月滚动编制资金计划,核对经营 / 投资 / 筹资分类。\n\n- 步骤一:取数\n- 步骤二:核对'),
  mk('kb-search-tips', '知识库检索技巧(草稿)', 'draft', '# 用法\n\n如何高效检索资金制度与口径。'),
];

const META = (s) => ({ id: s.id, name: s.name, description: s.description, status: s.status, updated_at: s.updated_at });

function jsonResponse(status, obj) {
  return new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json' } });
}

// 模拟后端 SKILL.md schema 校验(前端无法替代;仅供联调展示失败路径)。
function schemaErrors(content) {
  const c = content || '';
  const errs = [];
  if (!/^---\s*\n/.test(c)) errs.push('缺少 YAML frontmatter(--- 开头)');
  if (!/(^|\n)name:\s*\S+/.test(c)) errs.push('frontmatter 缺少 name');
  if (!/(^|\n)description:\s*\S+/.test(c)) errs.push('frontmatter 缺少 description');
  return errs;
}
function descOf(content) { const m = /(^|\n)description:\s*(.+)/.exec(content || ''); return m ? m[2].trim() : ''; }
function parseBody(init) { try { return JSON.parse(init.body || '{}'); } catch (e) { return {}; } }

function create(b) {
  const errs = schemaErrors(b.content);
  if (errs.length) return jsonResponse(422, { message: 'SKILL.md schema 校验失败', errors: errs });
  const s = { id: nid(), name: b.name || '(未命名)', description: descOf(b.content), status: 'draft', updated_at: Date.now(), content: b.content || '' };
  store.unshift(s);
  return jsonResponse(201, META(s));
}
function update(id, b) {
  const s = store.find((x) => x.id === id);
  if (!s) return jsonResponse(404, { message: '未找到' });
  const errs = schemaErrors(b.content);
  if (errs.length) return jsonResponse(422, { message: 'SKILL.md schema 校验失败', errors: errs });
  s.name = b.name || s.name; s.content = b.content || s.content; s.description = descOf(b.content) || s.description;
  s.status = 'draft'; s.updated_at = Date.now(); // 编辑回草稿待审(D5)
  return jsonResponse(200, META(s));
}
function setStatus(id, b) {
  const s = store.find((x) => x.id === id);
  if (!s) return jsonResponse(404, { message: '未找到' });
  s.status = b.status === 'active' ? 'active' : 'draft';
  s.updated_at = Date.now();
  return jsonResponse(200, META(s));
}
function upload(formData) {
  let name = 'pack.zip';
  try { const f = formData && formData.get && formData.get('file'); if (f) name = f.name || name; } catch (e) { /* ignore */ }
  if (/invalid|bad/i.test(name)) return jsonResponse(400, { message: 'zip 非法或解压失败(zip slip / 结构白名单校验未过)' });
  // 模拟逐条解压入库结果(多条成功入草稿 + 1 条拒绝)
  ['finance-plan-helper', 'kb-search-tips'].forEach((n) => store.unshift({ id: nid(), name: n, description: '来自上传包', status: 'draft', updated_at: Date.now(), content: `---\nname: ${n}\ndescription: 来自上传包\n---\n\n# 用法\n` }));
  return jsonResponse(200, {
    results: [
      { name: 'finance-plan-helper', ok: true, status: 'draft' },
      { name: 'kb-search-tips', ok: true, status: 'draft' },
      { name: 'broken-skill', ok: false, reason: 'SKILL.md 缺失(结构白名单校验失败)' },
    ],
  });
}

/** 分发 /skills* 请求 → Response;非 /skills 路由返回 null(由调用方继续)。 */
export function handleSkills(method, path, init) {
  if (!path.startsWith('/skills')) return null;
  if (path === '/skills') {
    if (method === 'GET') return jsonResponse(200, store.map(META));
    if (method === 'POST') return create(parseBody(init));
  }
  if (path === '/skills/upload' && method === 'POST') return upload(init.body);
  const mStatus = /^\/skills\/([^/]+)\/status$/.exec(path);
  if (mStatus && method === 'POST') return setStatus(decodeURIComponent(mStatus[1]), parseBody(init));
  const mId = /^\/skills\/([^/]+)$/.exec(path);
  if (mId) {
    const id = decodeURIComponent(mId[1]);
    if (method === 'GET') { const s = store.find((x) => x.id === id); return s ? jsonResponse(200, s) : jsonResponse(404, { message: '未找到' }); }
    if (method === 'PUT') return update(id, parseBody(init));
    if (method === 'DELETE') { const i = store.findIndex((x) => x.id === id); if (i >= 0) store.splice(i, 1); return jsonResponse(200, { ok: true }); }
  }
  return jsonResponse(404, { message: '未找到' });
}
