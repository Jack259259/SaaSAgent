"""真页面路径:Playwright 驱动 demo_app 表单(无 chromium 时 skip,核心测试不依赖浏览器)。"""

from __future__ import annotations

from pathlib import Path

import pytest

from sop_executor import PlaywrightUiRunner
from sop_executor.loader import load_sop_file

_REPO_ROOT = Path(__file__).parents[3]
_DEMO_HTML = Path(__file__).parent / "fixtures" / "demo_app" / "index.html"
_DEMO_SOP = _REPO_ROOT / "assets" / "sops" / "demo.create-item.yaml"


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            pw.chromium.launch(headless=True).close()
    except Exception:
        return False
    return True


@pytest.mark.skipif(
    not _chromium_available(), reason="chromium 未安装(playwright install chromium)"
)
async def test_playwright_drives_demo_form() -> None:
    sop = load_sop_file(_DEMO_SOP)
    assert sop.ui is not None
    runner = PlaywrightUiRunner()
    results, shots = await runner.run(
        sop.ui.steps, {"name": "演示条目", "amount": 100}, base_url=_DEMO_HTML.as_uri()
    )
    assert len(results) == 3 and all(r.ok for r in results)
    assert len(shots) == 3  # 每步一张截图
