"""知识图谱查询端点(/admin/kb/graph;只读)。

三只读端点对标既有 /admin/kb/*:鉴权复用 ``require_kb_admin``(红线 3);it_design 库叠加
``is_internal`` 细 ACL(红线 5/§9.1);user_ctx 透传 RagService(图节点/边的租户∧标签过滤在
rag-svc 内完成,红线 5/9)。功能开关 ``FP_KB_GRAPH``(默认开;="0" → 端点 404 完全隐藏,
图查询只读、风险低,故默认开而非默认关)。每次查询审计。

入参校验:kb 枚举(非法 404)、max_nodes 1–500、depth 1–3、top_k 1–50、
search_in ∈ {name, description, both}。
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from contracts import UserCtx
from contracts.models import ResultStatus
from orchestrator import emit_audit, who_from_user_ctx
from rag_svc import GraphData, GraphSearchResult, NodeDetail, RagService
from rag_svc import acl as rag_acl

from .auth import get_trace_id, require_kb_admin
from .deps import get_kb_graph_service

router = APIRouter()

_VALID_KBS = (rag_acl.KB_BUSINESS, rag_acl.KB_IT_DESIGN)


def require_graph_enabled() -> None:
    """功能开关(默认开;FP_KB_GRAPH=0 → 404 隐藏)。作为首个依赖,未开则先于鉴权返回 404。"""
    if os.environ.get("FP_KB_GRAPH", "1") == "0":
        raise HTTPException(status_code=404, detail="kb graph disabled")


def _audit(user_ctx: UserCtx, trace_id: str, action: str, status: ResultStatus) -> None:
    emit_audit(
        who=who_from_user_ctx(user_ctx),
        tool=f"kb_admin:graph:{action}",
        args_digest="-",  # 不记实体名/查询原文(§6)
        result_status=status,
        trace_id=trace_id,
    )


def _check_kb(kb: str, user_ctx: UserCtx, trace_id: str) -> None:
    """kb 枚举校验 + it_design 细 ACL(仅内部角色,红线 5/§9.1)。"""
    if kb not in _VALID_KBS:
        raise HTTPException(status_code=404, detail="未知知识库")
    if kb == rag_acl.KB_IT_DESIGN and not rag_acl.is_internal(user_ctx):
        _audit(user_ctx, trace_id, "access_it_design", ResultStatus.denied)
        raise HTTPException(status_code=403, detail="IT 设计库仅内部角色可访问")


@router.get("/admin/kb/graph")
async def kb_graph(
    _enabled: Annotated[None, Depends(require_graph_enabled)],
    user_ctx: Annotated[UserCtx, Depends(require_kb_admin)],
    trace_id: Annotated[str, Depends(get_trace_id)],
    service: Annotated[RagService, Depends(get_kb_graph_service)],
    kb: Annotated[str, Query()],
    max_nodes: Annotated[int, Query(ge=1, le=500)] = 200,
    entity_types: Annotated[str | None, Query()] = None,
    center_entity: Annotated[str | None, Query()] = None,
) -> GraphData:
    _check_kb(kb, user_ctx, trace_id)
    types = [t.strip() for t in entity_types.split(",") if t.strip()] if entity_types else None
    data = await service.get_graph(
        user_ctx, kb, entity_types=types, max_nodes=max_nodes, center_entity=center_entity
    )
    _audit(user_ctx, trace_id, "graph", ResultStatus.ok)
    return data


@router.get("/admin/kb/graph/node/{entity_id}")
async def kb_graph_node(
    _enabled: Annotated[None, Depends(require_graph_enabled)],
    entity_id: str,
    user_ctx: Annotated[UserCtx, Depends(require_kb_admin)],
    trace_id: Annotated[str, Depends(get_trace_id)],
    service: Annotated[RagService, Depends(get_kb_graph_service)],
    kb: Annotated[str, Query()],
    depth: Annotated[int, Query(ge=1, le=3)] = 1,
) -> NodeDetail:
    _check_kb(kb, user_ctx, trace_id)
    detail = await service.get_node(user_ctx, kb, entity_id, depth=depth)
    _audit(user_ctx, trace_id, "node", ResultStatus.ok)
    return detail


@router.get("/admin/kb/graph/search")
async def kb_graph_search(
    _enabled: Annotated[None, Depends(require_graph_enabled)],
    user_ctx: Annotated[UserCtx, Depends(require_kb_admin)],
    trace_id: Annotated[str, Depends(get_trace_id)],
    service: Annotated[RagService, Depends(get_kb_graph_service)],
    kb: Annotated[str, Query()],
    q: Annotated[str, Query(min_length=1)],
    top_k: Annotated[int, Query(ge=1, le=50)] = 10,
    search_in: Annotated[str, Query(pattern="^(name|description|both)$")] = "name",
) -> GraphSearchResult:
    _check_kb(kb, user_ctx, trace_id)
    result = await service.search_graph_nodes(user_ctx, kb, q, top_k=top_k, search_in=search_in)
    _audit(user_ctx, trace_id, "search", ResultStatus.ok)
    return result
