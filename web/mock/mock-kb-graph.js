// mock-kb-graph.js — 开发期 mock 的知识图谱端点(由 mock-sse.js 在 handleKb **之前**分发 /admin/kb/graph*)。
// 纯内存虚构图(资金计划领域,无真实业务内容),演示全流程 + 供 selftest。
// 真实后端见 agent-gateway /admin/kb/graph*(第 2 段)。字段对齐 docs/integration/knowledge-graph-api.md。
//
// ⚠ 必须先于 mock-kb.js 的 handleKb 分发:handleKb 的正则会把 /admin/kb/graph* 误当 kb="graph" 而 404。

const _INTERNAL_ROLES = ['internal', 'internal_support', 'internal_dev'];

function _json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}
function _rolesOf(init) {
  try {
    const h = (init && init.headers) || {};
    const raw = h['X-User-Ctx'] || h['x-user-ctx'];
    return raw ? (JSON.parse(raw).roles || []) : null;
  } catch (e) { return null; }
}
const _isInternal = (roles) => Array.isArray(roles) && roles.some((r) => _INTERNAL_ROLES.includes(r));

const _node = (id, type, desc) => ({
  entity_id: id, name: id, entity_type: type, description: desc,
  source: 'fixture://知识库/示例文档', degree: null, chunk_ref: 'fixture-chunk',
  tenant_id: null, acl_tags: ['public'],
});
const _edge = (s, t, rel) => ({
  edge_id: s + '->' + t, source_id: s, target_id: t, relation_type: rel,
  description: s + ' ' + rel + ' ' + t, source_doc: 'fixture://知识库/示例文档',
  tenant_id: null, acl_tags: ['public'],
});

// business:多类型连通图(hub=资金计划)。
const _BUSINESS_NODES = [
  _node('资金计划', '概念', '企业对未来资金收支的预测与安排'),
  _node('执行率', '指标', '实际执行与计划的比率'),
  _node('现金流量表', '报表', '经营/投资/筹资现金流'),
  _node('滚动预测', '方法', '逐月滚动测算资金缺口'),
  _node('授信额度', '概念', '银行授予的可用融资额度'),
  _node('资金调度', '方法', '集团内资金归集与调拨'),
  _node('偏差分析', '方法', '实际与计划差异按科目归因'),
  _node('月度报表', '报表', '逐月资金计划汇总'),
];
const _BUSINESS_EDGES = [
  _edge('资金计划', '执行率', '关联'),
  _edge('资金计划', '现金流量表', '包含'),
  _edge('资金计划', '滚动预测', '使用'),
  _edge('资金计划', '授信额度', '涉及'),
  _edge('资金计划', '资金调度', '驱动'),
  _edge('执行率', '偏差分析', '触发'),
  _edge('偏差分析', '滚动预测', '修正'),
  _edge('月度报表', '资金计划', '汇总'),
];
// it_design:仅内部可见。
const _IT_NODES = [
  _node('对账服务设计', '设计', '资金对账服务接口设计'),
  _node('数据模型', '设计', '资金计划核心数据模型'),
  _node('集成网关', '设计', '业务系统集成网关'),
];
const _IT_EDGES = [
  _edge('对账服务设计', '数据模型', '依赖'),
  _edge('集成网关', '对账服务设计', '调用'),
];
// 展开邻居用:资金计划 的额外邻居(含与现图重叠的"资金调度"→测增量去重)。
const _EXPAND = {
  资金计划: {
    nodes: [_node('融资计划', '概念', '债务与权益融资安排'), _node('资金调度', '方法', '集团内资金归集与调拨')],
    edges: [_edge('资金计划', '融资计划', '衍生'), _edge('资金计划', '资金调度', '驱动')],
  },
};

function _kbData(kb) {
  if (kb === 'business') return { nodes: _BUSINESS_NODES, edges: _BUSINESS_EDGES };
  if (kb === 'it_design') return { nodes: _IT_NODES, edges: _IT_EDGES };
  return null;
}
function _stats(nodes, edges) {
  return {
    total_nodes: nodes.length,
    total_edges: edges.length,
    entity_types: [...new Set(nodes.map((n) => n.entity_type).filter(Boolean))].sort(),
  };
}
function _subgraph(data, center) {
  const keep = new Set([center]);
  for (const e of data.edges) { if (e.source_id === center) keep.add(e.target_id); if (e.target_id === center) keep.add(e.source_id); }
  const nodes = data.nodes.filter((n) => keep.has(n.entity_id));
  const ids = new Set(nodes.map((n) => n.entity_id));
  const edges = data.edges.filter((e) => ids.has(e.source_id) && ids.has(e.target_id));
  return { nodes, edges };
}

/** mock 分发:命中 /admin/kb/graph* 返回 Response,否则 null(透传给 handleKb 等)。
 *  入参 url 为**完整 url(含 query)**(由 mock-sse 传入),内部自行解析 pathname + searchParams。 */
export function handleKbGraph(method, url, init) {
  let u;
  try { u = new URL(url, 'http://x'); } catch (e) { return null; }
  const path = u.pathname;
  if (!(path === '/admin/kb/graph' || path.startsWith('/admin/kb/graph/'))) return null;
  if (method !== 'GET') return _json({ detail: '未知端点' }, 404);
  const roles = _rolesOf(init);
  if (roles === null) return _json({ detail: '缺少身份' }, 401);
  return _dispatch(path, u.searchParams, roles);
}

function _dispatch(path, q, roles) {
  const kb = q.get('kb') || '';
  if (kb !== 'business' && kb !== 'it_design') return _json({ detail: '未知知识库' }, 404);
  if (kb === 'it_design' && !_isInternal(roles)) return _json({ detail: 'IT 库仅内部角色' }, 403);
  const data = _kbData(kb);

  // GET /admin/kb/graph
  if (path === '/admin/kb/graph') {
    const maxNodes = parseInt(q.get('max_nodes') || '200', 10);
    const center = q.get('center_entity');
    const types = (q.get('entity_types') || '').split(',').map((s) => s.trim()).filter(Boolean);
    let { nodes, edges } = center ? _subgraph(data, center) : { nodes: data.nodes.slice(), edges: data.edges.slice() };
    if (types.length) { nodes = nodes.filter((n) => types.includes(n.entity_type)); const ids = new Set(nodes.map((n) => n.entity_id)); edges = edges.filter((e) => ids.has(e.source_id) && ids.has(e.target_id)); }
    const isTrunc = nodes.length > maxNodes;
    if (isTrunc) { nodes = nodes.slice(0, maxNodes); const ids = new Set(nodes.map((n) => n.entity_id)); edges = edges.filter((e) => ids.has(e.source_id) && ids.has(e.target_id)); }
    return _json({ kb, nodes, edges, stats: _stats(nodes, edges), is_truncated: isTrunc });
  }

  // GET /admin/kb/graph/search
  if (path === '/admin/kb/graph/search') {
    const term = (q.get('q') || '').trim().toLowerCase();
    const searchIn = q.get('search_in') || 'name';
    const hit = (n) => {
      const inName = n.entity_id.toLowerCase().includes(term);
      const inDesc = (n.description || '').toLowerCase().includes(term);
      return searchIn === 'description' ? inDesc : searchIn === 'both' ? inName || inDesc : inName;
    };
    const entities = term ? data.nodes.filter(hit).slice(0, parseInt(q.get('top_k') || '10', 10)) : [];
    return _json({ entities, relations: [] });
  }

  // GET /admin/kb/graph/node/{id}
  const m = path.match(/^\/admin\/kb\/graph\/node\/(.+)$/);
  if (m) {
    const id = decodeURIComponent(m[1]);
    const node = data.nodes.find((n) => n.entity_id === id) || null;
    if (!node) return _json({ node: null, neighbors: [], edges: [] });
    const base = _subgraph(data, id);
    const extra = _EXPAND[id] || { nodes: [], edges: [] };
    const neighbors = base.nodes.filter((n) => n.entity_id !== id).concat(extra.nodes);
    return _json({ node, neighbors, edges: base.edges.concat(extra.edges) });
  }

  return _json({ detail: '未知端点' }, 404);
}

/** selftest 复用(当前无内存可变态;留作对齐其他 mock 的接口)。 */
export function _resetKbGraph() { /* 纯静态 fixture,无需重置 */ }
