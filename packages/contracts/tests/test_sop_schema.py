"""SOP 资产 schema 契约测试:正反例(附录 B)。"""

from __future__ import annotations

from pathlib import Path

import pytest

from contracts.loader import load_doc
from contracts.models import Sop
from contracts.validator import ContractValidationError, validate_sop

_FIX = Path(__file__).parent / "fixtures"


def test_sop_valid() -> None:
    doc = load_doc(_FIX / "sop_valid.yaml")
    validate_sop(doc)
    Sop.model_validate(doc)


def test_sop_invalid_rejected() -> None:
    doc = load_doc(_FIX / "sop_invalid.yaml")
    with pytest.raises(ContractValidationError):
        validate_sop(doc)


def test_sop_requires_api_or_ui() -> None:
    # 合法 SOP 删去 api 且无 ui → 违反 anyOf
    doc = load_doc(_FIX / "sop_valid.yaml")
    del doc["api"]
    with pytest.raises(ContractValidationError):
        validate_sop(doc)


def test_sop_missing_postconditions_rejected() -> None:
    doc = load_doc(_FIX / "sop_valid.yaml")
    del doc["postconditions"]
    with pytest.raises(ContractValidationError):
        validate_sop(doc)
