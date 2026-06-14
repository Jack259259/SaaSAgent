"""UI 步骤执行器(无 api 的步骤走此)。

FakeUiRunner:测试用,记录动作不开浏览器(hermetic)。
PlaywrightUiRunner:chromium headless 单实例(池化 TODO),逐步 fill/click 并截图。
执行期纯确定性:按 SOP 步骤定义动作,无 LLM。
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from .models import StepResult, UiStep
from .templating import resolve


class UiStepRunner(Protocol):
    async def run(
        self, steps: list[UiStep], context: dict[str, Any], *, base_url: str
    ) -> tuple[list[StepResult], dict[str, bytes]]: ...


def _selector(target: dict[str, str]) -> str:
    if "testid" in target:
        return f'[data-testid="{target["testid"]}"]'
    if "name" in target:
        return f'[name="{target["name"]}"]'
    if "role" in target:
        return target["role"]
    raise ValueError("ui 步缺少可用 target(testid/name/role)")


class FakeUiRunner:
    """不开浏览器的确定性替身;记录解析后的动作供断言。"""

    def __init__(self) -> None:
        self.actions: list[tuple[str, str, str | None]] = []

    async def run(
        self, steps: list[UiStep], context: dict[str, Any], *, base_url: str
    ) -> tuple[list[StepResult], dict[str, bytes]]:
        results: list[StepResult] = []
        for step in steps:
            value = resolve(step.value, context) if step.value is not None else None
            self.actions.append((step.action, _selector(step.target), value))
            results.append(
                StepResult(kind="ui", name=step.instruction[:60], ok=True, detail=step.action)
            )
        return results, {}


class PlaywrightUiRunner:
    """chromium headless。同步 API 置于 to_thread,避免 async/greenlet 纠缠。"""

    def __init__(self, *, headless: bool = True) -> None:
        self._headless = headless

    async def run(
        self, steps: list[UiStep], context: dict[str, Any], *, base_url: str
    ) -> tuple[list[StepResult], dict[str, bytes]]:
        return await asyncio.to_thread(self._run_sync, steps, context, base_url)

    def _run_sync(
        self, steps: list[UiStep], context: dict[str, Any], base_url: str
    ) -> tuple[list[StepResult], dict[str, bytes]]:
        from playwright.sync_api import sync_playwright

        results: list[StepResult] = []
        shots: dict[str, bytes] = {}
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self._headless)
            try:
                page = browser.new_page()
                page.goto(base_url)
                for index, step in enumerate(steps):
                    selector = _selector(step.target)
                    if step.action == "fill" and step.value is not None:
                        page.fill(selector, str(resolve(step.value, context)))
                    elif step.action == "click":
                        page.click(selector)
                    shots[f"step{index}"] = page.screenshot()
                    results.append(
                        StepResult(
                            kind="ui", name=step.instruction[:60], ok=True, detail=step.action
                        )
                    )
            finally:
                browser.close()
        return results, shots
