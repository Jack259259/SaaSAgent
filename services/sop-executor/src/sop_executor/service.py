"""SopService:find_sop(别名倒排)+ submit/resume 门面 + 运行报告。"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from contracts import UserCtx

from .executor import SopExecutor
from .httpcaller import HttpCaller
from .loader import load_sops
from .models import RunReport, RunState, Sop, SopMatch
from .steprunner import UiStepRunner

_TOKEN_RE = re.compile(r"[a-z0-9]+|[一-鿿]")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _index_tokens(sop: Sop) -> set[str]:
    toks = _tokens(sop.id) | _tokens(sop.name)
    for alias in sop.aliases:
        toks |= _tokens(alias)
    return toks


class SopService:
    def __init__(self, *, sops: dict[str, Sop], executor: SopExecutor) -> None:
        self._sops = sops
        self._executor = executor
        self._index: dict[str, set[str]] = {sid: _index_tokens(s) for sid, s in sops.items()}

    @classmethod
    def open(
        cls,
        *,
        sops_dir: Path = Path("assets/sops"),
        http: HttpCaller | None = None,
        ui_runner: UiStepRunner | None = None,
        page_base_url: str = "",
    ) -> SopService:
        caller = http or HttpCaller.for_base_url(
            os.environ.get("BUSINESS_API_URL", "http://localhost")
        )
        executor = SopExecutor(http=caller, ui_runner=ui_runner, base_url=page_base_url)
        return cls(sops=load_sops(sops_dir), executor=executor)

    def find_sop(self, query: str, *, top_k: int = 5) -> list[SopMatch]:
        q = _tokens(query)
        if not q:
            return []
        scored: list[SopMatch] = []
        for sid, toks in self._index.items():
            overlap = len(q & toks)
            if overlap:
                scored.append(SopMatch(id=sid, name=self._sops[sid].name, score=overlap / len(q)))
        scored.sort(key=lambda m: (-m.score, m.id))
        return scored[:top_k]

    async def submit(self, sop_id: str, inputs: dict[str, Any], user_ctx: UserCtx) -> RunState:
        sop = self._sops.get(sop_id)
        if sop is None:
            raise KeyError(sop_id)
        return await self._executor.submit(sop, inputs, user_ctx)

    async def resume(self, run_id: str, *, confirmed: bool, user_ctx: UserCtx) -> RunState:
        state = self._executor.get_state(run_id)
        if state is None:
            raise KeyError(run_id)
        return await self._executor.resume(
            state, self._sops[state.sop_id], confirmed=confirmed, user_ctx=user_ctx
        )

    def report(self, state: RunState) -> RunReport:
        return self._executor.report(state)
