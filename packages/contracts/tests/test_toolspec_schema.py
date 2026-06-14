"""工具规格契约测试:21 份合法 + 红线 4 不变式 + I/O schema 自身合法。"""

from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator

from contracts.loader import iter_toolspec_paths, load_doc, load_toolspecs
from contracts.models import SideEffect
from contracts.validator import ContractValidationError, validate_toolspec


def test_all_toolspecs_load_and_valid() -> None:
    specs = load_toolspecs()
    # 5 领域 + 18 基础(阶段 9a 新增 search_memory / load_skill)。
    assert len(specs) == 23, "应为 5 领域 + 18 基础 = 23 份"
    names = [ls.spec.name for ls in specs]
    assert len(set(names)) == 23, "工具名必须全局唯一"


def test_io_schemas_are_themselves_valid_jsonschema() -> None:
    for ls in load_toolspecs():
        Draft202012Validator.check_schema(ls.spec.input_schema)
        Draft202012Validator.check_schema(ls.spec.output_schema)


def test_redline4_business_write_requires_confirmation() -> None:
    for ls in load_toolspecs():
        if ls.spec.side_effects is SideEffect.write:
            assert ls.spec.confirmation_required is True, f"{ls.spec.name}: 业务写必须确认(红线 4)"


def test_redline4_write_without_confirmation_is_rejected() -> None:
    # 取 run_sop 原文,篡改为 write + confirmation_required=false,应被 schema 的 if/then 拒绝。
    path = next(p for p in iter_toolspec_paths() if p.name == "run_sop.yaml")
    raw = load_doc(path)
    raw["confirmation_required"] = False
    with pytest.raises(ContractValidationError):
        validate_toolspec(raw)


def test_unknown_error_code_is_rejected() -> None:
    path = next(p for p in iter_toolspec_paths() if p.name == "query_finance_data.yaml")
    raw = load_doc(path)
    raw["errors"] = ["NOT_A_REAL_CODE"]
    with pytest.raises(ContractValidationError):
        validate_toolspec(raw)


def test_web_tools_disabled_by_default() -> None:
    by_name = {ls.spec.name: ls.spec for ls in load_toolspecs()}
    assert by_name["web_search"].enabled_by_default is False
    assert by_name["web_fetch"].enabled_by_default is False


def test_run_sop_is_business_write_and_confirmed() -> None:
    by_name = {ls.spec.name: ls.spec for ls in load_toolspecs()}
    assert by_name["run_sop"].side_effects is SideEffect.write
    assert by_name["run_sop"].confirmation_required is True


def test_assistant_write_tools_present() -> None:
    by_name = {ls.spec.name: ls.spec for ls in load_toolspecs()}
    for name in ("write_workspace", "save_memory", "schedule_task", "notify", "escalate_to_human"):
        assert by_name[name].side_effects is SideEffect.assistant_write, name
