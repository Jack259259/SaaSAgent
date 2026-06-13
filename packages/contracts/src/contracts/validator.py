"""校验器:用 jsonschema(Draft 2020-12)直接对着 schema 文件校验实例。

跨文件 $ref(如 audit.json 引用 toolspec 的 errorCode 枚举)经 referencing.Registry
按各 schema 的 $id 解析,从而保持错误码等"单一事实源"。
"""

from __future__ import annotations

from functools import cache
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from .loader import load_all_schemas, load_schema


class ContractValidationError(ValueError):
    """契约校验失败(聚合全部错误,信息可读)。"""

    def __init__(self, kind: str, messages: list[str]) -> None:
        self.kind = kind
        self.messages = messages
        body = "\n".join(f"  - {m}" for m in messages)
        super().__init__(f"{kind} 契约校验失败:\n{body}")


@cache
def _registry() -> Registry[Any]:
    """以各 schema 的 $id 为键构建引用注册表,支撑跨文件 $ref。"""
    resources: list[tuple[str, Resource[Any]]] = []
    for doc in load_all_schemas().values():
        uri = doc.get("$id")
        if isinstance(uri, str):
            resources.append((uri, Resource.from_contents(doc, default_specification=DRAFT202012)))
    return Registry().with_resources(resources)


def _validate(kind: str, schema: dict[str, Any], instance: dict[str, Any]) -> None:
    validator = Draft202012Validator(schema, registry=_registry())
    errors = sorted(
        validator.iter_errors(instance), key=lambda e: [str(p) for p in e.absolute_path]
    )
    if errors:
        messages = [
            f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors
        ]
        raise ContractValidationError(kind, messages)


def validate_toolspec(instance: dict[str, Any]) -> None:
    _validate("toolspec", load_schema("toolspec"), instance)


def validate_envelope(instance: dict[str, Any]) -> None:
    _validate("envelope", load_schema("envelope"), instance)


def validate_agent_state(instance: dict[str, Any]) -> None:
    _validate("agent_state", load_schema("agent_state"), instance)


def validate_audit(instance: dict[str, Any]) -> None:
    _validate("audit", load_schema("audit"), instance)


def validate_sop(instance: dict[str, Any]) -> None:
    _validate("sop", load_schema("sop"), instance)
