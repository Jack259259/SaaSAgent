// knowledge-graph.js — 知识图谱可视化(vis-network 自托管)。对接 /admin/kb/graph*(第 2 段后端)。
// 前端只读:GET 图/搜索/节点详情;统一 http 透传 user_ctx(红线 3);文本经 DOMPurify 消毒(红线 7)。
// 角色门控复用 kb.js(canManageKb / isKbInternal);IT 库切换仅 internal* 角色可见。
// 纯函数(toVisData/mergeGraph/distinctTypes/typeColorIndex/sanitizeText/debounce/canAccessIT)供 selftest,
// 不依赖 vis 真实渲染;vis 实例在面板打开时惰性创建,关闭时销毁释放内存。
import { canManageKb, isKbInternal } from './kb.js';
import { getUserCtx } from './sse.js';

export const canAccessIT = (roles) => isKbInternal(roles); // it_design 库可见性(== canAccessITDesign)

export const KG_TABS = [
  { id: 'business', label: '业务知识库', internalOnly: false },
  { id: 'it_design', label: 'IT 知识库', internalOnly: true },
];

// ---- 纯函数(供 selftest;无 DOM/vis 依赖)----
/** 实体类型 → 分类色索引(0–7,确定性哈希);色值由 --kg-cat-{i} 令牌在渲染时解析。 */
export function typeColorIndex(type) {
  const s = String(type || '');
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h % 8;
}

/** 当前图中出现的实体类型(去重升序)。 */
export function distinctTypes(nodes) {
  return [...new Set((nodes || []).map((n) => n.entity_type).filter(Boolean))].sort();
}

/** 边去重键:edge_id 优先,缺失则用端点 + 关系拼接。 */
export function edgeKey(e) {
  return e.edge_id || e.source_id + '->' + e.target_id + '->' + (e.relation_type || '');
}

/** 纯文本消毒:剥离一切 HTML(tooltip / 详情文本为不可信内容,红线 7)。 */
export function sanitizeText(s) {
  const str = String(s == null ? '' : s);
  try {
    if (typeof DOMPurify !== 'undefined') return DOMPurify.sanitize(str, { ALLOWED_TAGS: [], ALLOWED_ATTR: [] });
  } catch (e) { /* fallthrough */ }
  return str.replace(/<[^>]*>/g, '');
}

/** GraphNode(契约)→ vis 节点。resolveColor 可选(selftest 不传 → 不带颜色)。 */
export function toVisNode(node, { resolveColor } = {}) {
  const tip = [
    node.entity_type && '类型:' + node.entity_type,
    node.description && '描述:' + node.description,
    node.source && '来源:' + node.source,
  ].filter(Boolean).join('\n');
  const vn = {
    id: node.entity_id,
    label: sanitizeText(node.name || node.entity_id),
    group: node.entity_type || '未分类',
    title: sanitizeText(tip),
    _type: node.entity_type || null,
  };
  if (resolveColor) {
    const c = resolveColor(node.entity_type);
    vn.color = { background: c, border: c, highlight: { background: c, border: '#1e293b' } };
  }
  return vn;
}

/** GraphEdge(契约)→ vis 边。 */
export function toVisEdge(edge) {
  return {
    id: edgeKey(edge),
    from: edge.source_id,
    to: edge.target_id,
    label: sanitizeText(edge.relation_type || ''),
    title: sanitizeText(edge.description || edge.relation_type || ''),
    arrows: 'to',
  };
}

/** GraphData → vis {nodes, edges}。 */
export function toVisData(graph, { resolveColor } = {}) {
  return {
    nodes: (graph.nodes || []).map((n) => toVisNode(n, { resolveColor })),
    edges: (graph.edges || []).map(toVisEdge),
  };
}

/** 增量合并(展开邻居):按 entity_id / edgeKey 去重;返回合并后数组 + 新增项。 */
export function mergeGraph(curNodes, curEdges, incoming) {
  const nodes = curNodes.slice();
  const edges = curEdges.slice();
  const nodeIds = new Set(nodes.map((n) => n.entity_id));
  const edgeIds = new Set(edges.map(edgeKey));
  const addedNodes = [];
  const addedEdges = [];
  for (const n of incoming.nodes || []) {
    if (n && n.entity_id && !nodeIds.has(n.entity_id)) { nodeIds.add(n.entity_id); nodes.push(n); addedNodes.push(n); }
  }
  for (const e of incoming.edges || []) {
    const k = edgeKey(e);
    if (!edgeIds.has(k)) { edgeIds.add(k); edges.push(e); addedEdges.push(e); }
  }
  return { nodes, edges, addedNodes, addedEdges };
}

/** 去抖:burst 内只触发最后一次(供搜索 300ms)。 */
export function debounce(fn, ms) {
  let t = null;
  return function (...args) {
    if (t) clearTimeout(t);
    t = setTimeout(() => fn.apply(this, args), ms);
  };
}

// ---- 统一 http(只读 GET;带 user_ctx 透传)----
function qs(params) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') p.set(k, v);
  return p.toString();
}
async function httpGet(url) {
  const headers = {};
  const ctx = getUserCtx();
  if (ctx) headers['X-User-Ctx'] = JSON.stringify(ctx);
  const res = await fetch(url, { method: 'GET', headers });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }
  if (!res.ok) {
    const msg = (data && (data.message || data.detail)) || 'HTTP ' + res.status;
    const err = new Error(typeof msg === 'string' ? msg : 'HTTP ' + res.status);
    err.status = res.status; err.data = data;
    throw err;
  }
  return data;
}

const enc = encodeURIComponent;
export const getGraph = (kb, { maxNodes = 200, entityTypes, centerEntity } = {}) =>
  httpGet('/admin/kb/graph?' + qs({ kb, max_nodes: maxNodes, entity_types: entityTypes, center_entity: centerEntity }));
export const searchGraph = (kb, q, { topK = 10, searchIn = 'name' } = {}) =>
  httpGet('/admin/kb/graph/search?' + qs({ kb, q, top_k: topK, search_in: searchIn }));
export const getGraphNode = (kb, id, { depth = 1 } = {}) =>
  httpGet('/admin/kb/graph/node/' + enc(id) + '?' + qs({ kb, depth }));

export function kgErr(e) {
  if (!e) return '操作失败';
  if (e.status === 401) return '未登录或缺少身份信息';
  if (e.status === 403) return '无权访问(仅内部管理员;IT 库仅内部角色)';
  if (e.status === 404) return '图谱端点未启用(FP_KB_GRAPH)或后端待部署';
  return e.message || '操作失败';
}

// ---- 渲染辅助(浏览器态;selftest 不触达)----
function getCss(name, fallback) {
  try { return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback; }
  catch (e) { return fallback; }
}
function resolveTypeColors() {
  return (type) => getCss('--kg-cat-' + typeColorIndex(type), '#0d9488');
}

// vis 实例(Network/DataSet 用 #private 字段)**绝不能进 Alpine 响应式状态**——否则会被 Proxy 包裹,
// vis 访问自身私有字段时抛 "Cannot read private member..."。故置于模块作用域(单面板,够用)。
let _net = null;
let _nodesDS = null;
let _edgesDS = null;
let _debouncedSearch = null;

/** 创建知识图谱面板的 Alpine 状态与方法(由 app.js 合入根组件)。 */
export function createKnowledgeGraph() {
  return {
    kgOpen: false,
    kgKb: 'business',
    kgLoading: false,
    kgError: '',
    kgMinimized: false,
    kgFullscreen: false,
    kgRawNodes: [],
    kgRawEdges: [],
    kgStats: { total_nodes: 0, total_edges: 0, entity_types: [] },
    kgIsTruncated: false,
    kgTypes: [],
    kgHiddenTypes: [],
    kgSelected: null,
    kgDetailOpen: false,
    kgSearchQuery: '',
    kgSearchResults: [],
    kgDepth: 1,
    // 注:vis 实例(_net/_nodesDS/_edgesDS)在模块作用域,不入响应式状态(见上方说明)。

    kgAdmin() { const c = getUserCtx(); return c ? canManageKb(c.roles) : false; },
    kgCanIT() { const c = getUserCtx(); return c ? isKbInternal(c.roles) : false; },
    kgTabs() { return KG_TABS.filter((t) => !t.internalOnly || this.kgCanIT()); },

    openKnowledgeGraph(kb) {
      if (!this.kgAdmin()) return; // 双保险
      let target = kb || 'business';
      if (target === 'it_design' && !this.kgCanIT()) target = 'business';
      this.kgOpen = true; this.kgMinimized = false; this.kgFullscreen = false;
      this.kgKb = target; this.kgSelected = null; this.kgDetailOpen = false;
      this.kgSearchQuery = ''; this.kgSearchResults = []; this.kgHiddenTypes = [];
      this.loadKgGraph();
    },
    closeKnowledgeGraph() {
      if (_net) { try { _net.destroy(); } catch (e) { /* noop */ } _net = null; }
      _nodesDS = null; _edgesDS = null;
      this.kgOpen = false; this.kgDetailOpen = false;
    },
    switchKgKb(kb) {
      if (kb === 'it_design' && !this.kgCanIT()) return; // 双保险
      if (kb === this.kgKb) return;
      this.kgKb = kb; this.kgSelected = null; this.kgDetailOpen = false;
      this.kgSearchQuery = ''; this.kgSearchResults = []; this.kgHiddenTypes = [];
      this.loadKgGraph();
    },
    refreshKg() { this.kgSelected = null; this.kgDetailOpen = false; this.loadKgGraph(); },

    async loadKgGraph({ center = null } = {}) {
      this.kgLoading = true; this.kgError = '';
      try {
        const data = await getGraph(this.kgKb, { maxNodes: 200, centerEntity: center });
        this.kgRawNodes = data.nodes || [];
        this.kgRawEdges = data.edges || [];
        this.kgStats = data.stats || { total_nodes: 0, total_edges: 0, entity_types: [] };
        this.kgIsTruncated = !!data.is_truncated;
        this.kgTypes = distinctTypes(this.kgRawNodes);
        this.kgHiddenTypes = [];
        this.$nextTick(() => this._kgRender());
      } catch (e) {
        this.kgError = kgErr(e); this.kgRawNodes = []; this.kgRawEdges = [];
      } finally { this.kgLoading = false; }
    },

    _kgOptions() {
      return {
        nodes: { shape: 'dot', size: 16, borderWidth: 2, font: { color: getCss('--text', '#0f172a'), size: 13, face: 'Inter' } },
        edges: { color: { color: getCss('--kg-edge', '#94a3b8'), highlight: getCss('--accent', '#0d9488') }, font: { size: 11, align: 'middle', color: getCss('--text-muted', '#64748b'), strokeWidth: 0 }, smooth: { type: 'continuous' }, arrows: { to: { enabled: true, scaleFactor: 0.6 } } },
        physics: { enabled: true, barnesHut: { gravitationalConstant: -3000, springLength: 130, springConstant: 0.04 }, stabilization: { iterations: 150 } },
        interaction: { hover: true, tooltipDelay: 120, zoomView: true, dragView: true, dragNodes: true },
      };
    },
    _kgRender() {
      if (typeof vis === 'undefined') return; // 无 vis(如 selftest)→ 跳过渲染
      const el = this.$refs.kgCanvas;
      if (!el) return;
      const resolve = resolveTypeColors();
      const { nodes, edges } = toVisData({ nodes: this.kgRawNodes, edges: this.kgRawEdges }, { resolveColor: resolve });
      _nodesDS = new vis.DataSet(nodes);
      _edgesDS = new vis.DataSet(edges);
      if (_net) {
        _net.setData({ nodes: _nodesDS, edges: _edgesDS });
        _net.setOptions({ physics: { enabled: true } });
      } else {
        _net = new vis.Network(el, { nodes: _nodesDS, edges: _edgesDS }, this._kgOptions());
        _net.on('click', (p) => {
          if (p.nodes && p.nodes.length) this.selectKgNode(p.nodes[0]);
          else { this.kgDetailOpen = false; this.kgSelected = null; this._clearHighlight(); }
        });
        _net.on('doubleClick', (p) => { if (p.nodes && p.nodes.length) this.expandKgNode(p.nodes[0]); });
        // 大图保护:稳定后关闭 physics(停止持续计算,降 CPU)。
        _net.once('stabilizationIterationsDone', () => { try { _net.setOptions({ physics: false }); } catch (e) { /* noop */ } });
      }
      this._applyTypeVisibility();
    },

    onKgSearch() {
      if (!_debouncedSearch) _debouncedSearch = debounce((q) => this._runKgSearch(q), 300);
      const q = (this.kgSearchQuery || '').trim();
      if (!q) { this.kgSearchResults = []; return; }
      _debouncedSearch(q);
    },
    async _runKgSearch(q) {
      try { const r = await searchGraph(this.kgKb, q, { topK: 10 }); this.kgSearchResults = (r && r.entities) || []; }
      catch (e) { this.kgSearchResults = []; }
    },
    pickKgSearch(entity) {
      this.kgSearchResults = [];
      this.kgSearchQuery = entity.name || entity.entity_id;
      this.loadKgGraph({ center: entity.entity_id });
    },

    selectKgNode(id) {
      const raw = this.kgRawNodes.find((n) => n.entity_id === id);
      if (!raw) return;
      this.kgSelected = raw; this.kgDetailOpen = true;
      this.highlightSubgraph(id);
    },
    highlightSubgraph(id) {
      if (!_nodesDS) return;
      const nb = new Set([id]);
      for (const e of this.kgRawEdges) {
        if (e.source_id === id) nb.add(e.target_id);
        if (e.target_id === id) nb.add(e.source_id);
      }
      const resolve = resolveTypeColors();
      const faded = getCss('--kg-faded', '#cbd5e1');
      _nodesDS.update(this.kgRawNodes.map((n) => ({
        id: n.entity_id,
        color: nb.has(n.entity_id) ? resolve(n.entity_type) : faded,
      })));
    },
    _clearHighlight() {
      if (!_nodesDS) return;
      const resolve = resolveTypeColors();
      _nodesDS.update(this.kgRawNodes.map((n) => ({ id: n.entity_id, color: resolve(n.entity_type) })));
    },

    async expandKgNode(id) {
      this.kgError = '';
      try {
        const detail = await getGraphNode(this.kgKb, id, { depth: this.kgDepth });
        const incNodes = [];
        if (detail.node) incNodes.push(detail.node);
        for (const n of detail.neighbors || []) incNodes.push(n);
        const merged = mergeGraph(this.kgRawNodes, this.kgRawEdges, { nodes: incNodes, edges: detail.edges || [] });
        this.kgRawNodes = merged.nodes; this.kgRawEdges = merged.edges;
        this.kgTypes = distinctTypes(this.kgRawNodes);
        this.kgStats = { ...this.kgStats, total_nodes: this.kgRawNodes.length, total_edges: this.kgRawEdges.length, entity_types: this.kgTypes };
        if (_nodesDS) {
          const resolve = resolveTypeColors();
          if (merged.addedNodes.length) _nodesDS.add(merged.addedNodes.map((n) => toVisNode(n, { resolveColor: resolve })));
          if (merged.addedEdges.length) _edgesDS.add(merged.addedEdges.map(toVisEdge));
          this._applyTypeVisibility();
        }
      } catch (e) { this.kgError = kgErr(e); }
    },

    toggleKgType(type) {
      const i = this.kgHiddenTypes.indexOf(type);
      if (i >= 0) this.kgHiddenTypes.splice(i, 1);
      else this.kgHiddenTypes.push(type);
      this._applyTypeVisibility();
    },
    _applyTypeVisibility() {
      if (!_nodesDS) return;
      const hidden = new Set(this.kgHiddenTypes);
      const hiddenIds = new Set(this.kgRawNodes.filter((n) => hidden.has(n.entity_type)).map((n) => n.entity_id));
      _nodesDS.update(this.kgRawNodes.map((n) => ({ id: n.entity_id, hidden: hidden.has(n.entity_type) })));
      _edgesDS.update(this.kgRawEdges.map((e) => ({ id: edgeKey(e), hidden: hiddenIds.has(e.source_id) || hiddenIds.has(e.target_id) })));
    },

    exportKgPng() {
      try {
        const cv = _net && _net.canvas && _net.canvas.frame && _net.canvas.frame.canvas;
        if (!cv) return;
        const a = document.createElement('a');
        a.href = cv.toDataURL('image/png');
        a.download = 'knowledge-graph-' + this.kgKb + '.png';
        document.body.appendChild(a); a.click(); a.remove();
      } catch (e) { this.kgError = '导出失败'; }
    },
    toggleKgMinimize() { this.kgMinimized = !this.kgMinimized; if (!this.kgMinimized) this.$nextTick(() => { if (_net) _net.redraw(); }); },
    toggleKgFullscreen() { this.kgFullscreen = !this.kgFullscreen; this.$nextTick(() => { if (_net) _net.redraw(); }); },

    // ---- 详情面板 / 图例 辅助 ----
    kgSelectedRelations() {
      if (!this.kgSelected) return [];
      const id = this.kgSelected.entity_id;
      return this.kgRawEdges
        .filter((e) => e.source_id === id || e.target_id === id)
        .map((e) => ({ source: e.source_id, target: e.target_id, rel: e.relation_type || '关联' }));
    },
    kgTypeCounts() {
      const m = {};
      for (const n of this.kgRawNodes) { const t = n.entity_type || '未分类'; m[t] = (m[t] || 0) + 1; }
      return Object.entries(m).map(([type, count]) => ({ type, count })).sort((a, b) => a.type.localeCompare(b.type));
    },
    kgTypeColorVar(type) { return 'var(--kg-cat-' + typeColorIndex(type) + ')'; },
    kgClean(s) { return sanitizeText(s); },
    kgTabLabel(id) { const t = KG_TABS.find((x) => x.id === id); return t ? t.label : id; },
  };
}
