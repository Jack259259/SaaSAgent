# 知识图谱 API 契约(agent-gateway /admin/kb/graph)

供前端「查看知识图谱」对齐。三只读端点,从 LightRAG 图(实体/关系)提取 nodes/edges。
鉴权复用 `require_kb_admin`(内部管理员;红线 3);`it_design` 库叠加 `is_internal` 细 ACL
(红线 5/§9.1);节点/边按租户∧标签在 rag-svc 内过滤(红线 5/9)。功能开关 `FP_KB_GRAPH`
(默认开;`=0` → 全部端点 404)。实现:`agent_gateway/kb_graph.py` + `rag_svc/graph.py`。

> 鉴权:同源 cookie/session 或 `X-User-Ctx`(测试态)。`kb ∈ {business, it_design}`,非法 → 404。
> 引擎:`FP_KB_GRAPH_ENGINE`(默认 `mock`,CI/无 LightRAG 实例;生产 `lightrag`)。

## 端点

### 1. GET `/admin/kb/graph` → `GraphData`
全图 / 子图概览。
| 参数 | 必填 | 取值 | 默认 | 说明 |
|---|---|---|---|---|
| `kb` | 是 | `business`\|`it_design` | — | 知识库 |
| `max_nodes` | 否 | 1–500 | 200 | 大图保护:超限按 degree 取 top-N,`is_truncated=true` |
| `entity_types` | 否 | CSV(如 `概念,指标`) | 全部 | 按实体类型过滤 |
| `center_entity` | 否 | 实体名 | — | 给定则返回以该实体为中心的子图(约 2 跳) |

### 2. GET `/admin/kb/graph/node/{entity_id}` → `NodeDetail`
单实体详情 + 邻居。
| 参数 | 必填 | 取值 | 默认 |
|---|---|---|---|
| `kb` | 是 | 同上 | — |
| `depth` | 否 | 1–3 | 1 |

无权 / 不存在的中心实体 → `node: null`(不经详情泄露受限实体)。

### 3. GET `/admin/kb/graph/search` → `GraphSearchResult`
实体模糊检索。
| 参数 | 必填 | 取值 | 默认 |
|---|---|---|---|
| `kb` | 是 | 同上 | — |
| `q` | 是 | 非空 | — |
| `top_k` | 否 | 1–50 | 10 |
| `search_in` | 否 | `name`\|`description`\|`both` | `name` |

## 响应模型(pydantic;字段映射 LightRAG 真实可得项)

```jsonc
// GraphNode
{
  "entity_id": "资金计划",      // LightRAG 节点 id(实体名)
  "name": "资金计划",
  "entity_type": "概念",        // = labels[0] / properties.entity_type;可 null
  "description": "…",           // 可 null
  "source": "手册/执行率口径",   // = properties.file_path;可 null
  "degree": 7,                  // best-effort(子图入射边计);可 null
  "chunk_ref": "chunk-1<SEP>…", // = properties.source_id;可 null
  "tenant_id": null,            // 租户归属;null=全局
  "acl_tags": ["public"]
}
// GraphEdge
{ "edge_id": "...", "source_id": "资金计划", "target_id": "执行率",
  "relation_type": "关联", "description": "…", "source_doc": "…",
  "tenant_id": null, "acl_tags": ["public"] }
// GraphData
{ "kb": "business", "nodes": [GraphNode], "edges": [GraphEdge],
  "stats": { "total_nodes": 12, "total_edges": 18, "entity_types": ["概念","指标"] },
  "is_truncated": false }
// NodeDetail
{ "node": GraphNode | null, "neighbors": [GraphNode], "edges": [GraphEdge] }
// GraphSearchResult
{ "entities": [GraphNode], "relations": [GraphEdge] }
```

## 错误
| 状态 | 场景 |
|---|---|
| 401 | 缺 `X-User-Ctx` |
| 403 | 非内部管理员;或非内部角色访 `it_design` |
| 404 | 非法 `kb`;或 `FP_KB_GRAPH=0`(端点隐藏) |
| 422 | `max_nodes`/`depth`/`top_k` 越界、`search_in` 非法、`q` 为空 |

## 备注(现状)
- **默认 Mock 引擎**:返回虚构资金计划领域 fixture(无真实业务内容),供前端联调 / CI;
  生产切 `lightrag` 后从真实图取数(需先 ingest 建图)。
- **degree / source / chunk_ref** 在真实路径为 best-effort(LightRAG 图节点无独立 degree 字段、
  file_path 取决于摄取时是否写入);前端展示需容忍 null。
- **acl_tags / tenant_id** 用于服务端过滤;真实 LightRAG 图原生不带,详见
  `docs/integration/backend-gaps.md §I` 与 `rag_svc/graph.py`。
