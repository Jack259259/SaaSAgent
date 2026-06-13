"""模型 ↔ schema 一致性(要求 8):pydantic 模型字段集/必填集必须与对应 JSON Schema 一致。

这是"schema 为唯一事实源"的防漂移闸:任一方改了字段而另一方未跟进即失败。
只比较顶层属性名集合与必填名集合(不比嵌套类型,避免脆弱)。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel

from contracts.loader import load_schema
from contracts.models import (
    AgentState,
    AuditEvent,
    Sop,
    ToolInvocation,
    ToolSpec,
    UserCtx,
)


def _schema_props_required(schema: dict[str, Any]) -> tuple[set[str], set[str]]:
    props = set(schema.get("properties", {}).keys())
    required = set(schema.get("required", []))
    return props, required


def _model_props_required(model: type[BaseModel]) -> tuple[set[str], set[str]]:
    js = model.model_json_schema()
    props = set(js.get("properties", {}).keys())
    required = set(js.get("required", []))
    return props, required


# (模型, 取对应 schema 字典的函数, 说明)
_CASES: list[tuple[type[BaseModel], Callable[[], dict[str, Any]], str]] = [
    (ToolSpec, lambda: load_schema("toolspec"), "ToolSpec"),
    (ToolInvocation, lambda: load_schema("envelope"), "ToolInvocation/envelope"),
    (UserCtx, lambda: load_schema("envelope")["$defs"]["userCtx"], "UserCtx"),
    (AgentState, lambda: load_schema("agent_state"), "AgentState"),
    (AuditEvent, lambda: load_schema("audit"), "AuditEvent"),
    (Sop, lambda: load_schema("sop"), "Sop"),
]


@pytest.mark.parametrize(("model", "get_schema", "label"), _CASES, ids=[c[2] for c in _CASES])
def test_property_names_match(
    model: type[BaseModel], get_schema: Callable[[], dict[str, Any]], label: str
) -> None:
    m_props, _ = _model_props_required(model)
    s_props, _ = _schema_props_required(get_schema())
    assert m_props == s_props, f"{label}: 属性集合不一致 model={m_props} schema={s_props}"


@pytest.mark.parametrize(("model", "get_schema", "label"), _CASES, ids=[c[2] for c in _CASES])
def test_required_names_match(
    model: type[BaseModel], get_schema: Callable[[], dict[str, Any]], label: str
) -> None:
    _, m_req = _model_props_required(model)
    _, s_req = _schema_props_required(get_schema())
    assert m_req == s_req, f"{label}: 必填集合不一致 model={m_req} schema={s_req}"
