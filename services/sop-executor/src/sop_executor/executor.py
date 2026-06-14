"""SOP 确定性状态机(方案 §5.4)。执行期零 LLM。

流程:preconditions → (requires_confirmation 则 confirm 步暂停落盘)→ resume 后执行
(api 优先,无 api 走 ui)→ postconditions 回查 → succeeded/failed。任一步失败即停(按 on_failure),
不跳步;postconditions 失败绝不 succeeded(红线)。confirm 恢复时执行器复验确认(双闸)。
"""

from __future__ import annotations

import uuid
from typing import Any

from contracts import UserCtx

from .conditions import check_postconditions, check_preconditions, dig
from .httpcaller import HttpCaller
from .identity import mint_user_token
from .models import Confirmation, RunReport, RunState, RunStatus, Sop, StepResult
from .runstore import InMemoryRunStore, RunStore
from .steprunner import FakeUiRunner, UiStepRunner
from .templating import resolve


class SopExecutor:
    def __init__(
        self,
        *,
        http: HttpCaller,
        ui_runner: UiStepRunner | None = None,
        store: RunStore | None = None,
        base_url: str = "",
    ) -> None:
        self._http = http
        self._ui = ui_runner or FakeUiRunner()
        self._store = store or InMemoryRunStore()
        self._base_url = base_url
        self._screenshots: dict[str, dict[str, bytes]] = {}  # 临时(进程内);跨重启丢失,postgres TODO

    def get_state(self, run_id: str) -> RunState | None:
        return self._store.get(run_id)

    async def submit(self, sop: Sop, inputs: dict[str, Any], user_ctx: UserCtx) -> RunState:
        state = RunState(
            run_id=uuid.uuid4().hex,
            sop_id=sop.id,
            status=RunStatus.pending,
            inputs=inputs,
            tenant_id=user_ctx.tenant_id,
            user_id=user_ctx.user_id,
        )
        pre = check_preconditions(sop, user_ctx)
        state.steps.append(pre)
        if not pre.ok:
            return self._fail(state, sop, pre.detail)
        state.status = RunStatus.running
        # confirm 步:写操作执行前暂停,状态落盘,等编排器确认(红线 4 第一闸)。
        if sop.requires_confirmation and not state.confirmed:
            state.status = RunStatus.paused
            state.pending_confirm = Confirmation(
                run_id=state.run_id,
                prompt=f"将执行『{sop.name}』(写操作),确认?",
                action_preview=self._preview(sop, inputs),
            )
            self._store.save(state)
            return state
        return await self._execute(sop, state, user_ctx)

    async def resume(
        self, state: RunState, sop: Sop, *, confirmed: bool, user_ctx: UserCtx
    ) -> RunState:
        # 双闸:执行器复验确认凭据(红线 4 第二闸)。
        if not confirmed:
            return self._fail(state, sop, "用户取消确认")
        state.confirmed = True
        state.pending_confirm = None
        state.status = RunStatus.running
        return await self._execute(sop, state, user_ctx)

    async def _execute(self, sop: Sop, state: RunState, user_ctx: UserCtx) -> RunState:
        token = mint_user_token(user_ctx)
        context: dict[str, Any] = {**state.inputs, **state.captures}
        if sop.api is not None:
            for call in sop.api.calls:
                path = str(resolve(call.path, context))
                status, data = await self._http.call(
                    call.method, path, body=resolve(call.body, context), token=token
                )
                ok = status < 400
                state.steps.append(
                    StepResult(
                        kind="api",
                        name=f"{call.method} {call.path}",
                        ok=ok,
                        detail=f"status={status}",
                    )
                )
                if not ok:
                    return self._fail(state, sop, f"api {call.path} status={status}")
                for var, src in call.capture.items():
                    context[var] = dig(data, src)
                    state.captures[var] = context[var]
        elif sop.ui is not None:
            results, shots = await self._ui.run(sop.ui.steps, context, base_url=self._base_url)
            state.steps.extend(results)
            self._screenshots[state.run_id] = shots
            if any(not r.ok for r in results):
                return self._fail(state, sop, "ui 步执行失败")

        post = await check_postconditions(sop, self._http, token, context)
        state.steps.append(post)
        if not post.ok:
            return self._fail(state, sop, f"postcondition: {post.detail}")
        state.status = RunStatus.succeeded
        self._store.save(state)
        return state

    def _fail(self, state: RunState, sop: Sop, reason: str) -> RunState:
        state.status = RunStatus.failed
        state.failure_hint = self._hint(sop, reason) or reason
        self._store.save(state)
        return state

    @staticmethod
    def _hint(sop: Sop, reason: str) -> str | None:
        for rule in sop.on_failure:
            if rule.when == "*" or rule.when in reason:
                return rule.hint
        return None

    @staticmethod
    def _preview(sop: Sop, inputs: dict[str, Any]) -> str:
        return f"{sop.postconditions.human_readable};参数={inputs}"

    def report(self, state: RunState) -> RunReport:
        return RunReport(
            run_id=state.run_id,
            sop_id=state.sop_id,
            status=state.status,
            steps=state.steps,
            screenshots=sorted(self._screenshots.get(state.run_id, {})),
            failure_hint=state.failure_hint,
            message=sop_message(state),
        )


def sop_message(state: RunState) -> str:
    if state.status == RunStatus.succeeded:
        return "SOP 执行成功,postconditions 回查通过。"
    if state.status == RunStatus.paused:
        return "SOP 暂停,等待用户确认写操作。"
    if state.status == RunStatus.failed:
        return f"SOP 执行失败:{state.failure_hint or '未知原因'}"
    return f"SOP 状态:{state.status.value}"
