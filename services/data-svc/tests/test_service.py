"""DataService:自纠循环、AMBIGUOUS 透出、校验失败硬拒、NOT_CONFIGURED、WrenAdapter 解析。"""

from __future__ import annotations

import httpx
import pytest

from contracts import UserCtx
from data_svc import (
    DataService,
    DuckDBExecutor,
    NotConfiguredError,
    PostgresExecutor,
    SqlValidator,
    StubEngine,
    ValidationError,
    WrenAdapter,
)
from data_svc.errors import AmbiguousFieldError
from data_svc.models import Clarification, Nl2SqlResult


def _uc(tenant: str = "t1") -> UserCtx:
    return UserCtx(tenant_id=tenant, user_id="u", roles=["analyst"], data_scope={})


class _CountingEngine:
    """记录 generate 调用次数,验证校验失败不触发自纠。"""

    name = "stub"

    def __init__(self, sql: str) -> None:
        self.sql = sql
        self.calls = 0

    async def generate(
        self, question: str, user_ctx: UserCtx, *, prior_error: str | None = None
    ) -> Nl2SqlResult:
        self.calls += 1
        return Nl2SqlResult(sql=self.sql)


async def test_self_correction_path(validator: SqlValidator, executor: DuckDBExecutor) -> None:
    # 首坏(列不存在,过校验但 EXPLAIN 失败)→ 第二次成功。
    engine = StubEngine(
        {"Q": ["SELECT nonexistent_col FROM fund_plan", "SELECT plan_id FROM fund_plan"]}
    )
    svc = DataService(engine=engine, validator=validator, executor=executor)
    result = await svc.query("Q", _uc())
    assert "tenant_id = 't1'" in result.sql
    assert sorted(r[0] for r in result.rows) == ["P1", "P2"]
    assert result.lineage.engine == "stub"
    assert result.row_count == 2


async def test_self_correction_exhausted(validator: SqlValidator, executor: DuckDBExecutor) -> None:
    engine = StubEngine(
        {
            "Q": [
                "SELECT bad_a FROM fund_plan",
                "SELECT bad_b FROM fund_plan",
                "SELECT bad_c FROM fund_plan",
            ]
        }
    )
    svc = DataService(engine=engine, validator=validator, executor=executor)  # max_corrections=2
    with pytest.raises(ValidationError):
        await svc.query("Q", _uc())


async def test_validation_failure_is_hard_reject_no_self_correct(
    validator: SqlValidator, executor: DuckDBExecutor
) -> None:
    engine = _CountingEngine("DELETE FROM fund_plan")
    svc = DataService(engine=engine, validator=validator, executor=executor)
    with pytest.raises(ValidationError):
        await svc.query("Q", _uc())
    assert engine.calls == 1  # 校验失败硬拒,未自纠重生成(红线 6)


async def test_ambiguous_field_raised(validator: SqlValidator, executor: DuckDBExecutor) -> None:
    engine = StubEngine(
        clarify={
            "Q": [
                Clarification(
                    field="执行率口径", question="按哪种?", options=["含在途", "不含在途"]
                )
            ]
        }
    )
    svc = DataService(engine=engine, validator=validator, executor=executor)
    with pytest.raises(AmbiguousFieldError) as excinfo:
        await svc.query("Q", _uc())
    assert excinfo.value.clarifications[0].field == "执行率口径"


async def test_wren_adapter_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WREN_API_URL", raising=False)
    with pytest.raises(NotConfiguredError):
        await WrenAdapter().generate("Q", _uc())


async def test_postgres_executor_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DB_DSN_READONLY", raising=False)
    with pytest.raises(NotConfiguredError):
        PostgresExecutor().execute("SELECT 1", timeout_ms=1000)


async def test_wren_adapter_parses_sql() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"sql": "SELECT plan_id FROM fund_plan"})

    engine = WrenAdapter(api_url="http://wren.local", transport=httpx.MockTransport(handler))
    result = await engine.generate("Q", _uc())
    assert result.sql == "SELECT plan_id FROM fund_plan"


async def test_wren_adapter_parses_clarifications() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"clarifications": [{"field": "口径", "question": "?", "options": ["a", "b"]}]},
        )

    engine = WrenAdapter(api_url="http://wren.local", transport=httpx.MockTransport(handler))
    result = await engine.generate("Q", _uc())
    assert result.clarifications[0].field == "口径"
