"""find_sop:按 aliases 倒排检索。"""

from __future__ import annotations

from pathlib import Path

import httpx

from sop_executor import HttpCaller, SopService
from sop_executor.demo_mock import DemoMockApp

_SOPS_DIR = Path(__file__).parents[3] / "assets" / "sops"


def _service() -> SopService:
    http = HttpCaller(
        httpx.AsyncClient(transport=httpx.ASGITransport(app=DemoMockApp()), base_url="http://mock")
    )
    return SopService.open(sops_dir=_SOPS_DIR, http=http)


def test_find_by_alias() -> None:
    matches = _service().find_sop("创建条目")
    assert matches and matches[0].id == "demo.create-item"


def test_find_by_english_alias() -> None:
    assert any(m.id == "demo.create-item" for m in _service().find_sop("create item"))


def test_find_no_match() -> None:
    assert _service().find_sop("zzznomatchzzz") == []
