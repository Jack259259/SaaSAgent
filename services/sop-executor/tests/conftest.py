"""sop-executor 测试夹具:加载 demo SOP。"""

from __future__ import annotations

from pathlib import Path

import pytest

from sop_executor import Sop
from sop_executor.loader import load_sop_file

REPO_ROOT = Path(__file__).parents[3]
DEMO_SOP_PATH = REPO_ROOT / "assets" / "sops" / "demo.create-item.yaml"
SCHEMA_PATH = REPO_ROOT / "contracts" / "sop" / "_schema.yaml"


@pytest.fixture
def demo_sop() -> Sop:
    return load_sop_file(DEMO_SOP_PATH)
