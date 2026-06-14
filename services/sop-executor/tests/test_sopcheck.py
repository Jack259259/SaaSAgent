"""make sop-validate 的校验:demo 通过;三类坏例(占位符、confirm 不一致、缺 api+ui)报错。"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from sop_executor.loader import load_raw
from sop_executor.sopcheck import check_sop

_REPO_ROOT = Path(__file__).parents[3]
_SCHEMA = load_raw(_REPO_ROOT / "contracts" / "sop" / "_schema.yaml")
_DEMO = load_raw(_REPO_ROOT / "assets" / "sops" / "demo.create-item.yaml")


def _demo_copy() -> dict[str, Any]:
    return copy.deepcopy(_DEMO)


def test_demo_sop_passes() -> None:
    assert check_sop(_demo_copy(), _SCHEMA) == []


def test_undefined_placeholder_rejected() -> None:
    raw = _demo_copy()
    raw["api"]["calls"][0]["body"] = {"name": "{{not_an_input}}"}
    assert any("未在 inputs" in e for e in check_sop(raw, _SCHEMA))


def test_unbalanced_braces_rejected() -> None:
    raw = _demo_copy()
    raw["api"]["calls"][0]["body"] = {"name": "{{name"}
    assert any("未闭合" in e for e in check_sop(raw, _SCHEMA))


def test_confirm_inconsistent_rejected() -> None:
    raw = _demo_copy()
    raw["requires_confirmation"] = False  # ui 仍有 confirm:true 步 → 不一致
    assert any("confirm" in e for e in check_sop(raw, _SCHEMA))


def test_missing_api_and_ui_rejected() -> None:
    raw = _demo_copy()
    del raw["api"]
    del raw["ui"]
    assert check_sop(raw, _SCHEMA)  # schema anyOf(api|ui)失败
